#!/usr/bin/env bash
# ==============================================================================
# 🎨 Kobean Manga Colorizer - Ultra-Fast Launcher Script
# ==============================================================================
# Usage:
#   ./run.sh                  -> Launch studio with default settings (auto-browser)
#   ./run.sh --reload         -> Launch studio with auto-reload (development)
#   ./run.sh --port 8080      -> Launch studio on custom port
#   ./run.sh --no-open        -> Launch without opening browser
#   ./run.sh --kill           -> Force terminate any existing process on port
# ==============================================================================

set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# Text Styling
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

PORT=8000
HOST="127.0.0.1"
KILL_OCCUPIED=0
EXTRA_ARGS=()

# Show help function
show_help() {
  echo -e "${BOLD}🎨 Kobean Manga Colorizer - Launch Helper${RESET}"
  echo ""
  echo "Usage: ./run.sh [options]"
  echo ""
  echo "Options:"
  echo "  -h, --help        Show this help message and exit"
  echo "  -p, --port PORT   Port to bind to (default: 8000)"
  echo "      --host HOST   Host address to bind to (default: 127.0.0.1)"
  echo "  -r, --reload      Enable auto-reload on code changes (dev mode)"
  echo "      --no-open     Do not automatically launch web browser"
  echo "  -k, --kill        Force terminate any existing process on the port"
  echo ""
  echo "Examples:"
  echo "  ./run.sh                  # One-command instant studio startup"
  echo "  ./run.sh --reload         # Launch in live developer mode"
  echo "  ./run.sh --port 8080      # Launch on port 8080"
  exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      show_help
      ;;
    -k|--kill)
      KILL_OCCUPIED=1
      shift
      ;;
    -p|--port)
      PORT="$2"
      EXTRA_ARGS+=("--port" "$2")
      shift 2
      ;;
    --host)
      HOST="$2"
      EXTRA_ARGS+=("--host" "$2")
      shift 2
      ;;
    -r|--reload)
      EXTRA_ARGS+=("--reload")
      shift
      ;;
    --no-open)
      EXTRA_ARGS+=("--no-open")
      shift
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

# Step 1: Detect Runtime Environment (prioritize UV, then .venv / venv)
USE_UV=0
PYTHON_BIN=""
if command -v uv >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    USE_UV=1
elif [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
elif [ -n "$VIRTUAL_ENV" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo -e "${RED}❌ Error: Neither uv nor Python 3 was found on your system.${RESET}"
    echo "Please install uv (https://astral.sh/uv) or Python 3.9+"
    exit 1
fi

# Step 2: Check for active listener port conflict
LISTEN_PID=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$LISTEN_PID" ]; then
    echo -e "${YELLOW}⚡ Port $PORT is already in use by process PID $LISTEN_PID.${RESET}"
    echo -e "${CYAN}👉 Restarting server cleanly on port $PORT...${RESET}"
    kill -9 $LISTEN_PID 2>/dev/null || true
    sleep 0.5
fi

# Step 3: Print Studio Banner
echo -e "${CYAN}${BOLD}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║               🎨  Kobean Manga Colorizer Studio               ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo -e "║  ${GREEN}🌐 Studio URL:    http://${HOST}:${PORT}${CYAN}                               ║"
echo "║  ⚡ Hardware:      Apple Silicon MPS / CUDA / CPU auto        ║"
echo "║  🚀 Engine:        UV Package Manager + FastAPI               ║"
echo "║  🛑 Stop Studio:   Press CTRL + C                             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Step 4: Execute main app
if [ "$USE_UV" -eq 1 ]; then
    exec uv run python "$SCRIPT_DIR/main.py" --host "$HOST" --port "$PORT" "${EXTRA_ARGS[@]}"
else
    exec "$PYTHON_BIN" "$SCRIPT_DIR/main.py" --host "$HOST" --port "$PORT" "${EXTRA_ARGS[@]}"
fi

