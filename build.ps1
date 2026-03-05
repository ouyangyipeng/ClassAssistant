# ==========================================
#   上课摸鱼搭子 - 一键打包脚本
#   用法: .\build.ps1 <版本号>
#   示例: .\build.ps1 v1.0.0
# ==========================================

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---------- 配置（按需修改） ----------
$CONDA_ENV = "class-assistant"
# 自动检测 conda 路径，检测不到则用默认值
if ($env:CONDA_EXE) {
    $CONDA_ACTIVATE = Join-Path (Split-Path (Split-Path $env:CONDA_EXE)) "Scripts\activate.bat"
} else {
    $CONDA_ACTIVATE = "F:\MyProgram\Anaconda3\Scripts\activate.bat"
}
# --------------------------------------

$VER_NUM = $Version -replace '^[vV]', ''
$ROOT = $PSScriptRoot
$API_DIR = Join-Path $ROOT "api-service"
$UI_DIR = Join-Path $ROOT "app-ui"
$RELEASE_DIR = Join-Path $ROOT "release"
$DIST_NAME = "ClassAssistant-$Version-win-x64"

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  上课摸鱼搭子 - 打包 $Version" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ================================================
# [1/6] 更新版本号
# ================================================
Write-Host "[1/6] 更新版本号为 $VER_NUM ..." -ForegroundColor Yellow

# tauri.conf.json
$file = Join-Path $UI_DIR "src-tauri\tauri.conf.json"
$content = [IO.File]::ReadAllText($file)
$content = $content -replace '"version":\s*"[^"]+"', "`"version`": `"$VER_NUM`""
[IO.File]::WriteAllText($file, $content)

# package.json
$file = Join-Path $UI_DIR "package.json"
$content = [IO.File]::ReadAllText($file)
$content = $content -replace '"version":\s*"[^"]+"', "`"version`": `"$VER_NUM`""
[IO.File]::WriteAllText($file, $content)

# Cargo.toml（仅替换 [package] 下的 version）
$file = Join-Path $UI_DIR "src-tauri\Cargo.toml"
$content = [IO.File]::ReadAllText($file)
$content = $content -replace '(?m)^version\s*=\s*"[^"]+"', "version = `"$VER_NUM`""
[IO.File]::WriteAllText($file, $content)

Write-Host "      version 已更新" -ForegroundColor Green

# ================================================
# [2/6] 打包后端（PyInstaller + conda）
# ================================================
Write-Host ""
Write-Host "[2/6] 打包后端 (PyInstaller) ..." -ForegroundColor Yellow

# 构建期间去掉 tesseract 路径，避免 PyInstaller 拾取损坏的 libfribidi-0.dll
$cleanPath = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'tesseract' }) -join ';'
$buildCmd = "set PATH=$cleanPath && cd /d `"$API_DIR`" && call `"$CONDA_ACTIVATE`" && call conda activate $CONDA_ENV && pyinstaller backend.spec --clean --noconfirm"
cmd /c $buildCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 后端打包失败！" -ForegroundColor Red
    exit 1
}

Write-Host "      后端打包完成" -ForegroundColor Green

# ================================================
# [3/6] 打包前端（Tauri）
# ================================================
Write-Host ""
Write-Host "[3/6] 打包前端 (Tauri) ..." -ForegroundColor Yellow

Push-Location $UI_DIR
try {
    # --no-bundle: 只编译 exe，跳过 MSI/NSIS 安装包（我们用 zip 分发）
    npx tauri build --no-bundle
    if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
} catch {
    Pop-Location
    Write-Host "[错误] 前端打包失败！" -ForegroundColor Red
    exit 1
}
Pop-Location

Write-Host "      前端打包完成" -ForegroundColor Green

# ================================================
# [4/6] 组装 release 目录
# ================================================
Write-Host ""
Write-Host "[4/6] 组装发布目录 ..." -ForegroundColor Yellow

# 清理旧 release
if (Test-Path $RELEASE_DIR) { Remove-Item $RELEASE_DIR -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $RELEASE_DIR "backend") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RELEASE_DIR "data\summaries") -Force | Out-Null

# 复制后端
Write-Host "      复制后端文件 ..."
$backendDist = Join-Path $API_DIR "dist\class-assistant-backend"
Copy-Item "$backendDist\*" (Join-Path $RELEASE_DIR "backend") -Recurse -Force
Copy-Item (Join-Path $API_DIR ".env.example") (Join-Path $RELEASE_DIR "backend\.env.example") -Force

# 复制前端 exe（尝试 productName，回退到 Cargo name）
Write-Host "      复制前端文件 ..."
$tauriRelease = Join-Path $UI_DIR "src-tauri\target\release"
$exeName = "上课摸鱼搭子.exe"
$exePath = Join-Path $tauriRelease $exeName
$exePathAlt = Join-Path $tauriRelease "app-ui.exe"

if (Test-Path $exePath) {
    Copy-Item $exePath (Join-Path $RELEASE_DIR $exeName) -Force
} elseif (Test-Path $exePathAlt) {
    Copy-Item $exePathAlt (Join-Path $RELEASE_DIR $exeName) -Force
} else {
    Write-Host "[错误] 找不到前端 exe！" -ForegroundColor Red
    Write-Host "       已查找: $exePath" -ForegroundColor Red
    Write-Host "       已查找: $exePathAlt" -ForegroundColor Red
    exit 1
}

# 复制数据文件
Write-Host "      复制数据文件 ..."
$kw = Join-Path $ROOT "data\keywords.txt"
if (Test-Path $kw) {
    Copy-Item $kw (Join-Path $RELEASE_DIR "data\keywords.txt") -Force
}

Write-Host "      发布目录组装完成" -ForegroundColor Green

# ================================================
# [5/6] 生成启动脚本
# ================================================
Write-Host ""
Write-Host "[5/6] 生成启动脚本 ..." -ForegroundColor Yellow

$launchBat = @"
@echo off
chcp 65001 >nul

if not exist "%~dp0backend\.env" (
    echo ==========================================
    echo   上课摸鱼搭子 $Version
    echo   首次运行请先编辑 .env 填入 API 密钥
    echo ==========================================
    echo.
    echo [提示] 未找到 .env 配置文件，正在从模板创建...
    copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul 2>&1
    echo [提示] 请编辑 backend\.env 填入你的 API 密钥后重新运行！
    echo.
    start notepad "%~dp0backend\.env"
    pause
    exit /b
)

if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%~dp0data\summaries" mkdir "%~dp0data\summaries"

:: 清理 PATH 中的 tesseract，避免损坏的 DLL 被加载
set "PATH=%PATH:tesseract=%"

:: 后台启动后端（无窗口）
start /b "" cmd /c "cd /d %%~dp0backend && class-assistant-backend.exe" >nul 2>&1

:: 等待后端就绪
ping -n 4 127.0.0.1 >nul 2>&1

:: 启动前端
start "" "%~dp0上课摸鱼搭子.exe"

:: 自身退出，不留窗口
exit
"@

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText((Join-Path $RELEASE_DIR "启动.bat"), $launchBat, $utf8NoBom)

Write-Host "      启动脚本已生成" -ForegroundColor Green

# ================================================
# [6/6] 压缩为 zip
# ================================================
Write-Host ""
Write-Host "[6/6] 压缩为 $DIST_NAME.zip ..." -ForegroundColor Yellow

$zipPath = Join-Path $ROOT "$DIST_NAME.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$RELEASE_DIR\*" -DestinationPath $zipPath -Force

$zipSizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)

Write-Host "      压缩完成" -ForegroundColor Green

# ================================================
# 完成
# ================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  打包完成！" -ForegroundColor Green
Write-Host "  版本:  $Version" -ForegroundColor Green
Write-Host "  输出:  $DIST_NAME.zip ($zipSizeMB MB)" -ForegroundColor Green
Write-Host "  目录:  release\" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
