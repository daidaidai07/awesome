"""
ダウンロード自動仕分けツール（統合版）
=====================================
GUIモード: PySide6ウィンドウ + watchdog監視 + ドラッグ＆ドロップ
デーモンモード: GUI無し、システムトレイ + watchdog監視のみ

使い方:
  python main.py              # GUIモード
  python main.py --daemon     # デーモンモード（システムトレイのみ）

依存:
  pip install PySide6 watchdog pyyaml
  (pyyamlは任意 — 無くてもフォルダスキャンで動作)
"""

import argparse
import sys
import time
from pathlib import Path

from config import (
    APP_NAME,
    UNKNOWN_DIR,
    load_projects_yaml,
    scan_all_subfolders,
    scan_projects,
)


def run_gui(yaml_config: dict):
    """GUIモードで起動。"""
    from PySide6.QtWidgets import QApplication

    from gui import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(yaml_config=yaml_config)
    window.show()

    sys.exit(app.exec())


def run_daemon(yaml_config: dict):
    """デーモンモードで起動（システムトレイ + watchdog監視のみ）。"""
    watch_dir = yaml_config.get("watch_folder", str(Path.home() / "Downloads"))
    root_folder = yaml_config.get("root_folder", str(Path.home() / "Desktop"))
    threshold = yaml_config.get("confidence_threshold", 0.7)

    if not Path(watch_dir).is_dir():
        print(f"エラー: 監視ディレクトリが見つかりません: {watch_dir}", file=sys.stderr)
        sys.exit(1)

    if not Path(root_folder).is_dir():
        print(f"エラー: 整理先ディレクトリが見つかりません: {root_folder}", file=sys.stderr)
        sys.exit(1)

    # PySide6が利用可能ならシステムトレイ付きで起動
    try:
        from PySide6.QtWidgets import QApplication

        from notifier import SystemTrayNotifier
        from watcher import FolderWatcher
        from mover import move_file_to_project
        from classifier import save_history_entry

        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        notifier = SystemTrayNotifier(root_folder)

        def on_sorted(filepath, result, moved_to):
            notifier.notify_sorted(
                Path(filepath).name,
                result.get("project", "unknown"),
                result.get("method", ""),
            )

        def on_low_confidence(filepath, result):
            notifier.notify_low_confidence(filepath, result)

        def on_project_selected(filepath, result, project, subfolder):
            """ユーザーがプロジェクトを選択した場合のコールバック。"""
            if subfolder:
                dest_dir = str(Path(root_folder) / project / subfolder)
            else:
                dest_dir = str(Path(root_folder) / project)
            try:
                moved = move_file_to_project(filepath, dest_dir)
                save_history_entry(
                    root_folder, Path(filepath).name, project, subfolder,
                    method="手動選択"
                )
                print(f"[手動] {Path(filepath).name} → {project}/{subfolder}")
            except Exception as e:
                print(f"[エラー] 移動失敗: {e}", file=sys.stderr)

        def on_skipped(filepath, result):
            """ユーザーが未分類を選んだ場合のコールバック。"""
            dest_dir = str(Path(root_folder) / UNKNOWN_DIR)
            try:
                moved = move_file_to_project(filepath, dest_dir)
                print(f"[未分類] {Path(filepath).name} → {UNKNOWN_DIR}")
            except Exception as e:
                print(f"[エラー] 移動失敗: {e}", file=sys.stderr)

        notifier.project_selected.connect(on_project_selected)
        notifier.skipped.connect(on_skipped)

        def on_log(message):
            print(message)

        watcher = FolderWatcher(
            watch_dir=watch_dir,
            root_folder=root_folder,
            confidence_threshold=threshold,
            yaml_config=yaml_config,
            on_sorted=on_sorted,
            on_low_confidence=on_low_confidence,
            on_log=on_log,
        )

        notifier.set_callbacks(on_quit=app.quit)
        notifier.set_status(f"監視中: {watch_dir}")
        notifier.show()
        watcher.start()

        print(f"{APP_NAME} デーモンモード")
        print(f"監視: {watch_dir}")
        print(f"整理先: {root_folder}")
        print(f"信頼度閾値: {threshold}")
        print("システムトレイから終了できます")

        sys.exit(app.exec())

    except ImportError:
        # PySide6なしの場合はCLIのみ
        from watcher import FolderWatcher

        def on_log(message):
            print(message)

        watcher = FolderWatcher(
            watch_dir=watch_dir,
            root_folder=root_folder,
            confidence_threshold=threshold,
            yaml_config=yaml_config,
            on_log=on_log,
        )

        watcher.start()

        print(f"{APP_NAME} デーモンモード（CLI）")
        print(f"監視: {watch_dir}")
        print(f"整理先: {root_folder}")
        print("終了するには Ctrl+C を押してください")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
            print("\n監視終了")


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--daemon", action="store_true",
        help="デーモンモード（GUI無し、システムトレイ + 常時監視）",
    )
    parser.add_argument(
        "--config", default=None,
        help="projects.yaml のパス（デフォルト: スクリプトと同じディレクトリ）",
    )
    parser.add_argument(
        "--watch-dir", default=None,
        help="監視するディレクトリ（projects.yaml の設定を上書き）",
    )
    parser.add_argument(
        "--root-dir", default=None,
        help="整理先ルートディレクトリ（projects.yaml の設定を上書き）",
    )
    args = parser.parse_args()

    # 設定読み込み
    yaml_config = load_projects_yaml(args.config)

    # コマンドライン引数で上書き
    if args.watch_dir:
        yaml_config["watch_folder"] = args.watch_dir
    if args.root_dir:
        yaml_config["root_folder"] = args.root_dir

    if args.daemon:
        run_daemon(yaml_config)
    else:
        run_gui(yaml_config)


if __name__ == "__main__":
    main()
