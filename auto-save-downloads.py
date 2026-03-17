"""
auto-save-downloads.py
ダウンロードフォルダを監視し、新しいファイルを日付付きの同名フォルダに自動整理する

使い方:
  python auto-save-downloads.py
  python auto-save-downloads.py --watch-dir "C:\\Users\\you\\Downloads"

保存形式:
  example.pdf           → Downloads\\YYMMDD_example\\example.pdf
  260313_example.pdf    → Downloads\\260313_example\\260313_example.pdf (YYMMDD_プレフィックスを流用)
  20260313_example.pdf  → Downloads\\260313_example\\20260313_example.pdf (YYYYMMDD_→YYMMDD_に変換)

依存: pip install watchdog
"""

import argparse
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

SKIP_EXTENSIONS = {".crdownload", ".part", ".tmp"}


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        self.watch_dir = Path(watch_dir)

    def on_created(self, event):
        if event.is_directory:
            return
        self._process(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self._process(event.dest_path)

    def _process(self, filepath):
        filepath = Path(filepath)

        # 監視ディレクトリ直下のファイルのみ対象
        if filepath.parent != self.watch_dir:
            return

        filename = filepath.name

        # 隠しファイルはスキップ
        if filename.startswith("."):
            return

        # 一時ファイルはスキップ
        if filepath.suffix.lower() in SKIP_EXTENSIONS:
            return

        # ダウンロード完了を待つ
        time.sleep(1)

        if not filepath.exists():
            return

        basename_no_ext = filepath.stem
        date_prefix = datetime.now().strftime("%y%m%d")

        # フォルダ名用: ファイル名に日付プレフィックス (YYYYMMDD_ or YYMMDD_) が付いている場合は除去して重複防止
        folder_base = basename_no_ext
        if re.match(r"^\d{8}_", basename_no_ext):
            date_prefix = basename_no_ext[2:8]
            folder_base = basename_no_ext[9:]
        elif re.match(r"^\d{6}_", basename_no_ext):
            date_prefix = basename_no_ext[:6]
            folder_base = basename_no_ext[7:]

        # 保存先フォルダを作成（必ず日付プレフィックスを付与）
        dest_dir = self.watch_dir / f"{date_prefix}_{folder_base}"
        dest_dir.mkdir(exist_ok=True)

        # 保存先ファイルパス（ファイル名はそのまま維持）
        dest_file = dest_dir / filename

        # 同名ファイルが既に存在する場合は連番を付与
        if dest_file.exists():
            counter = 1
            while True:
                dest_file = dest_dir / f"{filepath.stem}_{counter}{filepath.suffix}"
                if not dest_file.exists():
                    break
                counter += 1

        # ファイル移動（ロック中はリトライ）
        for attempt in range(10):
            try:
                shutil.move(str(filepath), str(dest_file))
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] {filename} → {dest_file}")
                return
            except (PermissionError, OSError):
                time.sleep(0.5)

        print(f"[警告] 移動失敗: {filename}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="ダウンロードフォルダ自動整理")
    parser.add_argument(
        "--watch-dir",
        default=os.path.join(os.path.expanduser("~"), "Downloads"),
        help="監視するディレクトリ (デフォルト: ~/Downloads)",
    )
    args = parser.parse_args()

    watch_dir = args.watch_dir
    if not os.path.isdir(watch_dir):
        print(f"エラー: ディレクトリが見つかりません: {watch_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"監視開始: {watch_dir}")
    print("終了するには Ctrl+C を押してください")

    handler = DownloadHandler(watch_dir)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n監視終了")

    observer.join()


if __name__ == "__main__":
    main()
