#!/usr/bin/env python3
"""
订阅检查模块（阶段 1：抓取订阅并产出当天文章列表）
流程：
1. 读取 src/watch_feeds.json 的订阅列表
2. 逐源抓取 feed，按 guid 去重（状态存在 result/temp_data/watch.db）
3. 把新增条目整理成文章列表，保存到 temp_data/「当天日期.json」
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import feedparser

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import PYTHON_ROOT, TEMP_DIR  # noqa: E402

import waf  # noqa: E402

from watchers import resolve_watcher  # noqa: E402
from strategies import resolve_strategy_for_feed  # noqa: E402

WATCH_FEEDS_PATH = PYTHON_ROOT / "src" / "watch_feeds.json"
WATCH_DB_PATH = TEMP_DIR / "watch.db"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
TIMEOUT = 20

# 新订阅的默认归档方式：「仅链接」——只把标题与链接列进索引页，
# 不下载原文、不渲染、不做 AI 摘要。要归档全文的源在 watch_feeds.json
# 里显式写 "archive": true（老订阅没这个字段，仍按归档处理）
DEFAULT_FEED_ARCHIVE = False


def load_watch_feeds():
    """读取订阅列表，返回 [{"name":..., "url":...}]"""
    if not WATCH_FEEDS_PATH.exists():
        print(f"[!] 订阅列表不存在: {WATCH_FEEDS_PATH}")
        return []
    try:
        with open(WATCH_FEEDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("feeds", [])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[!] 订阅列表读取失败: {exc}")
        return []


def _save_watch_feeds(feeds):
    with open(WATCH_FEEDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"feeds": feeds}, f, ensure_ascii=False, indent=2)
        f.write("\n")


# 站点没有在 HTML 里声明 feed 时，按常见路径再猜一轮
COMMON_FEED_PATHS = ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml")


class _FeedLinkParser(HTMLParser):
    """收集 <link rel="alternate" type="application/rss+xml|atom+xml">"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        rel = data.get("rel", "").lower()
        mime = data.get("type", "").lower()
        href = data.get("href", "").strip()
        if "alternate" in rel and href and ("rss" in mime or "atom" in mime):
            self.links.append(href)


def fetch_html(url):
    """下载网页文本（不声明 Accept-Encoding，避免压缩内容乱码）"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "text/html,application/xhtml+xml,*/*")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        final_url = resp.geturl()
    if waf.is_challenge(raw):
        raw = waf.fetch(url, {"User-Agent": UA,
                              "Accept": "text/html,application/xhtml+xml,*/*"},
                        timeout=TIMEOUT)
    return raw.decode(charset, errors="ignore"), final_url


def _is_feed(url):
    """能否解析成 feed，能则返回 feed 标题，否则 None"""
    status, payload, _, _ = fetch_feed(url, None, None)
    if status != "ok":
        return None
    title, entries, _ = _parse_feed(payload)
    return (title or url) if entries else None


def discover_feeds(url):
    """从一个网址找出可用的 feed 地址。返回 (候选列表, 失败原因)

    依次尝试：地址本身 → HTML 里的 <link rel="alternate"> 声明 → 常见路径
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return [], "地址必须以 http:// 或 https:// 开头"

    watcher = resolve_watcher(url)
    if watcher is not None:
        try:
            entries = watcher.fetch_entries(url)
        except Exception as exc:  # noqa: BLE001 - 失败原因直接展示
            return [], f"抓取失败：{exc}"
        if not entries:
            return [], "没有取到条目"
        return [{"url": url, "title": watcher.label(url)}], None

    title = _is_feed(url)
    if title:
        return [{"url": url, "title": title}], None

    try:
        html, final_url = fetch_html(url)
    except urllib.error.HTTPError as exc:
        return [], f"网页抓取失败：HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], f"网页抓取失败：{getattr(exc, 'reason', exc)}"

    parser = _FeedLinkParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - 畸形 HTML 不致命，继续猜路径
        pass

    candidates = [urljoin(final_url or url, href) for href in parser.links]
    if not candidates:
        parts = urlsplit(final_url or url)
        base = f"{parts.scheme}://{parts.netloc}"
        candidates = [urljoin(base, path) for path in COMMON_FEED_PATHS]

    results = []
    seen = set()
    for candidate in candidates:
        if candidate in seen or len(results) >= 6:
            continue
        seen.add(candidate)
        title = _is_feed(candidate)
        if title:
            results.append({"url": candidate, "title": title})

    if not results:
        return [], "没找到可用的 feed（该站点可能没有原生订阅源，可试试 RSSHub）"
    return results, None


def _connect():
    """打开状态库；首次运行自动建表"""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WATCH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            url         TEXT PRIMARY KEY,
            title       TEXT,
            etag        TEXT,
            modified    TEXT,
            last_check  TEXT,
            last_error  TEXT,
            fail_count  INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_url    TEXT NOT NULL,
            guid        TEXT NOT NULL,
            title       TEXT,
            link        TEXT,
            published   TEXT,
            first_seen  TEXT NOT NULL,
            UNIQUE (feed_url, guid)
        )
    """)
    conn.commit()
    return conn


def _now_text():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def fetch_feed(url, etag, modified):
    """抓取 feed。返回 (状态, 响应体, 新 etag, 新 Last-Modified)
    状态：ok / not_modified / error
    """
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/rss+xml, application/atom+xml, "
                             "application/xml, text/xml, */*")
    if etag:
        req.add_header("If-None-Match", etag)
    if modified:
        req.add_header("If-Modified-Since", modified)

    last_error = None
    for attempt in range(2):  # 网络抖动（SSL EOF / 超时）重试一次
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
                etag_value = resp.headers.get("ETag")
                modified_value = resp.headers.get("Last-Modified")
            # openresty WAF 的 JS 挑战页：换通行 Cookie 后重取（见 waf.py）
            if waf.is_challenge(body):
                body = waf.fetch(
                    url,
                    {"User-Agent": UA,
                     "Accept": "application/rss+xml, application/atom+xml, "
                               "application/xml, text/xml, */*"},
                    timeout=TIMEOUT)
            return "ok", body, etag_value, modified_value
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return "not_modified", None, None, None
            return "error", f"HTTP {exc.code}", None, None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = getattr(exc, "reason", exc)
            if attempt == 0:
                time.sleep(2)
    return "error", f"网络错误：{last_error}", None, None


def _entry_guid(entry):
    """优先用源站 id，其次 link，最后退回标题+时间的摘要值"""
    for key in ("id", "guid", "link"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    raw = f"{entry.get('title', '')}|{entry.get('published', '')}"
    return "sha1:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _entry_time(entry):
    """feedparser 的时间结构体是 UTC，转成本地时区的 ISO 字符串"""
    tm = entry.get("published_parsed") or entry.get("updated_parsed")
    if not tm:
        return ""
    return datetime.fromtimestamp(
        _utc_timestamp(tm), tz=timezone.utc
    ).astimezone().isoformat(timespec="seconds")


def _utc_timestamp(tm):
    import calendar
    return calendar.timegm(tm)


def _parse_feed(data):
    """解析 feed，返回 (feed 标题, 条目列表, 是否解析失败)"""
    parsed = feedparser.parse(data)
    title = (parsed.feed.get("title") or "").strip()
    entries = [{
        "guid": _entry_guid(item),
        "title": (item.get("title") or "").strip(),
        "link": (item.get("link") or "").strip(),
        "published": _entry_time(item),
    } for item in parsed.entries]
    return title, entries, bool(parsed.bozo)


def _save_feed_state(conn, url, title, etag, modified, error, fail_inc):
    conn.execute("""
        INSERT INTO feeds (url, title, etag, modified, last_check, last_error, fail_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title      = COALESCE(excluded.title, feeds.title),
            etag       = excluded.etag,
            modified   = excluded.modified,
            last_check = excluded.last_check,
            last_error = excluded.last_error,
            fail_count = CASE WHEN ? THEN feeds.fail_count + 1 ELSE 0 END
    """, (url, title, etag, modified, _now_text(), error,
          1 if fail_inc else 0, 1 if fail_inc else 0))


def _migrate_feed_state(conn, url, feed_title):
    """同名源换过订阅地址时，把旧地址的条目与状态搬到新地址，返回迁移后的条目数

    订阅地址一变，条目就是按 URL 存在库里的，新地址看起来像「首次检查」，
    一整天的新条目只会被记成基线而不归档。这里用 feed 标题认回旧地址，
    已存在的 guid 用 UPDATE OR IGNORE 跳过，然后把旧地址的行删掉。

    只认「已经从 watch_feeds.json 里消失」的旧地址：同名但仍在订阅列表里的源
    是另一个订阅（例如同站点的两个 feed），不能把它的历史条目抢过来。
    """
    if not feed_title:
        return 0
    active = {f["url"].strip() for f in load_watch_feeds() if f.get("url")}
    old_urls = [row["url"] for row in conn.execute(
        "SELECT url FROM feeds WHERE title = ? AND url != ?", (feed_title, url))
        if row["url"] not in active]
    for old_url in old_urls:
        conn.execute("UPDATE OR IGNORE entries SET feed_url = ? WHERE feed_url = ?",
                     (url, old_url))
        conn.execute("DELETE FROM entries WHERE feed_url = ?", (old_url,))
        conn.execute("DELETE FROM feeds WHERE url = ?", (old_url,))
    conn.commit()
    return conn.execute(
        "SELECT COUNT(*) FROM entries WHERE feed_url = ?", (url,)
    ).fetchone()[0]


def check_feed(conn, feed):
    """检查单个订阅。返回 (新增文章列表, 失败原因, 状态信息)

    订阅地址有两种：
    - 普通 RSS/Atom：走 HTTP + feedparser（支持 ETag/304）
    - 站点列表页（如 B 站 UP 主页）：交给对应 watcher 抓接口

    状态信息供「当日结果」与索引页表格使用：
      {"name","url","archive","status","new","entries","error"}
    status: ok（有更新，含首次检查）/ not_modified（无更新）/ error（失败）
    首次检查不再只记基线：当前 feed 里的条目全部按当天新增处理（该归档的归档，仅链接的列链接）
    """
    url = feed["url"].strip()
    name = feed.get("name") or url
    archive = feed.get("archive", True) is not False
    info = {"name": name, "url": url, "archive": archive,
            "status": "ok", "new": 0, "entries": 0, "error": ""}
    row = conn.execute("SELECT * FROM feeds WHERE url = ?", (url,)).fetchone()
    etag = row["etag"] if row else None
    modified = row["modified"] if row else None

    # 有专用策略的源，标题尾巴上的站点名由策略负责去掉（与渲染时同一套规则）
    strategy = resolve_strategy_for_feed(url, name, feed.get("strategy") or "")

    def clean_title(text):
        return strategy.clean_title(text) if strategy else (text or "")

    watcher = resolve_watcher(url)
    if watcher is not None:
        new_etag = new_modified = None
        try:
            entries = watcher.fetch_entries(url)
            feed_title = watcher.label(url)
            if not entries:
                status, payload = "error", "没有取到条目"
            else:
                status, payload = "ok", None
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其他源
            status, payload, entries, feed_title = "error", str(exc), [], None
    else:
        status, payload, new_etag, new_modified = fetch_feed(url, etag, modified)
        if status == "not_modified":
            _save_feed_state(conn, url, None, etag, modified, None, False)
            conn.commit()
            print(f"  · {name}：无更新（304）")
            info["status"] = "not_modified"
            return [], None, info
        if status == "ok":
            feed_title, entries, bozo = _parse_feed(payload)
            if not entries:
                status = "error"
                payload = "内容不是有效的 feed" if bozo else "feed 为空"

    if status == "error":
        _save_feed_state(conn, url, None, etag, modified, payload, True)
        conn.commit()
        print(f"  ✗ {name}：抓取失败 — {payload}")
        info["status"] = "error"
        info["error"] = str(payload)
        return [], f"{name}: {payload}", info

    known = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE feed_url = ?", (url,)
    ).fetchone()[0]
    first_run = known == 0
    if first_run:
        previous = _migrate_feed_state(conn, url, feed_title)
        if previous:
            # 换过订阅地址：把旧地址的条目迁过来，本次照常当作更新处理
            print(f"  ↺ {name}：订阅地址已变更，已沿用旧地址的 {previous} 条历史条目")
            first_run = False
    # archive=false：只在日志里提示新条目，不交给后续归档步骤（如只想知道热榜有什么）
    do_archive = archive
    info["entries"] = len(entries)

    articles = []
    stamp = _now_text()
    for item in entries:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO entries
                (feed_url, guid, title, link, published, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, item["guid"], item["title"], item["link"],
              item["published"], stamp))
        if cursor.rowcount:
            if not do_archive:
                articles.append({"no_archive": True, **{
                    "title": clean_title(item["title"]) or "无标题",
                    "published": item["published"],
                    "url": item["link"],
                }})
                continue
            articles.append({
                "entry_id": item["guid"],
                "title": clean_title(item["title"]) or "无标题",
                "url": item["link"],
                "feed_title": name,
                "published": item["published"],
                "summary": "",
            })

    _save_feed_state(conn, url, feed_title, new_etag, new_modified, None, False)
    conn.commit()

    info["status"] = "ok" if articles else "not_modified"
    info["new"] = len(articles)

    if not do_archive:
        articles = [a for a in articles if a.pop("no_archive", False)]

    if first_run:
        head = f"  ◐ {name}：首次检查，{len(articles)} 条全部列为当天新增"
    elif articles:
        head = f"  ✓ {name}：{len(articles)} 条更新" + ("（仅提示，不归档）" if not do_archive else "")
    else:
        head = f"  · {name}：无更新"
    print(head)
    for article in sorted(articles, key=lambda a: a["published"], reverse=True):
        print(f"      - {article['published']} {article['title']}")

    if not do_archive:
        return [], None, info
    return articles, None, info


def _days_since(text):
    """把本地时间文本（YYYY-MM-DD HH:MM:SS）换算成距今天数，解析失败返回 None"""
    if not text:
        return None
    try:
        seen = datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S").date()
    except (TypeError, ValueError):
        return None
    return (datetime.now().date() - seen).days


def list_feeds_state():
    """订阅列表 + 检查状态，供网页配置页展示"""
    conn = _connect()
    try:
        result = []
        for feed in load_watch_feeds():
            url = feed["url"].strip()
            row = conn.execute("SELECT * FROM feeds WHERE url = ?", (url,)).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE feed_url = ?", (url,)
            ).fetchone()[0]
            # 最近一次抓到新条目的时间：看它离今天多久，能判断哪个源停更了
            last_update = conn.execute(
                "SELECT MAX(first_seen) FROM entries WHERE feed_url = ?", (url,)
            ).fetchone()[0] or ""
            result.append({
                "name": feed.get("name") or url,
                "url": url,
                "archive": feed.get("archive", True) is not False,
                "strategy_hint": feed.get("strategy") or "",
                "entries": count,
                "last_update": last_update,
                "update_days": _days_since(last_update),
                "last_check": (row["last_check"] or "") if row else "",
                "last_error": (row["last_error"] or "") if row else "",
                "fail_count": row["fail_count"] if row else 0,
            })
        return result
    finally:
        conn.close()


def add_feed(url):
    """校验可解析后追加订阅。返回 (ok, 消息)"""
    url = (url or "").strip()
    if not url:
        return False, "订阅地址不能为空"
    if not url.lower().startswith(("http://", "https://")):
        return False, "订阅地址必须以 http:// 或 https:// 开头"

    feeds = load_watch_feeds()
    if any(f["url"].strip() == url for f in feeds):
        return False, "该订阅已存在"

    watcher = resolve_watcher(url)
    if watcher is not None:
        try:
            entries = watcher.fetch_entries(url)
        except Exception as exc:  # noqa: BLE001
            return False, f"无法抓取：{exc}"
        if not entries:
            return False, "没有取到条目"
        title = watcher.label(url)
        feeds.append({"name": title, "url": url,
                      "archive": DEFAULT_FEED_ARCHIVE})
        _save_watch_feeds(feeds)
        return True, f"已添加：{title}（仅链接，不下载总结）"

    status, payload, _, _ = fetch_feed(url, None, None)
    if status != "ok":
        return False, f"无法抓取：{payload}"
    feed_title, entries, _ = _parse_feed(payload)
    if not entries:
        return False, "该地址不是有效的 RSS/Atom 订阅源，也不在支持的站点列表里"

    feeds.append({"name": feed_title or url, "url": url,
                  "archive": DEFAULT_FEED_ARCHIVE})
    _save_watch_feeds(feeds)
    return True, f"已添加：{feed_title or url}（仅链接，不下载总结）"


def remove_feed(url):
    """从订阅列表删除。返回 (ok, 消息)"""
    url = (url or "").strip()
    feeds = load_watch_feeds()
    kept = [f for f in feeds if f["url"].strip() != url]
    if len(kept) == len(feeds):
        return False, "订阅列表里没有这个地址"
    _save_watch_feeds(kept)
    return True, "已删除"


def rename_feed(url, new_name):
    """改名（订阅的显示名 = 索引页表头与成品文件名前缀）。返回 (ok, 消息)

    只改 watch_feeds.json 的 name，不动状态库：条目仍按 url 去重，
    已归档的历史文件保持原名。
    """
    url = (url or "").strip()
    name = (new_name or "").strip()
    if not name:
        return False, "名称不能为空"
    if len(name) > 60:
        return False, "名称请控制在 60 个字符以内"
    feeds = load_watch_feeds()
    target = next((f for f in feeds if f["url"].strip() == url), None)
    if target is None:
        return False, "订阅列表里没有这个地址"
    for feed in feeds:
        if feed is not target and (feed.get("name") or feed["url"].strip()).strip() == name:
            return False, f"已有同名订阅：{name}"
    old = (target.get("name") or url).strip()
    if old == name:
        return True, "名称未变"
    target["name"] = name
    _save_watch_feeds(feeds)
    return True, f"已改名：{old} → {name}"


def validate_feeds():
    """逐条检测订阅链接是否可用（只读，不写状态库）

    返回 [{name, url, ok, status, entries, error, seconds}]
    status: ok / empty / not_modified / error
    """
    results = []
    for feed in load_watch_feeds():
        url = feed["url"].strip()
        name = feed.get("name") or url
        started = time.time()
        status, entries, error = "ok", 0, None

        try:
            watcher = resolve_watcher(url)
            if watcher is not None:
                try:
                    items = watcher.fetch_entries(url)
                except Exception as exc:  # noqa: BLE001
                    status, error = "error", str(exc)
                else:
                    entries = len(items)
                    status = "ok" if entries else "empty"
            else:
                state, payload, _, _ = fetch_feed(url, None, None)
                if state == "not_modified":
                    status = "not_modified"
                elif state == "error":
                    status, error = "error", payload
                else:
                    title, items, bozo = _parse_feed(payload)
                    entries = len(items)
                    if entries:
                        status = "ok"
                    else:
                        status = "empty"
                        error = "内容不是有效的 feed" if bozo else "feed 为空"
        except Exception as exc:  # noqa: BLE001 - 单条异常不影响其他
            status, error = "error", str(exc)

        results.append({
            "name": name,
            "url": url,
            "ok": status in ("ok", "empty"),
            "status": status,
            "entries": entries,
            "error": error,
            "seconds": round(time.time() - started, 1),
        })
    return results


def list_trend_entries(limit=None, date=None):
    """列出「仅链接」订阅（archive=false）的条目

    date 传入 "YYYY年MM月DD日" 时只取该日抓到的条目；当天没抓到就返回空列表，
    索引页整段不显示（不回退旧的「最近 N 条」）。limit 为 None 时返回全部条目。
    """
    limit_sql = "" if limit is None else "LIMIT ?"
    limit_args = () if limit is None else (limit,)

    conn = _connect()
    try:
        result = []
        for feed in load_watch_feeds():
            if feed.get("archive", True) is not False:
                continue
            url = feed["url"].strip()
            if date:
                # first_seen 形如 "2026-11-13 08:00:00"
                prefix = (date.replace("年", "-").replace("月", "-").replace("日", "")) + "%"
                rows = conn.execute(
                    f"""
                    SELECT title, link, published FROM entries
                    WHERE feed_url = ? AND first_seen LIKE ?
                    ORDER BY published DESC, id DESC
                    {limit_sql}
                    """,
                    (url, prefix, *limit_args),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT title, link, published FROM entries
                    WHERE feed_url = ?
                    ORDER BY published DESC, id DESC
                    {limit_sql}
                    """,
                    (url, *limit_args),
                ).fetchall()
            result.append({
                "name": feed.get("name") or url,
                "url": url,
                "entries": [{"title": row["title"], "link": row["link"],
                             "published": row["published"]} for row in rows],
            })
        return result
    finally:
        conn.close()


def _write_last_check(failures):
    """记录本次检查结果（供网页版展示链接异常）"""
    path = TEMP_DIR / "last_check.json"
    tmp = path.with_suffix(".json.tmp")
    data = {"checked_at": _now_text(), "failures": failures}
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"⚠️  检查结果写入失败：{exc}")


def export_articles(skip_auth_check=False, only_feed=None):
    """检查所有订阅，把新增文章写成 temp_data/「日期」.json

    only_feed: 只检查这一个源（按名字或网址匹配）。此时**不会覆盖**当天的列表文件：
      有新增文章就并入已有列表，没有就完全不动文件，也不改写 last_check.json。
      用于「只想刷新某个源」，避免为了一个源把 26 个源和整天的文章全部重抓。

    返回 (today, article_list, output_path, failure_reason, feed_results)
    feed_results 为每个源的抓取状态（见 check_feed），供当日结果与索引页表格使用
    """
    today = datetime.now().strftime("%Y年%m月%d日")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    feeds = load_watch_feeds()
    if not feeds:
        return today, [], None, "订阅列表为空（src/watch_feeds.json）", []

    if only_feed:
        wanted = only_feed.strip().lower()
        matched = [f for f in feeds
                   if (f.get("name") or "").strip().lower() == wanted
                   or f["url"].strip().lower() == wanted]
        if not matched:
            names = "、".join((f.get("name") or f["url"]) for f in feeds)
            return today, [], None, f"订阅列表里没有「{only_feed}」（可选：{names}）", []
        feeds = matched

    print(f"正在检查 {len(feeds)} 个订阅源...")
    conn = _connect()
    article_list = []
    failures = []
    failure_items = []
    feed_results = []
    try:
        for feed in feeds:
            try:
                articles, failure, info = check_feed(conn, feed)
            except Exception as exc:  # 单源异常不影响其他源
                name = feed.get("name") or feed["url"]
                articles, failure = [], f"{name}: 异常 {exc}"
                info = {"name": name, "url": feed["url"],
                        "archive": feed.get("archive", True) is not False,
                "strategy_hint": feed.get("strategy") or "",
                        "status": "error", "new": 0, "entries": 0,
                        "error": f"异常 {exc}"}
                print(f"  ✗ {failure}")
            article_list.extend(articles)
            feed_results.append(info)
            if failure:
                failures.append(failure)
                failure_items.append({
                    "name": feed.get("name") or feed["url"],
                    "url": feed["url"],
                    "error": failure,
                })
    finally:
        conn.close()

    if not only_feed:
        # 单源刷新时不改写整体状态，避免把其它源的异常记录冲掉
        _write_last_check(failure_items)
    failure_reason = "；".join(failures) if failures else None

    if not article_list:
        if failure_reason:
            print(f"\n未获取到新文章，且存在失败：{failure_reason}")
        else:
            print("\n没有新文章")
        return today, [], None, failure_reason, feed_results

    article_list.sort(key=lambda a: a["published"], reverse=True)
    output_path = TEMP_DIR / f"「{today}」.json"
    if only_feed:
        added = _merge_article_list(output_path, article_list)
        print(f"\n共 {len(article_list)} 篇新文章（仅 {only_feed}）")
        print(f"  已并入当天列表: {output_path}（新增 {added} 条）")
        if added:
            print("  提示：新文章还没下载，需要时再跑步骤 2/3/4")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(article_list, f, ensure_ascii=False, indent=2)
        print(f"\n共 {len(article_list)} 篇新文章")
        print(f"  已保存: {output_path}")
    return today, article_list, output_path, failure_reason, feed_results


def _merge_article_list(output_path, articles):
    """把新条目并入已有的当天列表（按 entry_id/url 去重），返回新增条数"""
    existing = []
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (OSError, json.JSONDecodeError):
            existing = []
    if not isinstance(existing, list):
        existing = []

    def _key(item):
        return item.get("entry_id") or item.get("url")

    seen = {_key(item) for item in existing}
    added = 0
    for item in articles:
        if _key(item) not in seen:
            seen.add(_key(item))
            existing.append(item)
            added += 1
    existing.sort(key=lambda a: a.get("published") or "", reverse=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return added


def main():
    if "--validate" in sys.argv:
        rows = validate_feeds()
        bad = 0
        for row in rows:
            if row["ok"]:
                print(f"✓ {row['name']}：{row['status']} · {row['entries']} 条 · {row['seconds']}s")
            else:
                bad += 1
                print(f"✗ {row['name']}：{row['error']}（{row['seconds']}s）")
                print(f"   {row['url']}")
        print()
        print(f"共 {len(rows)} 个源，异常 {bad} 个")
        return 1 if bad else 0

    today, article_list, output_path, failure_reason, _feed_results = export_articles()
    if failure_reason:
        print(f"\n失败: {failure_reason}")
    if not article_list:
        print("没有新文章，任务结束")
        return 0 if not failure_reason else 1
    print(f"\n文章列表: {len(article_list)} 篇，保存路径: {output_path}")
    return 0


if __name__ == "__main__":
    from utils import fix_encoding
    fix_encoding()
    sys.exit(main())
