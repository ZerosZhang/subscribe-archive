# core/watch_export.py — 订阅检查（步骤 1 的可选来源）

## 职责

在本地按订阅列表抓取 RSS/Atom，按 guid 去重，把**新增**条目整理成文章列表，保存为 JSON 到 `result/temp_data/「当天日期」.json`。不依赖任何云端账号。

## 用法

```bash
# 单独检查（只打印结果，会把新文章写进当天的 JSON）
.venv/Scripts/python.exe src/core/watch_export.py

# 走完整归档流程（由 config.json 的 source 决定来源，watch 即本模块）
.venv/Scripts/python.exe src/archive.py --only-step 1
```

## 配置

`src/watch_feeds.json`：

```json
{ "feeds": [ { "name": "少数派", "url": "https://sspai.com/feed" } ] }
```

无需额外开关：归档流程固定走本模块。

## 行为要点

- 状态库 `result/temp_data/watch.db`（SQLite），两张表：`feeds` 存 ETag/Last-Modified/失败状态，`entries` 存已见过的 guid
- 去重键：优先 `id` → `link` → `标题+时间` 的 sha1
- `validate_feeds()`：逐条实抓校验订阅链接（只读，不改 ETag/状态），网页版「订阅配置 → 检测链接」和 `python src/core/watch_export.py --validate` 都调用它
- 订阅项可加 `"archive": false`：仍然检查更新，但不交给后续下载/渲染步骤；每日索引页末尾会追加「热榜（仅链接）」小节，只有标题和原文链接（`list_trend_entries(date=...)` 取当天抓到的条目，没有则回退最新若干条）
- 首次检查某个源时**只记基线、不当作更新**，避免第一次就把历史文章全部归档
- `discover_feeds(url)`：从任意网址找 feed——先试地址本身，再解析网页里
  `<link rel="alternate" type="application/rss+xml|atom+xml">`，最后猜 `/feed`、`/rss` 等常见路径；
  每个候选都会实抓验证，最多返回 6 个；找不到时提示改用 RSSHub
- 支持条件请求：源返回 304 时几乎零流量
- 抓取失败（HTTP 错误、网络错误、非 feed 内容、空 feed）逐个源报告，不中断其他源；有失败时把原因汇总进 `failure_reason`
- `published` 输出为本地时区的 ISO 字符串，供 `render_html.format_datetime` 直接解析
- 没有「标记已读」动作：新条目一旦入库即视为已见，与「抓取后标记已读」语义一致

## 站点列表页抓取器（watchers）

有些站点没有 RSS 时，可以由 `src/watchers/` 下的抓取器直接取列表。框架保留，但目前**没有启用任何站点**（B 站抓取器已移除，B 站订阅改用 RSSHub 路由）。

- 抓取器接口：`detect(url)` 认领地址，`fetch_entries(url)` 返回 `[{guid, title, link, published}]`
- 新增抓取器：在 `src/watchers/` 新建文件，继承 `BaseWatcher`，实现上述两个方法，再到 `__init__.py` 导入

## 输出

`export_articles(skip_auth_check=False)` 返回 4 元组 `(today, article_list, output_path, failure_reason)`，字段结构（`entry_id`/`title`/`url`/`feed_title`/`published`/`summary`）。
