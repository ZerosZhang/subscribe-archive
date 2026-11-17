#!/usr/bin/env python3
"""零度博客（freedidi.com）解析策略"""

import re

from .base import BaseStrategy, register_strategy, _find_matching_close


@register_strategy
class FreedidiStrategy(BaseStrategy):
    """零度博客（零度解说）: WordPress + Hueman 主题

    正文在 entry-content → 内层 entry themeform 里，文末挂着打赏弹窗、
    阅读统计和空段落，都要清掉；教程视频是 YouTube 嵌入，管线会剥掉 iframe，
    这里先把它降级成一个普通链接。
    """

    name = "零度博客"

    # 标题尾部由主题追加的频道名（feed 与页面 <title> 都带）
    title_suffixes = ("零度解说", "零度博客")

    # YouTube 嵌入 → 普通链接
    _YT_EMBED_RE = re.compile(
        r'<iframe\b[^>]*src="(?:https?:)?//(?:www\.)?'
        r'(?:youtube(?:-nocookie)?\.com)/embed/([\w-]+)[^"]*"[^>]*>'
        r".*?</iframe>",
        re.DOTALL | re.IGNORECASE,
    )

    @classmethod
    def detect(cls, html_text, filename_hint=""):
        if "零度" in filename_hint:
            return True
        return "freedidi.com" in html_text and 'class="entry-content"' in html_text

    @classmethod
    def extract_body(cls, html_text):
        m = re.search(r'<div[^>]*class="entry-content"[^>]*>', html_text)
        if not m:
            return ""
        start = m.end()
        end = _find_matching_close(html_text, start)
        return html_text[start:end - 6]

    @classmethod
    def _strip_donation(cls, body_html):
        """删掉文末「打赏支持」弹窗（含支付宝/微信/加密货币二维码与复制按钮）"""
        m = re.search(r'<div[^>]*class="donation-container"[^>]*>', body_html)
        while m:
            end = _find_matching_close(body_html, m.end())
            body_html = body_html[:m.start()] + body_html[end:]
            m = re.search(r'<div[^>]*class="donation-container"[^>]*>', body_html)
        return body_html

    @classmethod
    def _clean(cls, body_html):
        body_html = cls._strip_donation(body_html)
        # 阅读统计占位、清浮动标记
        body_html = re.sub(r'<span[^>]*data-qqqrs="[^"]*"[^>]*>\s*</span>', "", body_html)
        body_html = re.sub(r'<div[^>]*class="clear"[^>]*>\s*</div>', "", body_html)
        # 去掉正文外层包裹（entry themeform），只留内容
        body_html = re.sub(r'<div[^>]*class="entry themeform"[^>]*>', "", body_html, count=1)
        body_html = re.sub(r"</div>\s*<!--\s*/?\.entry\s*-->", "", body_html)
        # YouTube 嵌入降级成链接，避免视频随 iframe 一起被剥掉
        body_html = cls._YT_EMBED_RE.sub(
            lambda m: (
                f'<p>视频：<a href="https://www.youtube.com/watch?v={m.group(1)}" '
                f'target="_blank" rel="noopener">'
                f"https://www.youtube.com/watch?v={m.group(1)}</a></p>"
            ),
            body_html,
        )
        body_html = re.sub(r'<div[^>]*class="video-container"[^>]*>\s*</div>', "", body_html)
        # 通篇用来撑行距的空段落
        body_html = re.sub(r"<p[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>", "", body_html)
        # 图片本地化只改写 src，留着 srcset 浏览器仍会回源站取图（离线就看不清）
        body_html = re.sub(r'\s(?:srcset|sizes)\s*=\s*"[^"]*"', "", body_html)
        return body_html.strip()

    @classmethod
    def extract_blocks(cls, body_html):
        body_html = cls._clean(body_html)
        if body_html.strip():
            return [(None, body_html)]
        return []
