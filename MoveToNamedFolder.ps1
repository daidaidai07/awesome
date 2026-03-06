Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

try {
    $clickedPath = $args[0]
    if (-not $clickedPath -or -not (Test-Path -LiteralPath $clickedPath)) {
        [Environment]::Exit(0)
    }

    $parentFolder = if ((Get-Item -LiteralPath $clickedPath).PSIsContainer) {
        (Get-Item -LiteralPath $clickedPath).Parent.FullName
    } else {
        [System.IO.Path]::GetDirectoryName($clickedPath)
    }

    # Explorer COM経由で選択中の全アイテムを取得（ファイル＋フォルダ）
    $selectedItems = @()
    try {
        $shell = New-Object -ComObject Shell.Application
        $windows = $shell.Windows()
        $windowCount = $windows.Count
        for ($i = 0; $i -lt $windowCount; $i++) {
            try {
                $window = $windows.Item($i)
                if (-not $window) { continue }
                $locationUrl = $window.LocationURL
                if (-not $locationUrl) { continue }

                $uri = New-Object System.Uri($locationUrl)
                $folderPath = $uri.LocalPath.TrimEnd('\')

                if ($folderPath -ne $parentFolder.TrimEnd('\')) { continue }

                $items = $window.Document.SelectedItems()
                if (-not $items -or $items.Count -eq 0) { continue }

                # クリックされたアイテムが選択一覧にあるか確認
                $tempList = @()
                $clickedFound = $false
                for ($j = 0; $j -lt $items.Count; $j++) {
                    $item = $items.Item($j)
                    $tempList += $item.Path
                    if ($item.Path -eq $clickedPath) {
                        $clickedFound = $true
                    }
                }

                if ($clickedFound -and $tempList.Count -gt 0) {
                    $selectedItems = $tempList
                    break
                }
            } catch {
                continue
            }
        }
        if ($shell) {
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
        }
    } catch { }

    if ($selectedItems.Count -eq 0) {
        $selectedItems = @($clickedPath)
    }

    # フォルダ名入力ダイアログ
    $inputName = [Microsoft.VisualBasic.Interaction]::InputBox(
        "格納先フォルダの名前を入力してください",
        "まとめたフォルダを作成",
        "")

    # 空欄またはキャンセル
    if ([string]::IsNullOrWhiteSpace($inputName)) {
        [Environment]::Exit(0)
    }

    # フォルダ名バリデーション
    if ($inputName -match '[\\/:*?"<>|]') {
        [System.Windows.Forms.MessageBox]::Show(
            "フォルダ名に使用できない文字が含まれています。`n使用できない文字: \ / : * ? "" < > |",
            "エラー",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        )
        [Environment]::Exit(0)
    }

    # 選択アイテムの最新更新日時を取得
    $latestDate = ($selectedItems | ForEach-Object {
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

    foreach ($itemPath in $selectedItems) {
        try {
            $item = Get-Item -LiteralPath $itemPath
            $itemName = $item.Name
            $destPath = Join-Path $folderPath $itemName

            # 上書き確認
            if (Test-Path -LiteralPath $destPath) {
                $result = [System.Windows.Forms.MessageBox]::Show(
                    "「${itemName}」は既に存在します。上書きしますか？",
                    "上書き確認",
                    [System.Windows.Forms.MessageBoxButtons]::YesNo,
                    [System.Windows.Forms.MessageBoxIcon]::Question
                )
                if ($result -eq [System.Windows.Forms.DialogResult]::No) {
                    continue
                }
                Remove-Item -LiteralPath $destPath -Recurse -Force
            }

            Move-Item -LiteralPath $itemPath -Destination $destPath -Force
            $successCount++
        } catch {
            $errorCount++
            $errorMessages += "[${itemName}] $($_.Exception.Message)"
        }
    }

    # 完了通知
    if ($errorCount -gt 0) {
        $msg = "成功: ${successCount}件`nエラー: ${errorCount}件`n`n" + ($errorMessages -join "`n")
        [System.Windows.Forms.MessageBox]::Show($msg, "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    } else {
        [System.Windows.Forms.MessageBox]::Show("${successCount}件を「${folderName}」に格納しました。", "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
    }
} catch {
    [System.Windows.Forms.MessageBox]::Show("予期しないエラー: $($_.Exception.Message)", "エラー", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
} finally {
    [Environment]::Exit(0)
}
