# Video Transcript Workflow

把 Bilibili、YouTube 视频链接或本地音视频文件整理成可直接交给 ChatGPT、Claude、Gemini 等长上下文模型的资料包，用于生成 Obsidian 学习笔记。

项目目标不是直接写一篇浅总结，而是稳定产出一组高质量原始资料：

- `metadata.json`
- `raw.json`
- `source.md`
- `transcript.txt`
- `transcript_segments.json`
- `transcript_timestamps.md`
- `prompt.md`

其中 `prompt.md` 会自动套用 `templates/prompt.md`，适合直接粘贴给大模型继续生成结构化学习笔记。

## 支持范围

| 输入类型 | 状态 | 说明 |
| --- | --- | --- |
| Bilibili 单视频 | 可用 | 优先抓取平台字幕，必要时可强制 Whisper 转录 |
| YouTube 单视频 | 可用 | 优先抓取字幕/自动字幕，必要时可强制 Whisper 转录 |
| 本地音频/视频 | 可用 | 适合播客、会议录音、手动下载的音视频 |
| Bilibili/YouTube 收藏夹 | 基础可用 | 保留旧的增量同步能力 |

## 快速开始

建议使用 Python 3.11+。

```powershell
python -m pip install -r requirements.txt
```

`faster-whisper` 首次运行会下载模型权重。中文内容建议从 `small` 模型起步；只测试链路时可用 `tiny`。

## 可选配置

公开视频通常不需要 cookies。需要登录态的视频或收藏夹同步，可以复制配置模板：

```powershell
Copy-Item config/credentials.example.yaml config/credentials.yaml
```

然后把 Netscape 格式 cookies 文件放入：

```text
config/cookies/
```

真实 cookies、`config/credentials.yaml`、输出目录、本地媒体文件都已被 `.gitignore` 排除，不应提交到仓库。

## 常用命令

从剪贴板读取视频链接并导出 AI 输入包：

```powershell
python scripts/main.py --bundle
```

指定视频链接：

```powershell
python scripts/main.py --bundle "https://www.bilibili.com/video/BVxxxxxxxxxx/"
```

强制使用 Whisper 转录：

```powershell
python scripts/main.py --bundle --transcribe --whisper-model small --whisper-language zh "https://www.bilibili.com/video/BVxxxxxxxxxx/"
```

处理本地音视频文件：

```powershell
python scripts/main.py --media-file "C:\path\to\episode.mp3" --whisper-model small --whisper-language zh
```

## 输出结构

```text
output/bundles/<platform-or-local-id>/
  metadata.json
  raw.json
  source.md
  transcript.txt
  transcript_segments.json
  transcript_timestamps.md
  prompt.md
```

`prompt.md` 是给大模型处理的输入包，不是最终笔记。最终笔记建议在模型端生成后再人工校对。

## 给代理的部署指南

Hermes、Claude、Codex 等自动化代理可以优先阅读：

```text
AGENT_SETUP.md
```

该文档包含环境准备、禁止提交的文件、常用命令、验证方式和安全工作流。

## 注意事项

- 不提交任何 cookies、真实配置、输出 bundle、数据库或媒体文件。
- Douyin 等强风控平台不在当前支持范围内；如果已获得本地音频文件，请使用 `--media-file`。
- 如果 YouTube 触发 429，或 Bilibili 字幕缺失/错配，可以使用 `--transcribe` 强制 Whisper。
- 长音频在 CPU 上转录可能耗时较久。
