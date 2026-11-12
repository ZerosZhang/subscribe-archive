#!/usr/bin/env python3
"""站点列表页抓取器包：导入全部 watcher 以触发注册
注意：导入顺序即注册顺序，第一个认领 URL 的 watcher 被使用"""

from .base import BaseWatcher, register_watcher, resolve_watcher, _WATCHERS
