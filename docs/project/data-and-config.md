# 数据与配置

| 内容 | 存储位置或方式 |
| --- | --- |
| 课堂、原文、笔记、资料和回执 | 用户目录 `classfox.sqlite3`，SQLite WAL 与事务 |
| 非秘密设置 | `preferences.json`，校验后原子写入 |
| 本地模型与运行时 | 用户目录 `models/`，固定下载清单、SHA-256 与安装标记 |
| 桌面 API Key | 系统凭据存储；图形界面和接口只报告是否配置 |
| 微信课堂、非秘密设置 | 微信本地存储；每堂课独立记录 |
| 微信 Key、配对密钥 | 当前进程内存，不默认持久化 |

桌面正式版用户目录：macOS `~/Library/Application Support/ClassFox`，Windows `%LOCALAPPDATA%\ClassFox`。调试版使用 `ClassFox Development`。自定义数据目录仅用于明确配置的开发/服务进程，不从小程序请求接受路径。

原文保存 UTC 时间及所属课堂，跨午夜不再只比较时分秒。生成笔记会保留原文；历史删除等能力只按界面实际提供的动作执行。手机重新配对使用新 owner，不会自动获得旧配对的电脑历史；手机本地副本继续可读。

资料解析保留提取文本，不长期保存上传源文件；语音管线使用有界内存和临时文件，不默认保存音频档案。分享/导出是用户主动创建的独立副本，需要自行管理。

独立后端支持 `CLASSFOX_DATA_DIR`、`CLASSFOX_API_TOKEN`、`CLASSFOX_PORT`；凭据提供器还支持明确命名的环境变量作为 API-only 使用方式。桌面启动会过滤继承环境，不自动读取旧 `.env`。旧数据、凭据和外观迁移见 [升级指南](../user-guide/migration.md)。
