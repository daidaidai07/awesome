Add-Type -AssemblyName System.Windows.Forms

$mutex = New-Object System.Threading.Mutex($false, "Global\FileOrganizer_Individual")
if (-not $mutex.WaitOne(1000)) {
    [Environment]::Exit(0)
}

try {
    $clickedPath = $args[0]
    if (-not $clickedPath -or -not (Test-Path -LiteralPath $clickedPath)) {
        return
    }

    $parentFolder = if ((Get-Item -LiteralPath $clickedPath).PSIsContainer) {
        (Get-Item -LiteralPath $clickedPath).Parent.FullName
    } else {
        [System.IO.Path]::GetDirectoryName($clickedPath)
    }

    # Explorer COM経由で選択中の全アイテムを取得
    $selectedItems = @()
    Start-Sleep -Milliseconds 200
    try {
        $shell = New-Object -ComObject Shell.Application
        $windows = $shell.Windows()
        $windowCount = $windows.Count
        $normalizedClicked = [System.IO.Path]::GetFullPath($clickedPath).ToLower()
        $normalizedParent = $parentFolder.TrimEnd('\').ToLower()
        $bestMatch = @()
        $folderMatch = @()
        for ($i = 0; $i -lt $windowCount; $i++) {
            try {
                $window = $windows.Item($i)
                if (-not $window) { continue }
                try {
                    $items = $window.Document.SelectedItems()
                } catch { continue }
                if (-not $items -or $items.Count -eq 0) { continue }
                $tempList = @()
                $clickedFound = $false
                for ($j = 0; $j -lt $items.Count; $j++) {
                    try {
                        $item = $items.Item($j)
                        $tempList += $item.Path
                        if ([System.IO.Path]::GetFullPath($item.Path).ToLower() -eq $normalizedClicked) {
                            $clickedFound = $true
                        }
                    } catch { continue }
                }
                if ($tempList.Count -gt 0) {
                    if ($clickedFound) {
                        $bestMatch = $tempList
                        break
                    }
                    if ($folderMatch.Count -eq 0) {
                        # フォルダパスで一致確認（フォールバック用）
                        $windowFolderPath = $null
                        $locationUrl = $window.LocationURL
                        if ($locationUrl) {
                            try {
                                $uri = New-Object System.Uri($locationUrl)
                                $windowFolderPath = $uri.LocalPath.TrimEnd('\').ToLower()
                            } catch { }
                        }
                        if (-not $windowFolderPath) {
                            try {
                                $windowFolderPath = $window.Document.Folder.Self.Path.TrimEnd('\').ToLower()
                            } catch { }
                        }
                        if ($windowFolderPath -eq $normalizedParent) {
                            $folderMatch = $tempList
                        }
                    }
                }
            } catch { continue }
        }
        if ($bestMatch.Count -gt 0) {
            $selectedItems = $bestMatch
        } elseif ($folderMatch.Count -gt 0) {
            $selectedItems = $folderMatch
        }
        if ($shell) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null }
    } catch { }

    if ($selectedItems.Count -eq 0) {
        $selectedItems = @($clickedPath)
    }

    # 命名規則選択ダイアログ
    function Show-NamingDialog {
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "個別のフォルダを作成"
        $form.Size = New-Object System.Drawing.Size(320, 240)
        $form.StartPosition = "CenterScreen"
        $form.FormBorderStyle = "FixedDialog"
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.TopMost = $true

        $label = New-Object System.Windows.Forms.Label
        $label.Text = "命名規則を選択してください："
        $label.Location = New-Object System.Drawing.Point(15, 15)
        $label.Size = New-Object System.Drawing.Size(280, 20)

        $radio1 = New-Object System.Windows.Forms.RadioButton
        $radio1.Text = "先頭に日付 (YYMMDD_)"
        $radio1.Location = New-Object System.Drawing.Point(25, 42)
        $radio1.Size = New-Object System.Drawing.Size(260, 24)
        $radio1.Checked = $true

        $radio2 = New-Object System.Windows.Forms.RadioButton
        $radio2.Text = "末尾に日付 (_YYMMDD)"
        $radio2.Location = New-Object System.Drawing.Point(25, 68)
        $radio2.Size = New-Object System.Drawing.Size(260, 24)

        $radio3 = New-Object System.Windows.Forms.RadioButton
        $radio3.Text = "先頭に番号 (01_, 02_...)"
        $radio3.Location = New-Object System.Drawing.Point(25, 94)
        $radio3.Size = New-Object System.Drawing.Size(260, 24)

        $radio4 = New-Object System.Windows.Forms.RadioButton
        $radio4.Text = "なし"
        $radio4.Location = New-Object System.Drawing.Point(25, 120)
        $radio4.Size = New-Object System.Drawing.Size(260, 24)

        $okButton = New-Object System.Windows.Forms.Button
        $okButton.Text = "OK"
        $okButton.Size = New-Object System.Drawing.Size(80, 28)
        $okButton.Location = New-Object System.Drawing.Point(70, 160)
        $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK

        $cancelButton = New-Object System.Windows.Forms.Button
        $cancelButton.Text = "キャンセル"
        $cancelButton.Size = New-Object System.Drawing.Size(80, 28)
        $cancelButton.Location = New-Object System.Drawing.Point(160, 160)
        $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

        $form.Controls.AddRange(@($label, $radio1, $radio2, $radio3, $radio4, $okButton, $cancelButton))
        $form.AcceptButton = $okButton
        $form.CancelButton = $cancelButton

        $dialogResult = $form.ShowDialog()
        $mode = $null
        if ($dialogResult -eq [System.Windows.Forms.DialogResult]::OK) {
            if ($radio1.Checked) { $mode = "DatePrefix" }
            if ($radio2.Checked) { $mode = "DateSuffix" }
            if ($radio3.Checked) { $mode = "NumberPrefix" }
            if ($radio4.Checked) { $mode = "None" }
        }
        $form.Dispose()
        return $mode
    }

    # 命名規則を適用する関数
    function Get-FormattedName {
        param([string]$Name, [string]$Mode, [datetime]$Date, [int]$Number)
        switch ($Mode) {
            "DatePrefix" {
                if ($Name -match '^\d{8}_' -or $Name -match '^\d{6}_') { return $Name }
                return $Date.ToString("yyMMdd") + "_" + $Name
            }
            "DateSuffix" {
                if ($Name -match '_\d{8}$' -or $Name -match '_\d{6}$') { return $Name }
                return $Name + "_" + $Date.ToString("yyMMdd")
            }
            "NumberPrefix" {
                return $Number.ToString("00") + "_" + $Name
            }
            "None" {
                return $Name
            }
        }
        return $Name
    }

    $namingMode = Show-NamingDialog
    if (-not $namingMode) { return }

    $successCount = 0
    $errorCount = 0
    $errorMessages = @()
    $counter = 0

    foreach ($itemPath in $selectedItems) {
        $counter++
        try {
            $item = Get-Item -LiteralPath $itemPath
            $itemName = $item.Name
            $directory = if ($item.PSIsContainer) { $item.Parent.FullName } else { $item.DirectoryName }

            if ($item.PSIsContainer) {
                # === フォルダ：リネームのみ ===
                if ($namingMode -eq "None") {
                    $successCount++
                    continue
                }
                $newFolderName = Get-FormattedName -Name $itemName -Mode $namingMode -Date $item.LastWriteTime -Number $counter
                if ($newFolderName -eq $itemName) {
                    $successCount++
                    continue
                }
                $destPath = Join-Path $directory $newFolderName
                if (Test-Path -LiteralPath $destPath) {
                    $result = [System.Windows.Forms.MessageBox]::Show(
                        "「${newFolderName}」は既に存在します。スキップしますか？",
                        "フォルダ名の競合",
                        [System.Windows.Forms.MessageBoxButtons]::YesNo,
                        [System.Windows.Forms.MessageBoxIcon]::Question
                    )
                    if ($result -eq [System.Windows.Forms.DialogResult]::Yes) { continue }
                }
                Rename-Item -LiteralPath $itemPath -NewName $newFolderName
                $successCount++
            } else {
                # === ファイル：フォルダ作成＋移動 ===
                $baseName = $item.BaseName
                $extension = $item.Extension
                $newBaseName = Get-FormattedName -Name $baseName -Mode $namingMode -Date $item.LastWriteTime -Number $counter

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
                    if ($result -eq [System.Windows.Forms.DialogResult]::No) { continue }
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
    try { $mutex.ReleaseMutex() } catch { }
    try { $mutex.Dispose() } catch { }
    [Environment]::Exit(0)
}
