# AI Desktop Companion

Local AI that watches your screen and gives feedback based on your activity. Runs on your machine with Ollama.

## Setup

```bash
# Generate certs and API key
./scripts/generate-certs.sh
./scripts/generate-api-key.sh

# Configure
cp .env.example .env
# Edit .env with your API_KEY

# Start server
docker compose up -d
./scripts/setup-models.sh  # first time only

# Setup client
cd client
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit with same API_KEY
```

## python companion_client.py -h

```bash
usage: companion_client.py [-h] [--check-tools] [--health] [--once] [-v] [-i INTERVAL]

Wayland AI Desktop Companion Client

options:
  -h, --help            show this help message and exit
  --check-tools         Check required tools and exit
  --health              Check server health and exit
  --once                Run once and exit (for testing)
  -v, --verbose         Verbose output - show full AI responses
  -i, --interval INTERVAL
                        Override capture interval (seconds)```
```

## Waybar

```jsonc
"custom/ai-companion": {
    "exec": "~/Build/companion/client/switch-persona.sh --json",
    "on-click": "~/Build/companion/client/switch-persona.sh --next-json",
    "return-type": "json",
    "interval": 30
}
```

## Personas

| Name                     | Icon | Style                             |
| ------------------------ | ---- | --------------------------------- |
| Drill Sergeant           | 󰺵    | Aggressive productivity coach     |
| Lazy Cat                 | 󰄛    | Indifferent cat wanting attention |
| Cyberpunk Operator       | 󰚩    | Cold robotic system AI            |
| Supportive Bro           | 󰋑    | High-energy hype man              |
| Existential Philosopher  | 󰠗    | Melancholic deep thinker          |

Edit `config/personas.json` to add your own.

## Requirements

- **Server:** Docker, Docker Compose
- **Client:** `sudo pacman -S grim playerctl libnotify python`

## API

| Endpoint                           | Method | Description     |
| ---------------------------------- | ------ | --------------- |
| `/api/v1/health`                   | GET    | Health check    |
| `/api/v1/analyze`                  | POST   | Submit activity |
| `/api/v1/personas`                 | GET    | List personas   |
| `/api/v1/personas/{name}/activate` | POST   | Switch persona  |

## Config

### Server (`.env`)

| Variable                   | Default       | Description                              |
| -------------------------- | ------------- | ---------------------------------------- |
| `API_KEY`                  | —             | Authentication key                       |
| `VISION_MODEL`             | `moondream`   | Vision model for screenshots             |
| `REASONING_MODEL`          | `llama3.2:3b` | Reasoning model for feedback             |
| `CONTEXT_WINDOW_SIZE`      | `10`          | How many entries to keep in context      |
| `CAPTURES_BEFORE_FEEDBACK` | `5`           | Captures to accumulate before feedback   |

### Client (`client/.env`)

| Variable                     | Default                  |
| ---------------------------- | ------------------------ |
| `COMPANION_API_KEY`          | —                        |
| `COMPANION_SERVER_URL`       | `https://localhost:8443` |
| `COMPANION_CAPTURE_INTERVAL` | `60`                     |
| `COMPANION_REQUEST_TIMEOUT`  | `300`                    |

## License

GNU GPL v3.0
