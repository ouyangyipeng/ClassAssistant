# 2.0 接口与 1.x 迁移

## 连接前置条件

桌面 Tauri 通过私有管道取得随机端口与凭据，再通过 IPC 交给工作区。HTTP 使用 `Authorization: Bearer <token>`；WebSocket `/api/v2/events` 在 5 秒内先发送 `{"type":"auth","token":"<token>"}`，后续客户端只发送 `ping`。不要把 token 放入 URL 或日志。

`GET /api/health` 只返回版本和健康状态，不需要 token。其他接口要求本机认证；本机浏览器 Origin 仍需在允许列表内。手机不使用这些管理接口，而是独立的加密命令协议。

## 核心 API

下表路径均以 `/api/v2` 为前缀。

| 方法与路径 | 用途 |
| --- | --- |
| `GET /status` | 当前桌面课堂与输入源 |
| `GET /sessions` | 分页历史课堂 |
| `POST /sessions` | 创建课堂；`course_name`、`source`、可选 `material_id` |
| `GET /sessions/{id}/entries` | 原文分页；`after_id`、`limit` |
| `POST /sessions/{id}/entries` | `text`（最多 8,000 字符）与 `source_id`（幂等标识） |
| `POST /sessions/{id}/pause`、`resume`、`stop` | 课堂生命周期 |
| `GET /sessions/{id}/export` | 完整原文导出 |
| `POST /sessions/{id}/assistant` | `kind` 为 `rescue`、`catchup`、`summary`、`followup`，返回 202 和任务 |
| `GET /assistant/{id}`、`DELETE /assistant/{id}` | 任务快照、取消 |
| `POST /assistant/test` | 固定短文本连接测试，报告首字和总耗时 |
| `GET /sessions/{id}/summaries` | 课堂笔记 |
| `GET /summaries/{id}/export` | Markdown 笔记 |
| `GET /materials`、`POST /materials` | 资料列表、multipart `file` 上传 |
| `GET /audio/devices` | 输入设备 |
| `POST /sessions/{id}/audio` | multipart `file` + `source_id`，30 秒以内 PCM WAV |
| `GET /settings`、`PUT /settings` | 类型化非秘密配置 |
| `GET /credentials` | 各类凭据是否已配置 |
| `PUT /credentials/{name}`、`DELETE /credentials/{name}` | 更新或删除凭据；不会回传 Key |
| `GET /models` | 安装状态与固定模型清单 |
| `POST /models/{id}/install`、`DELETE /models/{id}/install` | 开始或取消安装 |
| `POST /models/{id}/start`、`GET /models/runtime` | 预热和实际就绪状态 |
| `POST /import` | 显式旧数据导入，字段 `directory` |
| `POST /import-config` | 显式旧配置导入，字段 `path` |

事件是同步提示，持久数据以 HTTP 和 SQLite 为准。收到 `resync_required` 或重新连接时重新读取状态、原文和助手快照。任务取消/失败不会保存为成功笔记。完整字段与约束以类型化源码和行为测试为准，不将任意 Python 异常正文暴露给客户端。

## 迁移原则

旧的 `/api/start_monitor`、`/api/settings`、`/api/emergency_rescue` 等无鉴权接口已移除。兼容无鉴权写配置会保留旧安全问题，因此本次按 2.0 主版本边界迁移；旧桌面和新后端不能混用。服务端不再依赖固定 8765 端口，也不返回完整 `.env`。

第三方工具应创建自己的明确授权 API-only 实例，或由受信的本机宿主提供连接信息，不扫描端口、读取其他进程凭据或复用手机身份访问管理接口。错误响应为 `error` / `message` 或 FastAPI 校验详情，调用方必须判断 HTTP 状态和任务最终状态。
