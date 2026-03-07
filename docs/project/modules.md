# 代码模块说明

本页按目录和职责说明代码结构，目标是让开发者能在第一次进入仓库时，快速知道应该从哪里读起。

## 后端模块

### 入口与配置

| 文件 | 作用 |
| --- | --- |
| api-service/main.py | FastAPI 应用入口，注册路由、CORS 与健康检查接口 |
| api-service/config.py | 计算开发态/打包态路径，创建 data 目录，保证运行时文件落点稳定 |

### 路由层

| 文件 | 作用 |
| --- | --- |
| routers/monitor_router.py | 监控启停、暂停继续、关键词、麦克风检查、WebSocket 告警 |
| routers/ppt_router.py | 上传 PPT/PDF/Word 并解析为引用资料文本 |
| routers/rescue_router.py | 救场与课堂追问接口 |
| routers/summary_router.py | 课堂总结与进度总结接口 |
| routers/settings_router.py | 读取与保存 .env 配置 |

### 服务层

| 文件 | 作用 |
| --- | --- |
| services/monitor_service.py | 课堂监听核心，处理 ASR、写盘、去重、告警、会话状态 |
| services/asr_service.py | 抽象不同 ASR 提供方并统一回调方式 |
| services/transcript_service.py | 管理课堂转录、当前资料、cite 列表和最近转录读取 |
| services/llm_service.py | 统一封装救场、进度总结、追问、课堂笔记生成等模型调用 |
| services/ppt_service.py | 文档解析和文本抽取 |
| services/summary_service.py | 课后总结生成封装 |

## 前端模块

### 主入口

| 文件 | 作用 |
| --- | --- |
| app-ui/src/main.tsx | React 挂载入口 |
| app-ui/src/App.tsx | 主状态容器，协调工具栏、面板、警报层与窗口类型 |

### UI 组件

| 组件 | 作用 |
| --- | --- |
| TitleBar.tsx | 顶部状态显示与窗口感知 |
| ToolBar.tsx | 核心操作入口：上传、开始、暂停、继续、结束、设置 |
| StartMonitorPanel.tsx | 启动监控前填写课程名并选择资料 |
| RescuePanel.tsx | 查看救场答案并继续追问 |
| CatchupPanel.tsx | 查看课堂进度并继续追问 |
| SettingsPanel.tsx | 编辑后端配置 |
| AlertOverlay.tsx | 关键词触发后的覆盖层提醒 |
| Toast.tsx | 操作结果提示 |

### 通信与偏好

| 文件 | 作用 |
| --- | --- |
| services/api.ts | 所有 HTTP API 封装 |
| hooks/useWebSocket.ts | 告警 WebSocket 建连、断开、消息接收 |
| services/preferences.ts | UI 偏好读写与应用 |

## 桌面壳层模块

| 文件 | 作用 |
| --- | --- |
| src-tauri/src/lib.rs | Tauri 主逻辑，打包态启动后端、管理 splash 与主窗口 |
| src-tauri/src/main.rs | Rust 程序入口 |
| src-tauri/tauri.conf.json | 桌面窗口尺寸、透明度、构建命令、应用标识 |

## 运行数据目录

| 路径 | 作用 |
| --- | --- |
| data/class_transcript.txt | 当前课堂完整记录 |
| data/current_class_material.txt | 当前激活的课程资料文本 |
| data/cite | 已解析资料仓库 |
| data/keywords.txt | 红色告警词 |
| data/attention_keywords.txt | 黄色提醒词 |
| data/summaries | 自动生成的课堂总结 |

## 从哪里开始读代码

### 如果你想理解主业务流程

建议阅读顺序：

1. main.py
2. routers/monitor_router.py
3. services/monitor_service.py
4. services/transcript_service.py
5. services/llm_service.py

### 如果你想理解前端交互

建议阅读顺序：

1. app-ui/src/App.tsx
2. app-ui/src/components/ToolBar.tsx
3. app-ui/src/components/StartMonitorPanel.tsx
4. app-ui/src/components/RescuePanel.tsx 与 CatchupPanel.tsx
5. app-ui/src/services/api.ts

### 如果你想理解打包与发布

建议阅读顺序：

1. build.bat
2. build.ps1
3. src-tauri/tauri.conf.json
4. src-tauri/src/lib.rs

## 维护时最容易踩坑的点

- 不要把 splash 窗口逻辑与主界面的 Hook 条件早退混在同一个组件分支里。
- 不要把流式 ASR 的 partial 文本直接全部落盘。
- 不要假设开发态与发布态的 .env、data 目录路径相同。
- 修改打包流程时，要同时考虑版本号同步、后端健康检查与 release 目录组装。