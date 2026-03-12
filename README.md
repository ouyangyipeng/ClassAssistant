# 🦊 课狐 ClassFox - 你的上课摸鱼搭子 🐟

> 📚 项目文档：<https://ouyangyipeng.github.io/ClassAssistant/>

<!-- markdownlint-disable MD033 -->
<div align="center">
  <img src="docs/img/logo透明背景.png" alt="课狐 ClassFox Logo" width="128" />
  <br />
  <a href="https://github.com/ouyangyipeng/ClassAssistant/stargazers">
    <img src="https://img.shields.io/github/stars/ouyangyipeng/ClassAssistant?style=for-the-badge&logo=github" alt="GitHub stars" />
  </a>
  <a href="https://github.com/ouyangyipeng/ClassAssistant/issues">
    <img src="https://img.shields.io/github/issues/ouyangyipeng/ClassAssistant?style=for-the-badge&logo=github" alt="GitHub issues" />
  </a>
</div>
<!-- markdownlint-enable MD033 -->

> ClassFox — Hears what you miss.
>
> 课狐 ClassFox —— 听见你的错过，接住你的惊慌。
>
> 以耳廓狐为灵感的小体量课堂悬浮助手：资源占用轻，专门盯住你最容易错过的点名、提问和进度变化。

## 🚀 v1.2.0 近期优化

- **品牌升级**：项目产品名更新为“课狐 ClassFox”，强调“小体量 + 高听感”的课堂辅助定位。
- **单入口发布**：release 根目录只保留一个 课狐ClassFox.exe，后端由主程序静默拉起，避免首次使用误点多个入口。
- **启动体验升级**：新增居中启动遮罩与 logo 动画，启动阶段不再裸露命令行窗口。
- **紧凑悬浮窗**：主窗口压缩到更低调的 320 宽紧凑尺寸，监控、警报和扩展面板按场景单独控制高度。
- **追问链路补齐**：救场面板和“老师讲到哪了”都支持继续追问，返回区位置上移，避免在小窗里被截断。
- **关键词判定更准**：告警改为只检测当前新增落盘的那一行，避免把历史多行误拼成一次红灯命中。
- **Local 模式修正**：本地识别增加短时片段拼接与更保守的停顿判定，减少一句话只落前几个字的问题。
- **macOS 打包适配**：新增 macOS 下的后端资源打包、运行时目录初始化与多架构构建脚本。

## ✨ 核心功能

| 功能 | 说明 |
| ------ | ------ |
| 🎙️ 实时语音监控 | Local ASR / Seed-ASR / DashScope / Mock 多模式切换 |
| 🧹 去重转录 | 流式识别结果按句落盘，过滤重复、碎片标点和相近修正文 |
| 🧠 滚动课堂摘要 | 每累计 50 条课堂记录，自动压缩为一段历史摘要 |
| 🚨 点名预警 | 命中关键词后通过 WebSocket 推送红色警报弹层 |
| 🆘 一键救场 | 结合最近转录和课程资料，生成应答思路与参考答案 |
| 📍 老师讲到哪了 | 对最近课堂内容做即时进度总结 |
| 📝 课后总结 | 生成 Markdown 课堂笔记并落盘到 data/summaries |
| 📄 资料上传与引用 | PPT / PDF / Word 解析后存入 data/cite，开始监控前可选择引用资料 |
| ⚙️ 内置设置面板 | 前端可直接编辑后端 .env，无需手动找文件 |

## 🏗️ 架构概览

```text
Tauri + React UI
        │
        ├─ HTTP API
        └─ WebSocket Alert
                │
          FastAPI Backend
                │
      ┌─────────┼─────────┐
      │         │         │
    ASR       LLM     Transcript
      │                   │
  Local / Seed /      class_transcript.txt
  DashScope / Mock    current_class_material.txt
                      data/cite/*.txt
```

后端负责录音、ASR、关键词检测、滚动摘要和 LLM 调用；前端负责悬浮窗 UI、警报展示、资料上传、监控启动参数选择和设置编辑。

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/ouyangyipeng/ClassAssistant.git
cd ClassAssistant
```

### 2. 配置后端 Python 环境

```bash
cd api-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

### 3. 配置前端

```bash
cd ../app-ui
npm install
```

### 4. 开发模式启动

推荐直接运行：

- Windows: `dev.bat`
- macOS: `dev.sh`

也可以手动分别启动：

```bash
# 终端 A
cd api-service
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

```bash
# 终端 B
cd app-ui
npm run tauri dev
```

## 🍎 macOS 适配说明

- 新增 `app-ui/build-with-backend.sh`，用于 macOS 下一键打包后端与 Tauri 前端。
- 发布版会把后端二进制作为 Tauri `resources` 打进 `.app`，并在首次启动时把运行配置和数据落到 `~/Library/Application Support/ClassFox/`。
- 开发态可直接运行根目录 `dev.sh`，行为与 Windows 下的 `dev.bat` 对齐。
- 构建前请确保本机已安装 Rust、Node.js 18+、Python 3.10+ 和 `portaudio`。

```bash
chmod +x ./dev.sh ./app-ui/build-with-backend.sh
./dev.sh
./app-ui/build-with-backend.sh
```

## License

MIT
