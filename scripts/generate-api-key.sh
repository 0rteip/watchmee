#!/bin/bash
# Generate a secure API key for the AI Companion

set -e

# Generate a secure random key (32 bytes = 256 bits, URL-safe base64)
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo "Generated API Key:"
echo ""
echo "  $API_KEY"
echo ""
echo "Add this to your .env file:"
echo ""
echo "  API_KEY=$API_KEY"
echo ""
echo "And to your client .env file:"
echo ""
echo "  COMPANION_API_KEY=$API_KEY"
echo ""
