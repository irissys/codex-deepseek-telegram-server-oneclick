# Telegram 多 Agent 中文说明

这个桥接器文件是：

```text
telegram_multi_agent_bridge.py
```

它的目标是让一个 Telegram Bot 充当总控入口，通过 `@职位` 把任务分发给不同职位的 Codex Agent。

## 记忆规则

- 临时记忆就是 Codex session。
- 清除临时记忆就是删除对应职位的 `session.txt`。
- 清除全部临时记忆就是删除所有 `agents/*/session.txt`。
- 固定记忆存在 `memory_fixed.txt`。
- 职位身份存在 `role.txt`。
- 固定记忆和职位身份只在创建新 session 时注入。
- 如果某个职位已经有 session，后续消息会直接 resume 这个 session。

## 文件结构

```text
agents/
  ops/
    role.txt
    memory_fixed.txt
    session.txt
  dev/
    role.txt
    memory_fixed.txt
    session.txt
```

## Telegram 命令

### 查看帮助

```text
/help
```

显示中文命令说明。

### 查看职位

```text
/roles
```

列出所有职位 Agent。

### 创建职位

```text
/create <职位> <职位说明>
```

例：

```text
/create ops 你是服务器运维 Agent，负责维护 Linux、Moon Bridge、Codex、Telegram 桥接。
```

### 修改职位

```text
/setrole <职位> <职位说明>
```

修改职位说明，并清空该职位 session，让新说明下次生效。

### 添加固定记忆

```text
/fixmem <职位> <固定记忆>
```

例：

```text
/fixmem ops Moon Bridge 端口固定是 38442。
```

### 查看固定记忆

```text
/showmem <职位>
```

显示职位说明、固定记忆和当前 session id。

### 删除固定记忆

```text
/delmem <职位> <编号>
```

例：

```text
/delmem ops 2
```

删除第 2 条固定记忆，并清空该职位 session。

### 清除某职位临时记忆

```text
/clear <职位>
```

例：

```text
/clear ops
```

只删除 `ops/session.txt`，固定记忆保留。

### 清除全部临时记忆

```text
/clear_all
```

删除所有职位的 session，固定记忆保留。

### 给职位派任务

```text
@职位 <任务>
```

例：

```text
@ops 检查 Moon Bridge 是否正常
@运维 检查 Moon Bridge 是否正常
```

如果不写 `@职位`，普通消息会交给 `CEO` Agent。

职位名支持中文、英文、数字、下划线、短横线和点号。中文职位会保存到对应目录，例如：

```text
agents/运维/
```

## 启动方式

Linux 示例：

```bash
cd /home/ubuntu/codex_deepseek
kill "$(cat run/bridge.pid)" 2>/dev/null || true

export CODEX_COMMAND="/home/ubuntu/codex_deepseek/tools/npm-global/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"

mkdir -p logs run
nohup scripts/start_multi_agent_bridge.sh > logs/multi_agent_stdout.log 2> logs/multi_agent_stderr.log &
echo $! > run/bridge.pid

tail -f logs/multi_agent_bridge.log
```
