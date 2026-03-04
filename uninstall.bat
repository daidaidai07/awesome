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

:: コンテキストメニューのレジストリ削除
reg delete "HKCR\*\shell\MoveToSameNameFolder" /f >nul 2>&1
reg delete "HKCR\*\shell\MoveToNamedFolder" /f >nul 2>&1

:: スクリプトフォルダ削除
if exist "%USERPROFILE%\MoveToSameNameFolder" rmdir /s /q "%USERPROFILE%\MoveToSameNameFolder"

:: Windows 11 従来メニュー設定削除（簡易メニューに戻る）
reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f >nul 2>&1

:: Explorer 再起動
echo Explorer を再起動しています...
taskkill /f /im explorer.exe >nul 2>&1
start explorer.exe

echo.
echo アンインストールが完了しました。
echo 右クリックメニューから以下を削除しました：
echo   - 同名フォルダを作成して格納
echo   - フォルダ名を指定して格納
echo.
pause
