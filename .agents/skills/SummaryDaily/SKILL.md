# 每日文档总结 Skill

## 描述

本 Skill 用于为指定日期的归档文件夹生成当日**汇总索引页**（HTML）。归档管线本身已由步骤 4 自动生成索引页 `YYYY年MM月DD日.html`，本 Skill 用于人工重做或修正该索引页。

**触发条件**：用户说「总结今日文档」「生成今日汇总」「汇总今天的文章」「总结某天的文档」等类似表达时生效。

---

## 执行步骤

### 1. 确定目标文件夹

- 若用户说「今日」「今天」，取当前日期，格式为 `YYYY年MM月DD日`（如 `2026年05月26日`）。
- 若用户指定具体日期，按 `YYYY年MM月DD日` 格式拼接。
- 文件夹位于 `result/` 下。

### 2. 确定文章清单

- **以 `result/temp_data/「{日期}」.json` 为准**：JSON 里有多少条，索引页就列多少条，一条都不能少。
- 每条 JSON 记录对应的成品文件名为 `「{sanitize_filename(feed_title)}」{sanitize_filename(title)}.html`（与步骤 2 的命名规则一致）。
- 扫描目标文件夹内的 `*.html` 作为补充：**排除**与文件夹同名的索引页（如 `2026年05月26日.html`），忽略 `assets/` 等子目录。
- 记录每篇文章的**文件名/来源/标题/原文 URL**，并判定三种状态：
  - `ok`：成品 HTML 与摘要都齐全
  - `summary-failed`：有成品 HTML，但没有摘要
  - `missing`：JSON 里有、但目录里没有对应成品 HTML（下载或转换失败）

### 3. 逐篇阅读与总结

**必须一篇一篇地读取并总结。** 即使文件夹内有数十篇文章，也应逐篇完整阅读，不得跳过、不得仅读取开头段落、不得批量粗略处理。

对每篇文章执行以下操作：

1. **全文阅读**：读取整篇文章的 HTML 正文内容。
2. **理解核心**：把握文章主旨、核心观点、关键论据和结论。
3. **撰写摘要**：用 **1-3 句概括性文字** 写出文章的核心内容。

摘要撰写要求：

- **必须是概括性文字**，不是原文摘录或复制粘贴。
- 突出文章**最有价值的信息**（观点、数据、结论、洞察）。
- 语言简洁，避免冗余，单篇摘要控制在 80-200 字。
- 技术类文章说明其解决的问题或带来的价值；观点类文章提炼其核心论点。

### 4. 分组与排序

- 按**来源名称**分组。
- 各组按文章数量降序排列（数量多的来源在前），来源使用中文序号「一、二、三…」。

### 5. 生成索引页

索引页命名为 `YYYY年MM月DD日.html`，与日期文件夹同名，保存于该文件夹内。结构（与 `archive_core._write_index_page` 保持一致）：

```html
<header class="article-header">
  <h1 class="article-title">{日期} 归档</h1>
  <div class="article-meta"><span class="index-intro">本日共收录 {total} 篇文章，按来源分类整理。其中 {missing} 篇未能生成本地归档，已在页内标注并链接原文。</span></div>
</header>

<h2 class="index-source">{中文序号}、{来源名称}（{篇数} 篇）</h2>
<ul class="index-list">
  <!-- ok -->
  <li class="index-item"><a href="./{URL编码文件名}.html" target="_blank" rel="noopener noreferrer">{显示标题}</a>
    <div class="digest">{一句摘要}</div></li>
  <!-- summary-failed：有成品但没摘要 -->
  <li class="index-item"><a href="./{URL编码文件名}.html" target="_blank" rel="noopener noreferrer">{显示标题}</a>
    <div class="digest digest-warn">⚠️ AI 摘要生成失败：{原因}</div>
    <div class="digest">原文：<a href="{原文 URL}" target="_blank" rel="noopener noreferrer">{原文 URL}</a></div></li>
  <!-- missing：没有成品 HTML，标题直链原文 -->
  <li class="index-item"><a href="{原文 URL}" target="_blank" rel="noopener noreferrer">{显示标题}</a>
    <div class="digest digest-failed">⚠️ {失败原因}，点击标题跳转原文</div></li>
</ul>
```

格式约束：

- 链接使用相对路径 `<a href="./{文件名}.html" target="_blank" rel="noopener noreferrer">`，文件名含来源前缀，并对文件名做 **URL 编码**（`urllib.parse.quote`，与渲染模块一致）。
- 文章链接一律带 `target="_blank"`（配合 `rel="noopener noreferrer"`）**在新标签页打开**，避免从总览页跳转时覆盖掉当前页面。
- 显示标题为去掉来源前缀的标题；摘要中的换行折叠为空格；标题、名称、摘要均需 HTML 转义。
- **条目数必须与 `temp_data/「{日期}」.json` 一致**：转换失败或摘要失败的条目不得省略，就地标注即可。
- **没有成品 HTML 的条目**（JSON 里有、目录里没有对应文件）标题直接链接 JSON 里的 `url` 原文网页，配 `digest-failed` 说明。
- **有成品 HTML 但摘要失败的条目**仍链本地文件，配 `digest-warn` 说明，并附一行原文链接。
- **HTML 只放内容，样式全在数据根目录的 `result/style.css`**：索引页 `<head>` 里只有
  `<link rel="stylesheet" href="../style.css">`，**不要写内联 `<style>` 块**；
  所有日期、所有页面共用这一份样式表（`render_html.BASE_CSS` / `write_style_sheet()`），
  改这一个文件全部页面立刻生效。
- **不再使用** Obsidian wiki 链接 `[[...]]`，也**不再使用** callout（`> [!abstract]`）——归档产物是干净 HTML。
- 中文序号使用「一、二、三…」。

---

## 重要规则（从错误中总结）

### 规则1：不要创建任何新脚本

- 本工作流已完备，不需要创建任何新的 Python 脚本
- 如需修复问题，应手动读取文章并更新索引页，而非编写自动化脚本

### 规则2：不要使用正则匹配修复

- 修复索引页时，应直接读取文章内容并撰写摘要
- 不要尝试用正则表达式批量匹配和替换

### 规则3：逐篇确认内容存在

- 生成索引页前，必须逐篇读取文章确认内容存在
- 对于内容为空或只有元信息的文章，才标记为「无法提取完整内容」
- 不要依赖之前的读取结果，每次都要重新确认

### 规则4：链接必须指向实际文件名

- 使用 `<a href="./完整文件名.html" target="_blank" rel="noopener noreferrer">` 格式（在新标签页打开）
- 完整文件名包含来源前缀，如 `「少数派」文章标题.html`
- 显示标题是去掉来源前缀的简短标题

### 规则5：空文件必须保留元信息

- 当 HTML 下载失败时，生成的 HTML 文件仍需包含：
  - 标题（从 JSON 或文件名获取）
  - 来源（从 JSON 获取）
  - 原文链接（从 JSON 获取）
  - 发布时间（从 JSON 获取）
- 只有正文部分显示「⚠️ 无法提取文章内容。」

### 规则6：失败条目不得从索引页消失

- 索引页的条目以 `result/temp_data/「{日期}」.json` 为准，**JSON 有多少条就列多少条**。
- 转换失败（没有成品 HTML）或 AI 摘要失败的条目，不省略、不静默丢弃，直接在页内标注：
  - 无成品 HTML → `digest-failed`，标题直链 JSON 中的原文 URL
  - 摘要有缺失 → `digest-warn`，仍链本地文件并附原文链接
- 页首 `index-intro` 补一句「其中 N 篇未能生成本地归档，已在页内标注并链接原文。」（N=0 时省略）。

---

## 示例

用户：「总结今日文档」

Agent 行为：

1. 确定今日为 `2026年05月26日`。
2. 扫描 `result/2026年05月26日/`，得到文章列表及来源分布。
3. 逐篇读取全文，理解后撰写摘要。
4. 生成 `result/2026年05月26日/2026年05月26日.html` 索引页。
5. 向用户汇报：总篇数、来源分布、已生成的索引页路径。
