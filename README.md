## 简介

一个用于M-Team自动签到的脚本，主要是为了防止超40天未登录被删除账号。

## 部署

### 克隆项目

```bash

# 克隆项目
git clone https://github.com/0xBitwild/mteam_auto_check-in.git

# 进入项目目录
cd mteam_auto_check-in

```

### 本地运行

```bash

# 配置虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装配置Playwright
playwright install
playwright install-deps

# 运行
python3 mteam_auto_check-in.py

```

### Docker Compose 部署

```bash

# 修改docker-compose.yml中的环境变量
vi docker-compose.yml

# 启动
docker compose up -d

```

### kubernetes 部署

```bash

# 进入kubernetes-manifests目录
cd kubernetes-manifests

# 修改deployment.yml中的环境变量
vi deployment.yml

# 启动
kubectl apply -f deployment.yml

```
