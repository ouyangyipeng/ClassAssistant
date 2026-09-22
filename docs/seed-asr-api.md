# Seed-ASR 接入说明

此路径保留旧文档入口。当前协议以火山引擎 [大模型流式语音识别 API](https://www.volcengine.com/docs/6561/1354869) 为准，历史复制的接口说明不继续作为当前规范。

ClassFox 2.0 使用优化双向 `bigmodel_async`，区分新控制台 `X-Api-Key` 与旧控制台 App Key / Access Key。配置资源 ID 时区分 1.0 和 2.0，不混用凭据形式。

二进制管线依据 header、标志和长度解析数据，对 gzip 解压设置上限。只有 utterances 中 `definite` 的最终句写入课堂，临时修正用于实时显示。正常结束发送最终包并等待末句，断网、协议错误或超时不会伪装为成功。

已有真实回环 WebSocket 模拟服务和协议夹具验证，尚未使用真实在线账户或环境麦克风实测。配置入口见 [首次使用](user-guide/quickstart.md)，故障见 [排查指南](developer/troubleshooting.md)。
