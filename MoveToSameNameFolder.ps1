Add-Type -AssemblyName System.Windows.Forms

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

    $successCount = 0
    $errorCount = 0
    $errorMessages = @()

    foreach ($itemPath in $selectedItems) {
        try {
            $item = Get-Item -LiteralPath $itemPath
            $itemName = $item.Name
            $directory = if ($item.PSIsContainer) { $item.Parent.FullName } else { $item.DirectoryName }

            # 日付判定（YYYYMMDD_ または YYMMDD_ が先頭にあるか）
            $hasDate = $itemName -match '^\d{8}_' -or $itemName -match '^\d{6}_'

            if ($item.PSIsContainer) {
                # === フォルダの場合：日付プレフィックスを付けてリネーム ===
                if ($hasDate) {
                    $successCount++
                    continue
                }
                $datePrefix = $item.LastWriteTime.ToString("yyMMdd")
                $newFolderName = "${datePrefix}_${itemName}"
                $destPath = Join-Path $directory $newFolderName

                if (Test-Path -LiteralPath $destPath) {
                    $result = [System.Windows.Forms.MessageBox]::Show(
                        "「${newFolderName}」は既に存在します。スキップしますか？",
                        "フォルダ名の競合",
                        [System.Windows.Forms.MessageBoxButtons]::YesNo,
                        [System.Windows.Forms.MessageBoxIcon]::Question
                    )
                    if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
                        continue
                    }
                }

                Rename-Item -LiteralPath $itemPath -NewName $newFolderName
                $successCount++
            } else {
                # === ファイルの場合：同名フォルダを作成して格納 ===
                $baseName = $item.BaseName
                $extension = $item.Extension

                $newBaseName = $baseName
                if (-not $hasDate) {
                    $datePrefix = $item.LastWriteTime.ToString("yyMMdd")
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
                        "「${newFileName}」は既に存在します。上書きしますか？",
                        "上書き確認",
                        [System.Windows.Forms.MessageBoxButtons]::YesNo,
                        [System.Windows.Forms.MessageBoxIcon]::Question
                    )
                    if ($result -eq [System.Windows.Forms.DialogResult]::No) {
                        continue
                    }
                    Remove-Item -LiteralPath $destPath -Force
                }

                Move-Item -LiteralPath $itemPath -Destination $destPath -Force
                $successCount++
            }
        } catch {
            $errorCount++
            $errorMessages += "[${itemName}] $($_.Exception.Message)"
        }
    }

    # 完了通知
    if ($errorCount -gt 0) {
        $msg = "成功: ${successCount}件`nエラー: ${errorCount}件`n`n" + ($errorMessages -join "`n")
        [System.Windows.Forms.MessageBox]::Show($msg, "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    } elseif ($selectedItems.Count -gt 1) {
        [System.Windows.Forms.MessageBox]::Show("${successCount}件を処理しました。", "処理完了", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
    }
} catch {
    [System.Windows.Forms.MessageBox]::Show("予期しないエラー: $($_.Exception.Message)", "エラー", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
} finally {
    [Environment]::Exit(0)
}
