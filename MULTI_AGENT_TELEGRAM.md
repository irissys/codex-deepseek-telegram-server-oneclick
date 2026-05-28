# Multi-agent Telegram Bridge

`telegram_multi_agent_bridge.py` is a role-based Telegram router for Codex.

## Memory Model

- Temporary memory is the Codex session.
- Clearing temporary memory means deleting an agent's `session.txt`.
- Clearing all temporary memory means deleting all `agents/*/session.txt`.
- Fixed memory is injected only when a new session is created.
- Role text is also injected only when a new session is created.

## Files

```text
agents/
  CEO/
    role.txt
    memory_fixed.txt
    session.txt
  ops/
    role.txt
    memory_fixed.txt
    session.txt
```

## Commands

```text
/roles
/create <agent> <role text>
/setrole <agent> <role text>
/fixmem <agent> <memory text>
/showmem <agent>
/delmem <agent> <index>
/clear <agent>
/clear_all
@agent <task>
```

Examples:

```text
/create ops You are the server operations agent. Maintain Linux, Moon Bridge, Codex, and Telegram bridge services.
/fixmem ops Moon Bridge listens on 127.0.0.1:38442.
@ops Check Moon Bridge logs and tell me whether it is healthy.
/clear ops
```

## Linux Start

Stop the old single-agent bridge first:

```bash
cd /home/ubuntu/codex_deepseek
kill "$(cat run/bridge.pid)" 2>/dev/null || true
```

Start the multi-agent bridge:

```bash
cd /home/ubuntu/codex_deepseek
mkdir -p logs run
nohup scripts/start_multi_agent_bridge.sh > logs/multi_agent_stdout.log 2> logs/multi_agent_stderr.log &
echo $! > run/bridge.pid
tail -f logs/multi_agent_bridge.log
```

If Codex was locally installed by the deploy script, set `CODEX_COMMAND`:

```bash
export CODEX_COMMAND="/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
```

For permanent use, add that export to `scripts/start_multi_agent_bridge.sh` or create a dedicated launcher.
