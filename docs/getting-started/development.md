# 开发运行

## 一键启动

根目录提供了一个最省事的入口：

```powershell
./dev.bat
```

这个脚本会先清理旧进程，再启动开发后端和 Tauri 前端。

### 脚本会做什么

- 杀掉残留的 class-assistant-backend.exe
- 杀掉标题为 ClassAssistant-Backend 的旧终端
- 清理占用 8765 端口的监听进程
- 在 api-service 目录启动 uvicorn
- 在 app-ui 目录执行 npm run tauri dev

## 手动启动方式

### 启动后端

```powershell
cd api-service
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

### 启动前端

```powershell
cd app-ui
npm run tauri dev
```

## 开发时建议的验证顺序

1. 先访问后端健康检查，确认后端启动正常。
2. 再启动前端，确认界面可见、按钮可用。
3. 之后用 mock 或 local 模式先跑通完整流程。
4. 最后再切换到在线 ASR 或真实 LLM 做集成验证。

## 常用调试地址

- Swagger UI: http://127.0.0.1:8765/docs
- 健康检查: http://127.0.0.1:8765/api/health
- 麦克风检查: http://127.0.0.1:8765/api/check_mic

## 推荐开发流程

### 调整前端交互时

建议用 mock 模式，避免真实 ASR 和外部模型干扰 UI 调试。

### 调整 MonitorService 时

优先观察：

- data/class_transcript.txt 的写入效果
- 告警是否只对新增内容触发
- 暂停、继续、结束会话时的状态切换

### 调整打包链路时

优先验证：

- build.ps1 是否正确同步版本号
- release/backend/.env 是否被复制
- 发布态 exe 是否能自动拉起后端

## 文档站点本地预览

```powershell
.venv-docs\Scripts\mkdocs serve
```

如果你还没安装文档依赖，请先参考环境准备页。

## 推荐提交前自检

- 后端接口能正常启动
- 前端主窗口与 splash 切换正常
- mock / local 至少验证一种主流程
- 打包脚本没有破坏版本号同步逻辑
- 新增文档页面已在 mkdocs.yml 中加入导航