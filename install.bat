@echo off
chcp 65001 >nul

:: 管理者権限チェック
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo エラー: このバッチファイルは管理者として実行してください。
    echo 右クリック → 「管理者として実行」を選択してください。
    pause
    exit /b 1
)

set "INSTALL_DIR=%USERPROFILE%\MoveToSameNameFolder"

:: インストールフォルダ作成
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: スクリプトファイルをコピー
copy /Y "%~dp0MoveToSameNameFolder.ps1" "%INSTALL_DIR%\" >nul
copy /Y "%~dp0MoveToNamedFolder.ps1" "%INSTALL_DIR%\" >nul

:: ダウンロードブロック解除（Mark of the Web 除去）
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path '%INSTALL_DIR%\MoveToSameNameFolder.ps1'; Unblock-File -Path '%INSTALL_DIR%\MoveToNamedFolder.ps1'"

:: 旧バージョンのレジストリ削除（あれば）
reg delete "HKCR\*\shell\MoveToSameNameFolder" /f >nul 2>&1
reg delete "HKCR\*\shell\MoveToNamedFolder" /f >nul 2>&1
reg delete "HKCR\Directory\shell\MoveToSameNameFolder" /f >nul 2>&1
reg delete "HKCR\Directory\shell\MoveToNamedFolder" /f >nul 2>&1

:: ========== ファイル用サブメニュー ==========
reg add "HKCR\*\shell\FileOrganizer" /v "MUIVerb" /d "フォルダに格納" /f >nul
reg add "HKCR\*\shell\FileOrganizer" /v "SubCommands" /d "" /f >nul
reg add "HKCR\*\shell\FileOrganizer" /v "Icon" /d "shell32.dll,3" /f >nul

reg add "HKCR\*\shell\FileOrganizer\shell\01_Individual" /v "MUIVerb" /d "個別のフォルダを作成" /f >nul
reg add "HKCR\*\shell\FileOrganizer\shell\01_Individual" /v "Icon" /d "shell32.dll,3" /f >nul
reg add "HKCR\*\shell\FileOrganizer\shell\01_Individual\command" /ve /d "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%INSTALL_DIR%\MoveToSameNameFolder.ps1\" \"%%1\"" /f >nul

reg add "HKCR\*\shell\FileOrganizer\shell\02_Named" /v "MUIVerb" /d "まとめたフォルダを作成" /f >nul
reg add "HKCR\*\shell\FileOrganizer\shell\02_Named" /v "Icon" /d "shell32.dll,4" /f >nul
reg add "HKCR\*\shell\FileOrganizer\shell\02_Named\command" /ve /d "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%INSTALL_DIR%\MoveToNamedFolder.ps1\" \"%%1\"" /f >nul

:: ========== フォルダ用サブメニュー ==========
reg add "HKCR\Directory\shell\FileOrganizer" /v "MUIVerb" /d "フォルダに格納" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer" /v "SubCommands" /d "" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer" /v "Icon" /d "shell32.dll,3" /f >nul

reg add "HKCR\Directory\shell\FileOrganizer\shell\01_Individual" /v "MUIVerb" /d "個別のフォルダを作成" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer\shell\01_Individual" /v "Icon" /d "shell32.dll,3" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer\shell\01_Individual\command" /ve /d "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%INSTALL_DIR%\MoveToSameNameFolder.ps1\" \"%%1\"" /f >nul

reg add "HKCR\Directory\shell\FileOrganizer\shell\02_Named" /v "MUIVerb" /d "まとめたフォルダを作成" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer\shell\02_Named" /v "Icon" /d "shell32.dll,4" /f >nul
reg add "HKCR\Directory\shell\FileOrganizer\shell\02_Named\command" /ve /d "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%INSTALL_DIR%\MoveToNamedFolder.ps1\" \"%%1\"" /f >nul

:: Windows 11 従来メニュー有効化
reg add "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32" /ve /d "" /f >nul

:: Explorer 再起動
echo Explorer を再起動しています...
taskkill /f /im explorer.exe >nul 2>&1
start explorer.exe

echo.
echo インストールが完了しました。
echo 右クリックメニュー「フォルダに格納」に以下が追加されました：
echo   - 個別のフォルダを作成
echo   - まとめたフォルダを作成
echo.
pause
