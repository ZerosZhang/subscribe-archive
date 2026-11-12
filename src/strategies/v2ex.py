#!/usr/bin/env python3
"""V2EX 解析策略"""

import re

from .base import BaseStrategy, register_strategy, _find_matching_close


@register_strategy
class V2exStrategy(BaseStrategy):
    """V2EX: 主题正文在 div.topic_content 里"""

    name = "V2EX"

    @classmethod
    def detect(cls, html_text, filename_hint=""):
        if "V2EX" in filename_hint:
            return True
        return 'class="topic_content"' in html_text and "v2ex.com" in html_text

    @classmethod
    def extract_body(cls, html_text):
        m = re.search(r'<div[^>]*class="topic_content"[^>]*>', html_text)
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
