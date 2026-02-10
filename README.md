# AI Desktop Companion

Local AI that watches your screen and gives contextual feedback based on your activity. Runs entirely on your machine with Ollama — no cloud, no telemetry.

## Requirements

- **Server:** Docker, Docker Compose
- **Client:** Arch Linux + Wayland — `sudo pacman -S grim playerctl libnotify python`

## Setup

```bash
# 1. Generate certs and API key
./scripts/generate-certs.sh
./scripts/generate-api-key.sh

# 2. Configure
cp .env.example .env        # edit API_KEY

# 3. Start
docker compose up -d
./scripts/setup-models.sh    # first time only

# 4. Client
cd client
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # set same API_KEY
python companion_client.py   # or: --once, --health, -v, -i 30
```

## Models

Two models work together: a **vision** model reads your screen, a **reasoning** model generates feedback.

### Profiles

| Profile      | Vision    | Reasoning    | RAM    | Notes                    |
|--------------|-----------|--------------|--------|--------------------------|
| fast         | moondream | llama3.2:1b  | ~2.5GB | Default, old hardware OK |
| balanced     | moondream | llama3.2:3b  | ~3.5GB | Best bang for buck       |
| quality      | moondream | llama3:8b    | ~6GB   | Best responses           |
| vision-focus | llava:7b  | llama3.2:3b  | ~6GB   | Better image analysis    |
| experimental | llava:13b | qwen2.5:7b   | ~10GB  | Needs good hardware      |

### Switching

```bash
./scripts/switch-model.sh                    # interactive
./scripts/switch-model.sh -p balanced        # profile
./scripts/switch-model.sh -v llava:7b        # vision only
./scripts/switch-model.sh -r qwen2.5:7b      # reasoning only
./scripts/switch-model.sh -d llama3:8b       # remove model
./scripts/switch-model.sh -l                 # list
```

Models can also be hot-reloaded via API (`POST /api/v1/models/switch`).

## Personas

Personas change the AI's personality. Switch via Waybar click or API.

| Name                    | Icon | Style                         |
|-------------------------|------|-------------------------------|
| Drill Sergeant          | 󰺵    | Aggressive productivity coach |
| Lazy Cat                | 󰄛    | Indifferent cat               |
| Cyberpunk Operator      | 󰚩    | Cold robotic system AI        |
| Supportive Bro          | 󰋑    | High-energy hype man          |
| Existential Philosopher | 󰠗    | Melancholic deep thinker      |

Edit `config/personas.json` to add your own.

### Waybar Integration

```jsonc
"custom/ai-companion": {
    "exec": "~/Build/companion/client/switch-persona.sh --json",
    "on-click": "~/Build/companion/client/switch-persona.sh --next-json",
    "return-type": "json",
    "interval": 30
}
```

## API

All endpoints under `/api/v1/`, authenticated via `X-API-Key` header.

| Endpoint                     | Method | Description             |
|------------------------------|--------|-------------------------|
| `/health`                    | GET    | Health check (no auth)  |
| `/analyze`                   | POST   | Submit screenshot + ctx |
| `/models`                    | GET    | Current models info     |
| `/models/switch`             | POST   | Hot-reload models       |
| `/models/pull/{name}`        | POST   | Pull model from Ollama  |
| `/personas`                  | GET    | List personas           |
| `/personas/{name}/activate`  | POST   | Switch persona          |
| `/context`                   | GET    | Current context window  |
| `/todos/reload`              | POST   | Reload todo.txt         |

## Config

### Server `.env`

| Variable                 | Default     | Description                          |
|--------------------------|-------------|--------------------------------------|
| `API_KEY`                | —           | Authentication key (required)        |
| `VISION_MODEL`           | `moondream` | Vision model                         |
| `REASONING_MODEL`        | `llama3.2:1b` | Reasoning model                   |
| `CONTEXT_WINDOW_SIZE`    | `10`        | Context entries to keep              |
| `CAPTURES_BEFORE_FEEDBACK` | `5`      | Captures before generating feedback  |
| `REQUEST_TIMEOUT`        | `300`       | Ollama request timeout (seconds)     |

### Client `client/.env`

| Variable                       | Default                  | Description                 |
|--------------------------------|--------------------------|-----------------------------|
| `COMPANION_API_KEY`            | —                        | Must match server key       |
| `COMPANION_SERVER_URL`         | `https://localhost:8443` | Server URL                  |
| `COMPANION_CAPTURE_INTERVAL`   | `60`                     | Seconds between captures    |
| `COMPANION_REQUEST_TIMEOUT`    | `300`                    | HTTP timeout (seconds)      |
| `COMPANION_LOG_LEVEL`          | `INFO`                   | `DEBUG` / `INFO` / `WARNING`|
| `COMPANION_LOG_FILE`           | *(stdout)*               | Log file path               |

## License

GNU GPL v3.0
