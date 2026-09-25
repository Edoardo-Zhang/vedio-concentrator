# -*- coding: utf-8 -*-
"""render_mindmap.py — 把 Markdown 大纲渲染成离线交互式脑图 HTML（markmap）。

用法:
    python render_mindmap.py --md outline.md --out mindmap.html --title "标题" [--theme dark]
    python render_mindmap.py --selfcheck
"""
import argparse
import glob
import html
import json
import os
import sys

RT = os.environ.get("VEDIO_CONCENTRATOR_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "vedio-concentrator")

ASSET_CANDIDATES = [
    os.path.join(RT, "markmap"),
    os.path.join(os.path.expanduser("~"), ".vedio-concentrator", "markmap"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "markmap"),
]


def find_assets():
    for c in ASSET_CANDIDATES:
        if os.path.isdir(os.path.join(c, "markmap-autoloader")):
            return os.path.abspath(c)
    return None


def pick(base, patterns):
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(base, pat)))
        if hits:
            return hits[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    ap.add_argument("--out")
    ap.add_argument("--title", default="")
    ap.add_argument("--theme", default="auto", choices=["auto", "light", "dark"])
    ap.add_argument("--initial-expand", type=int, default=3,
                    help="默认展开层级，-1 全部展开（默认 3）")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    base = find_assets()
    if a.selfcheck:
        print("markmap assets: %s" % (base or "缺失（先跑 install_runtime.py）"))
        if base:
            for p in ("d3", "markmap-view", "markmap-lib", "markmap-toolbar",
                      "markmap-autoloader", "katex"):
                d = os.path.join(base, p)
                print("  [%s] %s" % ("OK" if os.path.isdir(d) else "!!", p))
        return 0 if base else 1

    if not a.md or not a.out:
        ap.print_help()
        return 2
    if not os.path.exists(a.md):
        print("!! 找不到 %s" % a.md)
        return 1
    with open(a.md, "r", encoding="utf-8") as f:
        md = f.read()

    if not md.strip():
        print("!! 大纲是空的")
        return 1

    if not base:
        print("!! 找不到 markmap 资源，请先运行 install_runtime.py")
        print("   （提示：仍可用支持 markmap 的编辑器直接打开 %s）" % a.md)
        return 1

    d3 = pick(base, ["d3/dist/d3.min.js", "d3/dist/d3.js"])
    view = pick(base, ["markmap-view/dist/browser/index.js",
                       "markmap-view/dist/browser/index.min.js",
                       "markmap-view/dist/index.js"])
    lib = pick(base, ["markmap-lib/dist/browser/index.iife.js",
                      "markmap-lib/dist/browser/index.js",
                      "markmap-lib/dist/browser/index.min.js",
                      "markmap-lib/dist/index.js"])
    toolbar = pick(base, ["markmap-toolbar/dist/browser/index.js",
                          "markmap-toolbar/dist/browser/index.min.js",
                          "markmap-toolbar/dist/index.iife.js",
                          "markmap-toolbar/dist/index.js"])
    missing = [n for n, p in (("d3", d3), ("markmap-view", view), ("markmap-lib", lib)) if not p]
    if missing:
        print("!! 缺少必需资源: %s（在 %s 下）" % (", ".join(missing), base))
        return 1

    def rel(p):
        return os.path.relpath(p, os.path.dirname(os.path.abspath(a.out))).replace("\\", "/")

    def embed(p):
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    title = a.title or os.path.splitext(os.path.basename(a.md))[0]
    md_escaped = md.replace("</script", "<\\/script")
    init = {
        "expand": a.initial_expand,
        "theme": a.theme,
        "toolbar": bool(toolbar),
        "title": title,
    }

    # 依赖内联进 HTML（单文件、离线、可随意拷贝）
    html_doc = TEMPLATE
    for key, val in (("title", html.escape(title)), ("d3", embed(d3)),
                     ("view", embed(view)), ("lib", embed(lib)),
                     ("toolbar", embed(toolbar) if toolbar else ""),
                     ("md", md_escaped),
                     ("init", json.dumps(init, ensure_ascii=False))):
        html_doc = html_doc.replace("/*{{%s}}*/" % key, val)
    html_doc = html_doc.replace("{{theme}}", a.theme)

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_doc)
    # 同时留一份 md 副本，方便用户拿去 Obsidian / XMind
    md_copy = os.path.splitext(out)[0] + ".md"
    if os.path.abspath(a.md) != md_copy:
        with open(md_copy, "w", encoding="utf-8") as f:
            f.write(md)
    print(">>> 脑图: %s  (%.1f KB)" % (out, os.path.getsize(out) / 1024.0))
    print(">>> 大纲副本: %s" % md_copy)
    return 0


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{{theme}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>/*{{title}}*/</title>
<style>
  :root { --bg:#ffffff; --fg:#1f2328; --line:#d8dee4; }
  html[data-theme="dark"], html[data-theme="auto"].dark { --bg:#0d1117; --fg:#e6edf3; --line:#30363d; }
  @media (prefers-color-scheme: dark) {
    html[data-theme="auto"] { --bg:#0d1117; --fg:#e6edf3; --line:#30363d; }
  }
  html, body { margin:0; padding:0; height:100%; background:var(--bg); color:var(--fg);
    font-family:"Microsoft YaHei","PingFang SC","Segoe UI",system-ui,sans-serif; overflow:hidden; }
  #mm { display:block; width:100vw; height:100vh; }
  #bar { position:fixed; left:12px; bottom:12px; z-index:9; display:flex; gap:8px; align-items:center;
    background:var(--bg); border:1px solid var(--line);
    border-radius:8px; padding:6px 10px; font-size:12px; opacity:.94; }
  #bar button { font:inherit; cursor:pointer; border:1px solid var(--line); background:transparent;
    color:var(--fg); border-radius:6px; padding:3px 8px; }
  #bar button:hover { border-color:#888; }
  #mmtb { position:fixed; right:12px; bottom:12px; z-index:9; }
  .mm-tip { position:fixed; right:12px; top:12px; z-index:9; font-size:12px; opacity:.65; }
</style>
</head>
<body>
<svg id="mm"></svg>
<div id="bar">
  <button onclick="mmFit()">适应窗口</button>
  <button onclick="mmZoom(1.25)">放大</button>
  <button onclick="mmZoom(0.8)">缩小</button>
  <button onclick="mmExpand(1)">展开一层</button>
  <button onclick="mmCollapse()">全部折叠</button>
  <button onclick="mmToggleTheme()">主题</button>
</div>
<div class="mm-tip">滚轮缩放 · 拖拽平移 · 点击圆点折叠</div>
<div id="mmtb"></div>

<script id="source" type="text/markdown">/*{{md}}*/</script>
<script>/*{{d3}}*/</script>
<script>/*{{view}}*/</script>
<script>
/*{{lib}}*/</script>
<script>/*{{toolbar}}*/</script>
<script>
window.__err = [];
window.addEventListener('error', function (e) {
  window.__err.push(String(e.message) + ' @' + (e.lineno || '?'));
  var el = document.getElementById('__errdbg');
  if (!el) { el = document.createElement('pre'); el.id = '__errdbg';
    el.style.cssText = 'position:fixed;left:8px;top:8px;z-index:99;color:#c00;font:12px monospace;max-width:60vw;white-space:pre-wrap';
    document.body.appendChild(el); }
  el.textContent = window.__err.join('\n');
});
</script>
<script>
(function () {
  var cfg = /*{{init}}*/;
  var mdEl = document.getElementById('source');
  var md = mdEl.textContent;
  if (!window.markmap || !window.markmap.Transformer || !window.markmap.Markmap) {
    document.body.insertAdjacentHTML('afterbegin',
      '<pre style="padding:16px;white-space:pre-wrap">markmap 资源未加载。</pre>');
    return;
  }
  var transformer = new markmap.Transformer();
  var res = transformer.transform(md);
  var mm = markmap.Markmap.create('#mm', {
    autoFit: false,
    duration: 300,
    initialExpandLevel: cfg.expand,
    spacingVertical: 8,
    spacingHorizontal: 110,
    paddingX: 16,
    maxWidth: 340,
    colorFreezeLevel: 2
  }, res.root);
  window.__mm = mm;
  if (cfg.toolbar && window.markmap.Toolbar) {
    try { document.getElementById('mmtb').appendChild(markmap.Toolbar.create(mm).el); } catch (e) {}
  }
  function isDark() {
    if (cfg.theme === 'dark') return true;
    if (cfg.theme === 'light') return false;
    return document.documentElement.classList.contains('dark') ||
      window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function paint() {
    var fg = isDark() ? '#e6edf3' : '#1f2328';
    document.getElementById('mm').style.background = isDark() ? '#0d1117' : '#ffffff';
    mm.options.style = function (id) {
      return { fill: fg, font: '600 16px "Microsoft YaHei","PingFang SC",sans-serif' };
    };
    if (res.root) { mm.setData(res.root); }
  }
  /* 精确适配：用 getBBox 拿内容真实外接矩形，再算平移+缩放，保证内容一定在视口里。
     低于 MIN 倍会缩得看不清，所以抬到 MIN 并让内容居中。 */
  var MIN = 0.5, MAX = 1.0;
  function fitToContent() {
    var svg = document.getElementById('mm');
    var W = svg.clientWidth || window.innerWidth || 1400;
    var H = svg.clientHeight || window.innerHeight || 800;
    var g = svg.querySelector('g');
    var b = null;
    try { b = g ? g.getBBox() : null; } catch (e) { b = null; }
    if (!b || !b.width || !b.height) { try { mm.fit(); } catch (e2) {} return; }
    var k = Math.min((W - 80) / b.width, (H - 60) / b.height);
    k = Math.max(MIN, Math.min(MAX, k));
    var tx = (W - b.width * k) / 2 - b.x * k;
    var ty = (H - b.height * k) / 2 - b.y * k;
    var t = d3.zoomIdentity.translate(tx, ty).scale(k);
    try {
      mm.transition(svg).call(mm.zoom.transform, t);
    } catch (e3) {
      try { svg.call(mm.zoom.transform, t); } catch (e4) { try { mm.fit(); } catch (e5) {} }
    }
  }
  function doFit() {
    if (!res.root) return;
    mm.setData(res.root);
    setTimeout(fitToContent, 400);
  }
  window.mmFit = doFit;
  window.mmZoom = function (k) { try { mm.rescale(k); } catch (e) {} };
  function setExpand(n) {
    (function walk(node, depth) {
      node.payload = node.payload || {};
      node.payload.fold = n >= 0 && depth >= n ? 1 : 0;
      (node.children || []).forEach(function (c) { walk(c, depth + 1); });
    })(res.root, 0);
    doFit();
  }
  window.mmExpand = function (n) { setExpand(cfg.expand + n); };
  window.mmCollapse = function () { setExpand(1); };
  window.mmToggleTheme = function () {
    document.documentElement.classList.toggle('dark');
    paint();
    doFit();
  };
  paint();
  window.addEventListener('resize', function () { doFit(); });
  setTimeout(doFit, 120);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
