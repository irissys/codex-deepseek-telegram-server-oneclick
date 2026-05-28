# Linux 服务器部署与运行手册

适用目录：

```bash
/home/ubuntu/codex_deepseek
```

目标架构：

```text
Telegram Bot
  -> telegram_multi_agent_bridge.py
  -> Codex CLI
  -> Moon Bridge
  -> DeepSeek V4 Pro
```

固定配置：

- Moon Bridge 端口：`38442`
- Codex 模型入口：`moonbridge`
- 后端模型：`deepseek-v4-pro`
- Telegram 白名单默认 ID：`8839852759`
- Telegram 多 Agent：支持
- 临时记忆：Codex session
- 固定记忆：`agents/<职位>/memory_fixed.txt`
- 职位身份：`agents/<职位>/role.txt`

## 1. 基础依赖

```bash
sudo apt update
sudo apt install -y curl tar unzip nodejs npm python3 python3-pip python3-httpx python3-venv python3-full git bubblewrap
```

如果 `python3-httpx` 已安装，通常不需要再用 pip 安装 `httpx`。

## 2. 进入目录

```bash
cd /home/ubuntu/codex_deepseek
```

## 3. 检查关键配置

DeepSeek API Key：

```bash
cat config/api_key.txt
grep -n "api_key" tools/moon-bridge/config.yml
```

两处都应该是真正的 DeepSeek Key，形如：

```text
sk-xxxxxxxxxxxxxxxx
```

Telegram Bot Token：

```bash
cat config/telegram_bot_token.txt
```

Telegram 白名单：

```bash
cat config/telegram_allowed_users.txt
```

应该包含：

```text
8839852759
```

Codex 项目目录：

```bash
cat config/codex_project_dir.txt
```

应该是纯路径，不要写 `cd`：

```text
/home/ubuntu/codex_deepseek
```

Telegram 代理：

```bash
cat config/telegram_proxy.txt
```

如果服务器能直连 Telegram，这个文件应为空。

## 4. 启动 Moon Bridge

先杀旧进程：

```bash
pkill -9 -f moonbridge || true
pkill -9 -f 'cmd/moonbridge' || true
pkill -9 -f 'go run ./cmd/moonbridge' || true
```

后台启动：

```bash
cd /home/ubuntu/codex_deepseek/tools/moon-bridge
nohup ../go/bin/go run ./cmd/moonbridge --config config.yml \
  > /home/ubuntu/codex_deepseek/tools/moonbridge-38442.log \
  2> /home/ubuntu/codex_deepseek/tools/moonbridge-38442.err.log &
```

确认监听：

```bash
ss -ltnp | grep 38442
```

看日志：

```bash
tail -n 80 /home/ubuntu/codex_deepseek/tools/moonbridge-38442.err.log
tail -n 80 /home/ubuntu/codex_deepseek/tools/moonbridge-38442.log
```

## 5. 测试 Moon Bridge

模型列表：

```bash
curl -s http://127.0.0.1:38442/v1/models
echo
```

Responses 测试：

```bash
curl -s http://127.0.0.1:38442/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"moonbridge","input":"只输出 OK","max_output_tokens":50}'
echo
```

如果返回 `Authentication Fails`，说明当前运行的 Moon Bridge 没有读到正确 API Key。重启 Moon Bridge。

## 6. Codex 命令路径

如果 Codex 是本地安装，路径通常是：

```bash
/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex
```

查找：

```bash
find tools -type f -name codex -o -name codex.cmd -o -name codex.exe
```

设置环境变量：

```bash
export CODEX_HOME=/home/ubuntu/codex_deepseek/tools/codex-home
export CODEX_COMMAND=/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex
```

测试 Codex：

```bash
$CODEX_COMMAND --ask-for-approval never \
  --cd /home/ubuntu/codex_deepseek \
  exec --skip-git-repo-check "只输出 OK"
```

## 7. 启动多 Agent Telegram 桥接

停止旧桥接：

```bash
cd /home/ubuntu/codex_deepseek
kill "$(cat run/bridge.pid)" 2>/dev/null || true
```

启动多 Agent 桥接：

```bash
cd /home/ubuntu/codex_deepseek

export CODEX_COMMAND="/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
export CODEX_HOME="/home/ubuntu/codex_deepseek/tools/codex-home"

mkdir -p logs run
nohup scripts/start_multi_agent_bridge.sh > logs/multi_agent_stdout.log 2> logs/multi_agent_stderr.log &
echo $! > run/bridge.pid
```

查看日志：

```bash
tail -f logs/multi_agent_bridge.log
```

确认进程：

```bash
cat run/bridge.pid
ps -p "$(cat run/bridge.pid)" -f
```

## 8. Telegram 多 Agent 命令

查看帮助：

```text
/help
```

列出职位：

```text
/roles
```

创建职位：

```text
/create ops 你是服务器运维 Agent，负责维护 Linux、Moon Bridge、Codex、Telegram 桥接。
```

修改职位：

```text
/setrole dev 你是开发 Agent，负责修改代码和部署脚本。
```

添加固定记忆：

```text
/fixmem ops Moon Bridge 端口固定是 38442。
```

查看固定记忆：

```text
/showmem ops
```

删除固定记忆：

```text
/delmem ops 2
```

清除某职位临时记忆：

```text
/clear ops
```

清除所有临时记忆：

```text
/clear_all
```

给职位派任务：

```text
@ops 检查 Moon Bridge 是否正常
@运维 检查 Moon Bridge 是否正常
```

职位名支持中文。`@运维 ...` 会使用：

```text
agents/运维/
```

## 9. 记忆规则

```text
agents/
  ops/
    role.txt
    memory_fixed.txt
    session.txt
```

- `role.txt`：职位身份。
- `memory_fixed.txt`：固定记忆。
- `session.txt`：临时记忆，也就是 Codex session。
- `/clear ops`：删除 `agents/ops/session.txt`。
- `/clear_all`：删除所有 `agents/*/session.txt`。
- 固定记忆只在新 session 创建时注入。

## 10. 常见问题

### Telegram 报 Connection refused

通常是 `config/telegram_proxy.txt` 写了不存在的代理，比如 `127.0.0.1:7892`。

直连：

```bash
cd /home/ubuntu/codex_deepseek
: > config/telegram_proxy.txt
```

然后重启 Telegram 桥接。

### Codex 找不到

日志：

```text
FileNotFoundError: No such file or directory: 'codex'
```

设置：

```bash
export CODEX_COMMAND="/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
```

### Codex 弹登录

说明没有读到 `CODEX_HOME`。

设置：

```bash
export CODEX_HOME=/home/ubuntu/codex_deepseek/tools/codex-home
```

### Moon Bridge 502 Authentication Fails

说明当前运行的 Moon Bridge 读到的是错误 API Key，或旧进程没重启。

执行：

```bash
pkill -9 -f moonbridge || true
pkill -9 -f 'cmd/moonbridge' || true
pkill -9 -f 'go run ./cmd/moonbridge' || true
```

然后重新启动 Moon Bridge。

### `npm EACCES`

全局安装 Codex 没权限，没关系。脚本会安装到本地：

```text
tools/npm-global
```

### `externally-managed-environment`

Ubuntu 系统 Python 不允许直接 pip 安装。优先：

```bash
sudo apt install -y python3-httpx
```

或使用 venv。
