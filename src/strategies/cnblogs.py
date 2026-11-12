#!/usr/bin/env python3
"""博客园解析策略"""

import re

from .base import BaseStrategy, register_strategy, _find_matching_close


@register_strategy
class CnblogsStrategy(BaseStrategy):
    """博客园 (cnblogs.com): 正文容器 id="cnblogs_post_body" """

    name = "博客园"

    @classmethod
    def detect(cls, html_text, filename_hint=""):
        if "博客园" in filename_hint:
            return True
        return 'id="cnblogs_post_body"' in html_text

    @classmethod
    def extract_body(cls, html_text):
        m = re.search(r'<div[^>]*id="cnblogs_post_body"[^>]*>', html_text)
        if not m:
            return ""
        start = m.end()
        end = _find_matching_close(html_text, start)
        return html_text[start:end - 6]

    @classmethod
    def extract_blocks(cls, body_html):
        if body_html.strip():
            return [(None, body_html)]
        return []
