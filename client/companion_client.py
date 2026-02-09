#!/usr/bin/env python3
"""
Wayland AI Desktop Companion - Client

A Wayland-native client for the AI Desktop Companion.
Captures screen activity, gathers system context, and sends to server for analysis.

Requirements (Arch Linux):
    pacman -S grim playerctl libnotify pipewire-pulse

Usage:
    python companion_client.py
    
Environment variables (or .env file):
    COMPANION_API_KEY=your-api-key
    COMPANION_SERVER_URL=https://localhost:8443
    COMPANION_CAPTURE_INTERVAL=60
    COMPANION_LOG_FILE=/path/to/companion.log
"""

import asyncio
import io
import json
import logging
import os
import signal
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from config import get_client_settings, ClientSettings
from wayland_utils import (
    detect_compositor,
    get_active_class_name,
    get_active_window_title,
    capture_screenshot,
    get_media_status,
    get_microphone_status,
    send_notification,
    check_required_tools
)

logger = logging.getLogger("companion-client")


def configure_logging(settings: ClientSettings, verbose: bool) -> None:
    """Configure logging using client settings."""
    log_level = logging.DEBUG if verbose else getattr(
        logging,
        settings.log_level.upper(),
        logging.INFO
    )

    handlers = []
    if settings.log_file:
        log_path = Path(settings.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    else:
        handlers.append(logging.StreamHandler(sys.stdout))

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )


class CompanionClient:
    """
    Wayland-native AI Desktop Companion client.
    
    Captures screen activity, gathers context, and communicates
    with the server for AI-powered feedback.
    """
    
    def __init__(self, settings: Optional[ClientSettings] = None, verbose: bool = False):
        """Initialize the companion client."""
        self.settings = settings or get_client_settings()
        self.compositor = detect_compositor()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self.verbose = verbose
        self.capture_count = 0

        configure_logging(self.settings, verbose)
        
        # HTTP client configuration
        self.http_client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"Initialized client for {self.compositor.value} compositor")
    
    async def start(self) -> None:
        """Start the companion client main loop."""
        logger.info("Starting Wayland AI Desktop Companion client...")
        
        # Check required tools
        tools = check_required_tools()
        missing_critical = []
        
        if not tools["grim"]["available"]:
            missing_critical.append("grim")
        if not tools["notify-send"]["available"]:
            logger.warning("notify-send not available - notifications disabled")
        
        if missing_critical:
            logger.error(f"Missing critical tools: {', '.join(missing_critical)}")
            logger.error("Install with: pacman -S " + " ".join(missing_critical))
            return
        
        # Log available tools
        for tool, info in tools.items():
            status = "✓" if info["available"] else "✗"
            logger.debug(f"  {status} {tool}: {info['description']}")
        
        # Initialize HTTP client with configurable timeout for slow CPU inference
        ssl_context = self._get_ssl_context()
        self.http_client = httpx.AsyncClient(
            timeout=float(self.settings.request_timeout),
            verify=ssl_context
        )
        
        self.running = True
        
        # Set up signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.shutdown())
            )
        
        logger.info(f"Client started. Capture interval: {self.settings.capture_interval}s")
        logger.info(f"Server: {self.settings.server_url}")
        
        # Initial notification
        if self.settings.show_notifications:
            send_notification(
                "AI Companion Started",
                f"Monitoring desktop activity every {self.settings.capture_interval}s",
                urgency="low"
            )
        
        # Main loop
        try:
            while self.running:
                try:
                    await self._capture_and_send()
                except Exception as e:
                    logger.error(f"Capture cycle error: {e}")
                
                # Wait for next interval or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.settings.capture_interval
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue loop
                    
        finally:
            await self.cleanup()
    
    async def shutdown(self) -> None:
        """Signal the client to shut down."""
        logger.info("Shutdown requested...")
        self.running = False
        self._shutdown_event.set()
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("Client stopped")
    
    def _get_ssl_context(self):
        """Get SSL context for HTTPS requests."""
        if not self.settings.verify_ssl:
            return False
        
        if self.settings.ca_cert_path and Path(self.settings.ca_cert_path).exists():
            return self.settings.ca_cert_path
        
        return True
    
    async def _capture_and_send(self) -> None:
        """Capture screen and context, send to server."""
        
        # Get microphone status first (for meeting detection)
        mic_status = get_microphone_status()
        is_in_meeting = mic_status == "unmuted"
        
        if is_in_meeting and self.settings.suppress_when_meeting:
            logger.debug("Mic unmuted (possible meeting), capture continues but notifications suppressed")
        
        # Gather context
        window_title = get_active_window_title(self.compositor)
        class_name = get_active_class_name(self.compositor)
        media_status, media_info = get_media_status()
        
        # Capture screenshot
        screenshot_data = await self._capture_screenshot()
        
        # Prepare metadata
        metadata = {
            "window_title": window_title,
            "class_name": class_name,
            "media_status": media_status,
            "media_info": media_info,
            "microphone_status": mic_status,
            "user_status": "in_meeting" if is_in_meeting else "active",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compositor": self.compositor.value
        }
        
        self.capture_count += 1
        logger.info(f"[Capture #{self.capture_count}] Window: {window_title}, Class: {class_name}")
        
        if self.verbose:
            logger.info(f"  Media: {media_status}" + (f" ({media_info})" if media_info else ""))
            logger.info(f"  Mic: {mic_status} | Status: {'IN_MEETING' if is_in_meeting else 'ACTIVE'}")
        
        # Send to server
        response = await self._send_to_server(metadata, screenshot_data)
        
        if response:
            feedback = response.get("feedback", "")
            persona = response.get("persona_used", "Assistant")
            suppress = response.get("suppress_notification", False)
            
            # Always log the response in verbose mode
            if self.verbose:
                logger.info(f"  ╭─ AI Response ({persona}) ─────────────────")
                logger.info(f"  │ {feedback}")
                logger.info(f"  ╰─ Suppressed: {suppress}")
                context_summary = response.get("context_summary", "")
                if context_summary:
                    logger.debug(f"  Context: {context_summary[:100]}...")
            else:
                # Normal mode: just show feedback briefly
                logger.info(f"  → {persona}: {feedback[:80]}{'...' if len(feedback) > 80 else ''}")
            
            # Send notification unless suppressed
            if feedback and self.settings.show_notifications and not suppress:
                send_notification(
                    f"{persona}",
                    feedback,
                    urgency="low",
                    timeout=self.settings.notification_timeout
                )
        else:
            logger.warning("  → No response from server")
    
    async def _capture_screenshot(self) -> Optional[bytes]:
        """Capture and process screenshot."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Capture with grim
            if not capture_screenshot(tmp_path):
                logger.warning("Screenshot capture failed")
                return None
            
            # Load and process image
            with Image.open(tmp_path) as img:
                # Resize if too large
                if img.width > self.settings.max_image_width:
                    ratio = self.settings.max_image_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize(
                        (self.settings.max_image_width, new_height),
                        Image.Resampling.LANCZOS
                    )
                
                # Convert to JPEG for compression
                buffer = io.BytesIO()
                img.convert("RGB").save(
                    buffer,
                    format="JPEG",
                    quality=self.settings.jpeg_quality,
                    optimize=True
                )
                return buffer.getvalue()
                
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    async def _send_to_server(
        self,
        metadata: dict,
        screenshot: Optional[bytes]
    ) -> Optional[dict]:
        """Send capture data to the server."""
        if not self.http_client:
            logger.error("HTTP client not initialized")
            return None
        
        try:
            # Prepare multipart form data
            files = {}
            if screenshot:
                files["image"] = ("screenshot.jpg", screenshot, "image/jpeg")
            
            data = {
                "metadata": json.dumps(metadata)
            }
            
            response = await self.http_client.post(
                f"{self.settings.server_url}/api/v1/analyze",
                data=data,
                files=files if files else None,
                headers={"X-API-Key": self.settings.api_key}
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            elif response.status_code == 401:
                logger.error("Authentication failed - check API key")
            else:
                logger.error(f"Server error: {response.status_code} - {response.text}")
                
        except httpx.ConnectError:
            logger.error(f"Cannot connect to server at {self.settings.server_url}")
        except httpx.TimeoutException:
            logger.error("Request to server timed out")
        except Exception as e:
            logger.error(f"Request failed: {e}")
        
        return None
    
    async def health_check(self) -> bool:
        """Check server connectivity."""
        if not self.http_client:
            self.http_client = httpx.AsyncClient(
                timeout=float(self.settings.request_timeout),
                verify=self._get_ssl_context()
            )
        
        try:
            response = await self.http_client.get(
                f"{self.settings.server_url}/api/v1/health"
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Server status: {data.get('status')}")
                logger.info(f"Ollama connected: {data.get('ollama_connected')}")
                logger.info(f"Models: {data.get('models_available', [])}")
                return True
            else:
                logger.error(f"Health check failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return False


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Wayland AI Desktop Companion Client"
    )
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Check required tools and exit"
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Check server health and exit"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for testing)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output - show full AI responses"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=None,
        help="Override capture interval (seconds)"
    )
    
    args = parser.parse_args()
    
    if args.check_tools:
        print("Checking required tools...\n")
        tools = check_required_tools()
        for tool, info in tools.items():
            status = "✓ Available" if info["available"] else "✗ Missing"
            print(f"  {tool}: {status}")
            print(f"    {info['description']}")
        
        compositor = detect_compositor()
        print(f"\nDetected compositor: {compositor.value}")
        
        window = get_active_window_title(compositor)
        class_name = get_active_class_name(compositor)
        print(f"Current active window: {window} (Class: {class_name})")
        
        media_status, media_info = get_media_status()
        print(f"Media status: {media_status}" + (f" ({media_info})" if media_info else ""))
        
        mic = get_microphone_status()
        print(f"Microphone: {mic}")
        
        return
    
    # Load settings
    try:
        settings = get_client_settings()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Make sure COMPANION_API_KEY is set or .env file exists")
        sys.exit(1)
    
    # Override interval if specified
    if args.interval:
        settings.capture_interval = args.interval
    
    client = CompanionClient(settings, verbose=args.verbose)
    
    if args.health:
        success = await client.health_check()
        sys.exit(0 if success else 1)
    
    if args.once:
        # Single capture for testing
        ssl_context = client._get_ssl_context()
        client.http_client = httpx.AsyncClient(timeout=float(settings.request_timeout), verify=ssl_context)
        try:
            await client._capture_and_send()
        finally:
            await client.http_client.aclose()
        return
    
    # Start main loop
    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
