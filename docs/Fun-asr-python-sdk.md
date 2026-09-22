# Fun-ASR 接入说明

此路径保留旧文档入口。供应商 SDK 文档随版本变化，使用 [阿里云官方实时识别文档](https://help.aliyun.com/zh/model-studio/fun-asr-realtime-websocket-api)，不把历史复制页作为当前 SDK 的完整规范。

ClassFox 2.0 使用有界 WebSocket 管线：等待 `task-started` 后发送 16 kHz 单声道 PCM；只保存 `sentence_end` 最终句，heartbeat 不作为转录；结束时发送 `finish-task` 并等待 `task-finished`。北京和新加坡的连接与 Key 应对应所选地区。

手机独立模式使用预设域名，Key 只保留内存；桌面凭据通过私有管道交给受管音频进程。合成服务测试覆盖成功、失败、末句和取消，尚未使用真实付费账户验证。配置入口见 [首次使用](user-guide/quickstart.md)。
