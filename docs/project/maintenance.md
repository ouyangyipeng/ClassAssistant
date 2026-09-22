# Issues 与历史分支

基线审查于 2026-09-22 完成，主线为 `1ea0b9b`。这里记录处理依据，尚未向 issue 发送结案消息，也未修改远端分支状态。

| 对象 | 2.0 处理 | 结案边界 |
| --- | --- | --- |
| [#12 救场等待](https://github.com/ouyangyipeng/ClassAssistant/issues/12) | 流式显示、上下文预算、取消、超时、计时、连接测试与显式预热 | 有真实本地模型样本；不同云端服务延迟仍需各自测量 |
| [#9 macOS 打不开](https://github.com/ouyangyipeng/ClassAssistant/issues/9) | 统一嵌套签名、权限和打包路径，避免错误 hardened runtime 配置 | 缺少 Developer ID/公证，不能宣称已彻底解决 |
| [#6 系统输入法](https://github.com/ouyangyipeng/ClassAssistant/issues/6) | 保留 WebSpeech，新增可靠文本入口，系统听写可直接输入；提供真离线 ASR | 没有劫持输入焦点或将系统听写伪装为持续后台 ASR |
| [#3 识别质量](https://github.com/ouyangyipeng/ClassAssistant/issues/3) | 离线 SenseVoice/VAD、在线 provider、设备选择、音量与错误状态、公开样本验证 | 未进行真实课堂噪声与多设备准确率评测 |
| 已关闭 #1 / #2 / #5 | 进程隔离、设置与 macOS 行为纳入回归 | 不重复关闭，不据已关闭状态跳过回归 |
| [PR #8](https://github.com/ouyangyipeng/ClassAssistant/pull/8) / `mac` | 吸收 macOS 资源位置、可写目录与打包经验；重写全局进程清理 | 保留历史贡献与分支，不把不安全清理原样合入 |
| [PR #11](https://github.com/ouyangyipeng/ClassAssistant/pull/11) | 保留 WebSpeech 与会话隔离方向，补齐停止末句、失败恢复与迟到事件测试 | 原 PR 已合入主线 |
| [PR #10](https://github.com/ouyangyipeng/ClassAssistant/pull/10) | 采用转录查看和 Markdown 展示的有效需求 | 原 PR 已关闭，不当作待合并分支 |
| `docs` | Markdown 文档源回到主线维护，保留原页面路径与发布入口 | 切换 Pages 前验证构建，不删除或强推旧分支 |

代码基于现有项目延续开发，历史贡献可在原 PR 和 Git 记录中追溯。2.0 通过新实现吸收有效能力，不制造机械合并提交或把闭合 PR 重新标记为开放。
