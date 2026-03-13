#
# auto-save-downloads.ps1
# ダウンロードフォルダを監視し、新しいファイルを日付付きの同名フォルダに自動整理する
#
# 使い方:
#   .\auto-save-downloads.ps1
#   .\auto-save-downloads.ps1 -WatchDir "C:\Users\you\Downloads"
#
# 保存形式:
#   example.pdf           → Downloads\YYMMDD_example\example.pdf
#   260313_example.pdf    → Downloads\260313_example\260313_example.pdf (YYMMDD_プレフィックスを流用)
#   20260313_example.pdf  → Downloads\260313_example\20260313_example.pdf (YYYYMMDD_→YYMMDD_に変換)
#
# 追加インストール不要（Windows標準のFileSystemWatcherを使用）

param(
    [string]$WatchDir = "$env:USERPROFILE\Downloads"
)

if (-not (Test-Path $WatchDir)) {
    Write-Error "エラー: ディレクトリが見つかりません: $WatchDir"
    exit 1
}

$SkipExtensions = @('.crdownload', '.part', '.tmp')

Write-Host "監視開始: $WatchDir"
Write-Host "終了するには Ctrl+C を押してください"

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $WatchDir
$watcher.Filter = "*.*"
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite

try {
    while ($true) {
        $result = $watcher.WaitForChanged([System.IO.WatcherChangeTypes]::Created -bor [System.IO.WatcherChangeTypes]::Renamed, 1000)
        if ($result.TimedOut) { continue }

        $filename = $result.Name
        if ($filename -match '\\') { continue }

        $filePath = Join-Path $WatchDir $filename

        Start-Sleep -Milliseconds 1000

        if (-not (Test-Path $filePath)) { continue }
        if ($filename.StartsWith('.')) { continue }
        $ext = [System.IO.Path]::GetExtension($filename)
        if ($ext -in $SkipExtensions) { continue }

        $basenameNoExt = [System.IO.Path]::GetFileNameWithoutExtension($filename)
        $datePrefix = Get-Date -Format "yyMMdd"

        # フォルダ名用: ファイル名に日付プレフィックス (YYYYMMDD_ or YYMMDD_) が付いている場合は除去して重複防止
        $folderBase = $basenameNoExt
        if ($basenameNoExt -match '^\d{8}_') {
            $datePrefix = $basenameNoExt.Substring(2, 6)
            $folderBase = $basenameNoExt.Substring(9)
        } elseif ($basenameNoExt -match '^\d{6}_') {
            $datePrefix = $basenameNoExt.Substring(0, 6)
            $folderBase = $basenameNoExt.Substring(7)
        }

        # 保存先フォルダを作成（必ず日付プレフィックスを付与）
        $destDir = Join-Path $WatchDir "${datePrefix}_${folderBase}"
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        # 保存先ファイルパス（ファイル名はそのまま維持）
        $destFile = Join-Path $destDir $filename

        # 同名ファイルが既に存在する場合は連番を付与
        if (Test-Path $destFile) {
            $counter = 1
            $nameOnly = [System.IO.Path]::GetFileNameWithoutExtension($filename)
            $extension = [System.IO.Path]::GetExtension($filename)
            do {
                $destFile = Join-Path $destDir "${nameOnly}_${counter}${extension}"
                $counter++
            } while (Test-Path $destFile)
        }

        # ダウンロード完了を待つ（ファイルがロックされている間はリトライ）
        $retries = 0
        while ($retries -lt 10) {
            try {
                Move-Item -Path $filePath -Destination $destFile -ErrorAction Stop
                $time = Get-Date -Format "HH:mm:ss"
                Write-Host "[$time] $filename → $destFile"
                break
            } catch {
                $retries++
                Start-Sleep -Milliseconds 500
            }
        }
        if ($retries -ge 10) {
            Write-Warning "移動失敗: $filename"
        }
    }
} finally {
    $watcher.Dispose()
    Write-Host "監視終了"
}
