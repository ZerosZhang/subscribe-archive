# core/waf.py — openresty WAF 的 JS 挑战

## 职责

少数站点（如零度博客 `www.freedidi.com`）前面挂了一层 openresty + 自研 WAF：没有通行 Cookie 的请求一律被换成几百字节的跳转页，正文页、`/feed`、`/wp-json` 全部拦，**静态资源（图片、CSS）不受影响**。本模块用标准库复现这套挑战流程，让 `save_webpages` 与 `watch_export` 能直接下载这些站点的 HTML。

## 挑战流程

```
GET /some/path                       → 200（约 290 字节）
                                       <script>location.replace("/some/path?_hgk=<token>")</script>
GET /some/path?_hgk=<token>  (Referer) → 302 + Set-Cookie: hg_pass=...; Max-Age=7200; HttpOnly; Secure
GET /some/path               (Cookie)  → 200 真实页面
```

要点：

- 换 token 的这次请求**必须带 Referer**（同站点根路径），否则继续收到挑战页
- 通行 Cookie 名为 `hg_pass`，有效期 2 小时，`HttpOnly` + `Secure`（只能走 https）
- Cookie 按域名在模块级 `CookieJar` 里复用：一次归档里第一篇文章过一遍挑战，后面直接命中

## 用法

```python
import waf

body = fetch(url)                      # 普通下载
if waf.is_challenge(body):             # 是挑战页（体积极小 + 带 _hgk token）
    body = waf.fetch(url, headers, timeout=25, use_proxy=True)
```

`waf.fetch(url, headers=None, timeout=25, use_proxy=True)`：先正常 GET，命中挑战页就自动换 Cookie 再重取，返回响应字节；失败照常抛 `urllib` 异常，行为与直接 `urlopen` 一致。

## 行为要点

- **只额外加一次请求**：页面本身正常时不产生任何开销，只是多一次 `is_challenge()` 判断（长度 + 正则）
- `use_proxy=False` 时用 `ProxyHandler({})` 直连（供 `_NO_PROXY_SITES` 那类站点使用）
- 换 token 的请求不跟随 302（`_StopRedirect`），Cookie 就在响应头里，跟过去等于白下正文
- 最多尝试 2 轮；服务端一直发挑战页时返回最后一次拿到的内容，不无限循环
- 非线程安全（模块级 jar），当前调用方都是串行下载

## 接入点

- `core/save_webpages.py::fetch_url`：读到 `is_challenge()` 为真的响应就交给 `waf.fetch`
- `core/watch_export.py::fetch_feed` / `fetch_html`：同上，保证这类站点也能被订阅检查与「自动找 feed」识别
