# archive.py — 一键归档 CLI 入口

## 职责

命令行入口，串行执行归档的 4 个步骤，核心逻辑委托给 `archive_core.py`。

| 编号 | 名称 | 说明 |
|------|------|------|
| 1 | fetch | 抓取订阅源的新文章列表（按 guid 去重，无需认证） |
| 2 | download | 下载原始 HTML 并优化文件名 |
| 3 | convert | 渲染为干净 HTML |
| 4 | summarize | AI 摘要与索引页生成 |

## 用法

```bash
# 完整执行（需 .venv 环境）
.venv/Scripts/python.exe src/archive.py

# 从第 4 步开始（断点续跑）
.venv/Scripts/python.exe src/archive.py --start-step 4

# 仅执行第 3 步
.venv/Scripts/python.exe src/archive.py --only-step 3

# 指定日期
.venv/Scripts/python.exe src/archive.py --date "2026年07月07日"

# 列出所有步骤
.venv/Scripts/python.exe src/archive.py --list-steps

# 只刷新某一个订阅源（只发 1 次请求，不改写当天列表，跑完本地重建索引页）
.venv/Scripts/python.exe src/archive.py --only-feed V2EX

# 重建索引页（不联网、不调 AI）
.venv/Scripts/python.exe src/archive.py --reindex "2026年11月25日"

# 强制重下：步骤 2 覆盖已有原始 HTML、步骤 3 重下已有图片
.venv/Scripts/python.exe src/archive.py --refresh --only-step 2
```

## 参数

| 参数 | 说明 |
|------|------|
| `--start-step N` | 从第 N 步开始执行（跳过前面步骤），有效范围 1-4 |
| `--only-step N` | 只执行第 N 步，有效范围 1-4 |
| `--list-steps` | 列出所有步骤及编号 |
| `--date "YYYY年MM月DD日"` | 指定日期（默认今天） |
| `--reindex [日期1,日期2]` | 只重建索引页（不联网、不调 AI），省略日期则重建全部 |
| `--refresh` | 步骤 2 覆盖已有原始 HTML、步骤 3 重下已有图片；默认**只补缺失** |
| `--only-feed 名字` | 只检查这一个源（名字或网址），默认只跑步骤 1，且不改写当天文章列表 |

## 行为

- 当天列表 `result/temp_data/「日期」.json` 已存在时，步骤 1 自动**跳过抓取**并复用该 JSON（避免重复抓取、重复记为已见）；要强制重抓需先删除该文件，或用 `--date` 指定另一个日期（`--only-feed` 是这条规则的唯一例外）
- 步骤 2 默认只补缺失（`overwrite=False`），步骤 3 复用 `assets/` 里已有的图片；`--refresh` 才全部重下。所以「手动重跑」几乎不会产生重复请求
- 跳过步骤 1-2 时，步骤 2 自动从 `result/temp_data/「日期」.json` 加载文章列表
- 步骤 2 无法加载列表时以退出码 1 结束
- **同一天重跑**（再次整轮执行）：复用列表 → 重下载并覆盖原始 HTML → 重渲染 → 重新生成摘要并覆盖（详见 `doc/archive_core.md`）
- 日志通过回调输出到 stdout（网页版界面 `src/webui.py` 复用同一核心）
- **失败邮件**：运行结束后若 `run_archive()` 返回的 `failures` 非空，调用 `core/notify.py` 发送通知邮件；未配置 `config.json` 的 `mail` 段时只打印一行提示，**不影响退出码**。`failures` **只包含系统性/流程级失败**（步骤 1 抓取或列表加载失败、流程 error、索引页写入失败）；下载/渲染/摘要的逐条内容失败只在日志与当日索引页内标注，**不再触发邮件**

## 关键实现

- `main()` 解析参数 → 计算步骤范围 → 调用 `archive_core.run_archive()`
- 步骤范围由 `len(STEPS)` 计算，步骤增删后范围自动跟随
- 日志回调：`lambda message: print(message, flush=True)`
- `notify_failures()`：从返回值取 `failures`，为空直接返回；否则读 `config.json` 的 `mail` 段发信（复用 `core/notify.py`）。内容级失败（下载/渲染/摘要）已不进 `failures`，失败信息在当日索引页 `YYYY年MM月DD日.html` 内就地标注

## 服务器定时运行（无界面）

在无界面的服务器上直接运行 CLI：

```bash
# 立即执行一次完整归档
.venv/Scripts/python.exe src/archive.py
```

若需要真正无人值守、且不依赖网页版内建定时，可在「任务计划程序」里手动新建任务：
程序填 `.venv\Scripts\python.exe`、参数填 `src\archive.py`、起始位置填项目目录，
触发器设为每天固定时刻。

- 只刷新单个源：`python src/archive.py --only-feed V2EX`（只发 1 次请求，不改写当天列表，跑完自动重建索引页）
- 强制重下：`python src/archive.py --refresh --only-step 2`（默认 `overwrite=False`，只补缺失的原始 HTML 与图片）
- 日志默认同时输出到 stdout 与 `result/logs/<日期>.log`（`archive_core.run_archive()` 负责落盘，
  同一天多次执行追加分段，见 `doc/runlog.md`）；需要额外留存时仍可在任务计划程序里自行重定向
  （例如 `cmd /c ".venv\Scripts\python.exe src/archive.py >> result\archive.log 2>&1"`）
- 计划任务以「运行该任务时的账户」启动，因此能读到该用户的配置文件与状态库
- 服务器上**只需** `.venv\Scripts\pip install openai`，CLI 不需要任何界面库
