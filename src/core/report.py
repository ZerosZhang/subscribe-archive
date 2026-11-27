#!/usr/bin/env python3
"""
当日归档结果的持久化（索引页的唯一数据来源）

一个日期一份 `result/temp_data/「日期」result.json`，记录：
- 每个订阅源当天的结果：抓取（RSS）→ 下载 → 渲染 → AI 摘要
- 逐条失败原因（文件名 → 原因），供索引页就地标注
- 每次执行的起止时间（同一天重复执行时追加，保留最近若干次）

设计要点：
- 同一天重复执行时**按步骤合并**：跑了哪一步就覆盖哪一步的结果，没跑的不动
- 索引页只读这个文件 + 文章列表 JSON，不再依赖本次运行的内存状态（--reindex 也能还原）
- 索引页「仅链接」分组只列当天抓到的条目，不回退显示旧内容（见 failed_fetch_urls）
"""

import json
import os
from datetime import datetime

from utils import TEMP_DIR

REPORT_VERSION = 1
MAX_RUNS = 10


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def report_path(today):
    return TEMP_DIR / f"「{today}」result.json"


def _empty(today):
    return {
        "version": REPORT_VERSION,
        "date": today,
        "updated_at": "",
        "runs": [],
        "feeds": {},
        "notes": {},
    }


def load(today):
    """读取当天结果文件；缺失或损坏时返回空骨架（不抛异常）"""
    path = report_path(today)
    data = _empty(today)
    if not path.exists():
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(loaded, dict):
        return data
    for key in ("runs", "feeds", "notes"):
        value = loaded.get(key)
        if isinstance(value, type(data[key])):
            data[key] = value
    data["version"] = loaded.get("version", REPORT_VERSION)
    data["updated_at"] = loaded.get("updated_at", "")
    return data


def save(today, data):
    """原子写入（临时文件 + os.replace），失败只打印不中断流程"""
    path = report_path(today)
    data["version"] = REPORT_VERSION
    data["date"] = today
    data["updated_at"] = _now_text()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"⚠️  当日结果写入失败：{exc}")
    return data


# =============================================================================
# 每次执行的生命周期
# =============================================================================

def begin_run(today, steps):
    """登记一次执行的开始，返回 run 字典（供 finish_run 使用）"""
    data = load(today)
    run = {
        "started_at": _now_text(),
        "finished_at": "",
        "steps": list(steps),
        "error": "",
    }
    data["runs"].append(run)
    data["runs"] = data["runs"][-MAX_RUNS:]
    save(today, data)
    return run


def finish_run(today, run, error=""):
    """登记执行的结束时间与整体错误（步骤内逐条失败不算）"""
    data = load(today)
    for item in reversed(data["runs"]):
        if item.get("started_at") == run.get("started_at") and item.get("steps") == run.get("steps"):
            item["finished_at"] = _now_text()
            item["error"] = error or ""
            break
    save(today, data)


# =============================================================================
# 步骤 1：订阅抓取
# =============================================================================

def update_fetch(today, feed_results):
    """写入每个源的抓取结果

    feed_results: [{"name","url","archive","status","new","entries","error"}]
    status: ok（有更新，含首次检查）/ not_modified（无更新）/ error（失败）；
    只有旧数据里还会出现 first_run（首次检查只记基线）
    """
    if not feed_results:
        return
    data = load(today)
    checked_at = _now_text()
    for item in feed_results:
        name = item.get("name") or item.get("url")
        if not name:
            continue
        feed = data["feeds"].setdefault(name, {})
        feed["url"] = item.get("url", feed.get("url", ""))
        feed["archive"] = bool(item.get("archive", True))
        prev = feed.get("fetch") or {}
        # 「当天累计新增」：同一天多次检查（含 --only-feed 的补刷）累加，
        # 否则后一次 304 会把当天的成果显示成「无更新」
        since = int(prev.get("today", prev.get("new") or 0) or 0)
        feed["fetch"] = {
            "status": item.get("status") or "ok",
            "new": int(item.get("new") or 0),
            "today": since + int(item.get("new") or 0),
            "entries": int(item.get("entries") or 0),
            "error": item.get("error") or "",
            "checked_at": checked_at,
        }
    save(today, data)


# =============================================================================
# 步骤 2/3/4：逐篇结果
# =============================================================================

def _apply_step(today, step_key, stats, notes, cleared=None):
    """把某一步的按源统计与逐条失败原因合并进结果文件

    stats: {来源: {"total","success","failed","errors":[{"title","reason"}]}}
    notes: {成品文件名: 失败原因}（与索引页的 missing_notes 同口径）
    cleared: 本次已成功的文件名——同一天重跑时要把旧的失败标注清掉
    """
    data = load(today)
    for source, stat in (stats or {}).items():
        key = _find_feed_key(data["feeds"], source) or source
        feed = data["feeds"].setdefault(key, {"url": "", "archive": True})
        feed[step_key] = {
            "total": int(stat.get("total") or 0),
            "success": int(stat.get("success") or 0),
            "failed": int(stat.get("failed") or 0),
            "errors": stat.get("errors") or [],
            "updated_at": _now_text(),
        }
    for name in cleared or []:
        data["notes"].pop(name, None)
    if notes:
        data["notes"].update(notes)
    save(today, data)


def update_download(today, stats, notes=None, cleared=None):
    _apply_step(today, "download", stats, notes, cleared)


def update_render(today, stats, notes=None, cleared=None):
    _apply_step(today, "render", stats, notes, cleared)


def update_summary(today, stats, notes=None, cleared=None):
    _apply_step(today, "summary", stats, notes, cleared)


# =============================================================================
# 读取端：索引页用
# =============================================================================

def notes(today):
    """成品文件名 → 失败原因（下载/渲染/摘要，后写的覆盖先写的）"""
    data = load(today)
    return dict(data.get("notes") or {})


def failed_fetch_urls(today):
    """当天抓取失败的订阅地址集合（索引页据此跳过该源的热榜分组）"""
    data = load(today)
    urls = set()
    for feed in (data.get("feeds") or {}).values():
        fetch = feed.get("fetch") or {}
        if fetch.get("status") == "error":
            if feed.get("url"):
                urls.add(feed["url"])
    return urls


def _status_of(feed):
    """按已有数据判定这个源当天的结果：(kind, label, detail)

    kind: ok / partial / fail / none / unknown
    """
    fetch = feed.get("fetch") or {}
    status = fetch.get("status")
    if status == "error":
        return "fail", "获取更新失败", fetch.get("error") or "抓取失败"

    # 「当天累计新增」优先：同一天补刷返回 304 时不会把已抓到的成果显示成无更新
    articles = int(fetch.get("today", fetch.get("new") or 0) or 0)
    entries = int(fetch.get("entries") or 0)
    if not feed.get("archive", True):
        # 仅链接的源（V2EX、知乎热榜）：抓到就算成功，没抓到算无更新
        if status == "first_run" and not articles:
            # 旧数据：首次检查的条目全部记在当天，按实际条数报（新数据首次检查已按正常更新处理）
            articles = entries
        if articles:
            return "ok", f"获取成功（{articles} 条链接）", ""
        if status in ("not_modified", "ok"):
            return "none", "无更新", ""
        return "unknown", "未检查", ""

    # 有归档的源：以最后一道真正跑过的工序为准，分母取「当天抓到的篇数」与工序总数中较大的
    for key in ("summary", "render", "download"):
        step = feed.get(key)
        if not step:
            continue
        step_total = int(step.get("total") or 0)
        success = int(step.get("success") or 0)
        if step_total <= 0:
            continue
        total = max(articles, step_total)
        detail = _step_detail(feed)
        if success >= total:
            return "ok", f"全部成功（{total}）", detail
        if success > 0:
            return "partial", f"部分成功（{success}/{total}）", detail
        return "fail", f"全部失败（0/{total}）", detail

    if status == "first_run":
        # 旧数据：当时首次检查只记基线、不归档也不下载，如实标出来
        return "none", f"首次检查（{entries} 条基线）", ""
    if status == "not_modified" or articles == 0:
        return "none", "无更新", ""
    return "unknown", f"待处理（{articles} 篇）", ""


def _step_detail(feed):
    """把各工序的失败篇数拼成一句说明，全成功时返回空串"""
    parts = []
    for key, label in (("download", "下载失败"), ("render", "渲染失败"), ("summary", "摘要失败")):
        step = feed.get(key)
        if not step:
            continue
        failed = int(step.get("failed") or 0)
        if failed:
            parts.append(f"{label} {failed} 篇")
    return "、".join(parts)


def _source_key(name):
    """来源名的比对键

    步骤 2 的统计用订阅名（如 `Blog | Yu Gao`），步骤 3 用成品文件名前缀（非法字符已清洗，
    变成 `Blog Yu Gao`）。清洗后同名即视为同一个源，避免结果表出现两行。
    """
    from save_webpages import sanitize_filename
    return sanitize_filename(name or "").strip().lower()


def _find_feed_key(feeds, name):
    """在 feeds 里按「原名 → 清洗后同名」找已有的源，找不到返回 None"""
    if name in feeds:
        return name
    key = _source_key(name)
    for existing in feeds:
        if _source_key(existing) == key:
            return existing
    return None


def feed_rows(today):
    """索引页顶部的订阅结果表：结果异常的排前面，未检查的排最后

    当天完全没有抓取记录（老日期、从未跑过步骤 1）时返回空列表，索引页就不显示表格。
    """
    data = load(today)
    feeds = data.get("feeds") or {}
    if not feeds:
        return []
    rows = []
    try:
        from watch_export import load_watch_feeds
        order = [f.get("name") or f["url"] for f in load_watch_feeds()]
    except Exception:  # noqa: BLE001 - 订阅列表读不到也要能出表
        order = []

    names = list(order)
    order_keys = {_source_key(x) for x in order}
    for name in feeds:
        if _source_key(name) in order_keys:
            continue
        names.append(name)

    used = set()
    for index, name in enumerate(names):
        key = _find_feed_key(feeds, name)
        if key and key in used:
            continue
        if key:
            used.add(key)
        feed = feeds.get(key) if key else None
        if feed is None:
            rows.append({"name": name, "url": "", "kind": "unknown",
                         "label": "未检查", "detail": "", "_index": index})
            continue
        kind, label, detail = _status_of(feed)
        rows.append({"name": name, "url": feed.get("url", ""),
                     "kind": kind, "label": label, "detail": detail, "_index": index})

    priority = {"fail": 0, "partial": 1, "ok": 2, "none": 3, "unknown": 4}
    rows.sort(key=lambda row: (priority.get(row["kind"], 9), row["_index"]))
    for row in rows:
        row.pop("_index", None)
    return rows


def summary_counts(today):
    """给日志/页头用的一句话统计：{ok, partial, fail, none, unknown}"""
    counts = {"ok": 0, "partial": 0, "fail": 0, "none": 0, "unknown": 0}
    for row in feed_rows(today):
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return counts
