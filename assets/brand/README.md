# ClassFox 品牌素材

- `fox-icon-master.png`：以仓库原始 `docs/img/logo.png` 为参照，去掉字标并整理为方形狐狸头图标；通过内置 Image Generation 生成，保留原标识的长耳、眼睛与鼻部形态。
- `thought-to-notes.png`：Image Generation 制作的概念插图，橙色声波丝带连接笔记纸张；不代表实际产品界面。
- 网页压缩副本与真实截图位于 `website/assets/`。截图来自实际 React 界面、真实临时 SQLite/API 与合成模型响应，不包含用户课堂、环境录音或真实 API Key。
- 应用图标通过项目内 Tauri CLI 生成：`pnpm --dir app-ui exec tauri icon ../assets/brand/fox-icon-master.png --output src-tauri/icons`。本次仅交付桌面平台图标。
- 不覆盖旧版原始品牌文件，便于追溯。原图所用字标在 README 的 Git 历史中保留。
