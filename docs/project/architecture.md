# 系统架构

## 总体结构

```text
┌──────────────────────┐
│  Tauri Desktop Shell │
│  - 窗口启动与隐藏     │
│  - 打包态拉起后端     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ React Floating UI    │
│ - 上传资料            │
│ - 开始/暂停监控       │
│ - 救场/追进度         │
│ - 设置编辑            │
└───────┬────────┬─────┘
        │        │
        │ HTTP   │ WebSocket
        ▼        ▼
┌──────────────────────┐
│ FastAPI Backend      │
│ - Router 分发        │
│ - MonitorService     │
│ - TranscriptService  │
│ - LLMService         │
│ - PPT/Summary 服务   │
└───────┬──────────────┘
        │
        ▼
┌──────────────────────┐
│ Runtime Data         │
│ data/class_transcript.txt
│ data/current_class_material.txt
│ data/cite/*.txt
│ data/summaries/*.md
└──────────────────────┘
```

## 一次完整课堂的处理流程

1. 用户在前端打开“开始摸鱼”面板，填写课程名并可选择一份 cite 文本。
2. 前端调用 POST /api/start_monitor。
3. 后端激活当前资料文件，重置会话状态，创建 ASR 实例并开始监听麦克风。
4. ASR 回调持续产生文本，MonitorService 负责去噪、合并、去重、写盘和关键词检测。
5. 命中关键词后，后端通过 WebSocket 向前端推送告警消息。
6. 用户可在任意时刻请求“救场”或“老师讲到哪了”，后端从最近转录和当前资料中组装上下文，再调用 LLM 生成结果。
7. 结束监控时，后端尝试自动生成课后总结并写入 data/summaries。

## 后端内部职责分层

### Router 层

- 处理 HTTP / WebSocket 入口
- 负责请求参数校验和响应结构封装
- 主要文件位于 api-service/routers

### Service 层

- MonitorService 负责监听会话主流程
- TranscriptService 负责转录与资料文件读写
- LLMService 负责各类模型提示词与调用
- SummaryService 负责课后总结封装
- PPTService 负责资料解析与文本提取

### Config 层

- 根据开发态或 PyInstaller 打包态计算项目根目录
- 创建 data、data/summaries、data/cite 等必需目录

## 前端内部职责分层

### 页面壳与状态编排

- App.tsx 是主入口，负责切分 splash 与主窗口
- MainApp 负责工具栏、面板、告警层、Toast 与监控状态编排

### 组件层

- StartMonitorPanel 负责课程名与资料选择
- RescuePanel 负责救场结果和追问
- CatchupPanel 负责进度总结和追问
- SettingsPanel 负责读取与编辑后端配置
- AlertOverlay 负责高优先级告警展示

### 通信层

- services/api.ts 封装 HTTP 请求
- hooks/useWebSocket.ts 管理告警通道生命周期

## 打包态与开发态差异

| 维度 | 开发态 | 打包态 |
| --- | --- | --- |
| 前端启动 | Vite + Tauri dev | Tauri release exe |
| 后端启动 | dev.bat 或手动 uvicorn | 主程序静默拉起 backend/class-assistant-backend.exe |
| 环境变量 | api-service/.env | release/backend/.env |
| 数据目录 | 项目根目录 data | release/data |

## 关键设计点

### 1. 转录不直接无限累积

MonitorService 会在累计一定数量的原始记录后调用 LLM 压缩历史内容，把旧内容折叠到“历史摘要”块中，避免上下文无限膨胀。

### 2. 不把所有 ASR 结果都当最终文本

在线 ASR 尤其是 Seed-ASR 会持续修正文本，服务端只把稳定分句写盘，避免一段话被反复追加成多份近似文本。

### 3. 打包态只暴露单入口

用户最终看到的是一个桌面 exe，而不是“前端程序 + 后端程序”两个入口，这显著降低了首次使用门槛。