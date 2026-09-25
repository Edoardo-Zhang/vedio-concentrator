# -*- coding: utf-8 -*-
"""vcproxy.py — 代理探测（v2mm.py / install_runtime.py 共用）。

解决的问题：
  * 不同人的代理客户端端口不一样（7897 / 7890 / 10809 / 1080 / 2080 ...），
    不能写死一个端口。
  * Windows 上很多客户端监听的是 IPv6 回环 `::1` 而不是 `127.0.0.1`，
    只测 IPv4 会漏掉。
  * 端口开着不代表协议对（SOCKS 端口当 HTTP 用会失败），所以要真发一次请求验证。

优先级：环境变量 > 自动探测（逐个候选做真实 HTTP 连通性验证）> 不代理。
"""
import os
import socket
import urllib.request

# 环境变量名，按优先级排列。前两个是本项目专用，后面兼容通用约定。
ENV_NAMES = ("VEDIO_CONCENTRATOR_PROXY", "HTTPS_PROXY", "https_proxy",
             "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")

# 常见客户端的 HTTP 代理端口
#   7897/7890 Clash 系  10809 v2rayN  10808/1080 常见混合端口
#   2080/20171 部分客户端  8118 privoxy  8889 其它
PORTS = (7897, 7890, 10809, 10808, 1080, 2080, 20171, 8118, 8889)

HOSTS = ("127.0.0.1", "::1")

# 用来验证代理是否真能用的地址。选一个稳定、体积极小、国内也能直连的端点，
# 这样即使代理挂了也不会误判成可用。
CHECK_URLS = ("http://www.gstatic.com/generate_204",)
TIMEOUT = 3.0

_UNSET = object()
_cache = _UNSET


def _env_proxy():
    for name in ENV_NAMES:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    return None


def _port_open(host, port):
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except OSError:
        return False
    for family, _type, _proto, _canon, addr in infos:
        s = socket.socket(family, socket.SOCK_STREAM)
        s.settimeout(0.25)
        try:
            if s.connect_ex(addr) == 0:
                return True
        except OSError:
            pass
        finally:
            s.close()
    return False


def _proxy_works(url):
    """真发一次请求确认这个代理可用（端口开着≠协议对）。"""
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": url, "https": url}))
    for target in CHECK_URLS:
        try:
            with op.open(target, timeout=TIMEOUT) as r:
                if r.status < 400:
                    return True
        except Exception:
            continue
    return False


def detect(verbose=False):
    """返回探测到的代理 URL；没有可用代理则返回 None。结果会缓存。"""
    global _cache
    if _cache is not _UNSET:
        return _cache

    env = _env_proxy()
    if env:
        # 环境变量是用户显式指定的，信任它，不做连通性验证
        # （有人就是要在不通代理的情况下用直连降级）
        if verbose:
            print("[代理] 使用环境变量: %s" % env)
        _cache = env
        return env

    for port in PORTS:
        for host in HOSTS:
            if not _port_open(host, port):
                continue
            hostpart = "[%s]" % host if ":" in host else host
            url = "http://%s:%d" % (hostpart, port)
            if _proxy_works(url):
                if verbose:
                    print("[代理] 自动探测到可用代理: %s" % url)
                _cache = url
                return url
            if verbose:
                print("[代理] %s 端口开着但连不通，跳过" % url)

    if verbose:
        print("[代理] 未探测到可用代理，将使用直连")
    _cache = None
    return None


def accepted_proxy(extra=()):
    """给 install_runtime 这类"多候选源"场景用：返回可用的代理 URL，
    没有则返回 None；调用方把 (url, proxy) 组成候选列表即可。"""
    p = detect()
    if p:
        return p
    for e in extra:
        if e:
            return e
    return None
