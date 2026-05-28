先把配置文件写进去：
mkdir -p /home/ubuntu/codex_deepseek/config

nano /home/ubuntu/codex_deepseek/config/telegram_bot_token.txt
nano /home/ubuntu/codex_deepseek/config/telegram_allowed_users.txt
nano /home/ubuntu/codex_deepseek/config/telegram_proxy.txt
nano /home/ubuntu/codex_deepseek/config/codex_project_dir.txt

# telegram_bot_token.txt
123456789:你的BotToken

# telegram_allowed_users.txt
你的Telegram数字ID

# telegram_proxy.txt
# 没有代理就留空

# codex_project_dir.txt
/home/ubuntu/codex_deepseek

然后再运行一键部署脚本：
cd /home/ubuntu/codex_deepseek/server_linux_agent_update
./install_server_multi_agent_bundle.sh
