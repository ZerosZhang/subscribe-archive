# core/report.py — 当日结果持久化

## 职责

一个日期一份 `result/temp_data/「日期」result.json`，记录当天每个订阅源走到哪一步、失败在哪。
**索引页只从这里取数**（配合文章列表 JSON 与成品 HTML），因此 `--reindex` 也能还原出与当天一致的页面。

## 文件结构

```json
{
  "version": 1,
  "date": "2026年11月25日",
  "updated_at": "2026-11-25 08:13:50",
  "runs": [
    {"started_at": "2026-11-25 08:00:12", "finished_at": "2026-11-25 08:13:50",
     "steps": [1, 2, 3, 4], "error": ""}
  ],
  "feeds": {
    "V2EX": {
      "url": "https://www.v2ex.com/index.xml",
      "archive": false,
      "fetch":    {"status": "error", "new": 0, "today": 0, "entries": 0,
                   "error": "网络错误：timed out", "checked_at": "..."}
    },
    "博客园": {
      "url": "https://www.cnblogs.com/rss",
      "archive": true,
      "fetch":    {"status": "ok", "new": 6, "today": 26, "entries": 20, "error": ""},
      "download": {"total": 20, "success": 18, "failed": 2, "errors": [...], "updated_at": "..."},
      "render":   {"total": 18, "success": 18, "failed": 0, "errors": [...]},
      "summary":  {"total": 18, "success": 17, "failed": 1, "errors": [...]}
    }
  },
  "notes": {"「博客园」某篇文章.html": "下载失败：HTTP 500"}
}
```

- `fetch.status`：`ok`（有更新，含首次检查）/ `not_modified`（304 或没有新条目）/ `error`（抓取失败）；
  `first_run` 只出现在旧数据里（当时首次检查只记基线）
- `fetch.new`：本次检查新增条数；`fetch.today`：**当天累计新增**（同一天多次检查/补刷累加）。
  表格文案用 `today`——否则当天补刷一次 304 就会把已抓到的成果显示成「无更新」
- `notes`：成品文件名 → 失败原因，与索引页的「就地标注」同口径；某一步重跑成功后会**删掉**对应旧标注
- `runs` 只保留最近 10 次

## 接口

| 函数 | 说明 |
|------|------|
| `load(today)` / `save(today, data)` | 读写（容错：缺失/损坏返回空骨架；原子写） |
| `begin_run(today, steps)` / `finish_run(today, run, error)` | 登记一次执行的起止时间与整体错误 |
| `update_fetch(today, feed_results)` | 步骤 1 写入每源抓取结果 |
| `update_download/render/summary(today, stats, notes, cleared)` | 步骤 2/3/4 写入按源统计与逐条原因；`cleared` 是本次已成功的文件名，用来清旧标注 |
| `notes(today)` | `{文件名: 原因}`，索引页与后续步骤共用 |
| `failed_fetch_urls(today)` | 当天抓取失败的订阅地址集合 |
| `feed_rows(today)` | 索引页表格数据：`[{name, url, kind, label, detail}]`，异常源排前面、未检查的排最后；当天完全没记录时返回 `[]` |
| `summary_counts(today)` | 各类结果的数量（ok/partial/fail/none/unknown） |

## 判定规则（feed_rows）

| `kind` | 触发条件 | 表格文案 |
|--------|----------|----------|
| `fail` | `fetch.status == "error"` | 获取更新失败 |
| `fail` | 有归档任务且所有篇都失败 | 全部失败（0/m） |
| `partial` | 有归档任务且部分篇失败 | 部分成功（n/m） |
| `ok` | 全部成功；仅链接源抓到即算成功 | 全部成功（m）/ 获取成功（m 条链接） |
| `none` | 304 / 没有新条目 | 无更新 |
| `none` | 归档源首次检查（旧数据，只记基线） | 首次检查（N 条基线） |
| `unknown` | 当天没有该源的记录 | 未检查 |

分母 `m` 取「当天累计新增」与最后一道工序总数中较大的那个（补抓/合并进来的文章会推高分母）；
仅链接源成功与否看 `today`（首次检查已经算进 `new`；旧数据里 `first_run` 且 `new=0` 时改看 `entries`）。
逐工序失败数写在「说明」列，例如「下载失败 2 篇、摘要失败 1 篇」。

`feed_rows()` 会把同一来源的两种写法认成一行：步骤 2 的统计键是订阅名（可能含 `|` 等字符），
步骤 3 的是成品文件名前缀（非法字符已清洗），比对时统一过 `sanitize_filename()` 后取同名。

## 与索引页的关系

- `archive_core._write_index_page()` 直接调 `feed_rows()` 画顶部表格，调 `failed_fetch_urls()`
  跳过抓取失败的「仅链接」源（**不再回退显示最近 30 条旧内容**）
- 只有 `feeds` 为空（老日期、从没跑过步骤 1）时不画表格，历史页面保持原样
