"""
ダウンロードフォルダ監視モジュール
=================================
watchdog ベースでダウンロードフォルダを常時監視し、
新しいファイルを3層分類 → プロジェクトフォルダへ自動振り分けする。

auto-save-downloads.py の DownloadHandler をベースに、
classifier.py の分類チェーンを統合。
"""

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from classifier import (
    classify_file,
    save_history_entry,
)
from config import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    SKIP_EXTENSIONS,
    UNKNOWN_DIR,
    load_projects_yaml,
    scan_all_subfolders,
    scan_projects,
)
from mover import move_file_to_project, move_file_to_watch_dir


class DownloadHandler(FileSystemEventHandler):
    """ダウンロードフォルダの新規ファイルを検知し、自動仕分けする。"""

    def __init__(
        self,
        watch_dir: str,
        root_folder: str,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        yaml_config: dict | None = None,
        on_sorted: Callable | None = None,
        on_low_confidence: Callable | None = None,
        on_log: Callable | None = None,
    ):
        self.watch_dir = Path(watch_dir)
        self.root_folder = root_folder
        self.confidence_threshold = confidence_threshold
        self.yaml_config = yaml_config
        self.on_sorted = on_sorted  # callback(filepath, result, moved_to)
        self.on_low_confidence = on_low_confidence  # callback(filepath, result)
        self.on_log = on_log  # callback(message)

    def _log(self, message: str):
        now = datetime.now().strftime("%H:%M:%S")
        text = f"[{now}] {message}"
        if self.on_log:
            self.on_log(text)
        else:
            print(text)

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

        self._log(f"検知: {filename}")

        # プロジェクト構造をスキャン
        projects = scan_projects(self.root_folder)
        subfolder_map = scan_all_subfolders(self.root_folder, projects)

        if not projects:
            self._log(f"プロジェクトフォルダなし → ダウンロードフォルダ内で整理: {filename}")
            moved = move_file_to_watch_dir(str(filepath), str(self.watch_dir))
            self._log(f"{filename} → {moved}")
            return

        # 3層分類
        result = classify_file(
            filename=filename,
            root_folder=self.root_folder,
            projects=projects,
            subfolder_map=subfolder_map,
            yaml_config=self.yaml_config,
            user_comment="",  # 常時監視モードではコメントなし
        )

        project = result["project"]
        subfolder = result.get("subfolder", "")
        confidence = result.get("confidence", 0.0)
        method = result.get("method", "不明")

        # 信頼度判定
        if confidence < self.confidence_threshold and project != "unknown":
            self._log(
                f"低信頼度 ({confidence:.2f}): {filename} → {project} [{method}]"
            )
            if self.on_low_confidence:
                # 通知コールバックで確認を求める
                self.on_low_confidence(str(filepath), result)
                return

        # プロジェクト不明 or unknown
        if project == "unknown" or project not in projects:
            dest_dir = str(Path(self.root_folder) / UNKNOWN_DIR)
            moved = self._move_with_retry(str(filepath), dest_dir, is_project=True)
            if moved:
                self._log(f"プロジェクト不明 → {UNKNOWN_DIR}: {filename} [{method}]")
                save_history_entry(
                    self.root_folder, filename, UNKNOWN_DIR, "", method=method
                )
            return

        # サブフォルダのバリデーション
        valid_subs = subfolder_map.get(project, [])
        if subfolder not in valid_subs:
            subfolder = valid_subs[0] if valid_subs else ""

        if subfolder:
            dest_dir = str(Path(self.root_folder) / project / subfolder)
        else:
            dest_dir = str(Path(self.root_folder) / project)

        moved = self._move_with_retry(str(filepath), dest_dir, is_project=True)
        if moved:
            display = f"{project}/{subfolder}" if subfolder else project
            self._log(f"{filename} → {display} [{method}] (信頼度: {confidence:.2f})")
            save_history_entry(
                self.root_folder, filename, project, subfolder, method=method
            )
            if self.on_sorted:
                self.on_sorted(str(filepath), result, moved)

    def _move_with_retry(self, filepath: str, dest_dir: str,
                         is_project: bool = True) -> str | None:
        """ファイル移動をリトライ付きで実行。"""
        for attempt in range(10):
            try:
                if is_project:
                    return move_file_to_project(filepath, dest_dir)
                else:
                    return move_file_to_watch_dir(filepath, str(self.watch_dir))
            except (PermissionError, OSError):
                time.sleep(0.5)

        self._log(f"移動失敗: {Path(filepath).name}")
        return None


class FolderWatcher:
    """ダウンロードフォルダ監視の管理クラス。"""

    def __init__(
        self,
        watch_dir: str,
        root_folder: str,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        yaml_config: dict | None = None,
        on_sorted: Callable | None = None,
        on_low_confidence: Callable | None = None,
        on_log: Callable | None = None,
    ):
        self.watch_dir = watch_dir
        self.root_folder = root_folder
        self.handler = DownloadHandler(
            watch_dir=watch_dir,
            root_folder=root_folder,
            confidence_threshold=confidence_threshold,
            yaml_config=yaml_config,
            on_sorted=on_sorted,
            on_low_confidence=on_low_confidence,
            on_log=on_log,
        )
        self._observer: Observer | None = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def start(self):
        """監視を開始する。"""
        if self.is_running:
            return

        if not Path(self.watch_dir).is_dir():
            raise FileNotFoundError(f"監視ディレクトリが見つかりません: {self.watch_dir}")

        self._observer = Observer()
        self._observer.schedule(self.handler, self.watch_dir, recursive=False)
        self._observer.start()

    def stop(self):
        """監視を停止する。"""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def update_config(
        self,
        root_folder: str | None = None,
        confidence_threshold: float | None = None,
        yaml_config: dict | None = None,
    ):
        """設定を動的に更新する。"""
        if root_folder is not None:
            self.root_folder = root_folder
            self.handler.root_folder = root_folder
        if confidence_threshold is not None:
            self.handler.confidence_threshold = confidence_threshold
        if yaml_config is not None:
            self.handler.yaml_config = yaml_config
