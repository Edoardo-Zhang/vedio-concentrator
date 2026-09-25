# 项目总结：vedio-concentrator 从构想到发布

> 记录这个 Skill 是怎么做出来、怎么发上 GitHub、以及过程中踩过的每一个坑。
>
> 时间：2026-09-25，约 4 小时（01:22 首次提交 → 05:05 发布 v1.0.2）
> 规模：8 次提交 · Python 2049 行 · PowerShell 921 行 · 文档 1316 行

---

## 一、最终形态

```
用户说：把这个视频做成脑图 https://...
        │
        ▼
  ① 下载视频 + 抓字幕 ────── 平台有字幕就直用（快且准）
        │                    没有才走 ②
        ▼
  ② 本地语音识别 ─────────── faster-whisper medium，GPU 11~17 倍实时
        │
        ▼
  ③ 读转写稿写大纲 ───────── 这步是 Agent（我）的活，不是脚本的
        │
        ▼
  ④ 渲染交互式脑图 ───────── 单文件 HTML，可缩放/折叠/离线
```

### 文件清单

| 类别 | 文件 |
|---|---|
| 核心脚本 | `v2mm.py`（下载+转写 644 行）、`render_mindmap.py`（渲染 301 行） |
| 运行时 | `install_runtime.py`（299 行）、`setup.py`、`setup_check.py`、`vcproxy.py` |
| 安装器 | `install.cmd` / `install.ps1`（双击即装）、`bootstrap.ps1`（一行安装） |
| 维护工具 | `更新.cmd`、`build_bundle.ps1`、`check_sync.py`（分叉护栏）、`build_dist.py` |
| 发版工具 | `release.ps1`（379 行，一条命令发版） |
| 演示工具 | `make_gif.ps1`（196 行，生成演示 GIF） |
| 文档 | `skill/SKILL.md`（给 Agent 看）、`README.md`（给用户看）、`GITHUB-GUIDE.md`、`维护必读.md` |

### 发布结果

```
仓库   https://github.com/Edoardo-Zhang/vedio-concentrator
v1.0.2 https://github.com/Edoardo-Zhang/vedio-concentrator/releases/tag/v1.0.2
```

安装包只有 **67 KB** —— 模型和 ffmpeg 不打包，安装时按实测速度选源现下。

---

## 二、四个阶段的演进

### 阶段 1：做出 Skill（01:22）

**第一个关键决策：这不该做成"插件"。**

一开始我说成"装个插件"，你纠正了我。DSH 的 JS 插件（`plugin.json` + 自定义工具）和 Agent Skill
是两套东西。你要的"给链接就下载并生成脑图"是**工作流**，所以做成 Skill（`SKILL.md` + 附带脚本）
才是对的。

**第二个决策：Skill 只放"怎么做"，重活交给独立脚本。**

`SKILL.md` 写流程和判断标准，`v2mm.py` / `render_mindmap.py` 干具体的事。好处是脚本能脱离
Agent 单独用，也能被 Agent 调用。

### 阶段 2：装到本机跑通（01:30~02:00）

装到 `~/.cursor/skills/vedio-concentrator/`（你现有 skill 的同款位置），运行时
（模型/ffmpeg/渲染库，1.6 GB）放 `%LOCALAPPDATA%\vedio-concentrator`。

**按你的工作约定先测速再下载**，实测结论：

| 源 | 直连 | 走代理(7897) |
|---|---|---|
| hf-mirror（模型 1.5 GB） | **59 MB/s** | — |
| github.com（ffmpeg 88 MB） | 不通 | 15 MB/s |
| jsdelivr（markmap） | 8 KB/s（太慢） | — |
| npmmirror（markmap） | 可用 | — |

所以模型走 hf-mirror 直连、ffmpeg 走代理、markmap 走 npmmirror。**没有一个源是全能的。**

### 阶段 3：发上 GitHub（03:00~04:30）

这段最折腾，因为要同时搞定**打包**和**发布**两件事，而你是 GitHub 新手。

关键教训：**"能跑"和"别人能装"是两件事。** 本机跑通只证明了一半，剩下的一半要靠
"当自己是陌生人，从 GitHub 下载再装一遍"来验证。

### 阶段 4：打磨与自动化（04:30~05:05）

徽章、演示 GIF、三份拷贝的护栏、一条命令发版。

---

## 三、踩过的 13 个坑（按类型分）

这一节是这份文档的核心。**每个坑都是实际调试出来的，不是预想的。**

### A. 编码类（Windows 上最集中，共 5 个）

#### A1. `.cmd` 用 LF 换行 → cmd.exe 把注释拆行执行

**症状**：`install.cmd` 报 `'选参数：install.cmd' is not recognized as an internal or external command`

**原因**：batch 文件必须是 CRLF。用 LF 时 `rem` 注释没被正确识别，后面的内容被当命令执行。

**修法**：打包时统一转 CRLF。

#### A2. `.ps1` 无 BOM → PowerShell 5.1 按 ANSI 解析

**症状**：`字符串缺少终止符`、`意外的标记`，指向看起来完全正常的行。

**原因**：PowerShell 5.1 对无 BOM 的 UTF-8 脚本按系统 ANSI（中文机器是 GBK）解析，
中文注释被解码成乱码，里面的引号打破了字符串边界。

**修法**：`.ps1` 必须带 UTF-8 BOM。

#### A3. 注释里的 ASCII 双引号 + 编码问题

**症状**：`[string]$Title = "",   # 默认 "v<版本>"` 报 `赋值表达式无效`。

**排查过程**：先怀疑引号 → 写最小复现 → **加 BOM 后正常** → 说明不是引号本身的问题，
是文件编码坏了。

**修法**：重写整个文件（在坏文件上打补丁会越修越坏）。

#### A4. 中文注释被 `Set-Content -Encoding UTF8` 弄坏

**症状**：`.gitignore` 里 `# 运行时产物与本地测试` 变成 `# 杩愯鏃朵骇鐗╀笌鏈湴娴嬭瘯`。

**原因**：PowerShell 读无 BOM 的 UTF-8 文件时按 ANSI 解码，再按 UTF-8 写回 = 双重编码。

**修法**：用 Python 或 `edit` 工具处理文本文件，别用 `Set-Content`。**这个坑我在同一个项目里踩了两次。**

#### A5. `Out-String` 的 `\r` 混进正则捕获

**症状**：GitHub 令牌长度变成 41（应该是 40），API 调用报莫名其妙的 401/404。

**原因**：`Out-String` 输出行尾是 `\r\n`，正则 `^password=(.*)` 把 `\r` 一起捕获了。

**修法**：`.Trim()`。

### B. PowerShell 陷阱（共 3 个）

#### B1. 原生命令的 stderr 会中断脚本 ⭐ 最隐蔽

**症状**：`msedge.exe : 22403 bytes written to file ...` 然后**整个脚本终止**。

**原因**：Edge / ffmpeg / git 都把**正常日志**写到 stderr。PowerShell 5.1 把原生命令的
stderr 包装成错误记录，配合 `$ErrorActionPreference = 'Stop'` 直接中断。

**反直觉点**：`2>&1 | Out-Null` **不管用**，必须包在 script block 里用 `2>$null`：

```powershell
function Invoke-Quiet {
    param([scriptblock]$Block)
    & $Block 2>$null | Out-Null      # 是 2>$null，不是 2>&1
}
```

**这个坑在项目里出现了三次**（Edge 截图、ffmpeg 合成、git push）。

#### B2. `Invoke-Quiet` 吞掉 `$LASTEXITCODE` ⭐

**症状**：故意让 git 失败，`$LASTEXITCODE` 仍然是 0。推送重试逻辑永远失效。

**原因**：块内的 `| Out-Null` 会重置 `$LASTEXITCODE`。

**修法**：需要退出码时用 `Start-Process -Wait -PassThru` 取 `.ExitCode`。

#### B3. `$Width:-1` 被解析成作用域变量

**症状**：`变量引用无效。':' 后面的变量名称字符无效`

**原因**：ffmpeg 的 `scale=1200:-1` 参数拼在双引号字符串里，PowerShell 把 `$Width:` 当成
作用域限定符。

**修法**：用 `${Width}` 明确边界。

### C. 逻辑类（共 3 个）

#### C1. yt-dlp 的 `download=False` 不写字幕

**症状**：`--no-video` 时提示"可用字幕: en"，但磁盘上什么也没有。

**原因**：yt-dlp 只在 `download=True` 时才写文件。`download=False` 是纯查询。

**修法**：始终 `download=True`，用 `skip_download: True` 阻止下媒体。

#### C2. `-NotesFile` 被静默忽略 ⭐ 最危险

**症状**：发布出去的 Release 说明是错的（全是重复的提交行），**脚本没报任何错**。

**原因**：`build_dist.py` 会清空整个 `dist/` 目录，而说明文件放在 `dist/` 里 →
第 5 步读时已被删除 → 静默回退到"自动收集提交"。

**修法**：① 脚本一开始就把说明读进内存；② 文件不存在时**直接报错退出**，不静默回退。

**教训**：不报错的 bug 比报错的 bug 危险得多。

#### C3. 截图拍到空白图

**症状**：无头浏览器截图时好时坏，`--virtual-time-budget` 30000 出图、60000 反而空白。

**原因**：脑图加载有 d3 过渡动画，无头浏览器不等动画结束就抓帧。

**修法**：给渲染器加 `?static=1` 参数关掉动画。调大 virtual-time-budget 是碰运气，不是解法。

**附带发现**：`file://` 协议下截图不稳定，必须走本地 HTTP 服务。

### D. 其他（共 2 个）

#### D1. 代理端口写死 + 只探测 IPv4

**症状**：探测不到代理（你的 Clash 监听的是 `::`，不是 `127.0.0.1`）。

**修法**：`vcproxy.py` 同时探测 `127.0.0.1` 和 `::1`，并且**真发一次请求验证**
（端口开着≠协议对，把 SOCKS 当 HTTP 用会失败）。

#### D2. git 的 HTTP/2 与国内代理不兼容

**症状**：`TLS connect error: error:0A000126:SSL routines::unexpected eof while reading`

**修法**：`git config http.version HTTP/1.1`，推送加重试。

**但要如实说**：这是**缓解不是根治**。实测代理访问 GitHub 约 10 次成功 1~3 次，很不稳。

### 附：还有两个"不是 bug 但很坑"

- **Desktop 建仓库会套一层子目录**：选中 `gh-publish` 当路径，Desktop 理解成"在它**里面**
  再建一个同名文件夹"，结果仓库建到了 `gh-publish\gh-publish\`。用
  **File → Add local repository** 入口更安全。
- **GitHub 的 Assets 永远至少显示 2 个**（自动生成的源码包），所以 `Assets (2)` 不代表
  你传成功了。判据是**有没有你上传的那个文件名**，发布前要看着数字从 `(2)` 变成 `(3)`。

---

## 四、关键设计决策

### 1. 为什么不做成"插件"

DSH 的插件是给 Agent 加**工具**，Skill 是给 Agent 加**工作流**。你要的是后者。
做成 Skill 还有个好处：脚本能独立使用，不绑定 Agent。

### 2. 为什么要区分"给 Agent 看"和"给用户看"的文档

| 文档 | 读者 | 内容侧重 |
|---|---|---|
| `SKILL.md` | Agent（我） | 判断标准、硬规则、"什么情况下该怎么做" |
| `README.md` | 人类用户 | 怎么装、怎么用、装完什么样 |
| `维护必读.md` | 未来的你 | 三份拷贝的关系、发版流程 |
| `reference.md` | Agent + 高级用户 | 全部参数、站点矩阵、性能数据 |

**Agent 看的文档要写"判断依据"，用户看的文档要写"操作步骤"。** 混在一起两边都不好用。

### 3. 为什么打包要规范化编码

打包脚本（`build_dist.py`）会自动处理：

| 扩展名 | 编码 | 行尾 |
|---|---|---|
| `.ps1` | UTF-8 **with BOM** | CRLF |
| `.cmd` | GBK(cp936) | CRLF |
| 其他 | UTF-8 无 BOM | CRLF |

这不是洁癖——**不这么做，别人下载后根本装不上**（坑 A1、A2）。

### 4. 为什么要"三份拷贝护栏"

本机同时存在三份 vedio-concentrator：

```
打包源 (vedio-concentrator)  ←→  Git仓库 (gh-publish)   镜像关系，必须一致
                                        │
                                        ▼
                                 已安装 (~/.cursor/skills/)  子集，只装该跑的
```

改了其中一份忘了另外两份 → "GitHub 上是新版、你自己机器上还是旧版"。
`check_sync.py` 就是干这个的，它比对内容时**忽略 BOM/换行/编码差异**，所以不会误报。

### 5. 为什么发版要做成一条命令

**因为手动发版漏了"上传附件"，GitHub 不会提醒你，Release 照样发布成功。**
v1.0.1 就这么漏过一次——用户下载不到任何东西。

`release.ps1` 的第 7 步会**重新从 GitHub 读回来核对**附件大小和 SHA256，对不上就报错退出。

---

## 五、可复用的经验

### 对你自己

1. **"能跑"和"别人能装"是两件事。** 交付前必须当陌生人在干净环境验一遍。
2. **Windows 上的文本编码是持续的麻烦。** 处理脚本文件时，优先用能明确指定编码的工具，
   别用 `Set-Content`。
3. **不报错的失败最危险。** 静默回退（比如"文件读不到就自动收集"）看起来友好，
   实际会把错误信息发出去。宁可报错停下。
4. **网络不稳时，重试比优化单次成功率更有效。** 推送加 4 次重试后基本都能过。

### 如果要做下一个 Skill

```
1. SKILL.md 写流程和判断标准；重活放独立脚本
2. 先测速再下载大文件（模型/依赖）
3. 同一条链路，先在本机跑通，再打包，再发版——三件事分开验证
4. 交付前用陌生人的方式装一遍
5. 需要人手点的步骤，尽量自动化（人手点 = 会漏）
```

### 一个调试方法论

这个项目里最有效的调试动作是**"写最小复现"**：

- 坑 A3（注释引号）→ 写 6 行脚本复现 → 发现加 BOM 就好 → 定位到是文件编码坏了
- 坑 B2（LASTEXITCODE）→ 故意让 git 失败 → 发现退出码还是 0 → 定位到 Out-Null
- 坑 C3（空白截图）→ 加 `__err` / `__dbg` 面板回显到 DOM → 发现是动画时序

**别猜。写 10 行代码验证你的假设。** 我在这上面浪费的时间，比实际修复的时间还多。

---

## 六、已知未解决 / 有风险的项

| 项 | 状态 |
|---|---|
| 代理访问 GitHub 不稳定 | 已加重试，未根治。建议开代理 TUN/全局模式 |
| 微信视频号不支持 | yt-dlp 限制，只能录屏或给本地文件 |
| 抖音/小红书常需 cookie | 只能用 `--cookies-from-browser`，无法完全自动 |
| `?static=1` 只为自动化 | 手动打开脑图不需要，别误加 |
| GIF 脚本的展开层级要手工同步 | 换大纲后需改 `make_gif.ps1` 里的 `$levels` |

---

## 七、时间线

| 时间 | 里程碑 | 提交 |
|---|---|---|
| 01:22 | 首次提交 v1.0.0（下载+转写+脑图跑通） | `53144e2` |
| 02:xx | 加维护工具、护栏、GITHUB-GUIDE | `81689b8` |
| 03:xx | README 徽章 + 稳定截图模式 | `86ff4f2` `a730777` |
| 04:xx | 演示 GIF + make_gif.ps1 | `1d61685` |
| 04:xx | release.ps1 一键发版 | `e734a22` |
| 05:05 | 发布 v1.0.2，历史清理 | `9b263e5` |

3 个 Release（v1.0.0 / v1.0.1 / v1.0.2），全部附件完好、哈希可校验。
