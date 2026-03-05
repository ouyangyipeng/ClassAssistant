@echo off
chcp 65001 >nul
:: ==========================================
::   上课摸鱼搭子 - 一键打包
::   用法: build.bat <版本号>
::   示例: build.bat v1.0.0
:: ==========================================
if "%~1"=="" (
    echo [错误] 请指定版本号！
    echo 用法: build.bat ^<版本号^>
    echo 示例: build.bat v1.0.0
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
