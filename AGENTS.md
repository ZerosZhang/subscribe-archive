# 订阅归档工具 —— AGENTS.md

## 技术栈

- **Python 3.10+**（虚拟环境 `.venv`，依赖见 `requirements.txt`：openai、feedparser）
- **Windows**（脚本内置 UTF-8 编码修复；不依赖 bash / PowerShell，直接调用 `npx.cmd`）
- 界面：桌面小窗口（标准库 `tkinter`，需 Python 安装时保留 tcl/tk）+ 本地网页版（标准库 `http.server`）；无数据库、无 CI/CD

## 部署与测试环境：Windows Server

**发布必须听指令（重要）**：改完代码先在本机调试、自测通过即可，**不要每改一版就发布到服务器**。
只有用户明确说「发布」时才部署；一次改动里用户没提发布，就只交付本地改动并说明尚未发布。
发布指：传文件到 `D:\FoloArchive`、重启服务器上的 `gui.py` / 服务进程、验证线上页面。

本项目**在远程 Windows Server 上部署和测试**，不在本机运行。服务器地址、账号、SSH 别名、系统版本等全部以这份文档为准，不要凭记忆填写：

```
D:\AgentCode\Project\「2026年10月28日」WindowsServer操作\ZerosServer连接与配置.md
```

- **连接方式**：`ssh srv`（已配公钥免密）；传文件用 `scp 文件 srv:C:/路径/`。远程桌面用 `mstsc /v:<服务器IP>`，最多 2 个并发会话
- **服务器部署路径**：`D:\FoloArchive`（含 `.venv`，venv 的 `pyvenv.cfg` 指向 `C:\Program Files\Python314`）
- **Python 基线**：`C:\Program Files\Python314\python.exe`，不在 `C:\Python314`（旧位置已废弃）
- **GUI 启动限制**：SSH 会话里的进程落在 session 0，桌面窗口不可见。要在交互桌面启动需用 `schtasks /create ... /it` 建一次性任务再 `/run`
- **代理**：服务器系统代理为 `127.0.0.1:7890`（mihomo），命令行工具需自行设置 `HTTP_PROXY` / `HTTPS_PROXY`

## 目录结构（关键路径）

```
./                              # 项目根（git 仓库）
├── .venv/                       # 虚拟环境（含 openai）
├── 一键部署.bat                 # 新机器一键部署（检查 Python/tkinter、建 venv、装依赖、自检）
├── 启动控制台.bat                 # 双击启动桌面小窗口（pythonw，无控制台黑框）
├── README.md                    # 公共仓库说明
├── doc/                         # 模块说明文档（与 src/ 结构对应）
├── result/                      # 数据目录（不提交 git）
│   ├── temp_data/               # 文章列表 JSON（按日期命名）
│   │   └── raw/YYYY年MM月DD日/  # 步骤 2 下载的原始 HTML（中间产物，不上传）
│   ├── YYYY年MM月DD日/          # 步骤 3/4 产出（可直接上传 NAS）
│   │   ├── 「来源」标题.html     # 干净 HTML，只放内容（含 AI 摘要区块），样式外链 ../style.css
│   │   ├── YYYY年MM月DD日.html  # 当天汇总索引页（同样外链 ../style.css）
│   │   └── assets/              # 本地化图片
│   └── style.css                # 公共样式表：所有日期、所有页面共用这一份，改一处全体生效
├── .agents/skills/              # 项目级 Skill（自动被发现）
│   ├── SummaryDaily/SKILL.md    # 每日总结 Skill（权威参考）
│   ├── MarkdownFormat/SKILL.md
└── src/                         # 源码
    ├── archive.py               # CLI 入口
    ├── gui.py                   # 桌面小窗口（tkinter，三按钮 + 托盘，见 doc/gui.md）
    ├── trayicon.py              # 系统托盘图标（纯 ctypes，见 doc/trayicon.md）
    ├── webui.py                 # 本地网页版界面 + 服务生命周期（纯标准库，见 doc/webui.md）
    ├── webui_page.py            # 网页版单页 HTML/CSS/JS（归档页 PAGE + 订阅配置页 CONFIG_PAGE）
    ├── scheduler.py             # 常驻定时运行（调 archive.py 子进程，见 doc/scheduler.md）
    ├── archive_core.py          # 核心流程（CLI / Web 共用）
    ├── heatmap.py               # 热力图数据扫描（纯标准库）
    ├── config.json              # API / 定时 / 邮件配置（不提交 git，模板 config.example.json）
    ├── watch_feeds.json         # 订阅检查的订阅列表（source=watch 时使用）
    ├── core/                    # 功能模块
    │   ├── utils.py             # 公共工具 + 路径常量（唯一事实来源）
    │   ├── watch_export.py      # 抓取 RSS/Atom 或站点列表页，判断更新（见 doc/watch_export.md）
    │   ├── save_webpages.py     # 下载原始 HTML 到 temp_data/raw/
    │   ├── render_html.py       # 原始 HTML → 干净 HTML（策略模式 + 图片本地化）
    │   ├── summarize.py         # AI 生成摘要并注入 HTML
    │   └── notify.py            # 失败邮件通知（见 doc/notify.md）
    ├── strategies/              # 正文解析策略（每来源一个文件）
    └── watchers/                # 列表页抓取器框架（可扩展，当前无内置站点）
```

**注意**：所有路径统一以 `src/core/utils.py` 中的常量为准（`PYTHON_ROOT`/`RESULT_DIR`/`TEMP_DIR`/`RAW_DIR`/`CONFIG_PATH`/`OUTPUT_BASE_DIR`），不要在其他模块硬编码路径。

## 常用命令（均使用 .venv）

```bash
# 一键归档（完整流程）
.venv/Scripts/python.exe src/archive.py

# 从指定步骤开始（断点续跑）
.venv/Scripts/python.exe src/archive.py --start-step 4

# 仅执行某一步骤（有效范围 1-4）
.venv/Scripts/python.exe src/archive.py --only-step 3

# 指定日期
.venv/Scripts/python.exe src/archive.py --date "2026年07月07日"

# 列出所有步骤
.venv/Scripts/python.exe src/archive.py --list-steps

# 桌面小窗口（tkinter；双击 启动控制台.bat 走 pythonw，无控制台黑框）
.venv/Scripts/python.exe  src/gui.py                                # 带控制台，便于排查
.venv/Scripts/pythonw.exe src/gui.py --port 9000 --no-schedule

# 托盘图标自测（真实添加一个图标，3 秒后自动移除；不依赖 tkinter）
.venv/Scripts/python.exe src/trayicon.py

# 网页版界面（纯标准库，无第三方依赖；日常通过 启动控制台.bat 启动）
.venv/Scripts/python.exe src/webui.py
.venv/Scripts/python.exe src/webui.py --host 0.0.0.0 --port 8765   # 允许局域网访问
.venv/Scripts/python.exe src/webui.py --no-browser                  # 不自动打开浏览器

# 常驻定时运行（不用计划任务；在项目目录下直接运行，结束进程即停止）
.venv/Scripts/python.exe src/scheduler.py            # 用 config.json 的 schedule 段
.venv/Scripts/python.exe src/scheduler.py --time 08:00
.venv/Scripts/python.exe src/scheduler.py --tail     # 只回显最近日志后退出

# 渲染原始 HTML 为成品 HTML（当天批量；或指定单个 HTML 文件）
.venv/Scripts/python.exe src/core/render_html.py
.venv/Scripts/python.exe src/core/render_html.py "result/temp_data/raw/2026年07月07日/「少数派」标题.html"

# AI 摘要（需 config.json；可附日期与处理篇数上限；已有摘要默认跳过，--force 全部重算）
.venv/Scripts/python.exe src/core/summarize.py 2026年07月07日
.venv/Scripts/python.exe src/core/summarize.py --force 2026年07月07日

# 单独检查订阅更新（watch 来源；首轮只记基线，不当更新）
.venv/Scripts/python.exe src/core/watch_export.py

# 归档进展热力图（自测扫描口径；需把 core/ 加入模块路径才能找到 utils）
PYTHONPATH="src/core;src" .venv/Scripts/python.exe src/heatmap.py

# 失败邮件配置自测（只打印配置与正文样例，不发信）
.venv/Scripts/python.exe src/core/notify.py

# 服务器无界面的归档（直接运行 CLI；需无人值守时用任务计划程序调用）
.venv/Scripts/python.exe src/archive.py
```

## 归档步骤（archive_core.py）

| 编号 | 名称 | 说明 |
|------|------|------|
| 1 | fetch | 抓取 `src/watch_feeds.json` 的 RSS/Atom，按 guid 去重后产出新条目。**当天 `result/temp_data/「日期」.json` 已存在则跳过抓取，直接复用**（不发网络请求、不标记已读）；要强制重抓需删掉该 JSON 或用 `--date` 指定别的日期 |
| 2 | download | 下载原始 HTML 到 `result/temp_data/raw/<日期>/` 并优化文件名。**以 `overwrite=True` 调用，重跑时覆盖旧文件** |
| 3 | convert | 策略识别 + 清洗，渲染为干净 HTML（图片本地化到 `assets/`）。对 raw 目录逐个重渲染，本就覆盖写 |
| 4 | summarize | AI 生成文章摘要并注入 HTML，生成当日索引页。**断点续跑：已有摘要的文章跳过（不调 API，直接复用），只补没摘要的那几篇**；`_summarize_step(..., force=True)` 才全部重算。索引页**以 `temp_data/「日期」.json` 的条目为准**（JSON 多少条就列多少条）；下载/渲染/摘要失败的条目在页内标注（无成品 HTML 时标题直链原文 URL） |

**同一天重跑**：复用列表（步骤 1 跳过）→ 重下载覆盖（步骤 2）→ 重渲染覆盖（步骤 3）→ 摘要**跳过已成功的、只补失败的** + 重建索引页（步骤 4，日志里 `·` 表示跳过、`✓` 表示新生成）。

`run_archive(selected_steps, today, log, on_progress=None, should_stop=None)` 通过回调解耦界面：
- CLI（archive.py）传 `log=print`
- 网页版界面（webui.py）传 `log=LOG.append`，并注入进度与停止回调
- 返回值 dict 含 `article_list`/`download`/`conversion`/`summary_result`/`step_times`/`error`/`failures`；`failures` 为字符串列表，**只汇总系统性/流程级失败**（步骤 1 抓取或列表加载失败、流程 error、索引页写入失败）供失败邮件判定；步骤 2/3/4 的逐条内容失败只进日志与索引页标注，**不再发邮件**
- 修改流程逻辑只需改 `archive_core.py`，两入口同步生效

## 核心脚本行为要点

### src/core/utils.py
- 路径常量：`OUTPUT_BASE_DIR = result/`（成品输出）、`TEMP_DIR = result/temp_data`、`RAW_DIR = result/temp_data/raw`（原始 HTML 中间产物）、`CONFIG_PATH = src/config.json`
- `fix_encoding()`：UTF-8 包装 stdout/stderr（已 UTF-8 跳过、无控制台时 None 跳过）
- `load_config()`：加载 API 配置，缺失/字段无效 `sys.exit(1)`
- `get_system_proxy()`：取环境变量，取不到则读 Windows 注册表系统代理，无则返回 `None`
- `find_npx()`：定位 `npx.cmd`（PATH 优先，兜底 `C:\Program Files\nodejs\npx.cmd`）
- `build_node_env()`：在 `os.environ` 基础上注入 `HTTP(S)_PROXY` + `NODE_USE_ENV_PROXY=1`
- 字节码缓存：`sys.pycache_prefix` 指向 `.venv/pycache`，源码目录不产生 `__pycache__`

### core/save_webpages.py
- 所有来源统一用 `urllib.request` 下载原始 HTML 到 `result/temp_data/raw/<日期>/`，由步骤 3 渲染
- 下载失败记录到 `failed_urls` 并返回干净原因（无 HTML 注释/换行），不中断流程
- `download_articles(..., overwrite=False)` 默认不覆盖已存在文件，CLI 用 `--overwrite` 强制覆盖；**归档管线（`archive_core._download_step`）固定传 `overwrite=True`**
- `_NO_PROXY_SITES`（如 `meta.appinn.net`）绕过系统代理直连；`_PLAIN_UA_SITES`（如 `mobius.blog`）改用普通客户端 UA

### core/render_html.py
- 策略模式：策略位于 `src/strategies/` 包，`@register_strategy` 装饰器注册
- **识别顺序很重要**——第一个匹配的策略被使用（碎言必须在少数派之前）；`strategies/__init__.py` 中的导入顺序即注册顺序
- 优先通过文件名识别（`「来源」标题`），其次 HTML 内容（域名 + 结构标记）
- 少数派要求 `sspai.com` + `article-body` 双重匹配，避免误判
- 清洗正文（剥离 `<script>/<style>/<iframe>`、`on*` 属性、`javascript:` 链接），套响应式模板，并把 `<img src>`（含懒加载属性）本地化到同级 `assets/`
- **HTML 与 CSS 分离**：`render_document()` 只输出内容 + `<link rel="stylesheet" href="../style.css">`（`STYLE_HREF`），没有内联 `<style>`；`BASE_CSS` 由 `write_style_sheet(page_dir)` 落到 `page_dir` 的**上一级**（数据根目录 `result/style.css`，内容一致时跳过写入、不动 mtime）。所有日期、所有页面共用这一份，改一处全体生效；代价是单独拷一个日期目录到 NAS 会掉样式（要连 `result/style.css` 一起带）
- 新增来源：在 `src/strategies/` 新建文件 + `__init__.py` 按顺序导入
- `resolve_strategy_for_feed(url, name)`：配置页用的近似判断（拿不到文章 HTML），先按名称提示、再按 `strategy_domains()` 从 `detect()` 源码里提取的域名匹配；`strategy_domains()` 只服务展示，不参与真实转换

### core/summarize.py
- `process_article(client, model, html_file, date, force=False)` **默认断点续跑**：先看 `data-folo="summary"` 区块里有没有非空文本，有就直接复用、不调 API（返回带 `skipped=True`）；`force=True` 才重新生成。已有摘要时 `write_summary_to_html` 先清旧内容再写；失败仍返回 `success=False` 与错误原因
- 客户端 `timeout=60.0` + `max_retries=0`（单条请求最多阻塞 60 秒，重试自己管）；重试最多 3 次，可重试错误（网络中断/超时 + 408/409/425/429/5xx）按 `RETRY_BACKOFF * 2^n` 等 2s → 4s 重试，401/400 等立即返回；每次重试打印 `↻ 文件名: 原因，Ns 后重试`
- **关闭模型思考**：请求带常量 `THINKING_BODY = {"thinking": {"type": "disabled"}}`。该模型默认先思考，摘要用不上——实测 1.7k 字文章关闭后 token 1626 → 216、9.5s → 2.6s，摘要质量不变（`reasoning_effort="minimal"` 无效）
- 并发 `MAX_WORKERS=10` + 文件锁；不生成索引页（索引页由 `archive_core._write_index_page` 生成，以 `temp_data/「日期」.json` 条目为准，摘要失败的条目在页内标注）

### gui.py（桌面小窗口，见 doc/gui.md）
- 只有两个按钮的 `tkinter` 窗口：**打开 web 页面 / 退出服务**；**不展示日志**（日志与进度都在网页版里看）；归档只从网页版触发
- **服务跑在本进程内**：调 `webui.start_service()` 建服务，再 `Service.serve_in_background()` 在后台线程 serve；因此按钮直接调 `webui.start_run()` / `state_payload()`，无子进程、无 IPC
- **关闭窗口 ≠ 退出**：X / Esc 走 `hide_to_tray()`（`root.withdraw()` + 气泡提示），服务与内建定时照常后台跑；真正退出走「退出服务」按钮或托盘右键「退出」，两条路都到 `exit_service()`
- `exit_service()` 先查 `state_payload()["running"]`，归档进行中弹确认框；确认后 `tray.stop()` → `Service.stop()` → `root.destroy()`
- **托盘回调跨线程**：托盘线程只 `self._tray_commands.put(command)`，界面线程用 `root.after(120, self._poll_tray)` 轮询消费；窗口隐藏时所有操作结果额外弹气泡反馈
- 托盘不可用时（`TrayIcon` 为 None / `start()` 抛错）状态行标红，且 `hide_to_tray()` 改为弹提示而不是隐藏窗口——否则用户既看不到窗口也没有托盘入口
- 服务起不来（`OSError`）只弹错误框 + 状态行标红，不崩；`None` 服务下按钮只提示不动作
- 缺 `tkinter` 时用 `ctypes` 调 `user32.MessageBoxW` 说明修复方法（pythonw 无控制台）；`启动控制台.bat` 也先做一次 `import tkinter` 检查
- 用 `pythonw.exe` 启动（`启动控制台.bat` 里 `start "" pythonw.exe src\gui.py`），不残留控制台窗口

### trayicon.py（系统托盘图标，纯 ctypes，见 doc/trayicon.md）
- `TrayIcon(tooltip, menu, on_command, on_activate=None, icon_path=None).start()` / `.stop()` / `.notify(title, text)`；`AVAILABLE` 表示当前平台是否支持（非 Windows 为 False）
- **独立托盘线程 + 自己的消息循环**（`GetMessageW`/`DispatchMessageW`），不借用 tkinter 的消息泵；也正因如此本模块不 import tkinter，可单独自测（`python src/trayicon.py` 弹 3 秒图标）
- 回调发生在**托盘线程**，调用方自己搬回界面线程（gui.py 用 queue + `root.after` 轮询）
- 坑位提醒：`WNDPROC` 必须被实例长期持有（否则 GC 后回调野指针崩溃）；`NOTIFYICONDATAW` 字段顺序必须与 `winshellapi.h` 一致（错了 Shell 静默失败），x64 上 976 字节；`TrackPopupMenu` 前必须 `SetForegroundWindow`，并用 `TPM_RETURNCMD` 取回选中项；`RegisterClassW` 返回 0 且 `GetLastError()==1410`（类已存在）不算失败
- 气泡提示走 `notify()` → `PostMessage(WM_APP+2)` → 托盘线程里 `NIM_MODIFY | NIF_INFO`，不跨线程直接调 Shell API

### webui.py（网页版界面 + 服务生命周期，纯标准库，见 doc/webui.md）
- `ThreadingHTTPServer` + 单页界面，**零第三方依赖**（Windows Server 2016 也能跑）；可独立运行，也可被 `gui.py` 嵌进同进程
- **服务生命周期**归 `webui`：`Service`（`serve_in_background()` / `serve_forever()` / `stop()`）与 `start_service(host, port, schedule, mirror)`（建服务 + 接管 stdout/stderr + 启停内建定时，端口占用抛 `OSError`）；`main()` 与 `gui.py` 共用，改动只需改一处。注意 `main()` 里 `mirror=sys.stdout` 必须在调用前求值
- 绑定 `127.0.0.1:8765`（`--host 0.0.0.0` 才允许局域网访问）；启动后自动开浏览器（`--no-browser` 可关）
- `sys.stdout`/`sys.stderr` 重定向到线程安全的 `LogBuffer`（`deque(maxlen=2000)`，支持增量拉取），底层模块的 `print()` 也能进页面日志
- 归档在后台线程跑，同一时间只允许一次；停止经 `should_stop` 在步骤边界生效
- **内建每日定时**（默认开启，`--no-schedule` 关闭）：启动时抢占命名互斥量 `SubscribeArchiveScheduler`，拿到就起 daemon 调度线程、并长期持有句柄；拿不到（外部 `scheduler.py` 在跑）只记日志、不重复调度。调度线程每 20 秒检查一次，满足 `enabled` + 到点 + 当天未跑 + 当天 `result/temp_data/「日期」.json` 不存在才触发；**进程启动时若已过当天的定时点，不补跑**（记 `_SCHED_LAST_RUN_DATE` 跳过，等明天），触发直接调 `start_run([1,2,3,4], 今天)`，成功才记 `_SCHED_LAST_RUN_DATE`
- `/api/schedule` 返回 `{owner, running, enabled, time, note}`；`owner` 为 `webui`/`external`/`disabled`，页面据此在标题下显示一行说明（如「常驻定时：每天 08:00 自动归档（由本进程负责）」）
- **归档日历（月视图）**：`GET /api/heatmap` 用 `heatmap.scan_daily_counts`（纯标准库模块）合并 `result/` 与 `result/归档/` 的篇数，叠加按天已读状态，返回 `{days:{日期:{"count","read"}}, total, recent30, read_days}`；前端渲染成月历（周一~周日七列，日号 + 篇数），三态上色（灰=无归档、绿=未读、蓝=已读），今天描边、未来日期淡化，「‹ 月份 ›」切换与「今天」跳转；单击在新标签页打开当天总览并标记已读，Shift/Alt+单击只切换已读
- **手动执行不再选日期**：页面只提交 `steps`，`start_run()` 的 `date_str` 省略时取当天；CLI 的 `--date` 仍可用
- **已读状态**：按天存 `result/read_state.json`（`{"YYYY年MM月DD日": true}`），`load_read_state()` 容错（缺失/损坏视为全部未读），`set_read_state()` 在锁内原子写入（临时文件 + `os.replace`）；接口 `POST /api/read` body `{"date","read"}` → `{ok, error}`
- **归档静态托管**：`GET /archive/<日期>/<相对路径>` 依次在 `OUTPUT_BASE_DIR` 与 `OUTPUT_BASE_DIR/"归档"` 下按扩展名返回 HTML/图片等（`Cache-Control: no-store`）；`_resolve_archive_file()` 拒绝 NUL/绝对路径/盘符/`..`，再用 `resolve()` + `is_relative_to()` 确认不越界，越界返回 404，只读不列目录
- **热榜页**：`GET /trends` 返回 `TRENDS_PAGE`，`GET /api/trends` 读 `watch_export.list_trend_entries()`，展示 `archive=false` 订阅的最新条目（只看标题、点标题跳原站）
- **执行日志页**：`GET /logs` 返回 `LOGS_PAGE`，整屏日志并每秒增量拉取 `/api/logs`；主页不再内嵌日志，标题右侧改为入口链接
- **上次运行摘要**：`_run_worker` 结束时 `_save_last_run()` 原子写 `result/last_run.json`（`finished_at`/`date`/`articles`/`error`/`failures`/`step_times`），`GET /api/last` 读取（缺失或损坏返回 `{}`）；主页页头第二行展示，运行结束后自动刷新
- **订阅配置页**：`GET /config` 返回 `CONFIG_PAGE`（`webui_page.py` 里的第二个页面常量），列出 `src/watch_feeds.json` 的订阅与检查状态；`GET /api/feeds` 汇总 `watch_export.list_feeds_state()`，`POST /api/feeds` 接受 `{"action":"add|remove","url":...}` 并调用 `watch_export.add_feed()/remove_feed()`（添加前先抓取校验，删除不清理 SQLite 中的历史条目）。`POST /api/discover` 调 `watch_export.discover_feeds()`，从任意网址找 feed（HTML 的 `<link rel="alternate">` 声明 → 常见路径 `/feed`、`/rss` 等，逐个实抓验证）。`feeds_payload()` 把依赖缺失收敛成 `error` 字段，缺 `feedparser` 时页面仍能打开

### src/heatmap.py / src/core/notify.py
- `heatmap.scan_daily_counts(base_dir)` 扫日期目录，按日期统计文章文件数（新 `.html` 与旧 `.md` 都认，索引页与 `assets/` 排除），纯标准库、无任何控件
- `notify.load_mail_config()/send_failure_mail()/format_failure_report()` 从 `config.json` 的 `mail` 段发失败邮件，容错设计（未配置/发信失败都不影响主流程）

## 定时归档方式（两种）

两种方式按需选一种；判据一致，都按「当天 `result/temp_data/「日期」.json` 是否存在」
判断当天是否已跑过，同一天只触发一次。推荐顺序如下：

1. **桌面小窗口（推荐）**：双击 `启动控制台.bat`（等价 `pythonw src/gui.py`），
   窗口里的服务就是网页版那一套，进程内自带调度线程，**一个进程同时提供界面与定时**；
   **关闭窗口只是收进系统托盘，定时照常跑**，要从托盘右键「退出」（或点「退出服务」）才停止。
2. **网页版内建定时**：跑 `python src/webui.py`，同样自带调度线程，
   但会留一个控制台窗口。桌面小窗口与它用的是同一份 `webui.start_service()`。
   任一方加 `--no-schedule` 都可关闭内建定时。
3. **常驻进程（无界面）**：在项目目录下直接运行 `python src/scheduler.py`，进程内自己盯时间；
   结束进程即停止（`Ctrl+C` 或任务管理器结束 `python.exe`）。
   **机器重启后需手动重新启动**。详见 `doc/scheduler.md`

**互斥关系**：内建定时（无论来自桌面小窗口还是 `python src/webui.py`）与 `scheduler.py`
抢同一个命名互斥量 `SubscribeArchiveScheduler`——谁先起谁负责，另一个启动时检测到互斥量被占用
就不会重复调度。想同时开界面又用 `scheduler.py`，请给对方加 `--no-schedule`。

也可自行用任务计划程序调用 `src/archive.py`（真正无人值守、不依赖网页版常驻）：
程序填 `.venv\Scripts\python.exe`、参数填 `src\archive.py`、起始位置填项目目录。

Windows Server 无界面场景直接跑 CLI：

```bash
# 立即执行一次完整归档
.venv/Scripts/python.exe src/archive.py
```

- 日志默认输出到 stdout，**不会**自动写入 `result\archive.log`；需要留存请自行重定向
- 计划任务以运行时的当前账户启动，因此能读到该账户的配置与状态库
- 服务器上**只需** `.venv\Scripts\pip install openai`（CLI 与网页版都不需要界面库；桌面小窗口需要 tkinter）
- 新机器部署：双击 `一键部署.bat`（检查 Python/tkinter → 建/修复 venv → 装 openai → 自检 → 可选启动桌面窗口）
- 失败邮件由 `archive.py` 直接发送（`notify_failures()`）

## 依赖

| 依赖 | 用途 | 安装位置 |
|------|------|---------|
| openai | summarize.py | .venv |
| feedparser | watch_export.py 解析 RSS/Atom | .venv |
| tkinter | gui.py 桌面小窗口 | Python 标准库，但**需安装 Python 时勾选 tcl/tk**（缺了窗口起不来，网页版不受影响） |
| 其他所有 | 核心流程 / 网页版界面 | Python 标准库 |

首次部署：
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

`config.json` 格式（模板 `src/config.example.json`；`schedule`/`mail` 均为可选项）：
```json
{
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-flash",
  "source": "watch",
  "schedule": { "enabled": true, "time": "08:00" },
  "mail": {
    "enabled": false,
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "use_ssl": true,
    "username": "you@example.com",
    "password": "邮箱授权码",
    "from": "you@example.com",
    "to": ["you@example.com"]
  }
}
```

## 编码约定

- 所有 `.py` 顶部 `from utils import fix_encoding; fix_encoding()`（`archive.py` 必须在导入其他模块之前执行；无控制台环境会自动跳过）
- 文件读写统一 `encoding="utf-8"`
- 路径处理用 `pathlib.Path`，路径常量一律来自 `utils.py`
- 注释和文档字符串用中文
- 文件名格式 `「来源」标题.html`，非法字符自动去除，同名自动追加 `_1`

## SummaryDaily Skill（重要规则）

每日汇总现已由管线自动生成：步骤 4 在 `result/<日期>/` 下产出 HTML 索引页 `YYYY年MM月DD日.html`（按来源分组，每篇给出链接与摘要；摘要按 AI 原文分行渲染，概括 / 背景 / 观点 各占一行，不压成一整段）。索引页**以 `result/temp_data/「日期」.json` 的条目为准**（JSON 多少条就列多少条），下载/渲染/摘要失败的条目在页内就地标注，没有成品 HTML 时标题直链原文 URL。需要人工重做或修正时，遵循 `.agents/skills/SummaryDaily/SKILL.md`。核心约束：

1. **不创建新脚本**——项目脚本已完备
2. **逐篇阅读全文**——不跳过，不截断，不依赖之前的读取结果
3. **链接指向实际文件名**——`<a href="./「来源」标题.html" target="_blank" rel="noopener noreferrer">显示标题</a>`，文件名含来源前缀并做 URL 编码；文章链接一律新标签页打开，避免从总览页跳转时覆盖当前页面。**没有本地成品 HTML 的条目改链 JSON 的 `url`（原文网页）**
4. **空文件保留元信息**——标题、来源、原文链接、发布时间，正文标记「⚠️ 无法提取文章内容。」
5. **失败条目必须保留在页内**——转换失败（无成品 HTML）或 AI 摘要失败的条目不得从索引页消失，需就地标注（`digest-failed` / `digest-warn`），条目数与 JSON 保持一致
6. 索引页文件名为日期目录下的 `YYYY年MM月DD日.html`，排除同名索引避免自引用；不再使用 Obsidian wikilink / callout
