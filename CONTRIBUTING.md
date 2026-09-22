# 参与 ClassFox 开发

先阅读 [开发指南](docs/getting-started/development.md)。为数据处理、对外接口和生命周期变更提供行为回归；测试使用合成凭据、独立临时目录和自己持有的进程。不要上传真实课堂、用户 Key、`.env`、系统凭据或配对二维码。

提交问题时提供平台与架构、版本、重现步骤、预期/实际结果、脱敏错误码，以及是否能在文本模式重现。模型质量问题可提供有授权的公开样本；不要把一个样本的准确结果称为整体识别率。

在自己的功能分支提交 PR，保持与默认分支的线性历史。合入前通过项目检查并完成审查，只使用 GitHub 的 **Rebase and merge**。不要把安装包、`site/`、模型权重、`node_modules/` 或虚拟环境提交到源代码分支。

Commit message 使用英文 Pedalboard 格式，标题不超过 50 个字符，正文每行不超过 72 个字符，五个字段必须保留：

```text
[feat] Implement classroom export

Root cause: NA
Solution: Export a complete classroom snapshot as Markdown.
Risks: Check Unicode text and interrupted file writes.
Dependency: NA
Links: NA
```

类型为 `feat`、`bug`、`doc`、`style`、`refactor`、`revert`、`milestone` 或 `chore`。修复标题使用 `[bug] Fix ...`，新增功能使用 `[feat] Implement ...`。正文应反映实际改动和证据。
