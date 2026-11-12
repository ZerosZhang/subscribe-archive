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

from watchers import resolve_watcher  # noqa: E402

WATCH_FEEDS_PATH = PYTHON_ROOT / "src" / "watch_feeds.json"
WATCH_DB_PATH = TEMP_DIR / "watch.db"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
TIMEOUT = 20


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
        return raw.decode(charset, errors="ignore"), resp.geturl()


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
                return ("ok", resp.read(),
                        resp.headers.get("ETag"), resp.headers.get("Last-Modified"))
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


def check_feed(conn, feed):
    """检查单个订阅。返回 (新增文章列表, 失败原因)

    订阅地址有两种：
    - 普通 RSS/Atom：走 HTTP + feedparser（支持 ETag/304）
    - 站点列表页（如 B 站 UP 主页）：交给对应 watcher 抓接口
    """
    url = feed["url"].strip()
    name = feed.get("name") or url
    row = conn.execute("SELECT * FROM feeds WHERE url = ?", (url,)).fetchone()
    etag = row["etag"] if row else None
    modified = row["modified"] if row else None

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
            print(f"  · {name}：无更新（304）")
            return [], None
        if status == "ok":
            feed_title, entries, bozo = _parse_feed(payload)
            if not entries:
                status = "error"
                payload = "内容不是有效的 feed" if bozo else "feed 为空"

    if status == "error":
        _save_feed_state(conn, url, None, etag, modified, payload, True)
        print(f"  ✗ {name}：抓取失败 — {payload}")
        return [], f"{name}: {payload}"

    known = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE feed_url = ?", (url,)
    ).fetchone()[0]
    first_run = known == 0
    # archive=false：只在日志里提示新条目，不交给后续归档步骤（如只想知道热榜有什么）
    do_archive = feed.get("archive", True) is not False

    articles = []
    stamp = _now_text()
    for item in entries:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO entries
                (feed_url, guid, title, link, published, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, item["guid"], item["title"], item["link"],
              item["published"], stamp))
        if cursor.rowcount and not first_run:
            if not do_archive:
                articles.append({"no_archive": True, **{
                    "title": item["title"] or "无标题",
                    "published": item["published"],
                    "url": item["link"],
                }})
                continue
            articles.append({
                "entry_id": item["guid"],
                "title": item["title"] or "无标题",
                "url": item["link"],
                "feed_title": name,
                "published": item["published"],
                "summary": "",
            })

    _save_feed_state(conn, url, feed_title, new_etag, new_modified, None, False)
    conn.commit()

    if not do_archive:
        articles = [a for a in articles if a.pop("no_archive", False)]
        if first_run:
            print(f"  ◐ {name}：首次检查，记录 {len(entries)} 条为基线（不归档）")
        elif articles:
            print(f"  ✓ {name}：{len(articles)} 条更新（仅提示，不归档）")
            for item in sorted(articles, key=lambda a: a["published"], reverse=True):
                print(f"      - {item['published']} {item['title']}")
        else:
            print(f"  · {name}：无更新")
        return [], None

    if first_run:
        print(f"  ◐ {name}：首次检查，记录 {len(entries)} 条为基线（不当作更新）")
    elif articles:
        print(f"  ✓ {name}：{len(articles)} 条更新")
        for article in sorted(articles, key=lambda a: a["published"], reverse=True):
            print(f"      - {article['published']} {article['title']}")
    else:
        print(f"  · {name}：无更新")
    return articles, None


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
            result.append({
                "name": feed.get("name") or url,
                "url": url,
                "entries": count,
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
        feeds.append({"name": title, "url": url})
        _save_watch_feeds(feeds)
        return True, f"已添加：{title}"

    status, payload, _, _ = fetch_feed(url, None, None)
    if status != "ok":
        return False, f"无法抓取：{payload}"
    feed_title, entries, _ = _parse_feed(payload)
    if not entries:
        return False, "该地址不是有效的 RSS/Atom 订阅源，也不在支持的站点列表里"

    feeds.append({"name": feed_title or url, "url": url})
    _save_watch_feeds(feeds)
    return True, f"已添加：{feed_title or url}"


def remove_feed(url):
    """从订阅列表删除。返回 (ok, 消息)"""
    url = (url or "").strip()
    feeds = load_watch_feeds()
    kept = [f for f in feeds if f["url"].strip() != url]
    if len(kept) == len(feeds):
        return False, "订阅列表里没有这个地址"
    _save_watch_feeds(kept)
    return True, "已删除"


def list_trend_entries(limit=30, date=None):
    """列出「仅链接」订阅（archive=false）的条目

    date 传入 "YYYY年MM月DD日" 时只取该日抓到的条目；该日没有则回退为最新若干条。
    """
    conn = _connect()
    try:
        result = []
        for feed in load_watch_feeds():
            if feed.get("archive", True) is not False:
                continue
            url = feed["url"].strip()
            rows = []
            if date:
                # first_seen 形如 "2026-11-13 08:00:00"
                prefix = (date.replace("年", "-").replace("月", "-").replace("日", "")) + "%"
                rows = conn.execute(
                    """
                    SELECT title, link, published FROM entries
                    WHERE feed_url = ? AND first_seen LIKE ?
                    ORDER BY published DESC, id DESC
                    LIMIT ?
                    """,
                    (url, prefix, limit),
                ).fetchall()
            if not rows:
                rows = conn.execute(
                    """
                    SELECT title, link, published FROM entries
                    WHERE feed_url = ?
                    ORDER BY published DESC, id DESC
                    LIMIT ?
                    """,
                    (url, limit),
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


def export_articles(skip_auth_check=False):
    """检查所有订阅，把新增文章写成 temp_data/「日期」.json

    返回 (today, article_list, output_path, failure_reason)
    """
    today = datetime.now().strftime("%Y年%m月%d日")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    feeds = load_watch_feeds()
    if not feeds:
        return today, [], None, "订阅列表为空（src/watch_feeds.json）"

    print(f"正在检查 {len(feeds)} 个订阅源...")
    conn = _connect()
    article_list = []
    failures = []
    try:
        for feed in feeds:
            try:
                articles, failure = check_feed(conn, feed)
            except Exception as exc:  # 单源异常不影响其他源
                articles, failure = [], f"{feed.get('name') or feed['url']}: 异常 {exc}"
                print(f"  ✗ {failure}")
            article_list.extend(articles)
            if failure:
                failures.append(failure)
    finally:
        conn.close()

    failure_reason = "；".join(failures) if failures else None

    if not article_list:
        if failure_reason:
            print(f"\n未获取到新文章，且存在失败：{failure_reason}")
        else:
            print("\n没有新文章")
        return today, [], None, failure_reason

    article_list.sort(key=lambda a: a["published"], reverse=True)
    output_path = TEMP_DIR / f"「{today}」.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(article_list, f, ensure_ascii=False, indent=2)
    print(f"\n共 {len(article_list)} 篇新文章")
    print(f"  已保存: {output_path}")
    return today, article_list, output_path, failure_reason


def main():
    today, article_list, output_path, failure_reason = export_articles()
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
