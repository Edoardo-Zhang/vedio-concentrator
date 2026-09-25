## 本次更新

### 新增
- **演示 GIF**：README 顶部换成脑图逐层展开的动画（120 KB，7.3 秒）
- **`scripts/release.ps1`**：一条命令完成发版全流程
  （改版本号 → 打包 → 推送 → 建 tag → 建 Release → 传附件 → 回填 SHA256 → 校验）
- **`scripts/make_gif.ps1`**：把脑图的展开过程做成演示 GIF
- **脑图 HTML 支持三个 URL 参数**，方便自动化截图/录屏：
  - `?static=1` 关掉动画一次性定型
  - `?expand=N` 覆盖展开层级
  - `?theme=dark` 覆盖主题

### 修复
- **`render_mindmap.py` 截图时提到空白图**：页面加载动画未结束时无头浏览器就抓帧。
  现在用 `?static=1` 可稳定复现，连跑三次结果字节数一致
- **`release.ps1` 在 Windows 上无法解析**：脚本经过多次编码转换后被损坏，
  已重写并统一为 UTF-8 with BOM + CRLF
- **推送遇到代理 TLS 失败**：git 默认的 HTTP/2 与国内代理不兼容，
  现在自动降级到 HTTP/1.1 并重试

### 说明
- `?static=1` 是**给自动化用的**，手动打开脑图不需要加
- GIF 由 `make_gif.ps1` 生成，改大纲后重跑即可，注意同步脚本里的展开层级数组
