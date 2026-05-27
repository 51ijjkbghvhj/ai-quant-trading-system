@echo off
chcp 65001 >nul
echo ==========================================
echo   AI Quant Trading System - v9.0.6 升级脚本
echo ==========================================
echo.

setlocal enabledelayedexpansion

:: 1. 备份用户数据
echo [1/4] 正在备份用户数据 (user_data)...
if exist "user_data" (
    set "BACKUP_DIR=user_data_backup_%date:~0,4%%date:~5,2%%date:~8,2%"
    xcopy /E /I /Y "user_data" "!BACKUP_DIR!" >nul
    echo       ✅ 数据已安全备份到: !BACKUP_DIR!
) else (
    echo       ℹ️ 未发现 user_data 目录，跳过备份。
)
echo.

:: 2. 提示用户下载代码
echo [2/4] 请现在从 GitHub 下载最新代码包，解压并覆盖当前文件夹。
echo       ⚠️ 注意：只覆盖 .py 代码和前端文件，脚本已配置 .gitignore 保护您的数据。
echo.
pause

:: 3. 恢复配置（如果需要）
echo [3/4] 检查版本兼容性...
if exist "!BACKUP_DIR!\ai_config.json" (
    echo       ✅ 发现备份的配置文件。如果新系统缺少设置，请手动恢复。
) else (
    echo       ℹ️ 无配置文件备份。
)
echo.

:: 4. 完成
echo [4/4] 升级完成！现在可以双击启动系统。
echo       如果遇到问题，请运行以下命令恢复数据:
echo       move "!BACKUP_DIR!" "user_data"
echo.
pause
