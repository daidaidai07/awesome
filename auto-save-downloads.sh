#!/bin/bash
#
# auto-save-downloads.sh
# ダウンロードフォルダを監視し、新しいファイルを日付付きの同名フォルダに自動整理する
#
# 使い方:
#   ./auto-save-downloads.sh [監視するディレクトリ]
#   デフォルトは ~/Downloads
#
# 保存形式:
#   example.pdf         → Downloads/example/example.pdf
#   260313_example.pdf  → Downloads/example/260313_example.pdf (フォルダ名から日付除去)
#
# 依存: inotify-tools (sudo apt install inotify-tools)

set -euo pipefail

WATCH_DIR="${1:-$HOME/Downloads}"

# 監視対象ディレクトリの存在確認
if [ ! -d "$WATCH_DIR" ]; then
    echo "エラー: ディレクトリが見つかりません: $WATCH_DIR" >&2
    exit 1
fi

# inotifywait の存在確認
if ! command -v inotifywait &>/dev/null; then
    echo "エラー: inotify-tools がインストールされていません" >&2
    echo "  sudo apt install inotify-tools" >&2
    exit 1
fi

echo "監視開始: $WATCH_DIR"
echo "終了するには Ctrl+C を押してください"

# ファイルの書き込み完了 (close_write) と移動完了 (moved_to) を監視
inotifywait -m -e close_write -e moved_to --format '%f' "$WATCH_DIR" |
while read -r filename; do
    filepath="$WATCH_DIR/$filename"

    # ファイルが存在しない場合はスキップ（既に移動済みなど）
    [ -f "$filepath" ] || continue

    # 隠しファイル・一時ファイルはスキップ
    case "$filename" in
        .*) continue ;;
        *.crdownload) continue ;;  # Chrome の途中ダウンロード
        *.part)       continue ;;  # Firefox の途中ダウンロード
        *.tmp)        continue ;;
    esac

    # ファイル名と拡張子を分離
    basename_no_ext="${filename%.*}"
    if [ "$basename_no_ext" = "$filename" ]; then
        # 拡張子なしのファイル
        basename_no_ext="$filename"
    fi

    # 日付プレフィックス (YYMMDD)
    date_prefix=$(date +%y%m%d)

    # フォルダ名用: ファイル名に日付プレフィックス (YYMMDD_) が付いている場合は除去
    folder_name="$basename_no_ext"
    if [[ "$basename_no_ext" =~ ^[0-9]{6}_ ]]; then
        folder_name="${basename_no_ext#??????_}"
    fi

    # 保存先フォルダを作成
    dest_dir="$WATCH_DIR/$folder_name"
    mkdir -p "$dest_dir"

    # 保存先ファイルパス（ファイル名はそのまま維持）
    dest_file="$dest_dir/${filename}"

    # 同名ファイルが既に存在する場合は連番を付与
    if [ -f "$dest_file" ]; then
        counter=1
        ext="${filename##*.}"
        name_without_ext="${filename%.*}"
        while [ -f "$dest_dir/${name_without_ext}_${counter}.${ext}" ]; do
            ((counter++))
        done
        dest_file="$dest_dir/${name_without_ext}_${counter}.${ext}"
    fi

    mv "$filepath" "$dest_file"
    echo "[$(date '+%H:%M:%S')] $filename → $dest_file"
done
