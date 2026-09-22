# 手机连接协议：本地验证版 v1

日期：2026-09-22。实现前设计，验证完成前不称为安全审计通过。

## 范围与信任边界

桌面管理 API 始终只在 loopback，凭据不下发给手机。用户主动选择局域网 IPv4 地址并开启独立手机入口；仅绑定该 RFC1918 地址，不默认监听全部网卡或公网。关闭入口、退出桌面或撤销连接后，旧手机凭据立即失效。首版同时最多 4 台手机。

允许手机创建自己的课堂、追加原文/PCM、控制自己课堂、请求救场/进度/总结和读取自己结果。不提供桌面设置、凭据、资料、文件路径、模型安装或任意 URL 代理。手机模式只允许已安装的电脑离线 ASR/LLM；不代用桌面 BYOK 额度。课堂权限从连接身份确定，忽略/拒绝客户端自报 owner。

网络攻击者可观察/篡改/重放 HTTP、控制恶意网站，但不知道二维码里的秘密。端点被攻破、二维码被拍摄、流量大小/时序和拒绝服务不由应用层加密解决。二维码不是可公开分享的普通链接。无需自签 HTTPS 或关闭 TLS 验证。

## 配对和密钥

1. 桌面系统 CSPRNG 生成 128-bit offer ID 和 256-bit PSK，有效 120 秒。二维码为 ClassFox 专用文本，包含固定协议版本、局域网 IP/端口、offer ID、PSK。秘密只通过已鉴权的桌面 API 返回，不记录日志/写磁盘/放 HTTP URL。新 offer 撤销旧的未完成 offer。
2. 手机使用 `wx.getRandomValues` 生成 256-bit client nonce；API 缺失或失败时停止，不降级 Math.random。连接 ID 为 offer ID。HKDF-SHA256 的 IKM 为 PSK 原始 32 字节，salt 为 client nonce 原始 32 字节，info 为 ASCII `classfox-phone-v1|{offer_id}|{purpose}`，输出 32 字节；purpose 分别为 `c2s`、`s2c` 和 `verification`。核对数字取 verification 前 4 字节大端整数模 1000000，并补足 6 位。
3. 手机第 1 个加密请求为 hello，只有设备昵称，不包含用户真实身份。第一条有效 hello 原子占用 offer，随后相同 nonce 的重试可用，其他 nonce 拒绝。相同密文重试返回原密文响应。服务端不能对同一 key/nonce 重新生成不同响应。
4. 六位核对数字来自独立 HKDF info，只供两端人工核对；不是 PSK。桌面展示昵称与数字，用户点击允许后连接才能操作课堂。批准不改变已缓存的响应；手机发新计数器的 status 获取变化。
5. offered 和 pending 都受创建后 120 秒的 monotonic 截止时间约束；批准绑定 offer ID 和 client nonce，批准后重新计时 8 小时。内存保存、退出失效；旧 ID 不可复活。手机不把 PSK、派生密钥、BYOK key 写入 storage。配对失效后重新扫码；手机已同步的课堂副本仍保留。新的配对不自动获取之前配对的桌面课堂。

## 加密请求/响应

固定 POST `/phone/v1`；外层仅 `version=1, id, client_nonce(hex), counter, ciphertext(base64)`。AES-256-GCM，128-bit tag。96-bit nonce 为 8 个零字节 + uint32 big-endian counter，计数从 1 到 2^32-1。AAD 为 `classfox-phone-v1|id|direction|counter` UTF-8。

客户端单连接串行队列，只能发送 `last_counter + 1`；超时只能重发完全相同的外层内容，不重做加密、不跳过未确认请求。服务端在任何副作用前预留 counter、请求指纹和独立执行任务；重复请求等待同一任务或返回缓存，较旧计数或同计数不同内容拒绝。HTTP 等待取消不取消已预留的任务。响应方向有独立 key，响应 counter 与请求一致；客户端验证后才推进计数。业务错误消费计数并缓存唯一密文。发生不可恢复的不确定结果时连接关闭，要求重新配对，避免 nonce 重用。

撤销先同步标记失效，再通过独立、可重入的 cleanup task 取消识别和该 owner 的全部助手任务；关闭入口也会等待已进入清理的任务。每 0.5 秒检查到期，不依赖手机继续请求；写入音频结果、保存总结前再次验证授权。模型服务内部对同一个配置快照强制 local-only，拒绝读取桌面在线凭据或回退到未受管端点。

所有操作名、课堂 ID、音频、转录、返回错误都在密文中。响应必须绑定请求计数。外层错误统一，不回显异常/输入。HTTP 实际接收上限 1 MiB、读取时限 5 秒、入口并发 16、backlog 32、全入口每秒 60 次、每连接每分钟 180 个新请求；未知 ID 不创建状态。解密 JSON 上限 700 KiB，PCM 每段 10 秒。原文每页 12 条（包含 8000 字符最大 JSON 转义的上界），笔记每页 1 条并支持 offset；超限结果在加密前转换为可缓存错误，不能销毁有效连接。拒绝浏览器 Origin、非 JSON、非固定路由和非选定 IP Host；不对手机网关开放 CORS。TLS 服务商请求仍严格使用 HTTPS/WSS。

## 验收

- Python cryptography 与 JS noble 的固定跨语言向量：中文/emoji、空数据、方向分离、AAD、counter、篡改拒绝。
- 配对前不可执行；确认后成功；过期/撤销/重启失败；第二手机不能占用已配对 offer。
- 重试不重复创建课堂/写音频/发模型请求；计数回退/跳跃/更换密文拒绝；并发重复请求最多执行一次。
- 其他 owner 的课堂/笔记/任务、桌面设置/key/材料均不可访问；本地模型未就绪/桌面切到 BYOK 时不消费线上额度。
- 请求体/频率/连接数有界；关闭入口取消自己的任务并保留已写原文；服务崩溃不影响桌面本地课堂。
- 手机与桌面内存之外不留配对密钥；只有合成数据的测试记录可提交。真机与校园网互通待 AppID/设备资源到位，模拟测试不替代此项。

## 依据

- [微信官方 API 类型](https://github.com/wechat-miniprogram/api-typings)：安全随机数 `wx.getRandomValues` 自 2.15.0 起，录音 `format: PCM`、16 kHz 单声道与帧回调；实际发行包版本另行锁定。
- [noble-ciphers](https://github.com/paulmillr/noble-ciphers)、[noble-hashes](https://github.com/paulmillr/noble-hashes)：AES-GCM、HKDF/SHA256；不自行实现加密原语。库审计范围不等于应用协议已审计。
- [cryptography AEAD](https://cryptography.io/en/50.0.1/hazmat/primitives/aead/)：AESGCM nonce 不得复用、附加数据校验、错误标签拒绝。

手机 BYOK、录音前后台生命周期和原生页面另行实现，不由此协议替代。
