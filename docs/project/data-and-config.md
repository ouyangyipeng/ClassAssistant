# 数据与配置

## 运行时文件布局

项目运行过程中依赖一组本地文件，而不是数据库。这样做实现简单、便于打包，但也意味着维护时必须清楚每个文件的职责。

| 文件/目录 | 含义 |
| --- | --- |
| data/class_transcript.txt | 当前课堂会话主记录，包含时间戳、会话头部信息、可能的历史摘要块 |
| data/current_class_material.txt | 当前会话激活的参考资料文本 |
| data/cite/*.txt | 上传资料解析出的可选引用文本 |
| data/keywords.txt | 红色高优先级告警关键词 |
| data/attention_keywords.txt | 黄色一般提醒关键词 |
| data/summaries/*.md | 课后总结 Markdown 文件 |
| data/_startup.log | 后端启动诊断日志 |

## class_transcript.txt 的特点

这个文件不是简单的“每行一句课堂文本”，它还承担会话组织和上下文压缩的作用。

### 包含的信息

- 课堂开始标记
- 课程名称
- 当前引用资料名称
- 带时间戳的课堂文本行
- 历史摘要块
- 课堂结束标记

### 为什么需要历史摘要块

如果把全部转录原文直接发给 LLM，随着课程时长增加，请求体会越来越大，成本和延迟都会上升。当前实现会在积累一定数量的记录后，把旧内容压缩成摘要，保留最近原文，形成“长历史摘要 + 短最新原文”的结构。

## 环境变量位置

| 运行场景 | 位置 |
| --- | --- |
| 开发态 | api-service/.env |
| 打包态 | release/backend/.env |

## 常用环境变量

```ini
ASR_MODE=local
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=deepseek-chat
SEED_ASR_APP_KEY=
SEED_ASR_ACCESS_KEY=
SEED_ASR_RESOURCE_ID=volc.bigasr.sauc.duration
DASHSCOPE_API_KEY=
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_CHUNK_SIZE=3200
API_PORT=8765
```

## 配置修改建议

### 对普通用户

优先使用应用内的“设置”面板修改配置。这样路径更短，也能避免直接编辑文件时出现编码或换行问题。

### 对开发者

如果你在调试启动链路、发布态问题或 PyInstaller 行为，仍然建议直接检查 .env 文件与 data/_startup.log。

## 端口约定

- 8765：开发态和默认打包态后端端口
- 18765：build.ps1 在验证打包产物时使用的临时健康检查端口

## 资料文件的生命周期

1. 用户上传 PPT/PDF/Word。
2. 后端解析文本并写入 data/cite/带时间戳的 txt。
3. 用户开始监听时，从 cite 列表中挑选当前资料。
4. 选中的资料被复制为 data/current_class_material.txt。
5. 救场、进度总结、课后总结优先从该文件中补充上下文。

## 关键词文件的建议维护方式

- 把“点名、回答、谁来、签到”类词放进红色告警词
- 把“重点、作业、考试、截止日期”类词放进黄色提醒词
- 修改词表后，重新开始监听或调用 reload_keywords 相关接口使其生效