# 上课摸鱼搭子 - 开发文档

## 项目概述
一款大学课堂辅助桌面悬浮窗应用，可实时录音转文字、监控点名关键词、一键获取LLM生成的答案，课后生成Markdown笔记。

## 技术栈
| 层级 | 技术 |
|------|------|
| 桌面端外壳 | Tauri 2.0 (Rust) |
| 前端 UI | React 19 + TypeScript + TailwindCSS 4 |
| 后端服务 | Python 3.11 + FastAPI |
| LLM 调用 | OpenAI Compatible API |
| 语音识别 | 预留本地/API 双接口 |

## 项目目录结构
```
/ClassAssistant
├── /app-ui                    # Tauri + React 前端
│   ├── /src
│   │   ├── /components        # React 组件
│   │   │   ├── TitleBar.tsx   # 无边框窗口标题栏（可拖拽）
│   │   │   ├── ToolBar.tsx    # 工具栏（上传/摸鱼/总结按钮）
│   │   │   ├── AlertOverlay.tsx  # 点名警报覆盖层（闪烁红光）
│   │   │   ├── RescuePanel.tsx   # 救场面板（显示上下文/问题/答案）
│   │   │   └── Toast.tsx      # Toast 提示消息
│   │   ├── /hooks
│   │   │   └── useWebSocket.ts   # WebSocket 连接 Hook
│   │   ├── /services
│   │   │   └── api.ts         # 后端 API 调用封装
│   │   ├── App.tsx            # 主应用组件
│   │   ├── main.tsx           # React 入口
│   │   └── index.css          # TailwindCSS 入口
│   ├── /src-tauri             # Tauri Rust 后端
│   │   ├── tauri.conf.json    # Tauri 窗口配置（无边框/透明/置顶）
│   │   ├── Cargo.toml         # Rust 依赖
│   │   └── /src/lib.rs        # Tauri 命令
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts         # Vite + React + TailwindCSS 配置
│   └── tsconfig.json
├── /api-service               # FastAPI 后端
│   ├── main.py                # FastAPI 入口
│   ├── /routers
│   │   ├── ppt_router.py      # PPT 解析路由
│   │   ├── monitor_router.py  # 监控服务路由 + WebSocket
│   │   ├── rescue_router.py   # 救场功能路由
│   │   └── summary_router.py  # 课后总结路由
│   ├── /services
│   │   ├── ppt_service.py     # PPT 文本提取
│   │   ├── monitor_service.py # 录音 + ASR + 关键词检测
│   │   ├── transcript_service.py  # 转录文本读写
│   │   └── llm_service.py     # LLM API 调用
│   ├── /utils
│   ├── requirements.txt
│   ├── .env                   # 环境变量（API Keys 等）
│   └── .env.example
├── /data                      # 运行时数据目录
│   ├── class_transcript.txt   # 实时转录文本
│   ├── current_class_material.txt  # PPT 解析文本
│   └── /summaries             # 课后笔记 Markdown
└── docs.md                    # 本文档
```

---

## 第一步：环境初始化

### 已完成的操作

#### 1. Rust 环境
```bash
winget install Rustlang.Rustup
# 已安装 rustc 1.93.1, cargo 1.93.1
```

#### 2. Python 虚拟环境 (conda)
```bash
conda create -n class-assistant python=3.11 -y
conda activate class-assistant
```

#### 3. Python 依赖安装
```bash
pip install fastapi uvicorn[standard] python-multipart python-pptx openai websockets python-dotenv aiofiles
```
已安装版本:
- fastapi 0.135.1
- uvicorn 0.41.0
- python-pptx 1.0.2
- openai 2.24.0
- websockets 16.0
- 等

#### 4. Tauri + React 前端初始化
```bash
npm create tauri-app@latest app-ui
cd app-ui
npm install react react-dom
npm install -D @types/react @types/react-dom @vitejs/plugin-react tailwindcss @tailwindcss/vite
```

### Tauri 窗口配置说明 (tauri.conf.json)
- `decorations: false` → 无边框窗口
- `transparent: true` → 透明背景（配合 CSS 实现毛玻璃效果）
- `alwaysOnTop: true` → 永久置顶
- 默认尺寸 320×80px（工具条模式），警报/救场时动态调大

### 启动方式
```bash
# 终端 1: 启动后端
conda activate class-assistant
cd api-service
uvicorn main:app --host 0.0.0.0 --port 8765 --reload

# 终端 2: 启动前端 (Tauri dev)
cd app-ui
npm run tauri dev
```

---

## 核心功能流程

### A. 正常模式 (工具条)
1. 悬浮小窗口 (320×80)，半透明毛玻璃效果
2. 显示「上传资料」「开始摸鱼」两个按钮
3. 可拖拽标题栏，悬浮时显示最小化/关闭按钮

### B. 监控模式
1. 点击「开始摸鱼」→ 后端启动录音 + ASR
2. ASR 识别文本写入 class_transcript.txt
3. 实时匹配关键词：["点名", "随机", "抽查", "叫人", "回答", "签到"] + 自定义
4. 前端通过 WebSocket 接收警报

### C. 点名警报
1. 检测到关键词 → 窗口闪烁红光 + 弹出「救场」按钮
2. 窗口自动放大到 320×200

### D. 救场模式
1. 点击「救场」→ 调用 LLM 分析最近 2 分钟转录 + PPT 资料
2. 窗口展开到 400×480
3. 显示三块信息：课堂内容 / 老师问题 / 建议答案

### E. 课后总结
1. 停止监控后点击「📝」按钮
2. 全量转录发送给 LLM 生成 Markdown 笔记
3. 保存到 /data/summaries/

---

## ASR 接口预留说明 (monitor_service.py)

当前使用 Mock 函数 `_mock_asr()`，返回空字符串。

预留三种接入方式：
1. **本地 Whisper**: `whisper.load_model("base").transcribe(audio)`
2. **GLM-ASR API**: `requests.post(ASR_API_URL, data=audio_bytes)`
3. **OpenAI Whisper API**: `client.audio.transcriptions.create(...)`

通过 `.env` 中的 `ASR_MODE` 环境变量切换。
