---
name: vedio-concentrator
description: >-
  Download a video from a URL (YouTube, Bilibili, Douyin, Xiaohongshu, WeChat Channels, X, and
  1000+ yt-dlp sites) and turn its spoken content into an interactive mind map. Also handles
  existing local media files. Use when the user gives a video link and asks to 下载/保存视频,
  总结视频, 提取字幕/文案, 转文字, 生成脑图/思维导图/mind map, or 把这个视频做成脑图.
  Covers 视频下载, 字幕提取, 语音转写, 视频总结, 脑图生成.
---

# Video → Mind Map

Turn a video URL into: the video file + a clean transcript + an interactive HTML mind map.

## Hard rules

1. **Never bundle the two halves into one blind command.** Downloading and structuring are separate
   steps, and structuring is *your* job. The user wants a mind map, not a transcript dump.
2. **Prefer real subtitles over speech recognition.** If the platform has subtitles, use them —
   they are faster and more accurate than any local model. Only fall back to ASR.
3. **Never summarize from the ASR text alone if the transcript looks broken.** Check a sample of
   10–20 lines first. Garbage in, garbage mind map.
4. **The mind map must be a structure, not a list.** Collapse repetition, group by theme,
   use 2–4 levels, keep every leaf under ~20 characters. Never paste sentences verbatim.
5. **Quote timestamps in the mind map** for key nodes as `(mm:ss)` so the user can jump back.
6. **Downloaded video is for personal use.** Say so if the user asks about redistribution.

## Quick start

```powershell
# 0. one-time check (tells you what is missing)
python "$env:USERPROFILE\.cursor\skills\vedio-concentrator\scripts\setup_check.py"

# 1. download video + subtitles (add --cookies-from-browser chrome if the site needs login)
python "$env:USERPROFILE\.cursor\skills\vedio-concentrator\scripts\v2mm.py" "<URL>" --outdir ".\video_out"

# 2. if the transcript is empty or poor, transcribe the audio locally
python "$env:USERPROFILE\.cursor\skills\vedio-concentrator\scripts\v2mm.py" --transcribe ".\video_out"

# 3. YOU read transcript.txt and write outline.md (see "Structuring" below)

# 4. render the mind map
python "$env:USERPROFILE\.cursor\skills\vedio-concentrator\scripts\render_mindmap.py" `
    --md ".\video_out\outline.md" --out ".\video_out\mindmap.html"
```

Outputs in the outdir: `video.*`, `subs.*`, `transcript.txt`, `transcript.srt`,
`meta.json`, `outline.md`, `mindmap.html`.

## Step 1 — download

`v2mm.py <URL> --outdir <dir>` does everything: resolves short/share links, picks a browser-quality
format, fetches subtitles, exports a normalized transcript, and writes `meta.json`.

Useful flags:

| Flag | When |
|---|---|
| `--cookies-from-browser chrome` | Bilibili 1080p+, Douyin, Xiaohongshu, member-only content |
| `--cookies cookies.txt` | exported Netscape cookie file |
| `--audio-only` | user only wants the content, not the video file |
| `--proxy http://127.0.0.1:7897` | YouTube / blocked sites (auto-detected by hostname) |
| `--lang zh,en` | force subtitle language priority |
| `--max-height 720` | save disk / bandwidth |

Notes that matter in practice:

- **Douyin / Xiaohongshu share links** are short links: always paste them as-is, the script resolves
  the redirect. They usually need cookies; without them yt-dlp reports "no video formats".
- **Bilibili** silently serves 360p without cookies. If quality matters, pass
  `--cookies-from-browser edge|chrome`.
- **YouTube** needs a proxy. The scripts find one automatically — env vars first, then common ports
  on both 127.0.0.1 and ::1, each verified with a real request — and apply it for youtube.com /
  youtu.be / googlevideo hosts. Never hardcode a proxy port for the user; if detection fails, tell
  them to set `VEDIO_CONCENTRATOR_PROXY`. Override per-run with `--proxy` or `--no-proxy`. Longer
  videos often hit "Sign in to confirm you're not a bot" — that one is fixed by
  `--cookies-from-browser edge`, not by changing the proxy.
- **WeChat Channels (视频号)** are not supported by yt-dlp. Tell the user to screen-record or supply
  a local file — then use `v2mm.py --local <file>`.
- The script always hands yt-dlp the bundled ffmpeg. Without it, Bilibili and most modern sites fail
  outright with "merging of multiple formats but ffmpeg is not installed".

## Step 2 — transcript

`v2mm.py` writes `transcript.txt` with `[mm:ss]` line prefixes and `transcript.srt` with real time
codes. Check the first lines:

- **Has content** → go to Step 3.
- **Empty** → run `v2mm.py --transcribe <outdir>`. Uses the local faster-whisper `medium` model
  (CUDA if available, else int8 CPU). Measured on this machine: ~11–17× realtime on GPU, so a
  30-minute video takes about 2 minutes.
- **Content but wrong language / duplicated lines** → re-run with `--transcribe --lang zh` to force it.

If the audio is music or has no speech, VAD filters everything out and the first pass returns zero
segments; the script automatically retries with VAD disabled, so a non-empty result for a song does
not mean it hallucinated. A genuinely empty result means there is no speech in the file.

Long videos (> 60 min) legitimately take minutes. Start it as a background job and keep talking to
the user instead of blocking.

## Step 3 — structuring (your job)

Read `transcript.txt` in full. Then write `outline.md`:

```markdown
# <视频标题>

## <主题块 1>
### <要点>
- <细节> (mm:ss)
### <要点>
- <细节>

## <主题块 2>
...
```

Rules:

1. **3 levels max** below the root (`#` → `##` → `###` → `-`). Deeper than that stops being a map.
2. **Every `##` is a chapter**, in video order. Ask: "if this were a course, what are the modules?"
3. **Kill filler.** Greetings, sponsor reads, "呃/那么/我们来看一下" never make it into the map.
4. **Numbers, names, and steps are the value.** Keep exact figures, product names, and ordered
   procedures; drop adjectives.
5. **Timestamps** on `###` nodes and important leaves: `(12:34)`.
6. **Do not invent content** that is not in the transcript. If a section is thin, keep it thin.

If the user asked for a specific angle ("只总结方法论" / "extract the marketing tactics"), restructure
the outline around that angle instead of following the video's own order.

## Step 4 — render

```powershell
python scripts\render_mindmap.py --md outline.md --out mindmap.html --title "<标题>"
```

Produces a self-contained interactive HTML (pan, zoom, fold/unfold, offline). If
`--theme dark` is passed the page uses a dark palette. Report the absolute path to the user.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no video formats found` | Site needs cookies: `--cookies-from-browser chrome` |
| `Sign in to confirm you're not a bot` | YouTube: `--cookies-from-browser edge` (proxy alone won't fix it) |
| `merging of multiple formats but ffmpeg is not installed` | Run `setup.py`; it installs ffmpeg into the runtime |
| `HTTP Error 403` mid-download | Re-run the same command; yt-dlp resumes |
| `Library cublas64_12.dll is not found` | Should be auto-handled; if not, re-run `setup.py` to reinstall the CUDA runtime |
| ASR is very slow | Check GPU: `python scripts\setup_check.py`; force CPU int8 with `--device cpu` |
| Chinese ASR full of wrong characters | `--prompt "本视频关键词：xxx,yyy"`; or switch to a large-v3 model |
| Mind map is one giant node | Markdown indentation is wrong — `###` needs a blank line before it |
| Mind map page is blank | `render_mindmap.py --selfcheck` to check the markmap assets |

For the full flag list and internals, see [reference.md](reference.md).
