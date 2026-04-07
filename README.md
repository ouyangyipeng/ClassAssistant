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
> ClassFox 课狐 —— 听见你的错过，接住你的惊慌。
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
- **试用配置内置**：打包时会直接把 api-service/.env.example 构建为 release/backend/.env，方便开箱即用。

## 🎬 Demo

### 摸鱼监控状态

![摸鱼监控状态演示](docs/img/%E6%91%B8%E9%B1%BC%E7%8A%B6%E6%80%81.gif)

### 点名警报与 AI 救场

![点名警报与 AI 救场演示](docs/img/%E7%82%B9%E5%90%8D%E8%AD%A6%E6%8A%A5%E4%B8%8Eai%E5%9B%9E%E7%AD%94.gif)

### 老师讲到哪儿了

![老师讲到哪儿了演示](docs/img/%E8%80%81%E5%B8%88%E8%AE%B2%E5%88%B0%E5%93%AA%E5%84%BF%E4%BA%86.gif)

## ✨ 核心功能

| 功能 | 说明 |
| ------ | ------ |
| 🎙️ 实时语音监控 | Local ASR / WebSpeech / Seed-ASR / DashScope / Mock 多模式切换 |
| 🧹 去重转录 | 流式识别结果按句落盘，过滤重复、碎片标点和相近修正文 |
| 🧠 滚动课堂摘要 | 每累计 50 条课堂记录，自动压缩为一段历史摘要，减小上下文体积 |
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
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install pyinstaller
```

如果你要使用麦克风采集模式（`local` / `dashscope` / `seed-asr`），再额外安装：

```bash
.venv\Scripts\pip install -r requirements-mic.txt
```

### 3. 配置前端依赖

```bash
cd app-ui
npm install
```

### 4. 配置环境变量

在 api-service 下创建 .env，可参考 .env.example：

```env
# ASR 模式: local | webspeech | mock | dashscope | seed-asr
ASR_MODE=local

# WebSpeech
WEBSPEECH_LANG=zh-CN

# Seed-ASR
SEED_ASR_APP_KEY=your_app_key
SEED_ASR_ACCESS_KEY=your_access_key
SEED_ASR_RESOURCE_ID=volc.bigasr.sauc.duration

# DashScope Fun-ASR
DASHSCOPE_API_KEY=sk-your-dashscope-key

# LLM
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-your-key
LLM_MODEL=deepseek-chat

# Audio
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_CHUNK_SIZE=3200
```

### 5. 启动开发模式

推荐直接运行根目录的 dev.bat。

它现在会先清理以下残留状态，再启动开发后端和 Tauri 前端：

- 上一次残留的 class-assistant-backend.exe
- 标题为 ClassAssistant-Backend 的开发后端终端
- 监听 8765 端口的旧进程

也可以手动分别启动：

```bash
cd api-service
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

```bash
cd app-ui
npm run tauri dev
```

## 🧭 使用流程

1. 点击“上传资料”，将 PPT / PDF / Word 解析为可引用文本。
2. 点击“开始摸鱼”，在启动面板里填写课程名称，并可选择一份 cite 资料。
3. 后端开始监听课堂音频，按句落盘到 data/class_transcript.txt。
4. 命中关键词时，前端立即显示警报弹层。
5. 需要时点击“救场”或“老师讲到哪了”，调用 LLM 生成结果。
6. 下课后点击“总结”，生成 Markdown 笔记。

## 🎙️ ASR 模式说明

| 模式 | 说明 |
| ------ | ------ |
| local | 基于 SpeechRecognition + Google Speech API，按句回调，适合直接体验（需安装 PyAudio） |
| webspeech | Edge/WebView2 Web Speech API，由前端采集后把文本注入后端 |
| mock | 不录音、不识别，适合纯 UI 联调 |
| dashscope | 阿里云百炼 Fun-ASR（需安装 PyAudio） |
| seed-asr | 字节 Seed-ASR，使用 utterances + definite 分句，避免流式累积文本反复写盘（需安装 PyAudio） |

说明：`webspeech` 与 `mock` 模式不依赖 PyAudio，可仅安装 `requirements.txt` 运行。

### 当前转录策略

- Local ASR 继续保持“识别完一句追加一行”的本地模式。
- Seed-ASR 只把 definite 的稳定句子落盘，partial 文本只保存在内存中。
- 会过滤孤立标点、极短碎片和与近期内容高度相似的重复句。
- 每 50 条记录会触发一次 LLM 压缩，把旧内容折叠进“历史摘要”块。

## 📁 运行时数据

| 路径 | 用途 |
| ------ | ------ |
| data/class_transcript.txt | 当前课堂完整记录，含滚动历史摘要块 |
| data/current_class_material.txt | 当前选中的参考资料文本 |
| data/cite/ | 上传资料解析后的候选引用文本 |
| data/keywords.txt | 用户自定义关键词 |
| data/summaries/ | 生成的课堂笔记 |

## ⚙️ 调试接口

后端启动后可访问：

- Swagger UI: <http://127.0.0.1:8765/docs>
- 健康检查: <http://127.0.0.1:8765/api/health>
- 麦克风检测: <http://127.0.0.1:8765/api/check_mic>

常用 API：

- POST /api/start_monitor
- POST /api/stop_monitor
- GET /api/cite_files
- GET /api/settings
- POST /api/settings
- POST /api/emergency_rescue
- POST /api/catchup
- POST /api/generate_summary

## 📦 打包发布

```powershell
./build.ps1 v1.2.0
```

打包流程会自动执行：

1. 同步前后端版本号。
2. 用 .venv 中的 PyInstaller 打包 FastAPI 后端。
3. 用 Tauri 构建桌面端 exe。
4. 组装 release 目录。
5. 把 api-service/.env.example 同步到 release/backend/.env 与 .env.example。
6. 用临时 .env 和独立端口 18765 做后端健康检查，结束后恢复正式配置。
7. 输出 zip 压缩包。

release 根目录现在只保留一个 课狐ClassFox.exe；后端配置会随安装包一起落到 backend/.env，用户无需再手动复制模板。

## 📥 免开发环境使用

从 Releases 下载 zip，解压后双击 课狐ClassFox.exe。

release/backend/.env 默认已经写入试用配置；如果额度耗尽或你要切换成自己的服务，直接在应用内“设置”面板修改并保存即可。

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ouyangyipeng/ClassAssistant&type=Date)](https://star-history.com/#ouyangyipeng/ClassAssistant&Date)

## 📝 更新说明

### v1.2.0

- 品牌名更新为 课狐 ClassFox，默认窗口标题与发布包名称同步调整。
- 发布目录改为单 exe 入口，内置启动后端，减少首次使用误操作。
- 新增课狐启动动画遮罩，启动阶段提供更明确的状态反馈。
- 救场与进度面板的返回区整体上移，适配当前更小的悬浮窗尺寸。
- 告警关键词判定改为只看当前新增行，修复跨行历史误报。
- Local ASR 调整停顿阈值并加入短时片段拼接，缓解本地识别只落前几个字的问题。
- 设置面板底部操作区再次上移，避免保存/取消按钮被底部边框遮挡。
- release/backend/.env 现在直接由 .env.example 构建，试用 key 可随包即用。

### v1.0.1

- 重构流式转录逻辑，解决 Seed-ASR 重复写盘和标点碎片问题。
- 增加 50 行滚动摘要压缩，降低长课堂上下文膨胀。
- 开始监控前新增课程名与 cite 资料选择面板。
- 资料上传改为保存到 data/cite，由用户在启动监控时选择引用。
- 新增设置面板，可直接读写后端 .env。
- dev.bat、启动.bat 和 Tauri 退出流程都增加旧后端清理逻辑。
- 打包脚本增加发布后端健康检查，当前已可成功产出 v1.0.1 压缩包。

## License

MIT
