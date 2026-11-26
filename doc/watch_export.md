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
- `export_articles(skip_auth_check=False, only_feed=None)`：`only_feed` 只检查一个源（名字或网址），**不覆盖当天的列表文件**——有新增条目就并入已有列表（`_merge_article_list` 按 `entry_id`/`url` 去重），没有就完全不动文件，也不改写 `last_check.json`
- `export_articles()` 返回 `(today, article_list, output_path, failure_reason, feed_results)`：
  `feed_results` 是**每个源的抓取状态**（`name/url/archive/status/new/entries/error`），
  由 `check_feed()` 一并返回；`archive_core` 用它写当日结果并生成索引页表格
- 每次 `export_articles()` 结束都会把本次检查的失败源写入 `result/temp_data/last_check.json`（`{checked_at, failures:[{name,url,error}]}`），网页版据此在首页提示
- 抓取失败/成功都会 `conn.commit()`：失败时 `feeds.last_error`、`fail_count`、`last_check` 会当场落库（旧版本失败分支漏了提交，导致配置页的「连续 N 次」不涨）
- `validate_feeds()`：逐条实抓校验订阅链接（只读，不改 ETag/状态），网页版「订阅配置 → 检测链接」和 `python src/core/watch_export.py --validate` 都调用它
- 订阅项可加 `"archive": false`：仍然检查更新，但不交给后续下载/渲染步骤；每日索引页会把它们编成「十、知乎热榜（仅链接）」这样的分组接在正文分组之后，只有标题和原文链接（`list_trend_entries(date=...)` 取当天抓到的条目，没有则回退最新若干条）。**当天抓取失败的源，索引页直接跳过整个分组**（不再回退显示旧内容），失败原因写进顶部结果表
- **新订阅默认「仅链接」**：`add_feed()` 追加的订阅项一律带 `"archive": false`（常量 `DEFAULT_FEED_ARCHIVE`），只提供标题与链接、不下载原文也不做 AI 摘要；要全文归档的源在 `watch_feeds.json` 里显式写 `"archive": true`。缺这个字段的老订阅沿用 `feed.get("archive", True)` 的旧语义（按归档处理），不受这条默认值影响
- 首次检查某个源时**只记基线、不当作更新**，避免第一次就把历史文章全部归档
- 遇到 openresty WAF 的 JS 挑战页（如零度博客的 `/feed`）自动换通行 Cookie 后重取，见 `doc/waf.md`
- 有专用策略的来源（`resolve_strategy_for_feed()` 命中）会在入库前用策略的 `clean_title()` 去掉标题尾部的站点名，与渲染时同一套规则
- 订阅项可加 `"strategy": "<策略>"` 手工标注实际命中的策略（认模块名 `hexo_blog`、显示名 `Hexo博客`，也认模块名前缀 `hexo`）。它只影响配置页「策略」列的展示与 `clean_title()` 的选取，**不改变真实转换**——转换时仍按页面结构 `detect()` 匹配，写错了不会套错策略，只是显示不准
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

`export_articles(skip_auth_check=False, only_feed=None)` 返回 5 元组 `(today, article_list, output_path, failure_reason, feed_results)`；文章字段结构为 `entry_id`/`title`/`url`/`feed_title`/`published`/`summary`，`feed_results` 见上（每源抓取状态）。
