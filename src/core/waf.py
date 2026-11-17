#!/usr/bin/env python3
"""openresty WAF 的 JS 挑战破解（零度博客 freedidi.com 等）

部分站点前面挂了一层 openresty + 自研 WAF，没有通行 Cookie 的请求会被换成
一个几百字节的跳转页：

    <script>location.replace("/?_hgk=<token>")</script>

带这个 token 再请求一次（需带 Referer），服务端 302 并下发 `hg_pass`
Cookie（HttpOnly / Secure，有效期 2 小时）。此后带 Cookie 即可正常访问；
静态资源（图片、样式）不受影响，只有 HTML 页面会被拦。

本模块用标准库复现这套流程，并按域名复用 Cookie：
调用方拿到响应后用 is_challenge() 判断，是挑战页就交给 fetch() 重取一次。
"""

import http.cookiejar
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

# 挑战页体积很小（约 300 字节），超过这个大小的一定是正常页面
_CHALLENGE_MAX_BYTES = 4096
# JS 跳转里的通行 token
_TOKEN_RE = re.compile(rb"_hgk=([A-Za-z0-9._~\-]+)")
# 最多试几次，服务端一直发挑战页时不死循环
_MAX_ATTEMPTS = 2
# URL 里保留原样的字符（与 save_webpages.fetch_url 保持一致）
_SAFE_CHARS = ":/?#[]@!$&()*+,;="

_cookie_jar = http.cookiejar.CookieJar()
_openers = {}


class _StopRedirect(urllib.request.HTTPRedirectHandler):
    """换 token 的那次请求不跟随跳转

    通行 Cookie 就在 302 的响应头里，跟过去只会白白下载一遍正文。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(use_proxy=True, follow=True):
    key = (bool(use_proxy), bool(follow))
    opener = _openers.get(key)
    if opener is None:
        handlers = [urllib.request.HTTPCookieProcessor(_cookie_jar)]
        if not follow:
            handlers.append(_StopRedirect())
        if not use_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        _openers[key] = opener
    return opener


def is_challenge(body):
    """响应字节是否为可破解的 WAF 挑战页"""
    if not body or len(body) > _CHALLENGE_MAX_BYTES:
        return False
    return _TOKEN_RE.search(body) is not None


def _quote(url):
    return quote(url, safe=_SAFE_CHARS)


def _get(url, headers, timeout, use_proxy, follow=True):
    req = urllib.request.Request(_quote(url), headers=headers)
    with _opener(use_proxy, follow).open(req, timeout=timeout) as resp:
        return resp.read()


def _with_token(url, token):
    parts = urlsplit(url)
    query = f"{parts.query}&_hgk={token}" if parts.query else f"_hgk={token}"
    return parts._replace(query=query).geturl()


def fetch(url, headers=None, timeout=25, use_proxy=True):
    """下载网页；遇到 WAF 挑战页先换通行 Cookie 再重取，返回响应字节

    失败时照常抛 urllib 的异常，与直接调用 urlopen 的调用方行为一致。
    """
    headers = dict(headers or {})
    body = _get(url, headers, timeout, use_proxy)

    for _ in range(_MAX_ATTEMPTS):
        if not is_challenge(body):
            return body
        token = _TOKEN_RE.search(body).group(1).decode("ascii")
        parts = urlsplit(url)
        challenge_headers = dict(headers)
        # 少了 Referer 服务端会继续发挑战页
        challenge_headers["Referer"] = f"{parts.scheme}://{parts.netloc}/"
        try:
            _get(_with_token(url, token), challenge_headers, timeout,
                 use_proxy, follow=False)
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
        body = _get(url, headers, timeout, use_proxy)

    return body
