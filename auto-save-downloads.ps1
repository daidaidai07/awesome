#
# auto-save-downloads.ps1
# ダウンロードフォルダを監視し、新しいファイルを日付付きの同名フォルダに自動整理する
#
# 使い方:
#   .\auto-save-downloads.ps1
#   .\auto-save-downloads.ps1 -WatchDir "C:\Users\you\Downloads"
#
# 保存形式:
#   example.pdf         → Downloads\YYMMDD_example\example.pdf
#   260313_example.pdf  → Downloads\YYMMDD_example\260313_example.pdf (日付重複を防止)
#
# 追加インストール不要（Windows標準のFileSystemWatcherを使用）

param(
    [string]$WatchDir = "$env:USERPROFILE\Downloads"
)

# 監視対象ディレクトリの存在確認
if (-not (Test-Path $WatchDir)) {
    Write-Error "エラー: ディレクトリが見つかりません: $WatchDir"
    exit 1
}

# スキップ対象の拡張子
$SkipExtensions = @('.crdownload', '.part', '.tmp')

function Move-DownloadedFile {
    param([string]$FilePath)

    $filename = [System.IO.Path]::GetFileName($FilePath)

    # ファイルが存在しない場合はスキップ
    if (-not (Test-Path $FilePath)) { return }

    # 隠しファイルはスキップ
    if ($filename.StartsWith('.')) { return }

    # 一時ファイルはスキップ
    $ext = [System.IO.Path]::GetExtension($filename)
    if ($ext -in $SkipExtensions) { return }

    # ファイル名と拡張子を分離
    $basenameNoExt = [System.IO.Path]::GetFileNameWithoutExtension($filename)

    # 日付プレフィックス (YYMMDD)
    $datePrefix = Get-Date -Format "yyMMdd"

    # フォルダ名用: ファイル名に日付プレフィックス (YYMMDD_) が付いている場合は除去して重複防止
    $folderBase = $basenameNoExt
    if ($basenameNoExt -match '^\d{6}_') {
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
        $nameWithoutExt = [System.IO.Path]::GetFileNameWithoutExtension($filename)
        $extension = [System.IO.Path]::GetExtension($filename)
        do {
            $destFile = Join-Path $destDir "${nameWithoutExt}_${counter}${extension}"
            $counter++
        } while (Test-Path $destFile)
    }

    # ダウンロード完了を待つ（ファイルがロックされている間はリトライ）
    $retries = 0
    while ($retries -lt 10) {
        try {
            Move-Item -Path $FilePath -Destination $destFile -ErrorAction Stop
            $time = Get-Date -Format "HH:mm:ss"
            Write-Host "[$time] $filename → $destFile"
            return
        } catch {
            $retries++
            Start-Sleep -Milliseconds 500
        }
    }
    Write-Warning "移動失敗: $filename (ファイルがロックされています)"
}

Write-Host "監視開始: $WatchDir"
Write-Host "終了するには Ctrl+C を押してください"

# FileSystemWatcher でフォルダを監視
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $WatchDir
$watcher.Filter = "*.*"
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite
$watcher.EnableRaisingEvents = $true

# イベント登録
$action = {
    $filePath = $Event.SourceEventArgs.FullPath
    # サブフォルダ内のファイルはスキップ
    $dir = [System.IO.Path]::GetDirectoryName($filePath)
    if ($dir -ne $Event.MessageData) { return }
    Start-Sleep -Milliseconds 500
    Move-DownloadedFile -FilePath $filePath
}

Register-ObjectEvent $watcher "Created" -Action $action -MessageData $WatchDir | Out-Null
Register-ObjectEvent $watcher "Renamed" -Action $action -MessageData $WatchDir | Out-Null

# Ctrl+C まで待機
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    $watcher.EnableRaisingEvents = $false
    Get-EventSubscriber | Unregister-Event
    $watcher.Dispose()
    Write-Host "監視終了"
}
