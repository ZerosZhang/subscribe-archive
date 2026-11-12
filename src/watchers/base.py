#!/usr/bin/env python3
"""站点列表页抓取器（watcher）基类与注册表

适用场景：站点没有 RSS，但列表可以从 API 或 HTML 里稳定取出。
每个 watcher 负责一个站点，返回统一结构：
    [{"guid": ..., "title": ..., "link": ..., "published": ...}]
"""


class BaseWatcher:
    """列表页抓取器基类"""

    name = "未知来源"

    @classmethod
    def detect(cls, url: str) -> bool:
        """这个 URL 是否由本 watcher 处理"""
        return False

    @classmethod
    def fetch_entries(cls, url: str) -> list:
        """抓取列表，返回 [{guid, title, link, published}, ...]"""
        return []

    @classmethod
    def label(cls, url: str) -> str:
        """订阅列表里显示的名字"""
        return cls.name


_WATCHERS = []


def register_watcher(cls):
    _WATCHERS.append(cls)
    return cls


def resolve_watcher(url: str):
    """按注册顺序找第一个认领该 URL 的 watcher，没有则 None"""
    for watcher in _WATCHERS:
        try:
            if watcher.detect(url or ""):
                return watcher
        except Exception:  # noqa: BLE001 - 单个 watcher 出错不影响其他
            continue
    return None
