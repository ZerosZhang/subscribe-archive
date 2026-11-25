# core/runlog.py — 运行日志落盘

## 职责

把一次归档的输出写到 `result/logs/YYYY年MM月DD日.log`，方便事后排查「当时到底报了什么错」
（网页版的日志只在内存里，进程重启就没了；CLI 默认也只打到 stdout）。

## 行为

- 一个日期一个文件，**追加写**：同一天多次执行按执行分段接在后面，每段有开始/结束时间戳
- 每行前缀 `[HH:MM:SS]`，便于对齐时序
- 捕获两类输出：
  1. 流程自己的 `log()` 回调
  2. 底层模块（`render_html` / `summarize` / `save_webpages`）直接 `print()` 的内容
     —— 通过临时替换 `sys.stdout` 实现，`run_archive()` 结束时恢复原样
- 同一行不会写两遍：CLI 下 `log` 就是 `print`（会经过 stdout 的分身），此时改为直接写
  原始流，绕开分身

## 接口

| 函数/类 | 说明 |
|---------|------|
| `RunLog(today)` | 打开 `result/logs/<日期>.log`（追加）；`header(steps)` / `footer(ok)` / `line(msg)` / `close()` |
| `make_logger(user_log, runlog, base_stream)` | 包一层日志回调：先落盘再交给原有出口 |
| `install_stdout_tee(runlog)` / `restore_stdout_tee(original)` | 接管 / 恢复 `sys.stdout` |

## 谁在调用

只有 `archive_core.run_archive()` 的外壳：开文件 → 接管 stdout → 跑主体 `_run_steps()` →
写结束行 → 恢复 stdout。所以 CLI（`archive.py`）与网页版（`webui.py`）**两边都自动有日志文件**，
`reindex_dates()` 不产生日志文件（它不经过 `run_archive`）。

## 注意

- 日志文件不参与 git（`result/` 整个目录都不提交）
- 不会自动清理旧日志；磁盘紧张时按日期删除 `result/logs/` 下的文件即可
