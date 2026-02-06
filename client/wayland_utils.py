"""
Wayland-native system utilities.
Handles screenshots, window detection, media status, and more.
Uses subprocess to call native Wayland tools.
"""
import subprocess
import shutil
import logging
import os
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class Compositor(Enum):
    """Supported Wayland compositors."""
    HYPRLAND = "hyprland"
    SWAY = "sway"
    KWIN = "kwin"
    GNOME = "gnome"
    WLROOTS = "wlroots"
    UNKNOWN = "unknown"


def detect_compositor() -> Compositor:
    """
    Detect the running Wayland compositor.
    
    Returns:
        Compositor enum value
    """
    # Check environment variables
    xdg_session = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    
    if not wayland_display:
        logger.warning("WAYLAND_DISPLAY not set - may not be running on Wayland")
    
    # Check for Hyprland
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Compositor.HYPRLAND
    
    # Check for Sway
    if os.environ.get("SWAYSOCK"):
        return Compositor.SWAY
    
    # Check XDG_CURRENT_DESKTOP
    if "hyprland" in xdg_session:
        return Compositor.HYPRLAND
    elif "sway" in xdg_session:
        return Compositor.SWAY
    elif "kde" in xdg_session or "plasma" in xdg_session:
        return Compositor.KWIN
    elif "gnome" in xdg_session:
        return Compositor.GNOME
    
    # Try to detect by checking running processes
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Hyprland"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return Compositor.HYPRLAND
    except:
        pass
    
    try:
        result = subprocess.run(
            ["pgrep", "-x", "sway"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return Compositor.SWAY
    except:
        pass
    
    return Compositor.UNKNOWN


def get_active_window_title(compositor: Optional[Compositor] = None) -> str:
    """
    Get the active window title using compositor-specific methods.
    
    Args:
        compositor: The compositor to use (auto-detected if None)
        
    Returns:
        Window title or "Unknown" if detection fails
    """
    if compositor is None:
        compositor = detect_compositor()
    
    try:
        if compositor == Compositor.HYPRLAND:
            return _get_hyprland_window_title()
        elif compositor == Compositor.SWAY:
            return _get_sway_window_title()
        elif compositor == Compositor.KWIN:
            return _get_kwin_window_title()
        elif compositor == Compositor.GNOME:
            return _get_gnome_window_title()
        else:
            # Try each method as fallback
            for method in [
                _get_hyprland_window_title,
                _get_sway_window_title,
                _get_kwin_window_title,
                _get_gnome_window_title
            ]:
                try:
                    title = method()
                    if title and title != "Unknown":
                        return title
                except:
                    continue
            return "Unknown"
    except Exception as e:
        logger.error(f"Failed to get window title: {e}")
        return "Unknown"
    
def get_active_class_name(compositor: Optional[Compositor] = None) -> str:
    """
    Get the active window class using compositor-specific methods.

    Args:
        compositor: The compositor to use (auto-detected if None)

    Returns:
        Window class or "Unknown" if detection fails
    """
    if compositor is None:
        compositor = detect_compositor()

    try:
        if compositor == Compositor.HYPRLAND:
            return _get_hyprland_window_class()
        elif compositor == Compositor.SWAY:
            return _get_sway_window_class()
        elif compositor == Compositor.KWIN:
            return _get_kwin_window_class()
        elif compositor == Compositor.GNOME:
            return _get_gnome_window_class()
        else:
            # Try each method as fallback
            for method in [
                _get_hyprland_window_class,
                _get_sway_window_class,
                _get_kwin_window_class,
                _get_gnome_window_class,
            ]:
                try:
                    title = method()
                    if title and title != "Unknown":
                        return title
                except:
                    continue
            return "Unknown"
    except Exception as e:
        logger.error(f"Failed to get window title: {e}")
        return "Unknown"

def _get_hyprland_window_class() -> str:
    """Get active window class from Hyprland."""
    result = subprocess.run(
        ["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=5
    )

    if result.returncode == 0:
        import json

        data = json.loads(result.stdout)
        return data.get("class", "Unknown") or data.get("initialClass", "Unknown")

    return "Unknown"


def _get_sway_window_class() -> str:
    """Get active window class from Sway."""
    result = subprocess.run(
        ["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=5
    )

    if result.returncode == 0:
        import json

        def find_focused(node):
            if node.get("focused"):
                return node.get("class", "Unknown")
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                result = find_focused(child)
                if result:
                    return result
            return None

        tree = json.loads(result.stdout)
        title = find_focused(tree)
        return title or "Unknown"

    return "Unknown"


def _get_kwin_window_class() -> str:
    """Get active window class from KWin/KDE Plasma."""
    # Try qdbus first
    result = subprocess.run(
        ["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.activeWindow"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Alternative: use kdotool if available
    if shutil.which("kdotool"):
        result = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowclass"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "Unknown"

    return "Unknown"


def _get_gnome_window_class() -> str:
    """Get active window class from GNOME."""
    # Use gdbus to query GNOME Shell
    script = """
    global.display.focus_window ? global.display.focus_window.get_class() : 'Unknown'
    """

    result = subprocess.run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            "/org/gnome/Shell",
            "--method",
            "org.gnome.Shell.Eval",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode == 0:
        # Parse the gdbus output format: (true, "'Window Title'")
        output = result.stdout.strip()
        if "true" in output:
            import re

            match = re.search(r"'([^']*)'", output)
            if match:
                return match.group(1)

    return "Unknown"


def _get_hyprland_window_title() -> str:
    """Get active window title from Hyprland."""
    result = subprocess.run(
        ["hyprctl", "activewindow", "-j"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        return data.get("title", "Unknown") or data.get("class", "Unknown")
    
    return "Unknown"


def _get_sway_window_title() -> str:
    """Get active window title from Sway."""
    result = subprocess.run(
        ["swaymsg", "-t", "get_tree"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        import json
        
        def find_focused(node):
            if node.get("focused"):
                return node.get("name", "Unknown")
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                result = find_focused(child)
                if result:
                    return result
            return None
        
        tree = json.loads(result.stdout)
        title = find_focused(tree)
        return title or "Unknown"
    
    return "Unknown"


def _get_kwin_window_title() -> str:
    """Get active window title from KWin/KDE Plasma."""
    # Try qdbus first
    result = subprocess.run(
        ["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.activeWindow"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    
    # Alternative: use kdotool if available
    if shutil.which("kdotool"):
        result = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or "Unknown"
    
    return "Unknown"


def _get_gnome_window_title() -> str:
    """Get active window title from GNOME."""
    # Use gdbus to query GNOME Shell
    script = """
    global.display.focus_window ? global.display.focus_window.get_title() : 'Unknown'
    """
    
    result = subprocess.run(
        ["gdbus", "call", "--session", 
         "--dest", "org.gnome.Shell",
         "--object-path", "/org/gnome/Shell",
         "--method", "org.gnome.Shell.Eval", script],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        # Parse the gdbus output format: (true, "'Window Title'")
        output = result.stdout.strip()
        if "true" in output:
            import re
            match = re.search(r"'([^']*)'", output)
            if match:
                return match.group(1)
    
    return "Unknown"


def capture_screenshot(output_path: str) -> bool:
    """
    Capture a screenshot using grim (Wayland-native).
    
    Args:
        output_path: Path to save the screenshot
        
    Returns:
        True if successful, False otherwise
    """
    if not shutil.which("grim"):
        logger.error("grim not found - please install it: pacman -S grim")
        return False
    
    try:
        result = subprocess.run(
            ["grim", output_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.debug(f"Screenshot saved to {output_path}")
            return True
        else:
            logger.error(f"grim failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Screenshot capture timed out")
        return False
    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
        return False


def capture_screenshot_region(output_path: str) -> bool:
    """
    Capture a screenshot of a selected region using grim + slurp.
    
    Args:
        output_path: Path to save the screenshot
        
    Returns:
        True if successful, False otherwise
    """
    if not shutil.which("grim") or not shutil.which("slurp"):
        logger.error("grim and slurp required - please install: pacman -S grim slurp")
        return False
    
    try:
        # Get region from slurp
        slurp_result = subprocess.run(
            ["slurp"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if slurp_result.returncode != 0:
            logger.error("Region selection cancelled")
            return False
        
        region = slurp_result.stdout.strip()
        
        # Capture the region
        result = subprocess.run(
            ["grim", "-g", region, output_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Region capture failed: {e}")
        return False


def get_media_status() -> Tuple[str, Optional[str]]:
    """
    Get media playback status using playerctl.
    
    Returns:
        Tuple of (status, info) where status is 'playing'/'paused'/'stopped'/'unknown'
        and info is the current track info (e.g., "Artist - Title")
    """
    if not shutil.which("playerctl"):
        logger.warning("playerctl not found - media status unavailable")
        return ("unknown", None)
    
    try:
        # Get status
        status_result = subprocess.run(
            ["playerctl", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        status = status_result.stdout.strip().lower()
        if status not in ["playing", "paused", "stopped"]:
            status = "unknown"
        
        # Get metadata if playing
        info = None
        if status == "playing":
            meta_result = subprocess.run(
                ["playerctl", "metadata", "--format", "{{ artist }} - {{ title }}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if meta_result.returncode == 0:
                info = meta_result.stdout.strip()
                # Also get player name
                player_result = subprocess.run(
                    ["playerctl", "metadata", "--format", "{{ playerName }}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if player_result.returncode == 0:
                    player = player_result.stdout.strip()
                    info = f"{player}: {info}"
        
        return (status, info)
        
    except Exception as e:
        logger.error(f"Failed to get media status: {e}")
        return ("unknown", None)


def get_microphone_status() -> str:
    """
    Get microphone mute status using pactl or wpctl.
    
    Returns:
        'muted', 'unmuted', or 'unknown'
    """
    # Try wpctl first (PipeWire)
    if shutil.which("wpctl"):
        try:
            result = subprocess.run(
                ["wpctl", "get-volume", "@DEFAULT_SOURCE@"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                if "[muted]" in output:
                    return "muted"
                elif "volume:" in output:
                    return "unmuted"
        except:
            pass
    
    # Fall back to pactl (PulseAudio)
    if shutil.which("pactl"):
        try:
            result = subprocess.run(
                ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                if "yes" in output:
                    return "muted"
                elif "no" in output:
                    return "unmuted"
        except:
            pass
    
    logger.warning("Could not determine microphone status")
    return "unknown"


def send_notification(
    title: str,
    body: str,
    urgency: str = "normal",
    icon: Optional[str] = None,
    timeout: int = 5000
) -> bool:
    """
    Send a desktop notification using notify-send.
    
    Args:
        title: Notification title
        body: Notification body text
        urgency: 'low', 'normal', or 'critical'
        icon: Optional icon name or path
        timeout: Timeout in milliseconds
        
    Returns:
        True if successful
    """
    if not shutil.which("notify-send"):
        logger.error("notify-send not found - please install libnotify")
        return False
    
    try:
        cmd = [
            "notify-send",
            "--urgency", urgency,
            "--expire-time", str(timeout),
            "--app-name", "AI Companion"
        ]
        
        if icon:
            cmd.extend(["--icon", icon])
        
        cmd.extend([title, body])
        
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False


def check_idle_status(idle_threshold_seconds: int = 300) -> bool:
    """
    Check if the user is idle using various Wayland methods.
    
    Args:
        idle_threshold_seconds: Seconds of inactivity to consider idle
        
    Returns:
        True if user appears idle, False otherwise
    """
    # Try hypridle/hyprland method
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            # Hyprland doesn't have direct idle query, but we can check
            # if any input devices have recent activity
            # This is a simplified check
            result = subprocess.run(
                ["hyprctl", "devices", "-j"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If we can query devices, user is probably active
            if result.returncode == 0:
                return False
        except:
            pass
    
    # Try swayidle-related check for Sway
    if os.environ.get("SWAYSOCK"):
        # swayidle itself doesn't provide query, but sway's idle inhibitors can help
        try:
            result = subprocess.run(
                ["swaymsg", "-t", "get_seats"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If we can communicate with sway, check further
            if result.returncode == 0:
                return False  # Basic activity check
        except:
            pass
    
    # Try generic XDG idle portal (requires xdg-desktop-portal)
    # Note: This requires D-Bus integration which is complex via subprocess
    
    # Fallback: check /proc for recent input activity
    try:
        # Check if any input device had recent activity
        import time
        for input_dev in ["/dev/input/mice", "/dev/input/mouse0"]:
            if os.path.exists(input_dev):
                stat = os.stat(input_dev)
                age = time.time() - stat.st_atime
                if age < idle_threshold_seconds:
                    return False
    except:
        pass
    
    # Default to not idle if we can't determine
    return False


def check_required_tools() -> dict:
    """
    Check which required tools are available.
    
    Returns:
        Dict with tool names as keys and availability as values
    """
    tools = {
        "grim": "Screenshot capture",
        "slurp": "Region selection (optional)",
        "playerctl": "Media status",
        "pactl": "PulseAudio mic status",
        "wpctl": "PipeWire mic status",
        "notify-send": "Desktop notifications",
        "hyprctl": "Hyprland integration",
        "swaymsg": "Sway integration",
    }
    
    result = {}
    for tool, description in tools.items():
        available = shutil.which(tool) is not None
        result[tool] = {
            "available": available,
            "description": description
        }
    
    return result
