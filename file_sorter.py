"""
ファイル自動仕分けツール
========================
Ollama（gemma3:4b）を使い、ドラッグ＆ドロップしたファイルを
プロジェクトフォルダへ自動分類するデスクトップアプリ。

依存ライブラリ:
    pip install PySide6

動作環境:
    - Windows 10/11 (64bit)
    - Python 3.13+
    - Ollama（http://localhost:11434 でgemma3:4bが起動済みであること）
"""

import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QSettings,
    Qt,
    QThread,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
APP_NAME = "ファイル自動仕分けツール"
APP_VERSION = "2.0.0"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 60
UNKNOWN_DIR = "_未分類"
SUBFOLDERS = ("検討資料", "受領資料", "その他")

# カラーテーマ
C_BG = "#0c0c10"
C_PANEL = "#16161e"
C_PANEL_LIGHT = "#1e1e2a"
C_BORDER = "#2a2a3a"
C_ACCENT_BLUE = "#6196ff"
C_ACCENT_PURPLE = "#a78bfa"
C_ACCENT_CYAN = "#67e8f9"
C_SUCCESS = "#34d399"
C_WARN = "#fbbf24"
C_ERROR = "#f87171"
C_TEXT = "#e8e8f0"
C_SUBTEXT = "#8888aa"
C_DIM = "#555570"


# ---------------------------------------------------------------------------
# プロジェクトフォルダ検出
# ---------------------------------------------------------------------------

def scan_projects(root: str) -> list[str]:
    """ルートフォルダ直下のディレクトリ名を取得。先頭が _ のものは除外。"""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    return sorted(
        d.name
        for d in root_path.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
    )


# ---------------------------------------------------------------------------
# Ollama 呼び出し（ファイル名＋コメントのみ。内容は読まない）
# ---------------------------------------------------------------------------

def build_prompt(filename: str, projects: list[str], user_comment: str = "") -> str:
    project_list = "\n".join(f"- {p}" for p in projects) if projects else "（なし）"

    comment_section = ""
    if user_comment.strip():
        comment_section = f"""
## ユーザーからの補足コメント（分類の最重要ヒント）
{user_comment.strip()}
"""

    return f"""あなたはファイル整理の専門家です。以下の情報をもとに、ファイルの分類先を答えてください。

## ファイル名
{filename}
{comment_section}
## 既存プロジェクトフォルダ一覧
{project_list}

## 分類ルール
- projectには既存プロジェクトフォルダ一覧のいずれか、または "unknown" を指定
- サブフォルダは必ず「検討資料」「受領資料」「その他」のいずれか1つ
  - 検討資料：自分たちが作成・編集する設計図・計算書・報告書・提案書など
  - 受領資料：発注者・他社・官庁から受け取った資料・データ・提供ファイルなど
  - その他：議事録・写真・メモ・分類が難しいもの
- ユーザーからの補足コメントがある場合、それを最優先の判断材料として使うこと

## 回答形式（JSONのみ・余計な文字禁止）
{{"project": "プロジェクト名またはunknown", "subfolder": "検討資料 or 受領資料 or その他"}}"""


def call_ollama(prompt: str) -> dict | None:
    """Ollama API を呼び出し、JSON をパースして返す。"""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    raw = body.get("response", "")
    json_match = re.search(r"\{[^}]*\"project\"[^}]*\}", raw, re.DOTALL)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return None


def check_ollama_connection() -> bool:
    """Ollama サーバーへの接続を確認する。"""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ファイル移動（フォルダの日付はファイル更新日から取得）
# ---------------------------------------------------------------------------

def get_file_mod_date(filepath: str) -> str:
    """ファイルの更新日を YYMMDD 形式で返す。"""
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%y%m%d")


def move_file(filepath: str, dest_dir: str) -> str:
    """ファイルを日付プレフィックス付きの個別フォルダへ移動する。
    フォルダ名: YYMMDD_ファイル名(拡張子なし)  ※日付はファイル更新日
    同名フォルダが既に存在する場合は連番を付与。
    移動後のパスを返す。"""
    src = Path(filepath)
    date_prefix = get_file_mod_date(filepath)
    folder_name = f"{date_prefix}_{src.stem}"

    file_folder = Path(dest_dir) / folder_name

    if file_folder.exists():
        counter = 2
        while True:
            candidate = Path(dest_dir) / f"{folder_name}_{counter}"
            if not candidate.exists():
                file_folder = candidate
                break
            counter += 1

    file_folder.mkdir(parents=True, exist_ok=True)

    target = file_folder / src.name
    shutil.move(str(src), str(target))
    return str(target)


# ---------------------------------------------------------------------------
# ワーカースレッド
# ---------------------------------------------------------------------------

class SortWorker(QObject):
    """バックグラウンドでファイル仕分けを実行するワーカー。"""

    log_signal = Signal(str, str)  # (message, color)
    status_signal = Signal(str)
    finished = Signal()
    undo_record = Signal(str, str)  # (moved_to, original_path)

    def __init__(self, files: list[str], root_folder: str, user_comment: str = ""):
        super().__init__()
        self.files = files
        self.root_folder = root_folder
        self.user_comment = user_comment

    def run(self):
        projects = scan_projects(self.root_folder)
        total = len(self.files)

        for i, filepath in enumerate(self.files, 1):
            filename = Path(filepath).name
            self.status_signal.emit(f"処理中… ({i}/{total}) {filename}")
            self.log_signal.emit(f"🔍 分類中: {filename}", C_SUBTEXT)

            prompt = build_prompt(filename, projects, self.user_comment)
            result = call_ollama(prompt)

            if result is None:
                dest_dir = str(Path(self.root_folder) / UNKNOWN_DIR)
                moved = move_file(filepath, dest_dir)
                moved_folder = Path(moved).parent.name
                self.undo_record.emit(moved, filepath)
                self.log_signal.emit(
                    f"⚠️ AI応答を解析できません → {UNKNOWN_DIR}/{moved_folder}/",
                    C_WARN,
                )
                continue

            project = result.get("project", "unknown")
            subfolder = result.get("subfolder", "その他")

            if subfolder not in SUBFOLDERS:
                subfolder = "その他"

            if project == "unknown" or project not in projects:
                dest_dir = str(Path(self.root_folder) / UNKNOWN_DIR)
                moved = move_file(filepath, dest_dir)
                moved_folder = Path(moved).parent.name
                self.undo_record.emit(moved, filepath)
                self.log_signal.emit(
                    f"⚠️ プロジェクト不明 → {UNKNOWN_DIR}/{moved_folder}/",
                    C_WARN,
                )
            else:
                dest_dir = str(Path(self.root_folder) / project / subfolder)
                moved = move_file(filepath, dest_dir)
                moved_folder = Path(moved).parent.name
                self.undo_record.emit(moved, filepath)
                self.log_signal.emit(
                    f"✅ {filename} → {project}/{subfolder}/{moved_folder}/",
                    C_SUCCESS,
                )

        self.status_signal.emit("✅ 完了")
        self.finished.emit()


# ---------------------------------------------------------------------------
# UI コンポーネント
# ---------------------------------------------------------------------------

def _card_frame(parent=None) -> QFrame:
    """角丸パネルカードを生成する。"""
    frame = QFrame(parent)
    frame.setStyleSheet(
        f"QFrame {{ background: {C_PANEL}; border: 1px solid {C_BORDER}; "
        f"border-radius: 14px; }}"
    )
    return frame


class DropZone(QFrame):
    """ドラッグ＆ドロップを受け付けるエリア。"""

    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        self.setMaximumHeight(160)
        self._update_style(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        icon_label = QLabel("📂")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 32px; border: none; background: transparent;")
        layout.addWidget(icon_label)

        text_label = QLabel("ここにファイルをドロップ")
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet(
            f"color: {C_SUBTEXT}; font-size: 13px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(text_label)

        hint_label = QLabel("複数ファイル対応")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setStyleSheet(
            f"color: {C_DIM}; font-size: 11px; border: none; background: transparent;"
        )
        layout.addWidget(hint_label)

    def _update_style(self, hover: bool):
        if hover:
            self.setStyleSheet(
                f"DropZone {{ background: qlineargradient("
                f"x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 #1a1a30, stop:1 #1a2a2a); "
                f"border: 2px dashed {C_ACCENT_BLUE}; border-radius: 14px; }}"
            )
        else:
            self.setStyleSheet(
                f"DropZone {{ background: {C_PANEL}; "
                f"border: 2px dashed {C_BORDER}; border-radius: 14px; }}"
            )

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_style(True)

    def dragLeaveEvent(self, event):
        self._update_style(False)

    def dropEvent(self, event: QDropEvent):
        self._update_style(False)
        urls: list[QUrl] = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).is_file()]
        if files:
            self.files_dropped.emit(files)


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(720, 780)
        self.setMinimumSize(560, 620)

        self._settings = QSettings("FileSorter", "FileSorter")
        self._worker_thread: QThread | None = None
        self._undo_stack: list[tuple[str, str]] = []
        self._pending_files: list[str] = []

        self._init_ui()
        self._apply_global_style()
        self._load_settings()
        self._refresh_projects()
        self._check_ollama()
        self._update_comment_indicator()

    # ---- UI 構築 ----

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        # ── ヘッダー ──
        header = QLabel(APP_NAME)
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            f"color: {C_TEXT}; font-size: 24px; font-weight: 800; "
            f"letter-spacing: 2px; padding-bottom: 2px;"
        )
        root.addWidget(header)

        sub = QLabel(f"Powered by Ollama + {OLLAMA_MODEL}  |  完全ローカル処理")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {C_DIM}; font-size: 11px; padding-bottom: 6px;")
        root.addWidget(sub)

        # Ollama 接続バッジ
        self._ollama_badge = QLabel()
        self._ollama_badge.setAlignment(Qt.AlignCenter)
        self._ollama_badge.setFixedHeight(22)
        root.addWidget(self._ollama_badge)

        root.addSpacing(14)

        # ── フォルダ選択カード ──
        folder_card = _card_frame()
        fc_layout = QHBoxLayout(folder_card)
        fc_layout.setContentsMargins(14, 10, 14, 10)

        folder_icon = QLabel("📁")
        folder_icon.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        fc_layout.addWidget(folder_icon)

        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setStyleSheet(
            f"background: transparent; color: {C_TEXT}; border: none; "
            f"font-size: 12px; padding: 2px 6px;"
        )
        fc_layout.addWidget(self._folder_edit, 1)

        change_btn = QPushButton("変更")
        change_btn.setFixedSize(56, 28)
        change_btn.setCursor(Qt.PointingHandCursor)
        change_btn.setStyleSheet(
            f"QPushButton {{ background: {C_ACCENT_PURPLE}18; color: {C_ACCENT_PURPLE}; "
            f"border: 1px solid {C_ACCENT_PURPLE}40; border-radius: 6px; "
            f"font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {C_ACCENT_PURPLE}35; }}"
        )
        change_btn.clicked.connect(self._select_folder)
        fc_layout.addWidget(change_btn)

        root.addWidget(folder_card)
        root.addSpacing(4)

        # プロジェクト一覧
        self._projects_label = QLabel()
        self._projects_label.setWordWrap(True)
        self._projects_label.setStyleSheet(
            f"color: {C_DIM}; font-size: 11px; padding: 2px 8px;"
        )
        root.addWidget(self._projects_label)

        root.addSpacing(10)

        # ── ドロップゾーン ──
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        root.addWidget(self._drop_zone)

        root.addSpacing(10)

        # ── コメント入力セクション ──
        comment_card = _card_frame()
        cc_layout = QVBoxLayout(comment_card)
        cc_layout.setContentsMargins(14, 10, 14, 10)
        cc_layout.setSpacing(8)

        comment_header = QHBoxLayout()
        comment_title = QLabel("💬 補足コメント")
        comment_title.setStyleSheet(
            f"color: {C_SUBTEXT}; font-size: 12px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        comment_header.addWidget(comment_title)

        self._comment_badge = QLabel()
        self._comment_badge.setStyleSheet(
            f"border: none; background: transparent; font-size: 11px;"
        )
        comment_header.addWidget(self._comment_badge)

        comment_header.addStretch()
        cc_layout.addLayout(comment_header)

        # コメント入力行
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._comment_edit = QLineEdit()
        self._comment_edit.setPlaceholderText(
            "例: A社から受領した構造計算書、○○橋の現場写真 …"
        )
        self._comment_edit.setStyleSheet(
            f"background: {C_PANEL_LIGHT}; color: {C_TEXT}; "
            f"border: 1px solid {C_BORDER}; border-radius: 8px; "
            f"padding: 8px 12px; font-size: 13px;"
        )
        self._comment_edit.textChanged.connect(self._update_comment_indicator)
        input_row.addWidget(self._comment_edit, 1)

        self._comment_clear_btn = QPushButton("✕")
        self._comment_clear_btn.setFixedSize(32, 32)
        self._comment_clear_btn.setCursor(Qt.PointingHandCursor)
        self._comment_clear_btn.setToolTip("コメントをクリア")
        self._comment_clear_btn.setStyleSheet(
            f"QPushButton {{ background: {C_ERROR}15; color: {C_ERROR}; "
            f"border: 1px solid {C_ERROR}30; border-radius: 8px; "
            f"font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {C_ERROR}30; }}"
        )
        self._comment_clear_btn.clicked.connect(self._clear_comment)
        input_row.addWidget(self._comment_clear_btn)

        cc_layout.addLayout(input_row)
        root.addWidget(comment_card)

        root.addSpacing(10)

        # ── ステータス ──
        self._status_label = QLabel("待機中")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setFixedHeight(24)
        self._status_label.setStyleSheet(
            f"color: {C_ACCENT_BLUE}; font-size: 13px; font-weight: bold;"
        )
        root.addWidget(self._status_label)

        root.addSpacing(6)

        # ── ログエリア ──
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(
            f"QTextEdit {{ background: {C_PANEL}; color: {C_TEXT}; "
            f"border: 1px solid {C_BORDER}; border-radius: 12px; "
            f"padding: 10px 12px; font-size: 12px; "
            f"selection-background-color: {C_ACCENT_BLUE}40; }}"
        )
        root.addWidget(self._log_area, 1)

        root.addSpacing(10)

        # ── ボタンバー ──
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        undo_btn = self._make_button("↩  元に戻す", C_WARN)
        undo_btn.clicked.connect(self._undo_last)
        btn_bar.addWidget(undo_btn)

        btn_bar.addStretch()

        clear_btn = self._make_button("ログをクリア", C_SUBTEXT)
        clear_btn.clicked.connect(self._log_area.clear)
        btn_bar.addWidget(clear_btn)

        root.addLayout(btn_bar)

    # ---- スタイル ----

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C_BG}; }}
            QWidget {{
                background: {C_BG}; color: {C_TEXT};
                font-family: 'Yu Gothic UI', 'Meiryo', 'Segoe UI', sans-serif;
            }}
            QScrollBar:vertical {{
                background: {C_PANEL}; width: 6px;
                border-radius: 3px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BORDER}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C_SUBTEXT}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
            QToolTip {{
                background: {C_PANEL_LIGHT}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 6px;
                padding: 4px 8px; font-size: 11px;
            }}
        """)

    @staticmethod
    def _make_button(text: str, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(34)
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}12; color: {color}; "
            f"border: 1px solid {color}35; border-radius: 8px; "
            f"padding: 0 18px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {color}28; border-color: {color}60; }}"
            f"QPushButton:pressed {{ background: {color}40; }}"
        )
        return btn

    # ---- コメントインジケーター ----

    def _update_comment_indicator(self):
        text = self._comment_edit.text().strip()
        if text:
            self._comment_badge.setText(f"✔ 入力済み（AIに送信されます）")
            self._comment_badge.setStyleSheet(
                f"color: {C_SUCCESS}; font-size: 11px; font-weight: bold; "
                f"border: none; background: transparent;"
            )
            self._comment_clear_btn.setVisible(True)
        else:
            self._comment_badge.setText("任意 — 入力するとAIの分類精度が上がります")
            self._comment_badge.setStyleSheet(
                f"color: {C_DIM}; font-size: 11px; "
                f"border: none; background: transparent;"
            )
            self._comment_clear_btn.setVisible(False)

    def _clear_comment(self):
        self._comment_edit.clear()

    # ---- 設定 ----

    def _load_settings(self):
        default = str(Path.home() / "Desktop")
        folder = self._settings.value("root_folder", default)
        if not Path(folder).is_dir():
            folder = default
        self._folder_edit.setText(folder)

    def _save_settings(self):
        self._settings.setValue("root_folder", self._folder_edit.text())

    @property
    def root_folder(self) -> str:
        return self._folder_edit.text()

    # ---- Ollama 接続確認 ----

    def _check_ollama(self):
        connected = check_ollama_connection()
        if connected:
            self._ollama_badge.setText("● 接続済み")
            self._ollama_badge.setStyleSheet(
                f"color: {C_SUCCESS}; font-size: 11px; font-weight: bold;"
            )
        else:
            self._ollama_badge.setText("● 未接続 — Ollama を起動してください")
            self._ollama_badge.setStyleSheet(
                f"color: {C_ERROR}; font-size: 11px; font-weight: bold;"
            )

    # ---- フォルダ選択 ----

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "整理先ルートフォルダを選択", self.root_folder
        )
        if folder:
            self._folder_edit.setText(folder)
            self._save_settings()
            self._refresh_projects()

    def _refresh_projects(self):
        projects = scan_projects(self.root_folder)
        if projects:
            self._projects_label.setText(
                f"検出プロジェクト ({len(projects)}):  " + "、".join(projects)
            )
        else:
            self._projects_label.setText("プロジェクトフォルダが見つかりません")

    # ---- ファイルドロップ処理 ----

    def _on_files_dropped(self, files: list[str]):
        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.warning(self, "処理中", "処理中です。完了をお待ちください。")
            return

        if not check_ollama_connection():
            self._check_ollama()
            self._append_log("❌ Ollama に接続できません。サーバーを起動してください。", C_ERROR)
            return

        self._refresh_projects()
        self._status_label.setText(f"処理中… (0/{len(files)})")

        user_comment = self._comment_edit.text().strip()
        if user_comment:
            self._append_log(f"💬 コメント反映: {user_comment}", C_ACCENT_PURPLE)

        # ワーカー起動
        self._worker_thread = QThread()
        self._worker = SortWorker(files, self.root_folder, user_comment)
        self._worker.moveToThread(self._worker_thread)

        self._worker.log_signal.connect(self._append_log)
        self._worker.status_signal.connect(self._status_label.setText)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.undo_record.connect(self._record_undo)

        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _on_worker_finished(self):
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
        self._comment_edit.clear()
        self._check_ollama()

    # ---- 元に戻す ----

    def _record_undo(self, moved_to: str, original_path: str):
        self._undo_stack.append((moved_to, original_path))

    def _undo_last(self):
        if not self._undo_stack:
            self._append_log("↩ 戻せる操作がありません。", C_SUBTEXT)
            return

        moved_to, original_path = self._undo_stack.pop()
        moved_path = Path(moved_to)

        if not moved_path.exists():
            self._append_log(f"❌ ファイルが見つかりません: {moved_to}", C_ERROR)
            return

        try:
            original_dir = str(Path(original_path).parent)
            Path(original_dir).mkdir(parents=True, exist_ok=True)
            shutil.move(str(moved_path), original_path)
            parent_folder = moved_path.parent
            if parent_folder.is_dir() and not any(parent_folder.iterdir()):
                parent_folder.rmdir()
            self._append_log(
                f"↩ 元に戻しました: {moved_path.name} → {original_path}",
                C_ACCENT_PURPLE,
            )
        except Exception as e:
            self._append_log(f"❌ 元に戻す操作に失敗: {e}", C_ERROR)

    # ---- ログ ----

    def _append_log(self, message: str, color: str = C_TEXT):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_area.append(
            f'<span style="color:{C_DIM}">{timestamp}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{color}">{message}</span>'
        )
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
