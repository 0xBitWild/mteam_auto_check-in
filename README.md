# mteam_auto_check-in

一个用于M-Team自动登录签到的脚本，主要是为了防止“连续40天不登录将被删除账号”。

# 特点

- 使用Playwright模拟浏览器登录；
- 支持LocalStorage保存及复用；
- 使用Schedule执行定时任务；
- 默认每天执行一次任务，执行时间做了随机化处理；
- 支持SMTP/Telegram通知；

# 使用条件

1. Python 3.x
2. 依赖如下Python库：
	- pyotp
	- playwright
	- requests
	- schedule
3. 确认M-Team帐号的2FA验证已修改为“启用密码+动态验证码二级验证”；
4. 确认成功从启用“动态验证码二级验证”的二维码中提取“TOTP Secret”；

# 部署方法

## 直接运行

```bash

# 克隆项目
git clone https://github.com/0xBitwild/mteam_auto_check-in.git

# 进入项目目录
cd mteam_auto_check-in

# 配置虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装配置Playwright
playwright install
playwright install-deps

# 配置环境变量

# M-Team 账号信息
export MTEAM_USERNAME=your_mteam_username
export MTEAM_PASSWORD=your_mteam_password
export MTEAM_TOTP_SECRET=your_mteam_totp_secret  

# SMTP 邮件通知
export SMTP_HOST=your_smtp_host
export SMTP_PORT=your_smtp_port
export SMTP_USERNAME=your_smtp_username
export SMTP_PASSWORD=your_smtp_password

# Telegram 通知
export TELEGRAM_BOT_TOKEN=your_telegram_bot_token
export TELEGRAM_CHAT_ID=your_telegram_chat_id

# 通知类型
export NOTIFY_TYPE=smtp # smtp, telegram, none
export NOTIFY_EMAIL=your_notify_email

# 运行
python3 mteam_auto_check-in.py

```

## Docker Compose 部署

```bash

# 下载docker-compose.yml文件
mkdir mteam_auto_check-in
cd mteam_auto_check-in
wget https://raw.githubusercontent.com/0xBitWild/mteam_auto_check-in/refs/heads/main/docker-compose.yaml

# 修改docker-compose.yml中的环境变量配置
vi docker-compose.yml

# 启动
docker compose up -d

```

## Kubernetes 部署

```bash

# 下载kubernetes manifests文件
mkdir mteam_auto_check-in
cd mteam_auto_check-in
wget https://raw.githubusercontent.com/0xBitWild/mteam_auto_check-in/refs/heads/main/kubernetes-manifests/deployment.yaml

# 修改deployment.yml中的环境变量配置
vi deployment.yml

# 启动
kubectl apply -f deployment.yml

```
