# Docker 化 + 飞牛 NAS 定时部署方案

> 目标：把项目打包成一个无人值守的 Docker 容器，在飞牛 NAS 上每天定时跑一次完整归档（fetch → download → convert → summarize）。
>
> 状态：**方案待确认**，确认后再落地代码。

---

## 1. 可行性结论

**容易。** 核心代码只用标准库 + `openai` + `feedparser`，没有 Node 依赖，Linux 容器下可直接运行。

| 检查项 | 位置 | 容器（Linux）下的行为 |
|--------|------|----------------------|
| 终端编码修复 | `src/core/utils.py` 的 `fix_encoding()` | 仅 `win32` 下包装，否则 `reconfigure(line_buffering=True)` |
| 路径 | 全部 | `pathlib` + `utils.py` 常量（相对项目根，可整体搬到 `/app`） |
| 定时相关 | `src/scheduler.py` | 用 Windows 命名互斥量做互斥，容器内改用 cron 即可，无需该模块 |
| 代理 | 订阅抓取 / 网页下载 | 读 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量 |

真正需要处理的只有 3 件事：**订阅列表**、**DeepSeek 配置**、**代理**。

---

## 2. 目标架构

```
飞牛 NAS
└── Docker 容器（常驻，内置 cron）
    ├── 每天 HH:MM 触发
    │     └── python /app/src/archive.py
    ├── openai + feedparser
    └── 挂载卷
          ├── /app/result                ← 宿主机共享目录，归档产物（HTML + assets）
          ├── /app/src/config.json       ← DeepSeek API 配置（只读）
          ├── /app/src/watch_feeds.json  ← 订阅列表（可写，便于网页端增删）
          └── 环境变量 HTTP(S)_PROXY     ← 可选代理（海外源需要）
```

数据流不变，只是执行位置从 Windows 桌面挪到 NAS 容器。

---

## 3. 新增文件清单

全部放在 git 仓库根：

```
.
├── Dockerfile                      # 镜像定义
├── docker-compose.yml              # 飞牛上直接用这个部署
├── .dockerignore                   # 排除 .venv/result/__pycache__
├── docker/
│   ├── entrypoint.sh               # 写 crontab + 启动 cron
│   └── crontab                     # 定时规则模板
└── doc/docker部署方案.md            # 本文档
```

---

## 4. Dockerfile 设计

```dockerfile
FROM python:3.12-slim-bookworm

# 时区 + cron（容器内定时必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Python 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app
COPY . /app/

RUN chmod +x /app/docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
```

要点：

- **时区**：不设 `TZ` 容器默认 UTC，cron 会在差 8 小时的时间点跑，这是最常见的坑。
- **无 Node**：订阅抓取由 `feedparser` 完成，不需要 Node 运行时，镜像可以小很多。

`.dockerignore`：

```
.venv/
result/
__pycache__/
*.pyc
.git/
doc/
```

---

## 5. 定时（容器内 cron）

`docker/crontab`：

```
# 分 时 日 月 周  命令
  0  8  *  *  *  cd /app && /usr/local/bin/python src/archive.py >> /app/result/archive.log 2>&1
```

`docker/entrypoint.sh`：

```bash
#!/bin/sh
set -e
printenv | grep -E '^(HTTP_PROXY|HTTPS_PROXY|http_proxy|https_proxy|TZ)=' > /etc/environment || true
crontab /app/docker/crontab
exec cron -f
```

---

## 6. docker-compose.yml（飞牛上使用）

```yaml
services:
  subscribe-archive:
    build: .
    container_name: subscribe-archive
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
      - HTTP_PROXY=${HTTP_PROXY:-}
      - HTTPS_PROXY=${HTTPS_PROXY:-}
    volumes:
      - /vol1/1000/订阅归档/result:/app/result
      - /vol1/1000/订阅归档/config.json:/app/src/config.json:ro
      - /vol1/1000/订阅归档/watch_feeds.json:/app/src/watch_feeds.json
```

宿主机目录里放三样东西：`config.json`（DeepSeek 配置）、`watch_feeds.json`（订阅列表）、`result/`（归档产物目录）。

---

## 7. 首次运行与验证

```bash
# 手动跑一次完整归档
docker exec -it subscribe-archive python /app/src/archive.py

# 只看订阅检查（步骤 1）
docker exec -it subscribe-archive python /app/src/core/watch_export.py

# 网页版（可选，需额外映射端口 8765 并加 --host 0.0.0.0）
docker exec -it subscribe-archive python /app/src/webui.py --host 0.0.0.0
```

验证点：

1. 步骤 1 输出「首次检查，记录 N 条为基线」
2. 步骤 2/3 生成 `result/<日期>/` 与 `assets/`
3. 步骤 4 生成摘要与当天索引页

---

## 8. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 步骤 1 报网络错误 | 海外源被墙 / 站点反爬 | 配 `HTTP(S)_PROXY`；或把该源换成 RSSHub 地址 |
| 步骤 4 报 401/400 | DeepSeek Key 无效或余额不足 | 更新 `config.json` 的 `api_key` |
| 时间点不对 | 未设 `TZ` | 容器 `TZ=Asia/Shanghai` |
| 产物权限不对 | 容器 root 写入 | 需要时在 compose 里加 `user: "1000:1000"` |
| 每天重复归档旧文 | 状态库被清空（`result/temp_data/watch.db`） | 保留该文件；删除后首轮会重新记基线 |

**备选方案**：不常驻 cron，改为飞牛计划任务触发 `docker exec subscribe-archive python /app/src/archive.py`。
