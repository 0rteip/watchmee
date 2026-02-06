#!/bin/bash
# Pull and prepare Ollama models for the AI Companion
# Run this after starting the Ollama container
#
# Usage:
#   ./setup-models.sh          # Interactive mode (choose profile)
#   ./setup-models.sh light    # Light profile (CPU optimized, ~3GB)
#   ./setup-models.sh heavy    # Heavy profile (full models, ~8GB)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# Model profiles
# Light: optimized for CPU, ~3GB total, faster inference
LIGHT_VISION="moondream"           # ~1.7GB - smallest vision model
LIGHT_REASONING="llama3.2:3b"      # ~2GB - fast 3B model

# Heavy: full quality, ~8GB total, slower on CPU
HEAVY_VISION="moondream"           # ~1.7GB - same (no larger alternative)
HEAVY_REASONING="llama3:8b"        # ~4.7GB - full 8B model

echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       AI Companion Model Setup                    ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo "Ollama host: $OLLAMA_HOST"
echo ""

# Check if Ollama is reachable
echo -e "${YELLOW}Checking Ollama connectivity...${NC}"
if ! curl -sf "$OLLAMA_HOST/api/tags" > /dev/null; then
    echo -e "${RED}Error: Cannot connect to Ollama at $OLLAMA_HOST${NC}"
    echo "Make sure the Ollama container is running: docker compose up -d ollama"
    exit 1
fi
echo -e "${GREEN}✓ Ollama is reachable${NC}"
echo ""

# Profile selection
PROFILE="$1"

if [ -z "$PROFILE" ]; then
    echo -e "${BLUE}Select model profile:${NC}"
    echo ""
    echo -e "  ${GREEN}1) light${NC} - CPU optimized (~3GB download)"
    echo "     Vision:    moondream (~1.7GB)"
    echo "     Reasoning: llama3.2:3b (~2GB) - Fast, good for most tasks"
    echo ""
    echo -e "  ${YELLOW}2) heavy${NC} - Full quality (~6GB download)"
    echo "     Vision:    moondream (~1.7GB)"
    echo "     Reasoning: llama3:8b (~4.7GB) - Best quality, slower on CPU"
    echo ""
    read -p "Enter choice [1/2]: " choice
    
    case $choice in
        1|light|l)
            PROFILE="light"
            ;;
        2|heavy|h)
            PROFILE="heavy"
            ;;
        *)
            echo -e "${RED}Invalid choice. Defaulting to 'light'${NC}"
            PROFILE="light"
            ;;
    esac
fi

# Set models based on profile
case $PROFILE in
    light|l)
        VISION_MODEL="$LIGHT_VISION"
        REASONING_MODEL="$LIGHT_REASONING"
        echo -e "${GREEN}Using LIGHT profile (CPU optimized)${NC}"
        ;;
    heavy|h)
        VISION_MODEL="$HEAVY_VISION"
        REASONING_MODEL="$HEAVY_REASONING"
        echo -e "${YELLOW}Using HEAVY profile (full quality)${NC}"
        ;;
    *)
        echo -e "${RED}Unknown profile: $PROFILE${NC}"
        echo "Usage: $0 [light|heavy]"
        exit 1
        ;;
esac

echo ""
echo "Vision model:    $VISION_MODEL"
echo "Reasoning model: $REASONING_MODEL"
echo ""

# Function to pull a model with progress
pull_model() {
    local model_name="$1"
    local model_desc="$2"
    
    echo -e "${YELLOW}Pulling $model_name ($model_desc)...${NC}"
    echo "This may take a while on first run..."
    
    curl -X POST "$OLLAMA_HOST/api/pull" -d "{\"name\": \"$model_name\"}" --no-buffer 2>/dev/null | while read line; do
        status=$(echo "$line" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ -n "$status" ]; then
            echo -ne "\r  $status                                        "
        fi
    done
    echo ""
    echo -e "${GREEN}✓ $model_name ready${NC}"
    echo ""
}

# Pull models
pull_model "$VISION_MODEL" "vision model"
pull_model "$REASONING_MODEL" "reasoning model"

# List available models
echo -e "${GREEN}=== Installed Models ===${NC}"
curl -sf "$OLLAMA_HOST/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for model in data.get('models', []):
    name = model.get('name', 'unknown')
    size = model.get('size', 0)
    size_gb = size / (1024**3)
    print(f'  - {name} ({size_gb:.1f} GB)')
"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Setup Complete!                             ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Update your .env file with these values:${NC}"
echo ""
echo "  VISION_MODEL=$VISION_MODEL"
echo "  REASONING_MODEL=$REASONING_MODEL"
echo ""
