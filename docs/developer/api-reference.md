# 接口与联调

## 基础信息

- 默认后端地址：http://127.0.0.1:8765
- API 前缀：/api
- WebSocket 告警地址：/api/ws/alerts

## 常用 HTTP 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | /api/health | 健康检查 |
| GET | /api/check_mic | 检查麦克风状态 |
| POST | /api/start_monitor | 开始课堂监听 |
| POST | /api/stop_monitor | 停止监听并尝试自动总结 |
| POST | /api/pause_monitor | 暂停监听 |
| POST | /api/resume_monitor | 继续监听 |
| GET | /api/monitor_status | 获取监控状态 |
| GET | /api/cite_files | 列出资料文本 |
| POST | /api/upload_ppt | 上传并解析资料 |
| POST | /api/emergency_rescue | 生成救场结果 |
| POST | /api/emergency_rescue_chat | 基于救场结果继续追问 |
| POST | /api/catchup | 生成课堂进度摘要 |
| POST | /api/catchup_chat | 基于课堂进度继续追问 |
| POST | /api/generate_summary | 手动生成课堂总结 |
| GET | /api/settings | 读取配置 |
| POST | /api/settings | 保存配置 |

## start_monitor 请求体

```json
{
  "course_name": "并行程序设计",
  "cite_filename": "week1_introduction_20260307_224812.txt"
}
```

字段说明：

- course_name：课程名称，可为空
- cite_filename：当前会话要引用的资料文件名，可为空

## stop_monitor 返回体的特殊点

停止监听后，接口除了返回监控状态，还可能附带：

- summary：自动生成的总结文件信息
- summary_error：如果自动总结失败，返回错误说明

## WebSocket 告警联调

前端建立连接后可以定期发送 ping，后端返回 pong 保活。

告警消息主体通常会包含以下信息：

```json
{
  "level": "danger",
  "keywords": ["点名", "请回答"],
  "text": "老师刚才提到了相关内容"
}
```

具体字段最终以 monitor_service.py 当前实现为准。

## 联调建议

### 前端联调

- 先用 /api/health 确认服务在线
- 再用 /api/cite_files 和 /api/settings 验证基础读接口
- 之后再接 start/stop、救场、catchup 等主流程接口

### 后端联调

- 优先使用 Swagger UI 验证请求格式
- 对会写文件的接口，检查 data 目录结果是否符合预期
- 对 WebSocket 告警，建议同时观察终端输出和前端覆盖层表现