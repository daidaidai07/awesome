Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

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

# フォルダ名入力ダイアログ
$inputName = [Microsoft.VisualBasic.Interaction]::InputBox(
    "格納先フォルダの名前を入力してください",
    "フォルダ名を指定して格納",
    "")

# 空欄またはキャンセル
if ([string]::IsNullOrWhiteSpace($inputName)) {
    exit
}

# フォルダ名バリデーション
if ($inputName -match '[\\/:*?"<>|]') {
    [System.Windows.Forms.MessageBox]::Show(
        "フォルダ名に使用できない文字が含まれています。`n使用できない文字: \ / : * ? "" < > |",
        "エラー",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    )
    exit
}

# 選択ファイルの最新更新日時を取得
$latestDate = ($selectedFiles | ForEach-Object {
    (Get-Item -LiteralPath $_).LastWriteTime
} | Measure-Object -Maximum).Maximum
$datePrefix = $latestDate.ToString("yyMMdd")

# フォルダ作成
$folderName = "${datePrefix}_${inputName}"
$folderPath = Join-Path $parentFolder $folderName
if (-not (Test-Path -LiteralPath $folderPath)) {
    New-Item -ItemType Directory -Path $folderPath | Out-Null
}

$successCount = 0
$errorCount = 0
$errorMessages = @()

foreach ($filePath in $selectedFiles) {
    try {
        $file = Get-Item -LiteralPath $filePath
        $fileName = $file.Name
        $destPath = Join-Path $folderPath $fileName

        # 上書き確認
        if (Test-Path -LiteralPath $destPath) {
            $result = [System.Windows.Forms.MessageBox]::Show(
                "${fileName} は既に存在します。上書きしますか？",
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
} else {
    [System.Windows.Forms.MessageBox]::Show("${successCount}件のファイルを「${folderName}」に格納しました。", "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
}
