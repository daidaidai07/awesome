Add-Type -AssemblyName System.Windows.Forms

$mutex = New-Object System.Threading.Mutex($false, "Global\FileOrganizer_Named")
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
                $tempList = @()
                $clickedFound = $false
                for ($j = 0; $j -lt $items.Count; $j++) {
                    $item = $items.Item($j)
                    $tempList += $item.Path
                    if ($item.Path -eq $clickedPath) { $clickedFound = $true }
                }
                if ($clickedFound -and $tempList.Count -gt 0) {
                    $selectedItems = $tempList
                    break
                }
            } catch { continue }
        }
        if ($shell) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null }
    } catch { }

    if ($selectedItems.Count -eq 0) {
        $selectedItems = @($clickedPath)
    }

    # フォルダ名＋命名規則の統合ダイアログ
    function Show-NamedFolderDialog {
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "まとめたフォルダを作成"
        $form.Size = New-Object System.Drawing.Size(340, 290)
        $form.StartPosition = "CenterScreen"
        $form.FormBorderStyle = "FixedDialog"
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.TopMost = $true

        $nameLabel = New-Object System.Windows.Forms.Label
        $nameLabel.Text = "フォルダ名："
        $nameLabel.Location = New-Object System.Drawing.Point(15, 18)
        $nameLabel.Size = New-Object System.Drawing.Size(70, 20)

        $nameBox = New-Object System.Windows.Forms.TextBox
        $nameBox.Location = New-Object System.Drawing.Point(90, 15)
        $nameBox.Size = New-Object System.Drawing.Size(220, 22)

        $ruleLabel = New-Object System.Windows.Forms.Label
        $ruleLabel.Text = "命名規則："
        $ruleLabel.Location = New-Object System.Drawing.Point(15, 50)
        $ruleLabel.Size = New-Object System.Drawing.Size(280, 20)

        $radio1 = New-Object System.Windows.Forms.RadioButton
        $radio1.Text = "先頭に日付 (260303_)"
        $radio1.Location = New-Object System.Drawing.Point(25, 74)
        $radio1.Size = New-Object System.Drawing.Size(280, 24)
        $radio1.Checked = $true

        $radio2 = New-Object System.Windows.Forms.RadioButton
        $radio2.Text = "末尾に日付 (_260303)"
        $radio2.Location = New-Object System.Drawing.Point(25, 100)
        $radio2.Size = New-Object System.Drawing.Size(280, 24)

        $radio3 = New-Object System.Windows.Forms.RadioButton
        $radio3.Text = "先頭に番号 (自動連番)"
        $radio3.Location = New-Object System.Drawing.Point(25, 126)
        $radio3.Size = New-Object System.Drawing.Size(280, 24)

        $radio4 = New-Object System.Windows.Forms.RadioButton
        $radio4.Text = "なし"
        $radio4.Location = New-Object System.Drawing.Point(25, 152)
        $radio4.Size = New-Object System.Drawing.Size(280, 24)

        $okButton = New-Object System.Windows.Forms.Button
        $okButton.Text = "OK"
        $okButton.Size = New-Object System.Drawing.Size(80, 28)
        $okButton.Location = New-Object System.Drawing.Point(80, 210)
        $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK

        $cancelButton = New-Object System.Windows.Forms.Button
        $cancelButton.Text = "キャンセル"
        $cancelButton.Size = New-Object System.Drawing.Size(80, 28)
        $cancelButton.Location = New-Object System.Drawing.Point(170, 210)
        $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

        $form.Controls.AddRange(@($nameLabel, $nameBox, $ruleLabel, $radio1, $radio2, $radio3, $radio4, $okButton, $cancelButton))
        $form.AcceptButton = $okButton
        $form.CancelButton = $cancelButton

        $dialogResult = $form.ShowDialog()
        $name = $nameBox.Text
        $mode = "DatePrefix"
        if ($radio2.Checked) { $mode = "DateSuffix" }
        if ($radio3.Checked) { $mode = "NumberPrefix" }
        if ($radio4.Checked) { $mode = "None" }
        $form.Dispose()

        if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK) {
            return $null
        }
        return @{ Name = $name; Mode = $mode }
    }

    $dialogResult = Show-NamedFolderDialog
    if (-not $dialogResult) { return }

    $inputName = $dialogResult.Name
    $namingMode = $dialogResult.Mode

    # 空欄チェック
    if ([string]::IsNullOrWhiteSpace($inputName)) { return }

    # フォルダ名バリデーション
    if ($inputName -match '[\\/:*?"<>|]') {
        [System.Windows.Forms.MessageBox]::Show(
            "フォルダ名に使用できない文字が含まれています。`n使用できない文字: \ / : * ? "" < > |",
            "エラー",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        )
        return
    }

    # 命名規則に基づきフォルダ名を生成
    switch ($namingMode) {
        "DatePrefix" {
            $latestDate = ($selectedItems | ForEach-Object {
                (Get-Item -LiteralPath $_).LastWriteTime
            } | Measure-Object -Maximum).Maximum
            $folderName = $latestDate.ToString("yyMMdd") + "_" + $inputName
        }
        "DateSuffix" {
            $latestDate = ($selectedItems | ForEach-Object {
                (Get-Item -LiteralPath $_).LastWriteTime
            } | Measure-Object -Maximum).Maximum
            $folderName = $inputName + "_" + $latestDate.ToString("yyMMdd")
        }
        "NumberPrefix" {
            $existingNumbers = @(Get-ChildItem -Path $parentFolder -Directory |
                Where-Object { $_.Name -match '^\d{2}_' } |
                ForEach-Object { [int]$_.Name.Substring(0, 2) })
            $nextNumber = if ($existingNumbers.Count -gt 0) {
                ($existingNumbers | Measure-Object -Maximum).Maximum + 1
            } else { 1 }
            $folderName = $nextNumber.ToString("00") + "_" + $inputName
        }
        "None" {
            $folderName = $inputName
        }
    }

    # フォルダ作成
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
                if ($result -eq [System.Windows.Forms.DialogResult]::No) { continue }
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
    try { $mutex.ReleaseMutex() } catch { }
    try { $mutex.Dispose() } catch { }
    [Environment]::Exit(0)
}
