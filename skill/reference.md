# vedio-concentrator — 参考手册

## 文件与目录

### Skill 目录
```
C:\Users\Lenovo\.cursor\skills\vedio-concentrator\
├── SKILL.md              # 触发条件 + 四步工作流
├── reference.md          # 本文件
├── setup.py              # 安装/修复运行时（幂等）
├── install_runtime.py    # 真正干活的安装器
└── scripts\
    ├── v2mm.py           # 下载 + 字幕 + ASR
    ├── render_mindmap.py # Markdown 大纲 -> 交互式脑图 HTML
    └── setup_check.py    # 环境自检（含 GPU 探测）
```

### 运行时目录
```
%LOCALAPPDATA%\vedio-concentrator\
├── bin\        ffmpeg.exe, ffprobe.exe
├── models\     faster-whisper-medium\  (model.bin ~1.5GB + config/tokenizer/vocab)
├── markmap\    markmap-lib / markmap-view / d3（离线渲染用）
├── cache\      下载临时文件
└── logs\       install.log, install.done
```

想换盘：设 `VEDIO_CONCENTRATOR_HOME=D:\vedio-concentrator` 后重跑 `setup.py`，并在调用脚本的会话里保持该环境变量。

## 〇、代理（自动探测，通常不用配）

`vcproxy.py` 是唯一的代理来源，`v2mm.py` 和 `install_runtime.py` 共用它。

优先级：`VEDIO_CONCENTRATOR_PROXY` > `HTTPS_PROXY` > `HTTP_PROXY` > 自动探测 > 直连。

自动探测会遍历这些端口：`7897` `7890`（Clash 系）、`10809` `10808`（v2rayN）、
`1080` `2080` `20171` `8118` `8889`；每个端口在 `127.0.0.1` 和 `::1` 上都试
（Windows 上不少客户端只监听 IPv6 的 `::`，只测 IPv4 会漏）。**端口开着不算数**——
还会真发一次 `generate_204` 请求验证，因为把 SOCKS 端口当 HTTP 用会失败。

环境变量被视为用户显式意图，不再做连通性验证（有人就是要它原样生效）。

```powershell
$env:VEDIO_CONCENTRATOR_PROXY = "http://127.0.0.1:你的端口"   # 临时
[Environment]::SetEnvironmentVariable("VEDIO_CONCENTRATOR_PROXY","http://127.0.0.1:你的端口","User")  # 永久
```

调试：

```powershell
python -c "import sys;sys.path.insert(0,r'<skill>\scripts');import vcproxy;vcproxy.detect(verbose=True)"
```

代码里要拿代理，别自己写死端口：

```python
import vcproxy
proxy = vcproxy.detect()          # 可能是 None，表示直连
```

## 一、站点支持与注意事项

| 站点 | 下载 | 字幕 | 备注 |
|---|---|---|---|
| YouTube | ✓ 走代理 | 人工+自动字幕齐全 | 代理自动探测；长视频易触发 bot 校验，用 `--cookies-from-browser edge` |
| Bilibili | ✓ | 人工/AI 字幕 | 不带 cookie 只有 360p；`--cookies-from-browser chrome` 可上 1080p |
| 抖音 | ✓ 短链自动还原 | 多数无字幕 | 常需 cookie；无字幕就走 ASR |
| 小红书 | ✓ | 多数无字幕 | 需 cookie；笔记页链接可能取不到视频，用分享短链 |
| 微信视频号 | ✗ | — | yt-dlp 不支持，让用户录屏或给本地文件 |
| X / Twitter | ✓ 走代理 | 部分有 | |
| 1000+ 其它站 | ✓ | 视站点 | yt-dlp 官方支持列表 |

平台规则会变。下载失败先 `python -m pip install -U yt-dlp`，这是最常见的一行修复。

## 二、v2mm.py 全部参数

```
python v2mm.py <URL> --outdir <dir> [选项]
python v2mm.py --local <文件> --outdir <dir>
python v2mm.py --transcribe <dir> [--media <文件>]
python v2mm.py --check <dir>
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--outdir, -o` | `.` | 输出目录，自动创建 |
| `--local` | — | 用本地媒体文件，跳过下载 |
| `--transcribe` | — | 只跑 ASR |
| `--check` | — | 列出目录里已有的产物 |
| `--media` | 自动挑最大 | 指定转写哪个文件 |
| `--cookies` | — | Netscape 格式 cookie 文件 |
| `--cookies-from-browser` | — | `chrome` / `edge` / `firefox` |
| `--proxy` | 按域名自动 | 显式指定代理 |
| `--no-proxy` | — | 强制直连 |
| `--lang` | `zh-Hans,zh-CN,...,en` | 字幕语言优先级；ASR 时取第一项作为强制语言 |
| `--max-height` | 1080 | 画质上限 |
| `--audio-only` | — | 只下音频 |
| `--no-video` | — | 只取元信息+字幕，不下载媒体 |
| `--model` | medium | 其它 faster-whisper 模型目录 |
| `--device` | auto | `auto` / `cuda` / `cpu` |
| `--compute-type` | auto | GPU→float16，CPU→int8 |
| `--beam-size` | 5 | 1 更快，5 更准 |
| `--prompt` | — | 初始提示，喂专有名词能明显降错字 |

## 三、产物说明

| 文件 | 内容 |
|---|---|
| `<id>.<ext>` | 视频本体（`--audio-only` 时是音频） |
| `<id>.<lang>.srt` | 平台原始字幕（`convert_subs_to_srt` 统一成 srt） |
| `transcript.txt` | **主输入**：`[mm:ss] 文本` 逐行，已去重去空 |
| `transcript.srt` | 带时间码，可拖进播放器对照 |
| `audio16k.wav` | ASR 用的中间音频，可删 |
| `meta.json` | 标题/UP主/时长/播放量/简介/来源链接 |
| `outline.md` | **你写的大纲**，脑图的唯一输入 |
| `mindmap.html` | 交互式脑图（依赖已内联，单文件离线可用） |
| `mindmap.md` | 大纲副本，可导入 Obsidian / XMind |

## 四、ASR 性能参考

本机 RTX 5070 Laptop 8GB + 31GB 内存：

| 配置 | 速度 | 说明 |
|---|---|---|
| CUDA float16 | 8~20× 实时 | 需 cuBLAS + cuDNN9（install_runtime.py 会装） |
| CPU int8 | 0.4~0.6× 实时 | 1 小时视频约 2 小时；GPU 不可用时的兜底 |

长视频务必用后台任务跑，不要阻塞对话：

```powershell
Start-Process -NoNewWindow python -ArgumentList 'v2mm.py','--transcribe','<dir>'
```

## 五、写 outline.md 的具体标准

```markdown
# 视频标题

## 01 章节名（要有信息量，别写"第一部分"）
### 要点标题
- 具体细节、数字、步骤 (12:34)
- 另一个细节

## 02 章节名
...
```

- 根节点之后最多三层；再深就不是脑图了
- `##` 按视频时间顺序排列，等于"课程模块"
- 数字、专有名词、操作步骤必须保真；形容词全部丢掉
- 时间码加在 `###` 和关键叶子上
- 只写转写里出现过的内容，不要脑补

## 六、故障速查

| 症状 | 原因 / 处理 |
|---|---|
| `no video formats found` | 需要 cookie：`--cookies-from-browser chrome` |
| `Sign in to confirm you're not a bot` | YouTube 没走代理：加 `--proxy http://127.0.0.1:7897` |
| 下载中途 403 | 直接重跑同一条命令，yt-dlp 会续传 |
| 字幕下到了但不是中文 | `--lang zh` 强制；或看 `*.srt` 文件名 |
| transcript 只有几十字 | 自动字幕缺内容，改跑 `--transcribe` |
| ASR 特别慢 | `setup_check.py` 看 GPU 是否可用；不行就 `--device cpu` 认命 |
| 中文错字多 | `--prompt "本视频关键词：xxx,yyy"`；或换 large-v3 模型 |
| 脑图只有一个大节点 | Markdown 层级不对：`###` 前要有空行，缩进用 `-` |
| HTML 打开空白 | 用 `render_mindmap.py --selfcheck` 查 markmap 资源 |
| 模型下载中断 | 重跑 `setup.py`，断点续传 |

## 七、换用更大的模型

```powershell
# 例：large-v3（~3GB，中文明显更准，速度约为 medium 的 1/3）
$d = "$env:LOCALAPPDATA\vedio-concentrator\models\faster-whisper-large-v3"
# 从 https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/ 取
#   model.bin config.json tokenizer.json vocabulary.txt (preprocessor_config.json)
python scripts\v2mm.py --transcribe <dir> --model $d
```

其它可选：`faster-whisper-small`（快 3 倍，中文错字偏多）、`faster-whisper-large-v3-turbo`。
