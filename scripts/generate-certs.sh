#!/bin/bash
# Generate self-signed SSL certificates for the AI Companion server
# Run this script from the project root directory

set -e

CERT_DIR="./certs"
DAYS_VALID=365
KEY_SIZE=4096

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== AI Companion SSL Certificate Generator ===${NC}"
echo ""

# Create certs directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Check if certificates already exist
if [ -f "$CERT_DIR/server.crt" ] && [ -f "$CERT_DIR/server.key" ]; then
    echo -e "${YELLOW}Warning: Certificates already exist in $CERT_DIR${NC}"
    read -p "Do you want to regenerate them? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing certificates."
        exit 0
    fi
fi

# Get hostname/IP for certificate
DEFAULT_HOST="localhost"
read -p "Enter hostname or IP for certificate [$DEFAULT_HOST]: " HOST
HOST=${HOST:-$DEFAULT_HOST}

echo ""
echo -e "${GREEN}Generating CA private key...${NC}"
openssl genrsa -out "$CERT_DIR/ca.key" $KEY_SIZE

echo -e "${GREEN}Generating CA certificate...${NC}"
openssl req -x509 -new -nodes \
    -key "$CERT_DIR/ca.key" \
    -sha256 -days $DAYS_VALID \
    -out "$CERT_DIR/ca.crt" \
    -subj "/C=US/ST=Local/L=Local/O=AI Companion/OU=Development/CN=AI Companion CA"

echo -e "${GREEN}Generating server private key...${NC}"
openssl genrsa -out "$CERT_DIR/server.key" $KEY_SIZE

echo -e "${GREEN}Generating server certificate signing request...${NC}"
openssl req -new \
    -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.csr" \
    -subj "/C=US/ST=Local/L=Local/O=AI Companion/OU=Server/CN=$HOST"

# Create extensions file for SAN (Subject Alternative Name)
cat > "$CERT_DIR/server.ext" << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = $HOST
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

# Add additional IP if not localhost
if [ "$HOST" != "localhost" ] && [ "$HOST" != "127.0.0.1" ]; then
    # Check if it looks like an IP address
    if [[ $HOST =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "IP.2 = $HOST" >> "$CERT_DIR/server.ext"
    else
        echo "DNS.3 = $HOST" >> "$CERT_DIR/server.ext"
    fi
fi

echo -e "${GREEN}Signing server certificate with CA...${NC}"
openssl x509 -req \
    -in "$CERT_DIR/server.csr" \
    -CA "$CERT_DIR/ca.crt" \
    -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial \
    -out "$CERT_DIR/server.crt" \
    -days $DAYS_VALID \
    -sha256 \
    -extfile "$CERT_DIR/server.ext"

# Set appropriate permissions
chmod 600 "$CERT_DIR"/*.key
chmod 644 "$CERT_DIR"/*.crt

# Clean up temporary files
rm -f "$CERT_DIR/server.csr" "$CERT_DIR/server.ext" "$CERT_DIR/ca.srl"

echo ""
echo -e "${GREEN}=== Certificate Generation Complete ===${NC}"
echo ""
echo "Generated files in $CERT_DIR/:"
ls -la "$CERT_DIR"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo "1. For the client to trust the server, either:"
echo "   - Set COMPANION_VERIFY_SSL=false (development only)"
echo "   - Set COMPANION_CA_CERT_PATH=$CERT_DIR/ca.crt"
echo ""
echo "2. The certificates are valid for $DAYS_VALID days"
echo ""
echo "3. Certificate details:"
openssl x509 -in "$CERT_DIR/server.crt" -noout -subject -dates
echo ""
echo -e "${GREEN}Done!${NC}"
