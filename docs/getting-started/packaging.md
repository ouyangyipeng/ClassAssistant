# 打包发布

## 打包入口

项目提供两个入口：

```powershell
./build.ps1 v1.2.0
```

或：

```powershell
./build.bat v1.2.0
```

其中 build.bat 只是 build.ps1 的包装入口。

## build.ps1 做了什么

### 1. 同步版本号

会同时更新：

- app-ui/package.json
- app-ui/src-tauri/Cargo.toml
- app-ui/src-tauri/tauri.conf.json

### 2. 打包 Python 后端

- 使用 api-service/.venv 中的 pyinstaller.exe
- 按 backend.spec 生成后端可执行文件

### 3. 打包 Tauri 前端

- 在 app-ui 目录执行 npx tauri build --no-bundle
- 只生成 exe，不走 MSI 或 NSIS 安装包

### 4. 组装 release 目录

- 复制后端到 release/backend
- 复制 .env.example 到 release/backend/.env.example 与 .env
- 复制前端 exe 到 release 根目录，并统一命名为课狐ClassFox.exe
- 复制关键词等运行数据文件

### 5. 验证打包产物

- 用临时 .env 启动打包后的后端
- 使用 18765 端口避免干扰开发环境
- 通过健康检查确认后端可用

### 6. 生成 zip

- 输出形如 ClassFox-v1.2.0-win-x64.zip 的压缩包

## 发布目录结构

```text
release/
├── 课狐ClassFox.exe
├── backend/
│   ├── class-assistant-backend.exe
│   ├── .env
│   └── .env.example
└── data/
    ├── keywords.txt
    └── summaries/
```

## 发布前建议确认

- 版本号参数书写正确，例如 v1.2.0
- api-service/.venv 已安装 pyinstaller
- app-ui 依赖已完整安装
- 本机 Rust 与 Tauri 构建环境正常

## 打包失败时先看哪里

### 后端阶段失败

优先检查：

- api-service/.venv 是否存在
- pyinstaller 是否安装成功
- requirements.txt 的依赖是否全部可导入

### 前端阶段失败

优先检查：

- npm install 是否完整执行
- Rust / cargo / tauri CLI 是否可用
- 前端 TypeScript 构建是否通过

### 产物验证失败

优先检查：

- release/backend/.env 是否被正确写入临时端口
- class-assistant-backend.exe 是否能独立启动
- /api/health 是否可访问