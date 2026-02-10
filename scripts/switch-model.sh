#!/bin/bash
# Switch AI models for the Companion server
# Can switch profiles or individual models
#
# Usage:
#   ./switch-model.sh                    # Interactive mode
#   ./switch-model.sh --profile balanced # Switch to profile
#   ./switch-model.sh --vision llava:7b  # Change vision model only
#   ./switch-model.sh --reasoning qwen2.5:7b # Change reasoning model only

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
PROFILES_FILE="$PROJECT_ROOT/config/model-profiles.json"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# Detect if sudo is needed for docker
DOCKER_CMD="docker"
if ! docker ps > /dev/null 2>&1; then
    if sudo docker ps > /dev/null 2>&1; then
        DOCKER_CMD="sudo docker"
        echo -e "${YELLOW}Note: Using sudo for docker commands${NC}"
    else
        echo -e "${RED}Error: Cannot access docker (tried with and without sudo)${NC}"
        exit 1
    fi
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is required but not installed${NC}"
    echo "Install with: sudo pacman -S jq"
    exit 1
fi

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

# Check if profiles file exists
if [ ! -f "$PROFILES_FILE" ]; then
    echo -e "${RED}Error: model-profiles.json not found at $PROFILES_FILE${NC}"
    exit 1
fi

# Function to get current models
get_current_models() {
    CURRENT_VISION=$(grep "^VISION_MODEL=" "$ENV_FILE" | cut -d'=' -f2)
    CURRENT_REASONING=$(grep "^REASONING_MODEL=" "$ENV_FILE" | cut -d'=' -f2)
}

# Function to update .env file
update_env() {
    local key=$1
    local value=$2
    
    if grep -q "^${key}=" "$ENV_FILE"; then
        # Update existing value
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        # Add new value
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# Function to check if model exists in Ollama
check_model_exists() {
    local model=$1
    local models_list=$(curl -sf "$OLLAMA_HOST/api/tags" | jq -r '.models[].name')
    
    # Exact match
    if echo "$models_list" | grep -q "^${model}$"; then
        return 0
    fi
    
    local model_base=$(echo "$model" | cut -d':' -f1)
    local model_tag=$(echo "$model" | grep -o ':.*' | cut -c2-)
    
    while IFS= read -r avail; do
        local avail_base=$(echo "$avail" | cut -d':' -f1)
        local avail_tag=$(echo "$avail" | grep -o ':.*' | cut -c2-)
        
        [ "$model_base" != "$avail_base" ] && continue
        
        # Same base: match only if one side has no tag (moondream vs moondream:latest)
        # Do NOT match different tags (llama3.2:3b vs llama3.2:1b)
        if [ -z "$model_tag" ] || [ -z "$avail_tag" ]; then
            return 0
        fi
        if [ "$model_tag" = "$avail_tag" ]; then
            return 0
        fi
    done <<< "$models_list"
    
    return 1
}

# Function to pull model if needed
ensure_model() {
    local model=$1
    echo -e "${YELLOW}Checking if model '$model' is available...${NC}"
    
    if check_model_exists "$model"; then
        echo -e "${GREEN}✓ Model already available${NC}"
        return 0
    fi
    
    echo -e "${YELLOW}Model not found. Pulling from Ollama...${NC}"
    echo -e "${CYAN}This may take a while depending on model size...${NC}"
    
    $DOCKER_CMD compose -f "$PROJECT_ROOT/docker-compose.yml" exec ollama ollama pull "$model"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Model pulled successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to pull model${NC}"
        return 1
    fi
}

# Function to restart server
restart_server() {
    echo -e "${YELLOW}Restarting server with new config...${NC}"
    # Must use 'up -d' instead of 'restart' to pick up new .env values
    $DOCKER_CMD compose -f "$PROJECT_ROOT/docker-compose.yml" up -d companion-server
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Server restarted${NC}"
        
        # Wait a moment and do a health check
        sleep 2
        echo -e "${CYAN}Checking server health...${NC}"
        
        # Get API key from .env
        API_KEY=$(grep "^API_KEY=" "$ENV_FILE" | cut -d'=' -f2)
        
        if curl -sf -k -H "X-API-Key: $API_KEY" https://localhost:8443/api/v1/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Server is healthy${NC}"
        else
            echo -e "${YELLOW}⚠ Server might still be starting up${NC}"
        fi
    else
        echo -e "${RED}✗ Failed to restart server${NC}"
        return 1
    fi
}

# Function to switch to a profile
switch_profile() {
    local profile=$1
    
    # Get profile data
    local profile_data=$(jq -r ".profiles.\"$profile\"" "$PROFILES_FILE")
    
    if [ "$profile_data" == "null" ]; then
        echo -e "${RED}Error: Profile '$profile' not found${NC}"
        echo "Available profiles:"
        jq -r '.profiles | keys[]' "$PROFILES_FILE" | sed 's/^/  - /'
        exit 1
    fi
    
    local vision_model=$(echo "$profile_data" | jq -r '.vision_model')
    local reasoning_model=$(echo "$profile_data" | jq -r '.reasoning_model')
    local profile_name=$(echo "$profile_data" | jq -r '.name')
    local ram_usage=$(echo "$profile_data" | jq -r '.ram_usage')
    
    # Calculate padding for box alignment (51 chars between borders)
    local text="  Switching to profile: $profile_name"
    local padding=$((51 - ${#text}))
    local spaces=$(printf '%*s' "$padding" '')
    
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${text}${spaces}║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Vision model:    ${CYAN}$vision_model${NC}"
    echo -e "Reasoning model: ${CYAN}$reasoning_model${NC}"
    echo -e "RAM usage:       ${YELLOW}$ram_usage${NC}"
    echo ""
    
    # Ensure models are available
    ensure_model "$vision_model" || exit 1
    ensure_model "$reasoning_model" || exit 1
    
    # Update .env
    update_env "VISION_MODEL" "$vision_model"
    update_env "REASONING_MODEL" "$reasoning_model"
    
    echo -e "${GREEN}✓ Configuration updated${NC}"
    
    # Restart server
    restart_server
    
    echo ""
    echo -e "${GREEN}✓ Successfully switched to '$profile' profile${NC}"
}

# Function to switch individual model
switch_model() {
    local model_type=$1  # "vision" or "reasoning"
    local model_name=$2
    
    local env_key
    if [ "$model_type" == "vision" ]; then
        env_key="VISION_MODEL"
    else
        env_key="REASONING_MODEL"
    fi
    
    echo -e "${GREEN}Switching $model_type model to: ${CYAN}$model_name${NC}"
    echo ""
    
    # Ensure model is available
    ensure_model "$model_name" || exit 1
    
    # Update .env
    update_env "$env_key" "$model_name"
    
    echo -e "${GREEN}✓ Configuration updated${NC}"
    
    # Restart server
    restart_server
    
    echo ""
    echo -e "${GREEN}✓ Successfully switched $model_type model${NC}"
}

# Helper to check if two model names refer to the same model
models_match() {
    local a=$1
    local b=$2
    [ "$a" = "$b" ] && return 0
    local a_base=$(echo "$a" | cut -d':' -f1)
    local b_base=$(echo "$b" | cut -d':' -f1)
    [ "$a_base" != "$b_base" ] && return 1
    # Same base, match if either has no tag
    local a_tag=$(echo "$a" | grep -o ':.*' | cut -c2-)
    local b_tag=$(echo "$b" | grep -o ':.*' | cut -c2-)
    [ -z "$a_tag" ] || [ -z "$b_tag" ] && return 0
    [ "$a_tag" = "$b_tag" ] && return 0
    return 1
}

# Function to remove a model
remove_model() {
    local model=$1
    
    # Check if model is currently in use
    get_current_models
    if models_match "$model" "$CURRENT_VISION" || models_match "$model" "$CURRENT_REASONING"; then
        echo -e "${RED}Error: Cannot remove model '$model' - it's currently in use${NC}"
        echo -e "${YELLOW}Switch to a different model first${NC}"
        return 1
    fi
    
    # Check if model exists
    if ! check_model_exists "$model"; then
        echo -e "${RED}Error: Model '$model' not found in Ollama${NC}"
        return 1
    fi
    
    # Confirm deletion
    echo -e "${YELLOW}About to remove model: ${CYAN}$model${NC}"
    read -p "Are you sure? [y/N]: " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        return 0
    fi
    
    echo -e "${YELLOW}Removing model...${NC}"
    $DOCKER_CMD compose -f "$PROJECT_ROOT/docker-compose.yml" exec ollama ollama rm "$model"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Model '$model' removed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to remove model${NC}"
        return 1
    fi
}

# Interactive mode
interactive_mode() {
    get_current_models
    
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     AI Companion Model Switcher                   ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Current configuration:"
    echo -e "  Vision:    ${CYAN}$CURRENT_VISION${NC}"
    echo -e "  Reasoning: ${CYAN}$CURRENT_REASONING${NC}"
    echo ""
    echo -e "${BLUE}Choose action:${NC}"
    echo "  1) Switch to a profile (fast/balanced/quality/etc)"
    echo "  2) List available profiles"
    echo "  3) Change vision model only"
    echo "  4) Change reasoning model only"
    echo "  5) List models in Ollama"
    echo "  6) Remove a model"
    echo "  7) Exit"
    echo ""
    read -p "Enter choice [1-7]: " choice
    
    case $choice in
        1)
            echo ""
            echo -e "${CYAN}Available profiles:${NC}"
            jq -r '.profiles | to_entries[] | "  \(.key): \(.value.name) - \(.value.description)"' "$PROFILES_FILE"
            echo ""
            read -p "Enter profile name: " profile
            switch_profile "$profile"
            ;;
        2)
            echo ""
            jq -r '.profiles | to_entries[] | "\n\u001b[1;36m\(.key)\u001b[0m - \(.value.name)\n  Description: \(.value.description)\n  Vision: \(.value.vision_model)\n  Reasoning: \(.value.reasoning_model)\n  RAM: \(.value.ram_usage) | Speed: \(.value.speed) | Quality: \(.value.quality)"' "$PROFILES_FILE"
            echo ""
            ;;
        3)
            echo ""
            echo -e "${CYAN}Available vision models:${NC}"
            jq -r '.models.vision | to_entries[] | "  \(.key): \(.value.description) (\(.value.size))"' "$PROFILES_FILE"
            echo ""
            read -p "Enter vision model name: " model
            switch_model "vision" "$model"
            ;;
        4)
            echo ""
            echo -e "${CYAN}Available reasoning models:${NC}"
            jq -r '.models.reasoning | to_entries[] | "  \(.key): \(.value.description) (\(.value.size))"' "$PROFILES_FILE"
            echo ""
            read -p "Enter reasoning model name: " model
            switch_model "reasoning" "$model"
            ;;
        5)
            echo ""
            echo -e "${CYAN}Models in Ollama:${NC}"
            curl -sf "$OLLAMA_HOST/api/tags" | jq -r '.models[] | "  \(.name) (\(.size / 1073741824 | floor)GB)"'
            echo ""
            ;;
        6)
            echo ""
            echo -e "${CYAN}Installed models:${NC}"
            curl -sf "$OLLAMA_HOST/api/tags" | jq -r '.models[] | "  \(.name) (\(.size / 1073741824 | floor)GB)"'
            echo ""
            echo -e "${YELLOW}Current models in use:${NC}"
            echo -e "  Vision: ${CYAN}$CURRENT_VISION${NC}"
            echo -e "  Reasoning: ${CYAN}$CURRENT_REASONING${NC}"
            echo ""
            read -p "Enter model name to remove: " model
            if [ -n "$model" ]; then
                remove_model "$model"
            fi
            ;;
        7)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac
}

# Main script logic
if [ $# -eq 0 ]; then
    # No arguments - interactive mode
    interactive_mode
else
    # Parse arguments
    case "$1" in
        --profile|-p)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Profile name required${NC}"
                exit 1
            fi
            switch_profile "$2"
            ;;
        --vision|-v)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Model name required${NC}"
                exit 1
            fi
            switch_model "vision" "$2"
            ;;
        --reasoning|-r)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Model name required${NC}"
                exit 1
            fi
            switch_model "reasoning" "$2"
            ;;
        --list|-l)
            echo -e "${CYAN}Available profiles:${NC}"
            jq -r '.profiles | keys[]' "$PROFILES_FILE" | sed 's/^/  - /'
            echo ""
            echo -e "${CYAN}Models in Ollama:${NC}"
            curl -sf "$OLLAMA_HOST/api/tags" | jq -r '.models[] | "  \(.name)"'
            ;;
        --remove|-d)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Model name required${NC}"
                exit 1
            fi
            remove_model "$2"
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  (no args)              Interactive mode"
            echo "  --profile, -p NAME     Switch to profile"
            echo "  --vision, -v MODEL     Change vision model"
            echo "  --reasoning, -r MODEL  Change reasoning model"
            echo "  --remove, -d MODEL     Remove a model from Ollama"
            echo "  --list, -l             List profiles and models"
            echo "  --help, -h             Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                         # Interactive"
            echo "  $0 --profile fast          # Switch to fast profile"
            echo "  $0 --vision llava:7b       # Change vision model"
            echo "  $0 -r qwen2.5:7b           # Change reasoning model"
            echo "  $0 -d llama3:8b            # Remove a model"
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
fi
