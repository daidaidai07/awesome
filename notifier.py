"""
システムトレイ通知モジュール
===========================
信頼度が低い場合のトースト通知と、プロジェクト選択ポップアップを提供。
PySide6 の QSystemTrayIcon を使用。
"""

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from config import APP_NAME, scan_projects, scan_subfolders


class ProjectSelectDialog(QDialog):
    """低信頼度ファイルのプロジェクト選択ダイアログ。"""

    def __init__(self, filename: str, ai_suggestion: dict,
                 root_folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("分類先を確認")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.selected_project = ""
        self.selected_subfolder = ""
        self.root_folder = root_folder

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ファイル名
        file_label = QLabel(f"ファイル: {filename}")
        file_label.setWordWrap(True)
        file_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(file_label)

        # AI提案
        suggested = ai_suggestion.get("project", "unknown")
        confidence = ai_suggestion.get("confidence", 0.0)
        method = ai_suggestion.get("method", "")
        hint_label = QLabel(
            f"AI提案: {suggested} (信頼度: {confidence:.0%}) [{method}]"
        )
        hint_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(hint_label)

        # プロジェクト選択
        proj_label = QLabel("プロジェクト:")
        proj_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(proj_label)

        self._project_combo = QComboBox()
        projects = scan_projects(root_folder)
        self._project_combo.addItems(projects)
        # AI提案をデフォルト選択
        if suggested in projects:
            self._project_combo.setCurrentText(suggested)
        self._project_combo.currentTextChanged.connect(self._on_project_changed)
        layout.addWidget(self._project_combo)

        # サブフォルダ選択
        sub_label = QLabel("サブフォルダ:")
        sub_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(sub_label)

        self._subfolder_combo = QComboBox()
        layout.addWidget(self._subfolder_combo)

        # 初期サブフォルダ
        if projects:
            self._on_project_changed(self._project_combo.currentText())
            suggested_sub = ai_suggestion.get("subfolder", "")
            if suggested_sub:
                idx = self._subfolder_combo.findText(suggested_sub)
                if idx >= 0:
                    self._subfolder_combo.setCurrentIndex(idx)

        # ボタン
        btn_row = QHBoxLayout()

        accept_btn = QPushButton("この分類先に移動")
        accept_btn.setStyleSheet(
            "background: #6196ff; color: white; border: none; "
            "border-radius: 6px; padding: 8px 16px; font-weight: bold;"
        )
        accept_btn.clicked.connect(self._accept)
        btn_row.addWidget(accept_btn)

        skip_btn = QPushButton("未分類にする")
        skip_btn.setStyleSheet(
            "background: #555; color: white; border: none; "
            "border-radius: 6px; padding: 8px 16px;"
        )
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)

        layout.addLayout(btn_row)

    def _on_project_changed(self, project: str):
        self._subfolder_combo.clear()
        subs = scan_subfolders(self.root_folder, project)
        self._subfolder_combo.addItems(subs)

    def _accept(self):
        self.selected_project = self._project_combo.currentText()
        self.selected_subfolder = self._subfolder_combo.currentText()
        self.accept()


class SystemTrayNotifier(QObject):
    """システムトレイアイコンとトースト通知を管理する。"""

    # シグナル: ユーザーが分類先を選択した時
    project_selected = Signal(str, dict, str, str)  # filepath, result, project, subfolder
    # シグナル: ユーザーが未分類を選んだ時
    skipped = Signal(str, dict)  # filepath, result

    show_dialog_signal = Signal(str, dict)  # filepath, result (for thread safety)

    def __init__(self, root_folder: str, parent=None):
        super().__init__(parent)
        self.root_folder = root_folder
        self._pending: list[tuple[str, dict]] = []

        self._tray = QSystemTrayIcon()
        self._tray.setToolTip(APP_NAME)

        # メニュー
        menu = QMenu()
        self._status_action = QAction("監視中")
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        show_action = QAction("ウィンドウを表示")
        show_action.triggered.connect(self._on_show_window)
        menu.addAction(show_action)

        quit_action = QAction("終了")
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._on_show_window_callback: Callable | None = None
        self._on_quit_callback: Callable | None = None

        # スレッドセーフなダイアログ表示
        self.show_dialog_signal.connect(self._show_dialog_in_main_thread)

    def set_callbacks(self, on_show_window: Callable = None,
                      on_quit: Callable = None):
        self._on_show_window_callback = on_show_window
        self._on_quit_callback = on_quit

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def set_status(self, text: str):
        self._status_action.setText(text)

    def notify_sorted(self, filename: str, project: str, method: str):
        """ファイル仕分け完了の通知。"""
        self._tray.showMessage(
            "ファイル仕分け完了",
            f"{filename} → {project} [{method}]",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def notify_low_confidence(self, filepath: str, result: dict):
        """低信頼度の通知 → プロジェクト選択ダイアログを表示。"""
        filename = Path(filepath).name
        confidence = result.get("confidence", 0.0)

        self._tray.showMessage(
            "分類先を確認してください",
            f"{filename} (信頼度: {confidence:.0%})",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

        # メインスレッドでダイアログを表示
        self.show_dialog_signal.emit(filepath, result)

    def _show_dialog_in_main_thread(self, filepath: str, result: dict):
        """メインスレッドでプロジェクト選択ダイアログを表示する。"""
        filename = Path(filepath).name
        dialog = ProjectSelectDialog(filename, result, self.root_folder)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project_selected.emit(
                filepath, result,
                dialog.selected_project,
                dialog.selected_subfolder,
            )
        else:
            self.skipped.emit(filepath, result)

    def _on_show_window(self):
        if self._on_show_window_callback:
            self._on_show_window_callback()

    def _on_quit(self):
        if self._on_quit_callback:
            self._on_quit_callback()
        else:
            QApplication.quit()
