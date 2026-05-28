#!/usr/bin/env bash
set -euo pipefail

ROOT="${INSTALL_ROOT:-/home/ubuntu/codex_deepseek}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT/app"
SCRIPTS_DIR="$ROOT/scripts"
CONFIG_DIR="$ROOT/config"
LOG_DIR="$ROOT/logs"
RUN_DIR="$ROOT/run"
DOCS_DIR="$ROOT/docs"
ADMIN_TELEGRAM_ID="${ADMIN_TELEGRAM_ID:-8839852759}"
CODEX_LOCAL_BIN="$ROOT/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"

mkdir -p "$ROOT" "$APP_DIR" "$SCRIPTS_DIR" "$CONFIG_DIR" "$LOG_DIR" "$RUN_DIR" "$DOCS_DIR"

cleanup_previous_deploy() {
  echo "Cleaning previous Telegram bridge/agent deployment while keeping config files..."

  local resolved_root
  resolved_root="$(cd "$ROOT" && pwd)"
  case "$resolved_root" in
    ""|"/"|"/home"|"/home/ubuntu"|"/root")
      echo "Refusing cleanup for unsafe install root: $resolved_root" >&2
      exit 1
      ;;
  esac

  if command -v systemctl >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    local service
    for service in codex-telegram-bridge.service codex-telegram-agent.service moonbridge.service; do
      sudo systemctl stop "$service" >/dev/null 2>&1 || true
      sudo systemctl disable "$service" >/dev/null 2>&1 || true
      sudo rm -f "/etc/systemd/system/$service"
    done
    sudo systemctl daemon-reload >/dev/null 2>&1 || true
    sudo systemctl reset-failed >/dev/null 2>&1 || true
  fi

  pkill -f "$resolved_root/telegram_multi_agent_bridge.py" 2>/dev/null || true
  pkill -f "$resolved_root/app/telegram_multi_agent_bridge.py" 2>/dev/null || true
  pkill -f "$resolved_root/telegram_codex_bridge.py" 2>/dev/null || true
  pkill -f "$resolved_root/agent_system/telegram_master.py" 2>/dev/null || true
  pkill -f "$resolved_root/start_multi_agent_bridge.sh" 2>/dev/null || true
  pkill -f "$resolved_root/app/start_multi_agent_bridge.sh" 2>/dev/null || true
  pkill -f "$resolved_root/scripts/start_multi_agent_bridge.sh" 2>/dev/null || true
  pkill -f "$resolved_root/start_bridge.sh" 2>/dev/null || true

  rm -rf \
    "$ROOT/agent_system" \
    "$ROOT/telegram_agent_system_bundle" \
    "$ROOT/bridge_sessions" \
    "$ROOT/run" \
    "$ROOT/app" \
    "$ROOT/scripts" \
    "$ROOT/docs"

  rm -f \
    "$ROOT/telegram_codex_bridge.py" \
    "$ROOT/telegram_multi_agent_bridge.py" \
    "$ROOT/start_bridge.sh" \
    "$ROOT/restart_bridge.sh" \
    "$ROOT/start_multi_agent_bridge.sh" \
    "$ROOT/restart_multi_agent_bridge.sh" \
    "$ROOT/bridge.pid" \
    "$ROOT/bridge.lock" \
    "$ROOT/bridge_offset.txt" \
    "$ROOT/bridge.log" \
    "$ROOT/bridge_stdout.log" \
    "$ROOT/bridge_stderr.log" \
    "$ROOT/multi_agent_bridge.pid" \
    "$ROOT/multi_agent_bridge.lock" \
    "$ROOT/multi_agent_bridge_offset.txt" \
    "$ROOT/multi_agent_bridge.log" \
    "$ROOT/multi_agent_stdout.log" \
    "$ROOT/multi_agent_stderr.log" \
    "$ROOT"/codex_reply_*.txt \
    "$ROOT"/codex_*_reply_*.txt

  if [[ -d "$ROOT/agents" ]]; then
    find "$ROOT/agents" -type f \( -name session.txt -o -name "*.lock" -o -name "*.pid" \) -delete
  fi
}

copy_file() {
  local name="$1"
  local target_dir="${2:-$APP_DIR}"
  if [[ -f "$SRC/$name" ]]; then
    mkdir -p "$target_dir"
    cp -f "$SRC/$name" "$target_dir/$name"
  fi
}

cleanup_previous_deploy

mkdir -p "$APP_DIR" "$SCRIPTS_DIR" "$CONFIG_DIR" "$LOG_DIR" "$RUN_DIR" "$DOCS_DIR"

copy_file "telegram_multi_agent_bridge.py" "$APP_DIR"
copy_file "SERVER_LINUX_RUNBOOK_CN.md" "$DOCS_DIR"
copy_file "MULTI_AGENT_TELEGRAM_CN.md" "$DOCS_DIR"
copy_file "MULTI_AGENT_TELEGRAM.md" "$DOCS_DIR"

if [[ ! -f "$CONFIG_DIR/telegram_allowed_users.txt" ]]; then
  printf '%s\n' "$ADMIN_TELEGRAM_ID" > "$CONFIG_DIR/telegram_allowed_users.txt"
fi

if [[ ! -f "$CONFIG_DIR/telegram_proxy.txt" ]]; then
  : > "$CONFIG_DIR/telegram_proxy.txt"
fi

if [[ ! -f "$CONFIG_DIR/codex_project_dir.txt" ]]; then
  printf '%s\n' "$ROOT" > "$CONFIG_DIR/codex_project_dir.txt"
fi

cat > "$SCRIPTS_DIR/start_multi_agent_bridge.sh" <<EOF_START
#!/usr/bin/env bash
set -euo pipefail
SCRIPTS_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
ROOT="\$(cd "\$SCRIPTS_DIR/.." && pwd)"
APP_DIR="\$ROOT/app"
CONFIG_DIR="\$ROOT/config"
LOG_DIR="\$ROOT/logs"
RUN_DIR="\$ROOT/run"
mkdir -p "\$CONFIG_DIR" "\$LOG_DIR" "\$RUN_DIR"
cd "\$ROOT"

export CODEX_HOME="\$ROOT/tools/codex-home"
if [[ -x "$CODEX_LOCAL_BIN" ]]; then
  export CODEX_COMMAND="$CODEX_LOCAL_BIN"
fi
export CODEX_PROJECT_DIR="\$(cat "\$CONFIG_DIR/codex_project_dir.txt" 2>/dev/null || printf '%s' "\$ROOT")"
export TELEGRAM_PROXY="\$(cat "\$CONFIG_DIR/telegram_proxy.txt" 2>/dev/null || true)"
export CODEX_EXEC_TIMEOUT="\${CODEX_EXEC_TIMEOUT:-900}"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost,::1"
export no_proxy="\$NO_PROXY"

exec python3 "\$APP_DIR/telegram_multi_agent_bridge.py"
EOF_START

chmod +x "$SCRIPTS_DIR/start_multi_agent_bridge.sh"

install_bridge_service() {
  if ! command -v systemctl >/dev/null 2>&1 || ! command -v sudo >/dev/null 2>&1; then
    echo "systemctl/sudo not found. Autostart service was not installed."
    return
  fi

  if systemctl list-unit-files codex-moonbridge.service >/dev/null 2>&1; then
    sudo systemctl enable codex-moonbridge.service >/dev/null 2>&1 || true
    sudo systemctl restart codex-moonbridge.service || true
  else
    echo "Warning: codex-moonbridge.service was not found. Codex requests need Moon Bridge on 127.0.0.1:38442." >&2
  fi

  local service_file="/etc/systemd/system/codex-telegram-bridge.service"
  local tmp_service
  tmp_service="$(mktemp)"
  cat > "$tmp_service" <<EOF_SERVICE
[Unit]
Description=Codex Telegram Multi-Agent Bridge
After=network-online.target codex-moonbridge.service
Wants=network-online.target codex-moonbridge.service
Requires=codex-moonbridge.service
Conflicts=codex-telegram-agent.service

[Service]
Type=simple
User=$(id -un)
Group=$(id -gn)
WorkingDirectory=$ROOT
ExecStart=$SCRIPTS_DIR/start_multi_agent_bridge.sh
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/multi_agent_stdout.log
StandardError=append:$LOG_DIR/multi_agent_stderr.log

[Install]
WantedBy=multi-user.target
EOF_SERVICE

  echo "Installing systemd autostart service: codex-telegram-bridge.service"
  sudo cp "$tmp_service" "$service_file"
  rm -f "$tmp_service"
  sudo systemctl daemon-reload
  sudo systemctl enable codex-telegram-bridge.service
  sudo systemctl restart codex-telegram-bridge.service
}

verify_single_system() {
  local bridge_count
  bridge_count="$(pgrep -fc "$ROOT/app/telegram_multi_agent_bridge.py" || true)"
  if [[ "$bridge_count" != "1" ]]; then
    echo "Warning: expected exactly one multi-agent bridge process, found $bridge_count." >&2
    ps -ef | grep -E 'telegram_multi_agent_bridge|telegram_master|telegram_codex_bridge' | grep -v grep >&2 || true
  fi

  if pgrep -f "$ROOT/agent_system/telegram_master.py" >/dev/null 2>&1 || pgrep -f "$ROOT/telegram_codex_bridge.py" >/dev/null 2>&1; then
    echo "Warning: an old Telegram bridge/agent process is still running." >&2
    ps -ef | grep -E 'telegram_master|telegram_codex_bridge' | grep -v grep >&2 || true
  fi

  if command -v ss >/dev/null 2>&1 && ! ss -lnt | awk '{print $4}' | grep -Eq '(^|:)38442$'; then
    echo "Warning: Moon Bridge does not appear to be listening on 127.0.0.1:38442." >&2
  fi
}

cat > "$SCRIPTS_DIR/restart_multi_agent_bridge.sh" <<'EOF_RESTART'
#!/usr/bin/env bash
set -euo pipefail
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS_DIR/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/logs" "$ROOT/run"

if [[ -f "$ROOT/run/bridge.pid" ]]; then
  kill "$(cat "$ROOT/run/bridge.pid")" 2>/dev/null || true
fi

pkill -f telegram_multi_agent_bridge.py 2>/dev/null || true

nohup "$SCRIPTS_DIR/start_multi_agent_bridge.sh" > "$ROOT/logs/multi_agent_stdout.log" 2> "$ROOT/logs/multi_agent_stderr.log" &
echo $! > "$ROOT/run/bridge.pid"
echo "multi-agent bridge pid: $(cat "$ROOT/run/bridge.pid")"
echo "log: $ROOT/logs/multi_agent_bridge.log"
EOF_RESTART

chmod +x "$SCRIPTS_DIR/restart_multi_agent_bridge.sh"

install_bridge_service
verify_single_system

echo "Installed server multi-agent bundle to: $ROOT"
echo
echo "Next:"
echo "  cd $ROOT"
echo "  sudo systemctl status codex-telegram-bridge.service --no-pager -l"
echo "  tail -f logs/multi_agent_bridge.log"
