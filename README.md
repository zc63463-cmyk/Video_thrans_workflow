# Video Collector

> 把 Bilibili / YouTube 视频或本地音视频整理成 AI 可直接处理的资料包

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/zc63463-cmyk/Video_thrans_workflow.git
cd Video_thrans_workflow

# 2. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 3. 迁移/部署自检
python scripts/doctor.py

# 4. 运行 — 无参数进入交互式菜单
python scripts/main.py
```

首次运行会自动创建 `output/` 目录结构，如无配置文件会提示是否从模板创建。

## 30 秒上手

```bash
# 从剪贴板读取视频链接，导出 AI 输入包
python scripts/main.py --bundle

# 指定链接
python scripts/main.py --bundle "https://www.bilibili.com/video/BVxxxxxxxxxx/"

# 强制下载音频并用 Whisper 转录
python scripts/main.py --bundle --transcribe "https://www.bilibili.com/video/BVxxxxxxxxxx/"

# 本地音频/视频 → Whisper 转录 + AI 输入包
python scripts/main.py --media-file "path/to/podcast.mp3"

# 批量处理（每行一个 URL 的文本文件）
python scripts/main.py --bundle --url-file urls.txt --workers 3
```

## 支持的输入

| 输入 | 说明 |
|------|------|
| Bilibili 视频 | `bilibili.com/video/BV...` 或 `b23.tv/...` 短链 |
| YouTube 视频 | `youtube.com/watch?v=...` 或 `youtu.be/...` 短链 |
| 本地音视频 | `.mp3` `.m4a` `.wav` `.mp4` `.mkv` 等格式 |

## 输出结构

```
output/bundles/<platform>-<video_id>-<title>/
  metadata.json              # 视频元数据
  raw.json                   # yt-dlp 原始抓取数据
  source.md                  # 原始资料 Markdown
  transcript.txt             # 转录纯文本
  transcript_segments.json   # 分段转录（含时间戳）
  transcript_timestamps.md   # 带时间戳的转录
  prompt.md                  # 给大模型的输入包 ← 核心产出
```

`prompt.md` 使用 `templates/prompt.md` 渲染，可直接粘贴给 ChatGPT / Claude / Gemini 等模型。

## 可选配置

公开视频**不需要任何配置**。以下场景需要配置：

- 需要登录才能观看的视频 → 配置 cookies
- 收藏夹同步 → 配置 cookies + 收藏夹 URL
- 自定义 Whisper 参数 → 配置 whisper 段

```bash
# 从模板创建配置文件
cp config/credentials.example.yaml config/credentials.yaml
```

然后编辑 `config/credentials.yaml`，将 Netscape 格式的 cookies 文件放入 `config/cookies/`。

## Whisper 转录

默认优先抓取平台自带字幕。如需强制使用 Whisper 转录：

```bash
# 先安装 Whisper 后端（二选一）
pip install faster-whisper    # 推荐，速度快
# pip install openai-whisper  # 官方版

# 强制转录
python scripts/main.py --bundle --transcribe --whisper-model small "https://..."
```

## 迁移部署自检

换机器或更新 cookies 后，先跑诊断：

```bash
# 检查 Python / yt-dlp / 配置路径
python scripts/doctor.py

# 检查指定 B 站视频是否能解析并下载音频
python scripts/doctor.py "https://www.bilibili.com/video/BVxxxxxxxxxx/"

# 手动指定 cookies
python scripts/doctor.py --cookies config/cookies/bilibili_netscape.txt "https://www.bilibili.com/video/BVxxxxxxxxxx/"
```

B 站音频下载会自动使用浏览器 UA、Referer、Origin、重试、IPv4 备用策略和低码率备用音频格式，降低 CDN 短时签名或 HTTP 412 导致的失败率。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--whisper-model` | small | tiny / base / small / medium / large-v3 |
| `--whisper-language` | zh | 语言代码，None=自动检测 |
| `--whisper-device` | cpu | cpu 或 cuda |

## 交互式菜单

无参数运行 `python scripts/main.py` 进入交互式菜单：

```
1 - 导出 AI 输入包（单视频）
2 - 导出 AI 输入包（批量 URL）
3 - 处理本地音视频文件
4 - 同步收藏夹
5 - 重新生成笔记
h - 显示帮助
q - 退出
```

单视频模式会自动尝试从剪贴板读取链接。

## 全部命令行参数

```
python scripts/main.py --help
```

| 参数 | 说明 |
|------|------|
| `input_url` | 位置参数，视频链接 |
| `--bundle` | 导出 AI 输入包 |
| `--media-file PATH` | 本地音视频文件路径 |
| `--url-file PATH` | 批量 URL 文件（每行一个） |
| `--workers N` | 并发线程数（默认 3） |
| `--use-cache` | 启用缓存 |
| `--transcribe` | 强制 Whisper 转录 |
| `--cookies PATH` | 手动指定 cookies 文件 |
| `--platform` | 收藏夹同步平台（bilibili/youtube/all） |
| `--regenerate` | 从数据库重新生成笔记 |
| `--output PATH` | 笔记输出目录 |
| `--bundle-output PATH` | AI 输入包输出目录 |
| `--config PATH` | 配置文件路径 |

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| `ModuleNotFoundError: No module named 'xxx'` | 运行 `pip install -r requirements.txt` |
| `Python 3.10+ required` | 升级 Python 版本 |
| YouTube 429 错误 | 配置 cookies，或加 `--transcribe` 跳过字幕 |
| B 站字幕缺失/错配 | 加 `--transcribe` 强制 Whisper 转录 |
| B 站音频 HTTP 412 | 先运行 `python -m pip install -U yt-dlp`，再用 `python scripts/doctor.py "<视频链接>"` 做音频下载自检；如仍失败，更新 cookies |
| Windows 终端 emoji 乱码 | 当前 CLI 状态文本使用 ASCII；若仍乱码，设置 `PYTHONUTF8=1` 或使用 Windows Terminal |
| Whisper 转录很慢 | 用 `--whisper-model tiny` 测试，或 `--whisper-device cuda` |

## 项目结构

```
video-collector/
  config/
    credentials.example.yaml   # 配置模板
    cookies/                   # Cookies 文件目录
  output/
    bundles/                   # AI 输入包输出
    notes/                     # Obsidian 笔记输出
  scripts/
    main.py                    # 主入口
    fetch_base.py              # 抓取器基类
    fetch_single.py            # 单视频抓取器
    fetch_bilibili.py          # B 站收藏夹抓取
    fetch_youtube.py           # YouTube 收藏夹抓取
    export_bundle.py           # AI 输入包导出
    transcribe.py              # Whisper 语音转录
    doctor.py                  # 迁移部署与音频下载诊断
    generate_notes.py          # Obsidian 笔记生成
    config_models.py           # Pydantic 配置模型
    cache_manager.py           # 缓存管理
    concurrent_processor.py    # 并发处理
    logger_config.py           # 日志配置
    exceptions.py              # 自定义异常
    whisper_pool.py            # Whisper 模型池
  templates/
    prompt.md                  # AI 输入包模板
    note.md                    # 笔记模板
```

## 许可

个人自用项目，欢迎参考但暂不开源协议。
