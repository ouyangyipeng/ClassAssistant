# 系统架构

```text
Tauri / React 工作区
  ├─ 原生窗口与原子导出
  └─ 私有管道启动 Python → 随机 loopback 端口 + 随机访问凭据
       ├─ FastAPI /api/v2 与已鉴权 WebSocket
       ├─ SQLite：课堂、追加原文、笔记、资料、导入与音频回执
       ├─ 独立语音与资料解析子进程
       ├─ 受管 llama.cpp 或用户 BYOK
       └─ 显式开启的手机 LAN 网关
            └─ 短时扫码 + 双端批准 + AES-GCM 消息 → 手机独立课堂
微信手机独立模式 → 预设 HTTPS / WSS 服务商
```

## 职责和生命周期

`classfox/app.py` 的 lifespan 创建并按逆序关闭资源。`runtime.py` 负责桌面课堂及音频启动/暂停/结束；`storage.py` 使用事务与互斥边界保存记录。业务对象使用类型化请求，磁盘记录以课堂和 owner 标识，不通过任意用户文件路径引用资料。

`assistant.py` 管理有界并发任务、取消和完整结果提交；`assistant_context.py` 固定原文快照和上下文预算。`llm.py` 持有每次请求的连接、超时和流完整性检查。只有成功完成的笔记写入存储，停止录音不等待总结。

`speech_process.py` 与 `document_process.py` 负责真正可终止的拥有进程，父子间使用私有输入协议。`model_install.py` 负责安装状态、校验、取消和原子启用；`model_process.py` 仅管理自己启动的 llama.cpp。任何清理都不按全局进程名称或端口匹配。

## 客户端恢复

桌面 `WorkspaceStore` 从 API 恢复课堂状态与历史，WebSocket 使用增量事件；事件丢失或队列溢出要求重新读取完整状态。文字流使用 Unicode code point 偏移，迟到结果不能覆盖新任务。浏览器语音由独立控制器管理，页面恢复时先暂停再由用户继续。

微信 `service.ts` 管理唯一录音实例、本地存储、问答取消和前后台转换；构建产物共用单个 `runtime.js`。手机 Key 不持久化，课堂记录和非秘密配置使用微信本地存储。

## 安全边界

桌面管理接口只监听 loopback，验证随机 token 和 Origin；WebSocket 首帧认证，凭据不放 URL。手机使用独立 opt-in 网关，扫码共享秘密经 HKDF 派生方向密钥，AES-GCM 绑定连接 ID、方向和单调计数。重试只重发相同密文；不确定状态废弃通道，撤销会关闭该手机的课堂与任务。

手机协议只允许课堂、原文、音频和助手操作，owner 由服务端绑定，不能使用手机请求选择桌面凭据或管理路径。传输加密不保护已被控制的电脑、手机或泄露的二维码；本机数据库也不是静态加密数据库。详细协议和威胁边界见仓库 `plan/phone-protocol.md`。
