#!/usr/bin/env python3
"""
归档核心流程模块
统一 CLI（archive.py）与网页版（webui.py）的 4 步执行逻辑：
fetch → download → convert（渲染为干净 HTML）→ summarize（注入摘要 + 生成索引页）

调用方通过回调注入日志、进度和停止检查，自身不依赖任何界面框架。
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote

# 功能模块目录 src/core/（utils、watch_export 等）
sys.path.insert(0, str(Path(__file__).parent / "core"))

from utils import format_duration, TEMP_DIR, RAW_DIR, OUTPUT_BASE_DIR, CONFIG_PATH
from save_webpages import sanitize_filename
import report
import runlog

# 步骤定义：(编号, 名称, 描述)
STEPS = [
    (1, "fetch", "获取文章列表（订阅检查）"),
    (2, "download", "下载网页并优化文件名"),
    (3, "convert", "渲染为 HTML"),
    (4, "summarize", "AI 摘要与索引页生成"),
]


def _load_article_list(today_str):
    """从 TempData 加载之前保存的文章列表"""
    json_path = TEMP_DIR / f"「{today_str}」.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _download_step(article_list, today, log, on_progress=None, overwrite=True):
    """步骤 2：下载网页到原始 HTML 目录并优化文件名

    overwrite=False 时已存在的原始 HTML 直接跳过（重跑只补缺失，不重复抓站点）。
    """
    from save_webpages import download_articles, optimize_titles

    output_dir = RAW_DIR / today
    step_start = time.time()

    def on_download_progress(index, total, article, status, info):
        title = article.get("title", "无标题")[:50]
        if status == "success":
            log(f"[{index}/{total}] {title}... ✓ ({info})")
        elif status == "fail":
            log(f"[{index}/{total}] {title}... ✗ 失败 ({info})")
        elif status == "skip":
            log(f"[{index}/{total}] {title}... - 跳过 ({info})")
        if on_progress:
            on_progress(20 + (index / total) * 30, f"步骤 2: 下载网页 {index}/{total}...")

    # 默认只补缺失：已下载过的原始 HTML 跳过，避免重复抓站点（--refresh 才覆盖重下）
    success, fail, skipped, failed = download_articles(
        article_list, output_dir, on_progress=on_download_progress, overwrite=overwrite
    )

    log("")
    log(f"✓ 下载完成: {success}/{len(article_list)}"
        + (f"（跳过已存在 {skipped} 篇）" if skipped else ""))
    log("正在优化文件名...")
    renamed = optimize_titles(output_dir)
    if renamed > 0:
        log(f"✓ 已优化 {renamed} 个文件名")
    else:
        log("✓ 文件名无需优化")

    step_time = time.time() - step_start
    log(f"  ⏱ 耗时: {format_duration(step_time)}")
    return success, fail, skipped, failed, step_time


def _summary_digest(summary):
    """索引页摘要块：保留 AI 摘要原有的分行（概括 / 背景 / 观点），跳过空行本身"""
    lines = (line.strip() for line in (summary or "").splitlines())
    return "<br>".join(html_escape(line) for line in lines if line)


def _expected_filename(article):
    """按步骤 2 的命名规则推出该文章在成品目录中的文件名

    与 save_webpages.download_articles 的命名保持一致（含标题为空的边界情形）。
    """
    feed = article.get("feed_title", "未知来源")
    title = article.get("title", "无标题")
    return f"「{sanitize_filename(feed)}」{sanitize_filename(title)}.html"


def _normalize_filename(name):
    """去掉同名追加的 _1/_2 后缀，便于宽松匹配"""
    return re.sub(r"_\d+(?=\.html$)", "", name)


def _split_archive_name(name):
    """从成品文件名「来源」标题.html 解析出 (来源, 显示标题)"""
    stem = name.removesuffix(".html")
    m = re.match(r"「(.+?)」(.*)", stem)
    if m:
        return m.group(1), (m.group(2).strip() or "无标题")
    return "其他", stem


def _group_by_source(filenames):
    """把文件名按「来源」前缀分组，返回 {来源: [文件名]}"""
    groups = {}
    for name in filenames:
        source, _ = _split_archive_name(name)
        groups.setdefault(source, []).append(name)
    return groups


def _step_stats(totals, failed, errors=None):
    """按来源汇总某一步的结果：{来源: {total, success, failed, errors}}

    totals: {来源: 篇数}；failed: {来源: [条目]}；errors: {来源: [{"title","reason"}]}
    """
    errors = errors or {}
    stats = {}
    for source, total in totals.items():
        fail_items = failed.get(source, [])
        stats[source] = {
            "total": total,
            "success": max(total - len(fail_items), 0),
            "failed": len(fail_items),
            "errors": errors.get(source, []),
        }
    return stats


def _download_stats(article_list, failed):
    """步骤 2 的按源统计 + 逐条失败标注（供当日结果与索引页使用）"""
    totals = {}
    for article in article_list:
        source = article.get("feed_title") or "未知来源"
        totals[source] = totals.get(source, 0) + 1

    failed_by_source = {}
    errors_by_source = {}
    notes = {}
    for idx, title, url, reason in failed:
        if isinstance(idx, int) and 1 <= idx <= len(article_list):
            article = article_list[idx - 1]
        else:
            article = {"title": title, "url": url}
        source = article.get("feed_title") or "未知来源"
        name = _expected_filename(article)
        failed_by_source.setdefault(source, []).append((idx, title, url, reason))
        errors_by_source.setdefault(source, []).append({
            "title": article.get("title") or title,
            "url": url or article.get("url") or "",
            "reason": reason,
        })
        notes[name] = f"下载失败：{reason}"
    return _step_stats(totals, failed_by_source, errors_by_source), notes


def _render_stats(today, conversion):
    """步骤 3 的按源统计 + 失败标注（以 raw 目录里的文件为总数）"""
    raw_dir = RAW_DIR / today
    raw_names = [p.name for p in sorted(raw_dir.glob("*.html"))] if raw_dir.exists() else []
    totals = {source: len(names) for source, names in _group_by_source(raw_names).items()}

    failed_by_source = {}
    errors_by_source = {}
    notes = {}
    for name, reason in conversion.get("failed", []):
        source = _split_archive_name(name)[0]
        failed_by_source.setdefault(source, []).append((name, reason))
        errors_by_source.setdefault(source, []).append({"file": name, "reason": str(reason)})
        notes[name] = f"渲染失败：{reason}"
    for name, reason in conversion.get("unknown", []):
        source = _split_archive_name(name)[0]
        failed_by_source.setdefault(source, []).append((name, reason))
        errors_by_source.setdefault(source, []).append({"file": name, "reason": str(reason)})
        notes[name] = "渲染失败：未识别来源，缺少解析策略"

    return _step_stats(totals, failed_by_source, errors_by_source), notes


def _summary_stats(html_files, summary_by_file, failure_by_file):
    """步骤 4 的按源统计 + 失败标注"""
    totals = {source: len(names)
              for source, names in _group_by_source([f.name for f in html_files]).items()}
    failed_by_source = {}
    errors_by_source = {}
    notes = {}
    for name, reason in failure_by_file.items():
        source = _split_archive_name(name)[0]
        failed_by_source.setdefault(source, []).append((name, reason))
        errors_by_source.setdefault(source, []).append({"file": name, "reason": str(reason)})
        notes[name] = f"AI 摘要生成失败：{reason}"
    return _step_stats(totals, failed_by_source, errors_by_source), notes


def _index_entry(source, display, filename, url, summary, status, note):
    """构造一个索引条目（字段含义见 _build_index_entries）"""
    return {
        "source": source, "display_title": display, "filename": filename,
        "url": url, "summary": summary, "status": status, "note": note,
    }


def _build_index_entries(today, article_list, summary_by_file, failure_by_file, missing_notes):
    """组装索引页条目：以文章列表 JSON 为准，逐条判定本地归档状态

    每条结构: {source, display_title, filename, url, summary, status, note}
    status:
      - ok              本地 HTML 与 AI 摘要都齐全
      - summary-failed  有本地 HTML，但摘要生成失败（页内标注，仍链本地文件）
      - missing         没有本地 HTML（下载/转换失败），标题直链原文
    """
    folder = OUTPUT_BASE_DIR / today
    index_name = f"{today}.html"
    existing = {}
    if folder.exists():
        for path in sorted(folder.glob("*.html")):
            if path.name != index_name:
                existing[path.name] = path

    existing_by_norm = {}
    for name in existing:
        existing_by_norm.setdefault(_normalize_filename(name), name)

    entries = []
    matched = set()

    for article in article_list:
        expected = _expected_filename(article)
        name = expected if expected in existing else existing_by_norm.get(_normalize_filename(expected))
        if name in matched:
            name = None

        source = article.get("feed_title") or "未知来源"
        display = article.get("title") or "无标题"
        url = article.get("url", "")

        if name:
            matched.add(name)
            result = summary_by_file.get(name)
            if result is not None:
                entries.append(_index_entry(source, display, name, url,
                                            result.get("summary", ""), "ok", ""))
            else:
                error = failure_by_file.get(name) or "未生成摘要"
                entries.append(_index_entry(source, display, name, url, "",
                                            "summary-failed", f"⚠️ AI 摘要生成失败：{error}"))
        else:
            reason = missing_notes.get(expected) or "本地归档未生成（下载或转换失败）"
            entries.append(_index_entry(source, display, None, url, "",
                                        "missing", f"⚠️ {reason}，点击标题跳转原文"))

    # 目录中不在文章列表里的成品文件也一并列出，避免历史数据被漏掉
    for name in sorted(existing):
        if name in matched:
            continue
        source, display = _split_archive_name(name)
        result = summary_by_file.get(name)
        if result is not None:
            entries.append(_index_entry(source, display, name, "", result.get("summary", ""), "ok", ""))
        else:
            error = failure_by_file.get(name) or "未生成摘要"
            entries.append(_index_entry(source, display, name, "", "",
                                        "summary-failed", f"⚠️ AI 摘要生成失败：{error}"))

    return entries


def _build_entries_from_files(html_files, summary_by_file, failure_by_file):
    """回退路径：没有文章列表 JSON 时，按成品文件组装索引条目"""
    entries = []
    for html_file in html_files:
        name = html_file.name
        source, display = _split_archive_name(name)
        result = summary_by_file.get(name)
        if result is not None:
            entries.append(_index_entry(source, display, name, "", result.get("summary", ""), "ok", ""))
        else:
            error = failure_by_file.get(name) or "未生成摘要"
            entries.append(_index_entry(source, display, name, "", "",
                                        "summary-failed", f"⚠️ AI 摘要生成失败：{error}"))
    return entries


def _write_index_page(today, index_path, entries):
    """生成当日 HTML 汇总索引页

    页面结构：顶部「订阅结果」表格 → 按来源分组的文章列表 → 仅链接的热榜；
    右侧是随页面滚动但自身不滚走的悬浮目录（position: sticky）。

    数据来源全部是本地文件（当日结果 JSON + 文章列表 JSON），不联网、不查运行态，
    所以 --reindex 也能生成完全一致的页面。
    """
    from render_html import render_document, write_style_sheet

    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]

    source_groups = {}
    for entry in entries:
        source_groups.setdefault(entry["source"], []).append(entry)

    missing_count = sum(1 for e in entries if e["status"] == "missing")
    intro = f"本日共收录 {len(entries)} 篇文章，按来源分类整理。"
    if missing_count:
        intro += f"其中 {missing_count} 篇未能生成本地归档，已在页内标注并链接原文。"

    feed_rows = report.feed_rows(today)
    failed_urls = report.failed_fetch_urls(today)

    toc_items = []          # (锚点, 显示文本, 计数)
    body = []

    # ---------- 顶部：订阅结果表 ----------
    if feed_rows:
        counts = {}
        for row in feed_rows:
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        summary = "、".join(
            f"{label} {counts.get(kind, 0)}"
            for kind, label in (("ok", "全部成功"), ("partial", "部分成功"),
                                ("none", "无更新"), ("fail", "失败"))
            if counts.get(kind)
        )
        if summary:
            intro += f"订阅源：{summary}。"

    body.append('<header class="article-header">')
    body.append(f'<h1 class="article-title">{html_escape(today)} 归档</h1>')
    body.append(
        '<div class="article-meta">'
        f'<span class="index-intro">{html_escape(intro)}</span>'
        "</div>"
    )
    body.append("</header>")

    if feed_rows:
        body.append('<section class="index-status">')
        body.append('<h2 class="index-section" id="feed-status">订阅结果</h2>')
        body.append('<table class="feed-table">')
        body.append(
            "<thead><tr><th>#</th><th>订阅源</th><th>当天结果</th><th>说明</th></tr></thead>"
        )
        body.append("<tbody>")
        for i, row in enumerate(feed_rows, 1):
            detail = row.get("detail") or ""
            body.append(
                f'<tr><td class="col-no">{i}</td>'
                f'<td class="col-name">{html_escape(row["name"])}</td>'
                f'<td class="col-status st-{row["kind"]}">{html_escape(row["label"])}</td>'
                f'<td class="col-detail">{html_escape(detail)}</td></tr>'
            )
        body.append("</tbody></table>")
        body.append("</section>")
        toc_items.append(("feed-status", "订阅结果", f"{len(feed_rows)} 个源"))

    # ---------- 正文：按来源分组的文章 ----------
    sorted_sources = sorted(source_groups.items(), key=lambda x: len(x[1]), reverse=True)
    for i, (source, articles) in enumerate(sorted_sources):
        num = chinese_nums[i] if i < len(chinese_nums) else str(i + 1)
        anchor = f"src-{i + 1}"
        toc_items.append((anchor, source, f"{len(articles)} 篇"))
        body.append(
            f'<h2 class="index-source" id="{anchor}">{num}、{html_escape(source)}'
            f'（{len(articles)} 篇）</h2>'
        )
        body.append('<ul class="index-list">')
        for entry in articles:
            display = html_escape(entry["display_title"])

            if entry["status"] == "missing":
                if entry.get("url"):
                    anchor_html = (
                        f'<a href="{html_escape(entry["url"], quote=True)}"'
                        f' target="_blank" rel="noopener noreferrer">{display}</a>'
                    )
                else:
                    anchor_html = f"<a>{display}</a>"
                body.append(
                    f'<li class="index-item">{anchor_html}'
                    f'<div class="digest digest-failed">{html_escape(entry["note"])}</div></li>'
                )
                continue

            href = quote(entry["filename"])
            anchor_html = f'<a href="./{href}" target="_blank" rel="noopener noreferrer">{display}</a>'

            if entry["status"] == "summary-failed":
                inner = f'<div class="digest digest-warn">{html_escape(entry["note"])}</div>'
                if entry.get("url"):
                    safe_url = html_escape(entry["url"], quote=True)
                    inner += (
                        '<div class="digest">原文：'
                        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
                        f'{html_escape(entry["url"])}</a></div>'
                    )
            else:
                inner = f'<div class="digest">{_summary_digest(entry.get("summary"))}</div>'

            body.append(f'<li class="index-item">{anchor_html}{inner}</li>')
        body.append("</ul>")

    # ---------- 热榜（archive=false 的订阅）----------
    try:
        from watch_export import list_trend_entries
        trend_feeds = list_trend_entries(date=today)
    except Exception as exc:  # noqa: BLE001 - 热榜失败不影响索引页
        print(f"⚠️  热榜条目读取失败：{exc}")
        trend_feeds = []

    next_index = len(sorted_sources)
    for feed in trend_feeds:
        # 当天没抓到（或抓取失败）的源整段不显示，绝不回退显示旧内容
        if feed.get("url") in failed_urls:
            continue
        if not feed.get("entries"):
            continue
        num = chinese_nums[next_index] if next_index < len(chinese_nums) else str(next_index + 1)
        anchor = f"trend-{next_index + 1}"
        toc_items.append((anchor, feed["name"], f"{len(feed['entries'])} 条"))
        body.append(
            f'<h2 class="index-source" id="{anchor}">{num}、{html_escape(feed["name"])}'
            f'（{len(feed["entries"])} 条 · 仅链接）</h2>'
        )
        body.append('<ul class="index-list">')
        for item in feed["entries"]:
            when = (item.get("published") or "").replace("T", " ")[:16]
            body.append(
                '<li class="index-item">'
                f'<a href="{html_escape(item.get("link") or "", quote=True)}"'
                f' target="_blank" rel="noopener noreferrer">'
                f'{html_escape(item.get("title") or "无标题")}</a>'
                f'<div class="digest">原文：{html_escape(item.get("link") or "")}'
                f'{(" · " + html_escape(when)) if when else ""}</div>'
                '</li>'
            )
        body.append("</ul>")
        next_index += 1

    # ---------- 右侧悬浮目录 ----------
    toc = ['<aside class="index-toc">', '<div class="toc-title">目录</div>', "<ol>"]
    for anchor, text, count in toc_items:
        toc.append(
            f'<li><a href="#{anchor}">{html_escape(text)}</a>'
            f'<span class="toc-count">{html_escape(count)}</span></li>'
        )
    toc.append("</ol>")
    toc.append("</aside>")

    layout = (
        '<div class="index-layout">'
        f'<div class="index-body">{"".join(body)}</div>'
        + "".join(toc)
        + "</div>"
    )

    page = render_document(f"{today} 归档", layout)
    write_style_sheet(index_path.parent)
    index_path.write_text(page, encoding="utf-8")


def _summarize_step(today, log, article_list=None, missing_notes=None, should_stop=None,
                    force=False):
    """步骤 4：AI 生成文章摘要并生成当日索引页

    已有摘要的文章默认跳过（断点续跑，只补没摘要的那几篇）；force=True 时全部重算。
    索引页以文章列表 JSON 为准（JSON 有多少条就列多少条）；转换失败（无本地 HTML）
    与摘要失败的条目在页内标注，缺本地 HTML 的条目标题直链原文。
    """
    from summarize import (load_config, create_client, scan_html_files,
                           extract_source, process_article, MAX_WORKERS)

    missing_notes = {**report.notes(today), **(missing_notes or {})}
    if article_list is None:
        article_list = _load_article_list(today)
        if article_list:
            log(f"📂 从文件加载了 {len(article_list)} 篇文章用于生成索引页")

    folder = OUTPUT_BASE_DIR / today
    if not folder.exists() and not article_list:
        log(f"⚠️  文件夹与文章列表均不存在: {folder}，跳过总结步骤")
        return None

    html_files = scan_html_files(folder, today) if folder.exists() else []

    summary_by_file = {}
    failure_by_file = {}
    failures = []
    processed = 0
    skipped = 0

    try:
        config = load_config()
    except SystemExit:
        config = None
        log("⚠️  未找到 config.json 或配置无效，本次不生成 AI 摘要（索引页仍会生成）")

    if not html_files:
        log("⚠️  没有找到可总结的 .html 文件，索引页将按文章列表生成并标注缺失项")
    elif config is None:
        for html_file in html_files:
            failure_by_file[html_file.name] = "未配置可用的 AI API"
    else:
        client = create_client(config)
        model = config["model"]

        source_files = {}
        for f in html_files:
            source_files.setdefault(extract_source(f.name), []).append(f)

        total_count = len(html_files)
        log(f"找到 {total_count} 篇文章待处理，来源分布:")
        for source, files in sorted(source_files.items(), key=lambda x: len(x[1]), reverse=True):
            log(f"  - {source}: {len(files)} 篇")
        log("")
        log("已有摘要的文章跳过（--force 可全部重算）" if not force else "全部重算（force=True）")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(process_article, client, model, html_file, today, force): html_file
                for html_file in html_files
            }

            for future in as_completed(future_to_file):
                if should_stop and should_stop():
                    executor.shutdown(wait=False)
                    break

                result = future.result()
                if result["success"]:
                    processed += 1
                    summary_by_file[result["filename"]] = result
                    if result.get("skipped"):
                        skipped += 1
                        log(f"  · [跳过] {result['filename']}（已有摘要）")
                    else:
                        log(f"  ✓ [{processed}/{total_count}] {result['filename']}")
                else:
                    failure_by_file[result["filename"]] = result["error"]
                    failures.append((result["filename"], result["error"]))
                    log(f"  ✗ {result['filename']}: {result['error']}")

    # 摘要结果先落盘：索引页（含 --reindex）只从本地文件还原，不依赖本次内存状态
    summary_stats, summary_notes = _summary_stats(html_files, summary_by_file, failure_by_file)
    summary_cleared = [f.name for f in html_files if f.name not in summary_notes]
    missing_notes.update(summary_notes)
    for name in summary_cleared:       # 摘要这次成功了，旧的失败标注要清掉
        missing_notes.pop(name, None)
    report.update_summary(today, summary_stats, summary_notes, summary_cleared)

    if article_list:
        entries = _build_index_entries(today, article_list, summary_by_file,
                                       failure_by_file, missing_notes)
    else:
        log("⚠️  未找到文章列表 JSON，索引页回退为按成品文件生成")
        entries = _build_entries_from_files(html_files, summary_by_file, failure_by_file)

    log("\n正在生成索引页...")
    index_path = folder / f"{today}.html"
    index_error = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _write_index_page(today, index_path, entries)
        log(f"已保存: {index_path}")
        if article_list:
            log(f"索引页共 {len(entries)} 条（文章列表 {len(article_list)} 条）")
    except Exception as exc:  # 索引页失败不掩盖摘要结果
        index_error = f"{type(exc).__name__}: {exc}"
        log(f"✗ 索引页生成失败: {index_error}")

    return {"processed": processed, "skipped": skipped, "failed": len(failures),
            "failures": failures, "path": index_path, "entries": len(entries),
            "index_error": index_error}


def reindex_dates(dates, log):
    """只重建索引页：不联网、不调 AI，用已有文章列表 JSON 与成品 HTML 重新生成

    用于「索引页被旧代码或旧逻辑生成错了，事后补正」的场景——正常归档仍走
    run_archive。返回 [{"date","path","entries","error"}]
    """
    from summarize import read_existing_summary, scan_html_files

    results = []
    for today in dates:
        folder = OUTPUT_BASE_DIR / today
        if not folder.exists():
            log(f"✗ {today}：目录不存在 {folder}")
            results.append({"date": today, "path": None, "entries": 0, "error": "目录不存在"})
            continue

        article_list = _load_article_list(today)
        html_files = scan_html_files(folder, today)
        summary_by_file = {}
        for html_file in html_files:
            text = read_existing_summary(html_file)
            if text:
                summary_by_file[html_file.name] = {"summary": text}

        if article_list:
            entries = _build_index_entries(today, article_list, summary_by_file, {},
                                           report.notes(today))
        else:
            log(f"⚠️  {today}：没有文章列表 JSON，索引页按成品文件生成")
            entries = _build_entries_from_files(html_files, summary_by_file, {})

        index_path = folder / f"{today}.html"
        try:
            _write_index_page(today, index_path, entries)
        except Exception as exc:  # noqa: BLE001 - 单日失败不影响其他日期
            error = f"{type(exc).__name__}: {exc}"
            log(f"✗ {today}：索引页生成失败 — {error}")
            results.append({"date": today, "path": None, "entries": 0, "error": error})
            continue

        log(f"✓ {today}：索引页 {len(entries)} 条 → {index_path}")
        results.append({"date": today, "path": index_path, "entries": len(entries),
                        "error": None})
    return results


def run_archive(selected_steps, today, log, on_progress=None, should_stop=None,
                refresh=False, only_feed=None):
    """执行归档流程（带运行日志落盘与当日结果持久化）

    参数:
        selected_steps: 要执行的步骤编号列表，如 [1, 2, 3, 4]
        today: 日期，如 "2026年08月24日"
        log: 日志回调 log(message)
        on_progress: 进度回调 on_progress(value, text)，可为 None
        should_stop: 停止检查回调 should_stop() -> bool，可为 None
        refresh: True 时步骤 2 重新下载已有原始 HTML、步骤 3 重新下载已有图片
        only_feed: 只检查这一个订阅源（名字或网址）；此时不改写当天的文章列表，
                   有新增条目就并入已有列表

    返回:
        dict 包含 article_list / download / conversion / summary_result /
             step_times / error / failures
        failures 为字符串列表，仅汇总**系统性/流程级**失败（步骤 1 抓取或列表加载失败、
        流程 error），供邮件通知判定；步骤 2/3/4 的逐条内容失败在索引页内标注，不进邮件

    副作用（都落在本地文件里）：
        result/logs/<日期>.log                  本次执行的完整输出（追加分段）
        result/temp_data/「日期」result.json     每源/每步结果，索引页的唯一数据来源
    """
    run_log = runlog.RunLog(today)
    base_stream = sys.stdout
    original_stdout, _tee = runlog.install_stdout_tee(run_log)
    run_meta = report.begin_run(today, selected_steps)
    run_log.header(selected_steps)

    result = None
    error_text = ""
    try:
        result = _run_steps(selected_steps, today,
                            runlog.make_logger(log, run_log, base_stream),
                            on_progress, should_stop,
                            refresh=refresh, only_feed=only_feed)
        return result
    except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
        error_text = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if result is not None:
            error_text = result.get("error") or ""
        report.finish_run(today, run_meta, error_text)
        run_log.footer(ok=not error_text)
        run_log.close()
        runlog.restore_stdout_tee(original_stdout)


def _run_steps(selected_steps, today, log, on_progress=None, should_stop=None,
               refresh=False, only_feed=None):
    """归档主体：按步骤执行并把结果写进当日结果文件"""
    from render_html import scan_and_convert
    from watch_export import export_articles

    total_steps = len(STEPS)
    log(f"{'=' * 60}")
    log(f"订阅归档 - {today}")
    log(f"{'=' * 60}")
    log("")

    article_list = None
    output_dir = OUTPUT_BASE_DIR / today
    success = fail = skipped = 0
    failed = []
    conversion = None
    summary_result = None
    step_times = {}
    error = None
    failures = []
    # 期望文件名 -> 缺失原因（下载/渲染失败），供索引页就地标注
    # 先并入已落盘的标注：只跑步骤 4（或 --reindex）时索引页也能还原此前的失败
    missing_notes = report.notes(today)

    def should_run(step_num):
        return step_num in selected_steps

    def stopped():
        return bool(should_stop and should_stop())

    def snapshot():
        return {"article_list": article_list, "download": (success, fail, skipped, failed),
                "conversion": conversion, "summary_result": summary_result,
                "step_times": step_times, "error": error, "failures": failures}

    # ========== 步骤 1: 获取文章列表（订阅检查）==========
    if should_run(1):
        if on_progress:
            on_progress(10, "步骤 1: 获取文章列表...")

        # 当天列表已存在则直接复用，避免重复抓取（抓取会把来源里的新文章标记为已读/已见）
        # --only-feed 例外：只刷新那一个源，且不会覆盖列表文件
        json_path = TEMP_DIR / f"「{today}」.json"
        if json_path.exists() and not only_feed:
            log(f"[步骤 1/{total_steps}] 获取文章列表 - ⏭️ 跳过（已存在 「{today}」.json）")
            log("  提示：如需重新抓取，请先删除该文件，或用 --date 指定其他日期")
            article_list = _load_article_list(today)
            if not article_list:
                log(f"✗ 无法从已存在的列表文件加载文章: {json_path}")
                failures.append(f"步骤 1 无法加载已存在的列表文件: {json_path}")
                return snapshot()
            log(f"📂 从文件加载了 {len(article_list)} 篇文章")
            log(f"  列表文件: {json_path}")
            log("")
        else:
            if only_feed:
                log(f"[步骤 1/{total_steps}] 只检查订阅源「{only_feed}」...")
            else:
                log(f"[步骤 1/{total_steps}] 获取文章列表（订阅检查）...")
            step_start = time.time()
            today_str, article_list, output_path, fetch_failure, feed_results = export_articles(
                skip_auth_check=False, only_feed=only_feed
            )
            # 每源抓取结果先落盘：即使后面没有新文章，索引页表格也要有据可查
            report.update_fetch(today, feed_results)

            if fetch_failure:
                failures.append(f"步骤 1 获取文章列表失败: {fetch_failure}")

            if not article_list:
                if fetch_failure:
                    log(f"✗ 获取文章列表失败: {fetch_failure}")
                    return snapshot()
                if only_feed:
                    # 单源刷新没有新增：当天列表不动，后续步骤改用已有列表
                    article_list = _load_article_list(today)
                    log(f"· 「{only_feed}」没有新增条目，当天列表保持不变")
                else:
                    log("✗ 没有新文章")
                    return snapshot()
            else:
                step_times[1] = time.time() - step_start
                log(f"✓ 共 {len(article_list)} 篇文章")
                log(f"  列表保存: {output_path}")
                log(f"  ⏱ 耗时: {format_duration(step_times[1])}")
                log("")
                if only_feed:
                    # 单源刷新后，后续步骤要用整天的列表
                    article_list = _load_article_list(today)
    else:
        log(f"[步骤 1/{total_steps}] 获取文章列表 - ⏭️ 跳过")

    if stopped():
        return snapshot()

    # ========== 步骤 2: 下载网页并优化文件名 ==========
    if should_run(2):
        if article_list is None:
            article_list = _load_article_list(today)
            if not article_list:
                log("❌ 无法加载文章列表，请先运行步骤 1")
                error = "无法加载文章列表，请先运行步骤 1"
                failures.append(f"流程错误: {error}")
                return snapshot()
            log(f"📂 从文件加载了 {len(article_list)} 篇文章")

        log(f"[步骤 2/{total_steps}] 下载网页并优化文件名...")
        if on_progress:
            on_progress(20, "步骤 2: 下载网页...")

        success, fail, skipped, failed, step_times[2] = _download_step(
            article_list, today, log, on_progress, overwrite=refresh
        )

        # 逐条下载失败只记入索引页标注（不进邮件）；同时写进当日结果文件
        download_stats, download_notes = _download_stats(article_list, failed)
        download_cleared = [
            _expected_filename(article) for article in article_list
            if _expected_filename(article) not in download_notes
        ]
        missing_notes.update(download_notes)
        for name in download_cleared:      # 重跑成功后把旧的失败标注一并清掉
            missing_notes.pop(name, None)
        report.update_download(today, download_stats, download_notes, download_cleared)
    else:
        log(f"[步骤 2/{total_steps}] 下载网页 - ⏭️ 跳过")

    if stopped():
        return snapshot()

    # ========== 步骤 3: 渲染为 HTML ==========
    if should_run(3):
        log("")
        log(f"[步骤 3/{total_steps}] 渲染为 HTML...")
        if on_progress:
            on_progress(60, "步骤 3: 渲染 HTML...")

        step_start = time.time()
        conversion = scan_and_convert(today, refresh=refresh)
        step_times[3] = time.time() - step_start
        log(f"  ⏱ 耗时: {format_duration(step_times[3])}")

        # 渲染失败/未识别来源同样只记入索引页标注（不进邮件），并写进当日结果文件
        render_stats, render_notes = _render_stats(today, conversion)
        raw_dir = RAW_DIR / today
        render_cleared = [
            p.name for p in sorted(raw_dir.glob("*.html")) if p.name not in render_notes
        ] if raw_dir.exists() else []
        missing_notes.update(render_notes)
        for name in render_cleared:
            missing_notes.pop(name, None)
        report.update_render(today, render_stats, render_notes, render_cleared)
    else:
        log(f"[步骤 3/{total_steps}] 渲染 HTML - ⏭️ 跳过")

    if stopped():
        return snapshot()

    # ========== 步骤 4: AI 摘要与索引页 ==========
    if should_run(4):
        log("")
        log(f"[步骤 4/{total_steps}] AI 摘要与索引页生成...")
        if on_progress:
            on_progress(80, "步骤 4: AI 摘要...")

        step_start = time.time()
        summary_result = _summarize_step(today, log, article_list, missing_notes, should_stop)
        step_times[4] = time.time() - step_start
        log(f"  ⏱ 耗时: {format_duration(step_times[4])}")

        # 逐条摘要失败已在索引页标注（不进邮件）；索引页自身写入失败才算流程问题
        if summary_result and summary_result.get("index_error"):
            failures.append(f"步骤 4 索引页生成失败: {summary_result['index_error']}")
    else:
        log(f"[步骤 4/{total_steps}] AI 摘要 - ⏭️ 跳过")

    # ========== 汇总 ==========
    total_time = sum(step_times.values())
    log("")
    log(f"{'=' * 60}")
    log("归档完成")
    log(f"{'=' * 60}")

    if article_list:
        log(f"文章总数: {len(article_list)} 篇")
    if should_run(2):
        log(f"下载成功: {success} 篇")
        if skipped > 0:
            log(f"跳过: {skipped} 篇")
        if fail > 0:
            log(f"下载失败: {fail} 篇")
            log("  失败原因：")
            for idx, title, url, reason in failed:
                log(f"    [{idx}] {title} - {reason}")
    if conversion:
        convert_ok = len(conversion.get("success", []))
        log(f"渲染成功: {convert_ok} 篇")
        convert_failed = conversion.get("failed", [])
        convert_unknown = conversion.get("unknown", [])
        if convert_failed or convert_unknown:
            log(f"渲染失败: {len(convert_failed)} 篇，未知来源: {len(convert_unknown)} 篇")
            log("  失败原因：")
            for name, reason in convert_failed:
                log(f"    [{reason}] {name} - 已匹配来源但渲染失败")
            for name, _ in convert_unknown:
                log(f"    [未知来源] {name} - 未添加解析策略")
    if summary_result:
        log(f"AI 摘要: {summary_result['processed']} 篇"
            f"（其中跳过已有摘要 {summary_result.get('skipped', 0)} 篇）")
        summary_failures = summary_result.get("failures", [])
        if summary_failures:
            log(f"AI 摘要失败: {len(summary_failures)} 篇")
            log("  失败原因：")
            for filename, err in summary_failures:
                log(f"    {filename}: {err}")

    if failures:
        log("")
        log(f"⚠️  共 {len(failures)} 项失败，详见上方日志")

    log(f"输出目录: {output_dir.absolute()}")
    log("")
    log(f"总耗时: {format_duration(total_time)}")
    log(f"{'=' * 60}")

    return snapshot()
