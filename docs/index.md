# 课狐 ClassFox 文档中心

课狐 ClassFox 是一个面向 Windows 桌面的课堂悬浮辅助工具。它把实时语音监听、点名提醒、课堂救场、进度追踪和课后总结串成同一条流程，目标不是替代认真听课，而是在你临时分神、记漏重点或需要快速跟上课堂时，给出一条低干扰的补救路径。

[快速开始](getting-started/environment.md){ .md-button .md-button--primary }
[用户指南](user-guide/quickstart.md){ .md-button }
[GitHub 仓库](https://github.com/ouyangyipeng/ClassAssistant){ .md-button }

## 视觉预览

![摸鱼状态](img/摸鱼状态.gif)

![点名警报与 AI 回答](img/点名警报与ai回答.gif)

![老师讲到哪儿了](img/老师讲到哪儿了.gif)

## 文档站点说明

当前 docs 分支同时保存两部分内容：

- docs/ 下的 Markdown 源文档
- 分支根目录下可直接由 GitHub Pages 发布的静态站点文件

这样做的原因是 GitHub Pages 直接从分支发布时不会替你执行 MkDocs 构建，所以发布所需 HTML、CSS、JS 和搜索索引必须已经准备好。

## 文档适用对象

- 想快速跑通项目并调试的开发者
- 只想下载并使用成品的普通用户
- 需要理解前后端分工、接口与运行数据的维护者
- 想在现有基础上继续扩展 ASR、LLM 或桌面端体验的二次开发者

## 你会在这里看到什么

### 项目概览

- 产品定位、目标场景、功能边界
- 桌面端、前端、后端、运行数据之间的关系
- 关键文件与关键模块的职责拆分

### 快速开始

- Windows 开发环境准备
- Python、Node.js、Rust、Tauri 的安装要求
- 本地开发启动、调试接口与打包发布流程

### 用户指南

- 如何上传资料、开始监听、暂停、继续、结束课程
- 如何使用“救场”“老师讲到哪了”“自动总结”等能力
- 如何在应用内完成配置，而不是手动编辑配置文件

### 开发者指南

- 核心接口说明
- WebSocket 告警消息结构
- 常见故障与排查顺序

## 项目特性一览

| 能力 | 说明 |
| --- | --- |
| 实时课堂监听 | 支持 local、mock、dashscope、seed-asr 多种 ASR 模式 |
| 点名/重点提醒 | 基于关键词检测分为危险提醒与一般提醒 |
| AI 救场 | 结合最近转录与课程资料生成问题理解和建议回答 |
| 进度追踪 | 把最近课堂内容压缩成可快速阅读的总结 |
| 自动课后总结 | 生成 Markdown 笔记并保存到 data/summaries |
| 资料引用 | 课程资料解析后可作为 LLM 辅助上下文 |
| 桌面端交付 | Tauri 打包单文件入口，启动时自动拉起内置后端 |

## 阅读建议

如果你是第一次接触该项目，建议按下面顺序阅读：

1. 先看项目介绍，明确产品目标和边界。
2. 再看环境准备与开发运行，确认本机依赖是否齐全。
3. 然后看代码模块说明，快速建立仓库结构认知。
4. 最后根据身份继续阅读用户指南或开发者指南。

## 文档预览方式

在仓库根目录执行：

```powershell
python -m venv .venv-docs
.venv-docs\Scripts\pip install -r requirements-docs.txt
.venv-docs\Scripts\mkdocs serve
```

默认本地地址为 [http://127.0.0.1:8000](http://127.0.0.1:8000) 。
