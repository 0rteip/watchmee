#!/bin/bash
# Switch AI persona on the fly
# Usage: 
#   ./switch-persona.sh           # Cycle to next persona (wheel mode)
#   ./switch-persona.sh --list    # Show all personas
#   ./switch-persona.sh --json    # Output current persona as JSON (for Waybar)
#   ./switch-persona.sh "Name"    # Switch to specific persona

set -e

# Load config from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env" 2>/dev/null || true
fi

API_KEY="${COMPANION_API_KEY:-}"
SERVER_URL="${COMPANION_SERVER_URL:-https://localhost:8443}"

# For non-json modes, check API key
check_api_key() {
    if [ -z "$API_KEY" ]; then
        echo "Error: COMPANION_API_KEY not set"
        echo "Set it in .env or export COMPANION_API_KEY=your-key"
        exit 1
    fi
}

# Colors (only for terminal output)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Get icon for persona from server API
get_icon() {
    local name="$1"
    local DATA=$(curl -sk -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/personas" 2>/dev/null)
    
    if [ -n "$DATA" ]; then
        echo "$DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    name = '$name'
    for p in data.get('personas', []):
        if p['name'] == name:
            print(p.get('icon', '🎭'))
            sys.exit(0)
    print('🎭')
except:
    print('🎭')
"
    else
        echo "🎭"
    fi
}

# Output JSON for Waybar
output_waybar_json() {
    local DATA=$(curl -sk -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/personas" 2>/dev/null)
    
    if [ -z "$DATA" ]; then
        echo '{"text": " 󰚩 ??", "tooltip": "AI Companion: Disconnected", "class": "disconnected"}'
        exit 0
    fi
    
    echo "$DATA" | python3 -c "
import sys, json

try:
    data = json.load(sys.stdin)
    active = data.get('active', 'Unknown')
    personas = data.get('personas', [])
    
    # Find active persona and get icon/short from JSON
    active_persona = next((p for p in personas if p['name'] == active), None)
    icon = (active_persona.get('icon') or '󰚩') if active_persona else '󰚩'
    short = (active_persona.get('short') or active[:6]) if active_persona else active[:6]
    
    # Build tooltip with all personas (icons from JSON)
    tooltip_lines = ['<b>󱙺 AI Companion</b>', '']
    for p in personas:
        name = p['name']
        p_icon = p.get('icon', '󰚩')
        if name == active:
            tooltip_lines.append(f'<b>{p_icon} {name}</b> ◀')
        else:
            tooltip_lines.append(f'{p_icon} {name}')
    
    tooltip_lines.append('')
    tooltip_lines.append('<i>Click to switch</i>')
    
    tooltip = '\\n'.join(tooltip_lines)
    
    # CSS class based on persona (lowercase, no spaces)
    css_class = active.lower().replace(' ', '-')
    
    output = {
        'text': f' {icon} {short}',
        'tooltip': tooltip,
        'class': css_class,
        'alt': active
    }
    
    print(json.dumps(output))
except Exception as e:
    print(json.dumps({'text': '⚠️', 'tooltip': f'Error: {e}', 'class': 'error'}))
"
}

# Function to activate a persona (with optional JSON output)
activate_persona() {
    local PERSONA_NAME="$1"
    local JSON_MODE="${2:-false}"
    local ENCODED_NAME=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$PERSONA_NAME'))")
    
    RESULT=$(curl -sk -X POST -H "X-API-Key: $API_KEY" \
        "$SERVER_URL/api/v1/personas/$ENCODED_NAME/activate" 2>/dev/null)
    
    if echo "$RESULT" | grep -q "success"; then
        if [ "$JSON_MODE" = "true" ]; then
            output_waybar_json
        else
            echo -e "${GREEN}✓ Active: ${MAGENTA}$PERSONA_NAME${NC}"
            
            # Send notification
            if command -v notify-send &> /dev/null; then
                local icon=$(get_icon "$PERSONA_NAME")
                notify-send "$icon AI Companion" "Switched to: $PERSONA_NAME" --urgency=low
            fi
        fi
        return 0
    else
        if [ "$JSON_MODE" = "true" ]; then
            echo "{\"text\": \"⚠️\", \"tooltip\": \"Error: $RESULT\", \"class\": \"error\"}"
        else
            echo "Error: $RESULT"
        fi
        return 1
    fi
}

# Function to get next persona (wheel mode)
cycle_next_persona() {
    local JSON_MODE="${1:-false}"
    
    # Get current state from server
    local DATA=$(curl -sk -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/personas" 2>/dev/null)
    
    # Use Python to find next persona
    local NEXT_PERSONA=$(echo "$DATA" | python3 -c "
import sys, json
data = json.load(sys.stdin)
personas = [p['name'] for p in data.get('personas', [])]
active = data.get('active', '')

if not personas:
    sys.exit(1)

try:
    current_idx = personas.index(active)
    next_idx = (current_idx + 1) % len(personas)
except ValueError:
    next_idx = 0

print(personas[next_idx])
")
    
    if [ -n "$NEXT_PERSONA" ]; then
        activate_persona "$NEXT_PERSONA" "$JSON_MODE"
    else
        if [ "$JSON_MODE" = "true" ]; then
            echo '{"text": "⚠️", "tooltip": "Error: No personas", "class": "error"}'
        else
            echo "Error: Could not determine next persona"
        fi
        exit 1
    fi
}

# Show list of personas
show_list() {
    echo -e "${CYAN}╭─────────────────────────────────────╮${NC}"
    echo -e "${CYAN}│         Available Personas          │${NC}"
    echo -e "${CYAN}╰─────────────────────────────────────╯${NC}"
    echo ""
    
    curl -sk -H "X-API-Key: $API_KEY" "$SERVER_URL/api/v1/personas" | python3 -c "
import sys, json
data = json.load(sys.stdin)
active = data.get('active', '')
personas = data.get('personas', [])
for i, p in enumerate(personas):
    name = p['name']
    desc = p['description']
    if name == active:
        print(f'  \033[0;35m▶ {name}\033[0m ← active')
    else:
        print(f'  ○ {name}')
    print(f'    {desc}')
    print()
"
}

# Main logic
case "${1:-}" in
    --json|-j)
        # Output current status as JSON for Waybar
        check_api_key
        output_waybar_json
        ;;
    --next-json)
        # Cycle and output JSON (for Waybar on-click)
        check_api_key
        cycle_next_persona "true"
        ;;
    --list|-l)
        check_api_key
        show_list
        ;;
    --help|-h)
        echo "Usage: $0 [option|persona_name]"
        echo ""
        echo "Options:"
        echo "  (no args)      Cycle to next persona (wheel mode)"
        echo "  --list, -l     Show all available personas"
        echo "  --json, -j     Output current persona as JSON (Waybar)"
        echo "  --next-json    Cycle next + output JSON (Waybar on-click)"
        echo "  --help, -h     Show this help"
        echo "  \"Name\"         Switch to specific persona by name"
        echo ""
        echo "Waybar config example:"
        echo '  "custom/ai-persona": {'
        echo '    "exec": "~/Build/companion/client/switch-persona.sh --json",'
        echo '    "on-click": "~/Build/companion/client/switch-persona.sh --next-json",'
        echo '    "return-type": "json",'
        echo '    "interval": 30'
        echo '  }'
        ;;
    "")
        # No argument: cycle to next persona
        check_api_key
        cycle_next_persona "false"
        ;;
    *)
        # Specific persona name provided
        check_api_key
        activate_persona "$1" "false"
        ;;
esac