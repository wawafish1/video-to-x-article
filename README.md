# 视频转 X 文章工作台

一个本地运行的视频内容整理工具：上传视频后自动提取音频、生成转写稿、清洗口语内容，并整理成适合发布到 X 的短帖、Thread 和长文草稿。

## 功能

- 支持上传 `.mp4`、`.mov`、`.m4v`、`.webm`、`.mkv`
- 使用 FFmpeg 自动提取和压缩音频
- 通过 OpenAI 兼容接口完成语音转写
- 生成清洗稿，标记疑似错字、数字、人名和待核查信息
- 生成 X 单条短帖、最多 8 条的 Thread 和长文版
- 提供行情解读、知识科普、项目介绍、观点评论、新闻快讯五种模板
- 在线预览、分段复制、编辑和保存最终稿
- 下载转写稿、清洗稿、文章包和最终稿
- 搜索或删除历史处理任务
- 大音频自动切片，源视频大小可配置

## 工作流程

```text
上传视频
  -> FFmpeg 提取音频
  -> 语音转写
  -> 清洗和结构化
  -> 生成 X 内容包
  -> 人工校对并保存最终稿
```

## 环境要求

- Windows、macOS 或 Linux
- Python 3.11 或更新版本
- FFmpeg
- 支持以下接口的 OpenAI API 或兼容中转服务：
  - `/v1/audio/transcriptions`
  - `/v1/chat/completions`

## 安装

### 1. 获取代码

```bash
git clone https://github.com/wawafish1/video-to-x-article.git
cd video-to-x-article
```

### 2. 安装 FFmpeg

Windows：

```powershell
winget install Gyan.FFmpeg
ffmpeg -version
```

macOS：

```bash
brew install ffmpeg
```

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install ffmpeg
```

### 3. 创建 Python 环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 4. 配置环境变量

复制示例配置：

```powershell
Copy-Item .env.example .env
```

macOS / Linux 使用：

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://你的兼容服务地址/v1
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENAI_TEXT_MODEL=gpt-5.4-mini
MAX_TRANSCRIPTION_MB=23
MAX_UPLOAD_MB=1024
```

配置说明：

| 配置项 | 用途 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | API 密钥，必填 | 空 |
| `OPENAI_BASE_URL` | 兼容接口地址；使用 OpenAI 官方接口时可留空 | 空 |
| `OPENAI_TRANSCRIPTION_MODEL` | 语音转写模型 | `whisper-1` |
| `OPENAI_TEXT_MODEL` | 清洗和改写模型 | `gpt-5.4-mini` |
| `MAX_TRANSCRIPTION_MB` | 超过该大小的音频会自动切片 | `23` |
| `MAX_UPLOAD_MB` | 单个源视频的大小上限 | `1024` |

> 不要提交 `.env`。它已加入 `.gitignore`，但仍应避免把真实 API Key 写进代码、README 或截图。

## 启动

Windows 可以双击项目根目录的 `start_app.bat`，它会启动服务并打开浏览器。

也可以手动启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 54810
```

打开：

```text
http://127.0.0.1:54810/
```

开发时可启用自动重载：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 54810
```

## 使用方法

1. 点击“选择视频文件”或将视频拖入上传区域。
2. 选择与视频内容匹配的模板。
3. 点击“开始生成”。
4. 在处理记录中查看实时状态。
5. 处理完成后切换文章包、清洗稿、转写稿和最终稿。
6. 发布前核对“待人工核查”和“风险提示”。
7. 在最终稿中编辑、保存或下载内容。

处理耗时取决于视频长度、网络速度和接口响应速度。任务处理期间请保持本地服务运行。

## 输出文件

每个任务的生成内容保存在 `outputs/<job_id>/`：

```text
audio.mp3
raw_transcript.txt
cleaned_transcript.md
x_article_bundle.md
final_article.md
```

上传的视频保存在 `uploads/<job_id>/`，任务索引保存在本地 SQLite 文件 `jobs.db`。这些运行数据均被 Git 忽略。

## 项目结构

```text
app/
  config.py       环境配置
  main.py         FastAPI 路由和任务流程
  rewrite.py      清洗、改写提示词和文本模型调用
  storage.py      SQLite 任务存储
  transcribe.py   FFmpeg 处理和语音转写
static/
  styles.css      工作台样式
templates/
  index.html      页面结构和前端交互
.env.example      环境变量示例
requirements.txt  Python 依赖
start_app.bat     Windows 一键启动入口
```

## 健康检查

服务启动后访问：

```text
GET /api/health
```

返回结果会显示服务状态、FFmpeg 是否可用、API 是否已配置，以及当前模型名称。接口不会返回 API Key。

## 部署到现有服务器

本项目可以和“写作助手”部署在同一台服务器，但会使用独立容器与独立数据目录。建议使用子域名：

```text
https://video.mywriting-assistant.xyz
```

部署前请确认服务器已运行写作助手的 Caddy HTTPS 代理，并为 `video` 添加一条 DNS 记录：

| 主机记录 | 类型 | 记录值 |
| --- | --- | --- |
| `video` | `A` | 服务器公网 IP |

### 1. 本机创建私有迁移包

迁移包包含 API 配置、历史任务、原视频与生成文件，不能提交到 GitHub 或发送给他人。它会把任务数据库中的本机路径自动转换为 Docker 容器内路径。

Windows PowerShell：

```powershell
cd "C:\Users\87271\Documents\视频转文章提取"
.\.venv\Scripts\python.exe .\scripts\prepare_server_migration.py --output "C:\Users\87271\Documents\视频转文章提取\server-migration-video-to-x.zip"
```

### 2. 服务器更新写作助手的 HTTPS 代理

在服务器的 `/opt/writing-assistant` 中拉取包含视频子域名配置的版本，然后重建 Caddy：

```bash
cd /opt/writing-assistant
git pull
sudo docker compose up -d --build
```

这一步会创建共享 Docker 网络 `writing-assistant-proxy`，供两个应用之间的 HTTPS 代理使用。

### 3. 服务器部署视频应用

```bash
sudo mkdir -p /opt/video-to-x-article
sudo chown admin:admin /opt/video-to-x-article
git clone https://github.com/wawafish1/video-to-x-article.git /opt/video-to-x-article
cd /opt/video-to-x-article
sudo dnf install -y unzip
unzip -o /tmp/server-migration-video-to-x.zip -d .
sudo docker compose up -d --build
```

将第 1 步生成的私有迁移包上传到服务器的 `/tmp/server-migration-video-to-x.zip` 后，再执行上述命令。部署完成后可以删除它：

```bash
rm -f /tmp/server-migration-video-to-x.zip
```

### 4. 验证

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 video-to-x-article
```

浏览器访问：

```text
https://video.mywriting-assistant.xyz
```

### 日常更新

代码更新不会覆盖 `data/` 中的视频、任务记录和生成文件：

```bash
cd /opt/video-to-x-article
git pull
sudo docker compose up -d --build
```

服务器磁盘为 40 GiB 时，应及时在应用中删除不需要的历史任务。删除任务会同时删除对应上传视频和生成文件，能避免磁盘被长期占满。

## 常见问题

### 页面无法打开

本项目是本地应用，电脑重启或服务窗口关闭后需要重新启动。Windows 用户可以再次双击 `start_app.bat`。

### FFmpeg 未找到

安装后重新打开终端并运行：

```powershell
ffmpeg -version
```

如果仍无法识别，请确认 FFmpeg 已加入系统 `PATH`。

### 文本生成可用，但语音转写失败

部分中转服务只兼容文本接口，不提供 `/audio/transcriptions`。请确认服务商支持音频上传和当前转写模型。

### 任务在应用重启后显示失败

本地后台任务不会跨进程恢复。处理期间关闭应用会中断任务，需要重新上传视频。

## 数据与安全

- API Key 仅从本地 `.env` 读取。
- 视频和生成稿默认保存在本机，不会提交到 Git。
- 转写和改写时，音频或文本会发送到你配置的 API 服务。
- 删除任务会永久删除该任务的上传视频和全部生成文件。
- 行情、投资、政策和新闻内容发布前应人工核实，不应把模型输出直接视为事实。
