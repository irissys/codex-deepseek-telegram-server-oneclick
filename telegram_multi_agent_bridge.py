import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
CONFIG_DIR = ROOT / "config"
LOG_DIR = ROOT / "logs"
RUN_DIR = ROOT / "run"
LOG_FILE = LOG_DIR / "multi_agent_bridge.log"
LOCK_FILE = RUN_DIR / "multi_agent_bridge.lock"
OFFSET_FILE = RUN_DIR / "multi_agent_bridge_offset.txt"
AGENTS_DIR = ROOT / "agents"

DEFAULT_PROJECT_DIR = ROOT
DEFAULT_CODEX_HOME = ROOT / "tools" / "codex-home"
DEFAULT_TELEGRAM_PROXY = ""
DEFAULT_AGENT = "CEO"

LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(console)


def acquire_lock():
    if os.name == "nt":
        import msvcrt

        handle = LOCK_FILE.open("a+b")
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("Another multi-agent bridge is already running.")
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("utf-8"))
        handle.flush()
        return handle

    import fcntl

    handle = LOCK_FILE.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("Another multi-agent bridge is already running.")
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")


def read_config(name: str) -> str:
    return read_text(CONFIG_DIR / name)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def append_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.strip() + "\n")


def get_bot_token() -> str:
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().lstrip("\ufeff")
        or read_config("telegram_bot_token.txt")
        or read_config("bot_token.txt")
    )


def get_allowed_users() -> set[str]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip() or read_config("telegram_allowed_users.txt")
    return {x.strip().lstrip("\ufeff") for x in raw.replace("\n", ",").split(",") if x.strip()}


def read_offset() -> int | None:
    raw = read_text(OFFSET_FILE)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def write_offset(offset: int) -> None:
    write_text(OFFSET_FILE, str(offset))


def normalize_agent_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
    name = name.strip("._-")
    return name or DEFAULT_AGENT


def agent_dir(name: str) -> Path:
    return AGENTS_DIR / normalize_agent_name(name)


def role_file(name: str) -> Path:
    return agent_dir(name) / "role.txt"


def fixed_memory_file(name: str) -> Path:
    return agent_dir(name) / "memory_fixed.txt"


def session_file(name: str) -> Path:
    return agent_dir(name) / "session.txt"


def ensure_agent(name: str, role: str = "") -> str:
    name = normalize_agent_name(name)
    agent_dir(name).mkdir(parents=True, exist_ok=True)
    if role and not role_file(name).exists():
        write_text(role_file(name), role)
    if not role_file(name).exists():
        write_text(role_file(name), f"You are the {name} agent.")
    if not fixed_memory_file(name).exists():
        write_text(fixed_memory_file(name), "")
    return name


def list_agents() -> list[str]:
    if not AGENTS_DIR.exists():
        return []
    return sorted(p.name for p in AGENTS_DIR.iterdir() if p.is_dir())


def read_session(name: str) -> str:
    return read_text(session_file(name))


def write_session(name: str, session_id: str) -> None:
    write_text(session_file(name), session_id)


def clear_session(name: str) -> None:
    try:
        session_file(name).unlink()
    except FileNotFoundError:
        pass


def clear_all_sessions() -> int:
    count = 0
    for name in list_agents():
        path = session_file(name)
        if path.exists():
            path.unlink()
            count += 1
    return count


def extract_session_id(output: str) -> str:
    match = re.search(r"session id:\s*([0-9a-fA-F-]{20,})", output)
    return match.group(1) if match else ""


def build_initial_prompt(agent: str, task: str) -> str:
    role = read_text(role_file(agent))
    fixed_memory = read_text(fixed_memory_file(agent))
    return f"""You are a persistent role-based Codex agent.

[Agent name]
{agent}

[Role]
{role}

[Fixed memory]
{fixed_memory if fixed_memory else "(none)"}

[Current task]
{task}
"""


class TelegramApi:
    def __init__(self, token: str):
        proxy = os.environ.get("TELEGRAM_PROXY", "").strip()
        if not proxy:
            proxy = read_config("telegram_proxy.txt")
        if proxy == "-":
            proxy = ""
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.Client(proxy=proxy or None, timeout=65)

    def request(self, method: str, payload: dict) -> dict:
        response = self.client.post(f"{self.base_url}/{method}", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data

    def get_updates(self, offset: int | None) -> list[dict]:
        payload = {"timeout": 55, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self.request("getUpdates", payload).get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        text = text or "(empty)"
        for i in range(0, len(text), 3900):
            self.request("sendMessage", {"chat_id": chat_id, "text": text[i : i + 3900], "disable_web_page_preview": True})

    def send_typing(self, chat_id: int) -> None:
        try:
            self.request("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except Exception as exc:
            logging.warning("sendChatAction failed: %s", exc)


def build_codex_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(Path(env.get("CODEX_HOME", DEFAULT_CODEX_HOME)).resolve())
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env["no_proxy"] = env["NO_PROXY"]
    return env


def resolve_codex_command() -> str:
    configured = os.environ.get("CODEX_COMMAND", "").strip()
    if configured:
        return configured
    for candidate in ("codex", "codex.cmd", "codex.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    local_candidates = [
        ROOT / "tools" / "npm-global" / "node_modules" / "@openai" / "codex-linux-x64" / "vendor" / "x86_64-unknown-linux-musl" / "bin" / "codex",
        ROOT / "tools" / "npm-global" / "node_modules" / ".bin" / "codex",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return "codex"


def run_codex_for_agent(agent: str, task: str, allow_retry: bool = True) -> str:
    agent = ensure_agent(agent)
    project_dir = Path(os.environ.get("CODEX_PROJECT_DIR", str(DEFAULT_PROJECT_DIR))).resolve()
    timeout = int(os.environ.get("CODEX_EXEC_TIMEOUT", "900"))
    output_file = Path(tempfile.NamedTemporaryFile(prefix=f"codex_{agent}_reply_", suffix=".txt", dir=RUN_DIR, delete=False).name)
    session_id = read_session(agent)

    if session_id:
        prompt = task
        exec_args = [
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_file),
            "resume",
            session_id,
            "-",
        ]
        logging.info("Resuming agent=%s session=%s", agent, session_id)
    else:
        prompt = build_initial_prompt(agent, task)
        exec_args = [
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_file),
            "-",
        ]
        logging.info("Starting new session for agent=%s", agent)

    command = [resolve_codex_command(), "--ask-for-approval", "never", "--cd", str(project_dir), *exec_args]
    try:
        result = subprocess.run(
            command,
            cwd=project_dir,
            env=build_codex_env(),
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "Cannot find codex. Set CODEX_COMMAND to the full Codex binary path."
    except subprocess.TimeoutExpired:
        return f"Codex timed out after {timeout} seconds."

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    combined = "\n".join(x for x in (stdout, stderr) if x)
    new_session_id = extract_session_id(combined)
    if new_session_id:
        write_session(agent, new_session_id)

    try:
        final_message = output_file.read_text(encoding="utf-8", errors="replace").strip()
    except FileNotFoundError:
        final_message = ""
    try:
        output_file.unlink()
    except OSError:
        pass

    if result.returncode == 0:
        return final_message or stdout or "(Codex completed without output.)"

    if session_id and allow_retry and ("No saved session found" in combined or "not found" in combined.lower()):
        clear_session(agent)
        return run_codex_for_agent(agent, task, allow_retry=False)

    return f"Codex failed with exit code {result.returncode}:\n{stderr or stdout or 'No error details.'}"


def parse_agent_task(text: str) -> tuple[str, str]:
    match = re.match(r"^@(\S+)\s+([\s\S]+)$", text.strip())
    if match:
        return normalize_agent_name(match.group(1)), match.group(2).strip()
    return DEFAULT_AGENT, text.strip()


def numbered_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def handle_command(text: str) -> str | None:
    parts = text.strip().split(maxsplit=2)
    if not parts or not parts[0].startswith("/"):
        return None
    cmd = parts[0].lower()

    if cmd in ("/help", "/start"):
        return """多 Agent 命令说明：

记忆规则：
- 临时记忆 = 该职位自己的 Codex session
- 固定记忆 = 新建 session 时注入的长期设定
- 清除临时记忆不会删除固定记忆

基础命令：
/help
显示这份中文说明。

/roles
列出所有职位 Agent。

/create <职位> <职位说明>
创建或更新一个职位，并清空该职位 session，让新职位说明下次生效。
例：/create ops 你是服务器运维 Agent，负责维护 Linux、Moon Bridge 和 Telegram 桥接。

/setrole <职位> <职位说明>
修改职位说明，并清空该职位 session。
例：/setrole dev 你是开发 Agent，负责修改代码和写部署脚本。

/fixmem <职位> <固定记忆>
给某个职位添加固定记忆。固定记忆会在新 session 创建时注入。
例：/fixmem ops Moon Bridge 端口固定是 38442。

/showmem <职位>
查看职位说明、固定记忆和当前 session id。
例：/showmem ops

/delmem <职位> <编号>
删除某条固定记忆，并清空该职位 session。
例：/delmem ops 2

/clear <职位>
清除某个职位的临时记忆，也就是删除该职位 session。
例：/clear ops

/clear_all
清除所有职位的临时记忆，也就是删除所有 session。

使用职位：
@职位 <任务>
把任务交给指定职位 Agent。
例：@ops 检查 Moon Bridge 是否正常

不带 @职位 的普通消息会交给 CEO Agent。"""

    if cmd == "/roles":
        agents = list_agents()
        return "当前职位 Agent：\n" + "\n".join(f"- {name}" for name in agents) if agents else "还没有创建任何职位 Agent。"

    if cmd in ("/create", "/setrole"):
        if len(parts) < 3:
            return f"用法：{cmd} <职位> <职位说明>"
        agent, role = parts[1], parts[2]
        agent = ensure_agent(agent)
        write_text(role_file(agent), role)
        if cmd == "/setrole":
            clear_session(agent)
        return f"职位 '{agent}' 的说明已保存，并已清空 session。下次任务会按新职位说明创建临时记忆。"

    if cmd == "/fixmem":
        if len(parts) < 3:
            return "用法：/fixmem <职位> <固定记忆>"
        agent = ensure_agent(parts[1])
        append_line(fixed_memory_file(agent), parts[2])
        return f"已给 '{agent}' 添加固定记忆。它会在新 session 创建时生效。"

    if cmd == "/showmem":
        if len(parts) < 2:
            return "用法：/showmem <职位>"
        agent = ensure_agent(parts[1])
        lines = numbered_lines(read_text(fixed_memory_file(agent)))
        role = read_text(role_file(agent))
        memory = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines)) or "(none)"
        session = read_session(agent) or "(none)"
        return f"职位：{agent}\n\n职位说明：\n{role}\n\n固定记忆：\n{memory}\n\n当前临时记忆 session：\n{session}"

    if cmd == "/delmem":
        if len(parts) < 3:
            return "用法：/delmem <职位> <编号>"
        agent = ensure_agent(parts[1])
        try:
            index = int(parts[2]) - 1
        except ValueError:
            return "编号必须是数字。"
        lines = numbered_lines(read_text(fixed_memory_file(agent)))
        if index < 0 or index >= len(lines):
            return "固定记忆编号超出范围。"
        removed = lines.pop(index)
        write_text(fixed_memory_file(agent), "\n".join(lines))
        clear_session(agent)
        return f"已删除 '{agent}' 的固定记忆：{removed}\n并已清空 session，让固定记忆变更下次生效。"

    if cmd == "/clear":
        if len(parts) < 2:
            return "用法：/clear <职位>"
        agent = ensure_agent(parts[1])
        clear_session(agent)
        return f"已清除 '{agent}' 的临时记忆 session。固定记忆保留。"

    if cmd == "/clear_all":
        count = clear_all_sessions()
        return f"已清除 {count} 个职位的临时记忆 session。固定记忆保留。"

    return "未知命令。发送 /help 查看中文命令说明。"


def handle_message(api: TelegramApi, allowed_users: set[str], message: dict) -> None:
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = str(user.get("id", "")).strip()
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return
    if user_id not in allowed_users:
        logging.warning("Rejected message from user_id=%s chat_id=%s", user_id, chat_id)
        api.send_message(chat_id, "This Telegram user id is not allowed.")
        return

    command_reply = handle_command(text)
    if command_reply is not None:
        api.send_message(chat_id, command_reply)
        return

    agent, task = parse_agent_task(text)
    task_id = uuid.uuid4().hex[:8]
    api.send_message(chat_id, f"已派发给 @{agent}，任务 id：{task_id}")
    api.send_typing(chat_id)
    reply = run_codex_for_agent(agent, task)
    api.send_message(chat_id, reply)


def main() -> None:
    acquire_lock()
    token = get_bot_token()
    if not token:
        raise SystemExit("Missing Telegram Bot Token.")
    allowed_users = get_allowed_users()
    if not allowed_users:
        raise SystemExit("No Telegram whitelist configured.")
    ensure_agent(DEFAULT_AGENT, "You are the CEO Telegram-controlled Codex agent.")

    api = TelegramApi(token)
    offset = read_offset()
    logging.info("Multi-agent bridge started. offset=%s", offset)
    while True:
        try:
            for update in api.get_updates(offset):
                offset = int(update["update_id"]) + 1
                write_offset(offset)
                message = update.get("message")
                if message:
                    handle_message(api, allowed_users, message)
        except httpx.HTTPStatusError as exc:
            logging.error("Telegram HTTP error %s: %s", exc.response.status_code, exc.response.text[:500])
            time.sleep(5)
        except Exception as exc:
            logging.exception("Bridge loop error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
