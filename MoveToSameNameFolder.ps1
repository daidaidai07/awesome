Add-Type -AssemblyName System.Windows.Forms

$clickedFile = $args[0]
if (-not $clickedFile -or -not (Test-Path -LiteralPath $clickedFile)) {
    exit
}

$parentFolder = [System.IO.Path]::GetDirectoryName($clickedFile)

# Explorer COM経由で選択中の全ファイルを取得
$selectedFiles = @()
try {
    $shell = New-Object -ComObject Shell.Application
    $windows = $shell.Windows()
    for ($i = 0; $i -lt $windows.Count; $i++) {
        $window = $windows.Item($i)
        $locationUrl = $window.LocationURL
        if (-not $locationUrl) { continue }
        try {
            $uri = New-Object System.Uri($locationUrl)
            $folderPath = $uri.LocalPath
        } catch {
            continue
        }
        if ($folderPath.TrimEnd('\') -eq $parentFolder.TrimEnd('\')) {
            $items = $window.Document.SelectedItems()
            for ($j = 0; $j -lt $items.Count; $j++) {
                $item = $items.Item($j)
                if (-not $item.IsFolder) {
                    $selectedFiles += $item.Path
                }
            }
            break
        }
    }
} catch { }

if ($selectedFiles.Count -eq 0) {
    $selectedFiles = @($clickedFile)
}

$successCount = 0
$errorCount = 0
$errorMessages = @()

foreach ($filePath in $selectedFiles) {
    try {
        $file = Get-Item -LiteralPath $filePath
        $fileName = $file.Name
        $baseName = $file.BaseName
        $extension = $file.Extension
        $directory = $file.DirectoryName

        # 日付判定（YYYYMMDD_ または YYMMDD_ が先頭にあるか）
        $hasDate = $fileName -match '^\d{8}_' -or $fileName -match '^\d{6}_'

        $newBaseName = $baseName
        if (-not $hasDate) {
            $datePrefix = $file.LastWriteTime.ToString("yyMMdd")
            $newBaseName = "${datePrefix}_${baseName}"
        }

        # フォルダ作成
        $folderPath = Join-Path $directory $newBaseName
        if (-not (Test-Path -LiteralPath $folderPath)) {
            New-Item -ItemType Directory -Path $folderPath | Out-Null
        }

        # 移動先パス
        $newFileName = "${newBaseName}${extension}"
        $destPath = Join-Path $folderPath $newFileName

        # 上書き確認
        if (Test-Path -LiteralPath $destPath) {
            $result = [System.Windows.Forms.MessageBox]::Show(
                "${newFileName} は既に存在します。上書きしますか？",
                "上書き確認",
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Question
            )
            if ($result -eq [System.Windows.Forms.DialogResult]::No) {
                continue
            }
            Remove-Item -LiteralPath $destPath -Force
        }

        Move-Item -LiteralPath $filePath -Destination $destPath -Force
        $successCount++
    } catch {
        $errorCount++
        $errorMessages += "[${fileName}] $($_.Exception.Message)"
    }
}

# 完了通知
if ($errorCount -gt 0) {
    $msg = "成功: ${successCount}件`nエラー: ${errorCount}件`n`n" + ($errorMessages -join "`n")
    [System.Windows.Forms.MessageBox]::Show($msg, "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
} elseif ($selectedFiles.Count -gt 1) {
    [System.Windows.Forms.MessageBox]::Show("${successCount}件のファイルを処理しました。", "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
}
