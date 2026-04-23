# Agent Setup Guide

本文档面向 Hermes、Claude、Codex 等自动化代理，用于在干净环境里部署、验证和维护本项目。

## 项目目标

Video Transcript Workflow 将以下输入整理成可交给长上下文模型的资料包：

- Bilibili 视频 URL
- YouTube 视频 URL
- 本地音频/视频文件，例如 `.mp3`、`.m4a`、`.wav`、`.mp4`

生成结果用于继续产出高质量 Obsidian 学习笔记。

## 仓库结构

```text
config/
  credentials.example.yaml
  cookies/.gitkeep
scripts/
  main.py
  fetch_base.py
  fetch_single.py
  fetch_bilibili.py
  fetch_youtube.py
  export_bundle.py
  transcribe.py
  generate_notes.py
  sync.py
templates/
  prompt.md
  video_note.md
requirements.txt
README.md
AGENT_SETUP.md
```

## 禁止提交

不要提交以下文件或目录：

- `config/credentials.yaml`
- `config/cookies/*`，但保留 `config/cookies/.gitkeep`
- `output/`
- 本地媒体文件：`*.mp3`、`*.m4a`、`*.mp4`、`*.wav` 等
- `scripts/__pycache__/`、`.pytest_cache/`、虚拟环境目录
- `.env` 或任何包含 token/cookie/password 的文件

`.gitignore` 已覆盖这些路径。若新增输出目录，先更新 `.gitignore`。

## 环境准备

使用 Python 3.11+：

```powershell
python -m pip install -r requirements.txt
```

核心依赖：

- `PyYAML`
- `yt-dlp`
- `faster-whisper`

`faster-whisper` 首次运行会下载模型权重，可能需要较长时间和额外磁盘空间。

## 可选本地配置

仅在需要 cookies、收藏夹同步或默认 Whisper 参数时创建真实配置：

```powershell
Copy-Item config/credentials.example.yaml config/credentials.yaml
```

cookies 文件必须是 Mozilla/Netscape 格式，放在：

```text
config/cookies/
```

示例：

```text
config/cookies/bilibili_netscape.txt
```

## 常用命令

编译检查：

```powershell
python -m compileall scripts
```

从剪贴板 URL 导出资料包：

```powershell
python scripts/main.py --bundle
```

从显式 URL 导出资料包：

```powershell
python scripts/main.py --bundle "https://www.bilibili.com/video/BVxxxxxxxxxx/"
```

强制 Whisper 转录：

```powershell
python scripts/main.py --bundle --transcribe --whisper-model small --whisper-language zh "https://www.bilibili.com/video/BVxxxxxxxxxx/"
```

处理本地音视频：

```powershell
python scripts/main.py --media-file "C:\path\to\audio.mp3" --whisper-model small --whisper-language zh
```

## 输出契约

每次成功导出 bundle 后，目录结构应为：

```text
output/bundles/<bundle-name>/
  metadata.json
  raw.json
  source.md
  transcript.txt
  transcript_segments.json
  transcript_timestamps.md
  prompt.md
```

`prompt.md` 由 `templates/prompt.md` 渲染生成。

## Prompt 模板契约

`templates/prompt.md` 可以使用以下占位符：

```text
{metadata_json}
{source_markdown}
{transcript_text}
{transcript_segments_json}
{extra_context}
```

如果修改模板，请保留这些占位符，或者同步更新 `scripts/export_bundle.py`。

## 质量与安全规则

1. 先检查 `.gitignore`，再添加任何生成物。
2. 至少运行 `python -m compileall scripts`。
3. 不要在未被明确要求时运行耗时很长的 Whisper 转录。
4. 不要打印 cookies、PAT、API key 或其他凭据。
5. 所有生成输出都应留在 `output/`。
6. 若需要真实 cookies，请让用户在本地配置，不要把内容写入仓库。

## 已知非目标

- 不绕过 DRM。
- 不提供 Douyin 抓取支持。
- 默认不调用模型 API 自动生成最终笔记。
- 暂不做硬字幕 OCR。
