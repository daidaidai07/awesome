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
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
APP_VERSION = "3.1.0"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 60
UNKNOWN_DIR = "_未分類"

# 整理先フォルダ直下に保存されるファイル
HISTORY_FILE = "_分類履歴.json"
RULES_FILE = "_分類ルール.json"


# ---------------------------------------------------------------------------
# カラーテーマ（ダーク / ライト）
# ---------------------------------------------------------------------------

class Theme:
    """ダーク・ライト両対応のカラーテーマ。"""

    DARK = {
        "bg": "#0c0c10", "panel": "#16161e", "panel_light": "#1e1e2a",
        "border": "#2a2a3a", "accent_blue": "#6196ff", "accent_purple": "#a78bfa",
        "success": "#34d399", "warn": "#fbbf24", "error": "#f87171",
        "text": "#e8e8f0", "subtext": "#8888aa", "dim": "#555570",
        "drop_hover": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1a1a30,stop:1 #1a2a2a)",
        "input_bg": "#1e1e2a",
    }
    LIGHT = {
        "bg": "#f5f5f8", "panel": "#ffffff", "panel_light": "#f0f0f5",
        "border": "#d8d8e0", "accent_blue": "#3b6fdf", "accent_purple": "#7c5cbf",
        "success": "#16a368", "warn": "#d49a08", "error": "#dc3545",
        "text": "#1a1a2e", "subtext": "#6e6e88", "dim": "#9999aa",
        "drop_hover": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #e8e8ff,stop:1 #e0f0f0)",
        "input_bg": "#f0f0f5",
    }

    def __init__(self, mode: str = "dark"):
        self._mode = mode
        self._colors = self.DARK if mode == "dark" else self.LIGHT

    @property
    def mode(self) -> str:
        return self._mode

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._colors[name]
        except KeyError:
            raise AttributeError(f"No color '{name}' in theme")

    def toggle(self) -> "Theme":
        return Theme("light" if self._mode == "dark" else "dark")


# ---------------------------------------------------------------------------
# 分類履歴（学習機能）
# ---------------------------------------------------------------------------

def _history_path(root: str) -> Path:
    return Path(root) / HISTORY_FILE


def load_history(root: str) -> list[dict]:
    """分類履歴を読み込む。"""
    hp = _history_path(root)
    if not hp.exists():
        return []
    try:
        with open(hp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history_entry(root: str, comment: str, project: str, subfolder: str):
    """分類結果を履歴に追記する。直近100件を保持。"""
    if not comment.strip():
        return
    history = load_history(root)
    history.append({
        "comment": comment.strip(),
        "project": project,
        "subfolder": subfolder,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    # 直近100件のみ保持
    history = history[-100:]
    hp = _history_path(root)
    try:
        with open(hp, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def build_history_context(root: str) -> str:
    """過去の分類履歴をプロンプト用テキストに変換する。直近20件。"""
    history = load_history(root)
    if not history:
        return ""
    recent = history[-20:]
    lines = []
    for h in recent:
        lines.append(
            f"  コメント「{h['comment']}」→ {h['project']}/{h['subfolder']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 分類ルール（キーワード → フォルダ マッピング）
# ---------------------------------------------------------------------------

def _rules_path(root: str) -> Path:
    return Path(root) / RULES_FILE


def load_rules(root: str) -> list[dict]:
    """分類ルールを読み込む。
    各ルール: {"keyword": "...", "project": "...", "subfolder": "..."}
    """
    rp = _rules_path(root)
    if not rp.exists():
        return []
    try:
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_rules(root: str, rules: list[dict]):
    """分類ルールを保存する。"""
    rp = _rules_path(root)
    try:
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def match_rule(comment: str, rules: list[dict]) -> dict | None:
    """コメントに一致するルールを返す。キーワードが含まれていればマッチ。"""
    if not comment.strip():
        return None
    comment_lower = comment.strip().lower()
    for rule in rules:
        keyword = rule.get("keyword", "").strip().lower()
        if keyword and keyword in comment_lower:
            return rule
    return None


def match_comment_to_project(
    comment: str, projects: list[str], subfolder_map: dict[str, list[str]],
) -> dict | None:
    """コメントにプロジェクト名やサブフォルダ名が含まれていれば直接マッチする。
    完全一致を優先し、部分一致はフォルダ名が2文字以上の場合のみ。
    """
    if not comment.strip():
        return None
    comment_text = comment.strip()

    # 完全一致（コメント全体がフォルダ名そのもの）
    for p in projects:
        if comment_text == p:
            subs = subfolder_map.get(p, [])
            return {"project": p, "subfolder": subs[0] if subs else ""}

    # プロジェクト名の部分一致（2文字以上のフォルダ名）
    # 長い名前を先にチェック（「ツール管理」が「ツール」より優先）
    sorted_projects = sorted(projects, key=len, reverse=True)
    for p in sorted_projects:
        if len(p) >= 2 and p in comment_text:
            # サブフォルダもコメントから探す
            subs = subfolder_map.get(p, [])
            matched_sub = ""
            for s in sorted(subs, key=len, reverse=True):
                if len(s) >= 2 and s in comment_text:
                    matched_sub = s
                    break
            if not matched_sub and subs:
                matched_sub = subs[0]
            return {"project": p, "subfolder": matched_sub}

    return None


# ---------------------------------------------------------------------------
# フォルダ構造スキャン
# ---------------------------------------------------------------------------

def scan_projects(root: str) -> list[str]:
    """ルートフォルダ直下のディレクトリ名を取得。先頭が _ や . のものは除外。"""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    return sorted(
        d.name
        for d in root_path.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
    )


def scan_subfolders(root: str, project: str) -> list[str]:
    """プロジェクトフォルダ内のサブフォルダ一覧を取得。"""
    project_path = Path(root) / project
    if not project_path.is_dir():
        return []
    return sorted(
        d.name
        for d in project_path.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
    )


def scan_all_subfolders(root: str, projects: list[str]) -> dict[str, list[str]]:
    """全プロジェクトのサブフォルダ構造を取得。"""
    result = {}
    for p in projects:
        subs = scan_subfolders(root, p)
        if subs:
            result[p] = subs
    return result


# ---------------------------------------------------------------------------
# Ollama 呼び出し
# ---------------------------------------------------------------------------

def build_prompt(
    filename: str,
    projects: list[str],
    subfolder_map: dict[str, list[str]],
    user_comment: str = "",
    history_context: str = "",
) -> str:
    # フォルダ構造を整形
    structure_lines = []
    for p in projects:
        subs = subfolder_map.get(p, [])
        if subs:
            structure_lines.append(f"- {p}/")
            for s in subs:
                structure_lines.append(f"    - {s}/")
        else:
            structure_lines.append(f"- {p}/  （サブフォルダなし）")
    folder_structure = "\n".join(structure_lines) if structure_lines else "（なし）"

    # コメントセクション
    comment_section = ""
    if user_comment.strip():
        comment_section = f"""
## ユーザーからの補足コメント（分類の最重要ヒント）
{user_comment.strip()}
"""

    # 履歴セクション
    history_section = ""
    if history_context.strip():
        history_section = f"""
## 過去の分類パターン（参考にして一貫した分類をすること）
{history_context}
"""

    # サブフォルダ名の全リストをまとめる
    all_subs = set()
    for subs in subfolder_map.values():
        all_subs.update(subs)
    subfolder_list = "、".join(sorted(all_subs)) if all_subs else "（サブフォルダなし）"

    return f"""あなたはファイル整理の専門家です。以下の情報をもとに、ファイルの分類先を答えてください。

## ファイル名
{filename}
{comment_section}{history_section}
## 既存フォルダ構造
{folder_structure}

## 分類ルール（優先度の高い順に適用すること）
1. コメントに既存フォルダ名と一致・部分一致する語句があれば、そのフォルダを最優先で選ぶ
   - 例: コメントが「ツール」でフォルダに「ツール」があれば → project は「ツール」
   - 例: コメントが「○○の資料」でフォルダに「○○」があれば → project は「○○」
2. コメントの内容（説明文）からファイルの用途を推測し、最も適切なフォルダを選ぶ
3. 過去の分類パターンがある場合、同様のコメントには同じ分類先を使う
4. projectには上記の既存プロジェクトフォルダのいずれか、または "unknown" を指定
5. subfolderには、そのプロジェクト内に実際に存在するサブフォルダ名を正確に指定すること
   - 存在するサブフォルダ: {subfolder_list}

## 回答形式（JSONのみ・余計な文字禁止）
{{"project": "プロジェクト名またはunknown", "subfolder": "サブフォルダ名"}}"""


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
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ファイル移動
# ---------------------------------------------------------------------------

def get_file_mod_date(filepath: str) -> str:
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%y%m%d")


def move_file(filepath: str, dest_dir: str) -> str:
    """ファイルを YYMMDD_ファイル名/ フォルダへ移動。日付はファイル更新日。"""
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
    log_signal = Signal(str, str)  # (message, color)
    status_signal = Signal(str)
    finished = Signal()
    undo_record = Signal(str, str)  # (moved_to, original_path)
    history_record = Signal(str, str, str)  # (comment, project, subfolder)

    def __init__(
        self, files: list[str], root_folder: str, user_comment: str = "",
        theme: Theme | None = None,
    ):
        super().__init__()
        self.files = files
        self.root_folder = root_folder
        self.user_comment = user_comment
        self.t = theme or Theme()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _move_and_log(self, filepath: str, project: str, subfolder: str,
                      projects: list[str], subfolder_map: dict, method: str):
        """分類結果をもとにファイルを移動しログ出力する共通処理。"""
        filename = Path(filepath).name

        if project == "unknown" or project not in projects:
            dest_dir = str(Path(self.root_folder) / UNKNOWN_DIR)
            moved = move_file(filepath, dest_dir)
            moved_folder = Path(moved).parent.name
            self.undo_record.emit(moved, filepath)
            self.log_signal.emit(
                f"⚠️ プロジェクト不明 → {UNKNOWN_DIR}/{moved_folder}/",
                self.t.warn,
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

        moved = move_file(filepath, dest_dir)
        moved_folder = Path(moved).parent.name
        self.undo_record.emit(moved, filepath)

        display_path = f"{project}/{subfolder}/{moved_folder}/" if subfolder else f"{project}/{moved_folder}/"
        self.log_signal.emit(
            f"✅ {filename} → {display_path}  [{method}]", self.t.success,
        )
        self.history_record.emit(self.user_comment, project, subfolder)

    def run(self):
        projects = scan_projects(self.root_folder)
        subfolder_map = scan_all_subfolders(self.root_folder, projects)
        history_context = build_history_context(self.root_folder)
        rules = load_rules(self.root_folder)
        total = len(self.files)

        # ルールマッチ判定（コメント全体で1回だけ判定）
        matched_rule = match_rule(self.user_comment, rules) if self.user_comment else None

        # コメント → プロジェクト名の直接マッチ判定
        comment_match = (
            match_comment_to_project(self.user_comment, projects, subfolder_map)
            if self.user_comment and not matched_rule else None
        )

        for i, filepath in enumerate(self.files, 1):
            if self._cancelled:
                self.status_signal.emit("⏹ 中断しました")
                self.finished.emit()
                return

            filename = Path(filepath).name
            self.status_signal.emit(f"処理中… ({i}/{total}) {filename}")

            # ルールにマッチ → AIスキップで即振り分け
            if matched_rule:
                self.log_signal.emit(
                    f"⚡ ルール適用: {filename}（キーワード: {matched_rule['keyword']}）",
                    self.t.accent_blue,
                )
                self._move_and_log(
                    filepath,
                    matched_rule.get("project", "unknown"),
                    matched_rule.get("subfolder", ""),
                    projects, subfolder_map, "ルール",
                )
                continue

            # コメントにフォルダ名が含まれている → 直接振り分け
            if comment_match:
                self.log_signal.emit(
                    f"📁 コメントからフォルダ名を検出: {filename} → {comment_match['project']}",
                    self.t.accent_blue,
                )
                self._move_and_log(
                    filepath,
                    comment_match["project"],
                    comment_match.get("subfolder", ""),
                    projects, subfolder_map, "コメント直接",
                )
                continue

            # ルール不一致・フォルダ名不一致 → AI分類
            if self._cancelled:
                self.status_signal.emit("⏹ 中断しました")
                self.finished.emit()
                return

            self.log_signal.emit(f"🔍 AI分類中: {filename}", self.t.subtext)

            prompt = build_prompt(
                filename, projects, subfolder_map,
                self.user_comment, history_context,
            )
            result = call_ollama(prompt)

            if result is None:
                dest_dir = str(Path(self.root_folder) / UNKNOWN_DIR)
                moved = move_file(filepath, dest_dir)
                moved_folder = Path(moved).parent.name
                self.undo_record.emit(moved, filepath)
                self.log_signal.emit(
                    f"⚠️ AI応答を解析できません → {UNKNOWN_DIR}/{moved_folder}/",
                    self.t.warn,
                )
                continue

            self._move_and_log(
                filepath,
                result.get("project", "unknown"),
                result.get("subfolder", ""),
                projects, subfolder_map, "AI",
            )

        self.status_signal.emit("✅ 完了")
        self.finished.emit()


# ---------------------------------------------------------------------------
# UI コンポーネント
# ---------------------------------------------------------------------------

class RulesDialog(QDialog):
    """分類ルール管理ダイアログ。
    キーワード → プロジェクト/サブフォルダ のマッピングを登録・編集・削除。
    """

    def __init__(self, root_folder: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.root_folder = root_folder
        self.t = theme
        self.setWindowTitle("分類ルール管理")
        self.resize(560, 440)
        self._rules = load_rules(root_folder)
        self._init_ui()
        self._apply_style()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 説明
        desc = QLabel(
            "コメントに含まれるキーワードで、AIを使わず即座に振り分けます。\n"
            '例: キーワード「ワークス」→ プロジェクトA / 協力者受領資料'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {self.t.subtext}; font-size: 12px;")
        layout.addWidget(desc)

        # ルール一覧
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {self.t.panel}; color: {self.t.text}; "
            f"border: 1px solid {self.t.border}; border-radius: 8px; "
            f"padding: 4px; font-size: 12px; }}"
            f"QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}"
            f"QListWidget::item:selected {{ background: {self.t.accent_blue}30; }}"
        )
        layout.addWidget(self._list, 1)

        # 追加フォーム
        form_frame = QFrame()
        form_frame.setStyleSheet(
            f"QFrame {{ background: {self.t.panel}; border: 1px solid {self.t.border}; "
            f"border-radius: 10px; }}"
        )
        form = QFormLayout(form_frame)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(8)

        input_style = (
            f"background: {self.t.input_bg}; color: {self.t.text}; "
            f"border: 1px solid {self.t.border}; border-radius: 6px; "
            f"padding: 5px 8px; font-size: 12px;"
        )
        label_style = f"color: {self.t.subtext}; font-size: 12px; font-weight: bold;"

        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("例: ワークス")
        self._keyword_edit.setStyleSheet(input_style)
        kw_label = QLabel("キーワード")
        kw_label.setStyleSheet(label_style)
        form.addRow(kw_label, self._keyword_edit)

        # プロジェクト選択
        self._project_combo = QComboBox()
        self._project_combo.setStyleSheet(
            f"QComboBox {{ {input_style} }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {self.t.panel}; "
            f"color: {self.t.text}; selection-background-color: {self.t.accent_blue}40; }}"
        )
        projects = scan_projects(self.root_folder)
        self._project_combo.addItems(projects)
        self._project_combo.currentTextChanged.connect(self._on_project_changed)
        pj_label = QLabel("プロジェクト")
        pj_label.setStyleSheet(label_style)
        form.addRow(pj_label, self._project_combo)

        # サブフォルダ選択
        self._subfolder_combo = QComboBox()
        self._subfolder_combo.setStyleSheet(
            f"QComboBox {{ {input_style} }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {self.t.panel}; "
            f"color: {self.t.text}; selection-background-color: {self.t.accent_blue}40; }}"
        )
        sf_label = QLabel("サブフォルダ")
        sf_label.setStyleSheet(label_style)
        form.addRow(sf_label, self._subfolder_combo)

        # 初期表示
        if projects:
            self._on_project_changed(projects[0])

        layout.addWidget(form_frame)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        add_btn = QPushButton("＋ ルール追加")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(34)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {self.t.success}18; color: {self.t.success}; "
            f"border: 1px solid {self.t.success}40; border-radius: 8px; "
            f"padding: 0 16px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {self.t.success}35; }}"
        )
        add_btn.clicked.connect(self._add_rule)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("🗑 選択を削除")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setFixedHeight(34)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {self.t.error}18; color: {self.t.error}; "
            f"border: 1px solid {self.t.error}40; border-radius: 8px; "
            f"padding: 0 16px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {self.t.error}35; }}"
        )
        del_btn.clicked.connect(self._delete_rule)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()

        close_btn = QPushButton("閉じる")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {self.t.subtext}18; color: {self.t.subtext}; "
            f"border: 1px solid {self.t.subtext}40; border-radius: 8px; "
            f"padding: 0 16px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {self.t.subtext}35; }}"
        )
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _apply_style(self):
        self.setStyleSheet(
            f"QDialog {{ background: {self.t.bg}; color: {self.t.text}; }}"
        )

    def _on_project_changed(self, project: str):
        self._subfolder_combo.clear()
        subs = scan_subfolders(self.root_folder, project)
        self._subfolder_combo.addItems(subs)

    def _refresh_list(self):
        self._list.clear()
        for rule in self._rules:
            kw = rule.get("keyword", "")
            pj = rule.get("project", "")
            sf = rule.get("subfolder", "")
            display = f'「{kw}」 → {pj} / {sf}' if sf else f'「{kw}」 → {pj}'
            self._list.addItem(display)

    def _add_rule(self):
        keyword = self._keyword_edit.text().strip()
        project = self._project_combo.currentText()
        subfolder = self._subfolder_combo.currentText()

        if not keyword:
            QMessageBox.warning(self, "入力エラー", "キーワードを入力してください。")
            return
        if not project:
            QMessageBox.warning(self, "入力エラー", "プロジェクトを選択してください。")
            return

        self._rules.append({
            "keyword": keyword,
            "project": project,
            "subfolder": subfolder,
        })
        save_rules(self.root_folder, self._rules)
        self._refresh_list()
        self._keyword_edit.clear()

    def _delete_rule(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._rules.pop(row)
        save_rules(self.root_folder, self._rules)
        self._refresh_list()


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self, theme: Theme):
        super().__init__()
        self.t = theme
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setMaximumHeight(150)
        self._update_style(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(4)

        self._icon = QLabel("📂")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size: 30px; border: none; background: transparent;")
        layout.addWidget(self._icon)

        self._text = QLabel("ここにファイルをドロップ（複数可）")
        self._text.setAlignment(Qt.AlignCenter)
        self._text.setStyleSheet(
            f"color: {self.t.subtext}; font-size: 13px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(self._text)

    def apply_theme(self, theme: Theme):
        self.t = theme
        self._text.setStyleSheet(
            f"color: {self.t.subtext}; font-size: 13px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        self._update_style(False)

    def _update_style(self, hover: bool):
        if hover:
            self.setStyleSheet(
                f"DropZone {{ background: {self.t.drop_hover}; "
                f"border: 2px dashed {self.t.accent_blue}; border-radius: 14px; }}"
            )
        else:
            self.setStyleSheet(
                f"DropZone {{ background: {self.t.panel}; "
                f"border: 2px dashed {self.t.border}; border-radius: 14px; }}"
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
        self.resize(720, 800)
        self.setMinimumSize(560, 640)

        self._settings = QSettings("FileSorter", "FileSorter")
        self._worker_thread: QThread | None = None
        self._undo_stack: list[tuple[str, str]] = []
        self._last_dropped_files: list[str] = []
        self._last_batch_undo: list[tuple[str, str]] = []

        # テーマ初期化
        saved_mode = self._settings.value("theme_mode", "dark")
        self._theme = Theme(saved_mode)

        self._init_ui()
        self._apply_theme()
        self._load_settings()
        self._refresh_projects()
        self._check_ollama()
        self._update_comment_indicator()

    # ---- UI 構築 ----

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(0)

        # ── ヘッダー行 ──
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        header_row.addStretch()

        # ルール管理ボタン
        self._rules_btn = QPushButton("⚙")
        self._rules_btn.setFixedSize(36, 36)
        self._rules_btn.setCursor(Qt.PointingHandCursor)
        self._rules_btn.setToolTip("分類ルール管理")
        self._rules_btn.clicked.connect(self._open_rules_dialog)
        header_row.addWidget(self._rules_btn)

        # テーマ切替ボタン
        self._theme_btn = QPushButton()
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        self._theme_btn.setToolTip("ダーク / ライト 切替")
        self._theme_btn.clicked.connect(self._toggle_theme)
        header_row.addWidget(self._theme_btn)

        root.addLayout(header_row)

        # Ollama 接続バッジ
        self._ollama_badge = QLabel()
        self._ollama_badge.setObjectName("badge")
        self._ollama_badge.setAlignment(Qt.AlignCenter)
        self._ollama_badge.setFixedHeight(22)
        root.addWidget(self._ollama_badge)

        root.addSpacing(12)

        # ── フォルダ選択 ──
        self._folder_card = QFrame()
        self._folder_card.setObjectName("card")
        fc_layout = QHBoxLayout(self._folder_card)
        fc_layout.setContentsMargins(14, 10, 14, 10)

        folder_icon = QLabel("📁")
        folder_icon.setStyleSheet("font-size: 15px; border: none; background: transparent;")
        fc_layout.addWidget(folder_icon)

        self._folder_edit = QLineEdit()
        self._folder_edit.setObjectName("folder_path")
        self._folder_edit.setReadOnly(True)
        fc_layout.addWidget(self._folder_edit, 1)

        self._change_btn = QPushButton("変更")
        self._change_btn.setObjectName("small_btn")
        self._change_btn.setFixedSize(56, 28)
        self._change_btn.setCursor(Qt.PointingHandCursor)
        self._change_btn.clicked.connect(self._select_folder)
        fc_layout.addWidget(self._change_btn)

        root.addWidget(self._folder_card)
        root.addSpacing(4)

        # プロジェクト＆サブフォルダ一覧
        self._projects_label = QLabel()
        self._projects_label.setObjectName("projects_info")
        self._projects_label.setWordWrap(True)
        root.addWidget(self._projects_label)

        root.addSpacing(10)

        # ── ドロップゾーン ──
        self._drop_zone = DropZone(self._theme)
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        root.addWidget(self._drop_zone)

        root.addSpacing(10)

        # ── コメント入力 ──
        self._comment_card = QFrame()
        self._comment_card.setObjectName("card")
        cc_layout = QVBoxLayout(self._comment_card)
        cc_layout.setContentsMargins(14, 10, 14, 10)
        cc_layout.setSpacing(6)

        # コメントヘッダー行
        ch = QHBoxLayout()
        self._comment_title = QLabel("💬 補足コメント")
        self._comment_title.setObjectName("comment_title")
        ch.addWidget(self._comment_title)

        self._comment_badge = QLabel()
        self._comment_badge.setObjectName("comment_badge")
        ch.addWidget(self._comment_badge)
        ch.addStretch()
        cc_layout.addLayout(ch)

        # 入力行
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._comment_edit = QLineEdit()
        self._comment_edit.setObjectName("comment_input")
        self._comment_edit.setPlaceholderText(
            "例: ワークスから受領した構造計算書、○○橋の現場写真 …"
        )
        self._comment_edit.textChanged.connect(self._update_comment_indicator)
        self._comment_edit.returnPressed.connect(self._on_comment_send)
        input_row.addWidget(self._comment_edit, 1)

        self._comment_send_btn = QPushButton("送信")
        self._comment_send_btn.setObjectName("send_btn")
        self._comment_send_btn.setFixedSize(56, 32)
        self._comment_send_btn.setCursor(Qt.PointingHandCursor)
        self._comment_send_btn.setToolTip("コメントを反映して再分類")
        self._comment_send_btn.clicked.connect(self._on_comment_send)
        self._comment_send_btn.setEnabled(False)
        input_row.addWidget(self._comment_send_btn)

        self._comment_clear_btn = QPushButton("✕")
        self._comment_clear_btn.setObjectName("clear_btn")
        self._comment_clear_btn.setFixedSize(32, 32)
        self._comment_clear_btn.setCursor(Qt.PointingHandCursor)
        self._comment_clear_btn.setToolTip("コメントをクリア")
        self._comment_clear_btn.clicked.connect(self._comment_edit.clear)
        input_row.addWidget(self._comment_clear_btn)

        cc_layout.addLayout(input_row)

        # 学習済みヒント
        self._history_hint = QLabel()
        self._history_hint.setObjectName("history_hint")
        self._history_hint.setWordWrap(True)
        cc_layout.addWidget(self._history_hint)

        root.addWidget(self._comment_card)

        root.addSpacing(10)

        # ── ステータス ──
        status_row = QHBoxLayout()
        status_row.addStretch()

        self._status_label = QLabel("待機中")
        self._status_label.setObjectName("status")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setFixedHeight(24)
        status_row.addWidget(self._status_label)

        self._stop_btn = QPushButton("⏹ 停止")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setFixedSize(64, 24)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setToolTip("処理を中断して元に戻す")
        self._stop_btn.clicked.connect(self._stop_processing)
        self._stop_btn.setVisible(False)
        status_row.addWidget(self._stop_btn)

        status_row.addStretch()
        root.addLayout(status_row)

        root.addSpacing(6)

        # ── ログ ──
        self._log_area = QTextEdit()
        self._log_area.setObjectName("log")
        self._log_area.setReadOnly(True)
        root.addWidget(self._log_area, 1)

        root.addSpacing(10)

        # ── ボタンバー ──
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self._undo_btn = QPushButton("↩  元に戻す")
        self._undo_btn.setObjectName("action_btn_warn")
        self._undo_btn.setCursor(Qt.PointingHandCursor)
        self._undo_btn.setFixedHeight(34)
        self._undo_btn.clicked.connect(self._undo_last)
        btn_bar.addWidget(self._undo_btn)

        btn_bar.addStretch()

        self._clear_log_btn = QPushButton("ログをクリア")
        self._clear_log_btn.setObjectName("action_btn_dim")
        self._clear_log_btn.setCursor(Qt.PointingHandCursor)
        self._clear_log_btn.setFixedHeight(34)
        self._clear_log_btn.clicked.connect(self._log_area.clear)
        btn_bar.addWidget(self._clear_log_btn)

        root.addLayout(btn_bar)

    # ---- テーマ ----

    def _apply_theme(self):
        t = self._theme
        # テーマ切替ボタンのアイコン
        icon = "☀️" if t.mode == "dark" else "🌙"
        self._theme_btn.setText(icon)

        self.setStyleSheet(f"""
            QMainWindow {{ background: {t.bg}; }}
            QWidget {{
                background: {t.bg}; color: {t.text};
                font-family: 'Yu Gothic UI', 'Meiryo', 'Segoe UI', sans-serif;
            }}

            QPushButton#small_btn {{
                background: {t.accent_purple}18; color: {t.accent_purple};
                border: 1px solid {t.accent_purple}40; border-radius: 6px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton#small_btn:hover {{ background: {t.accent_purple}35; }}

            QFrame#card {{
                background: {t.panel}; border: 1px solid {t.border};
                border-radius: 12px;
            }}

            #folder_path {{
                background: transparent; color: {t.text}; border: none;
                font-size: 12px; padding: 2px 6px;
            }}

            #projects_info {{
                color: {t.dim}; font-size: 11px; padding: 2px 8px;
            }}

            #comment_title {{
                color: {t.subtext}; font-size: 12px; font-weight: bold;
                border: none; background: transparent;
            }}
            #comment_badge {{
                border: none; background: transparent; font-size: 11px;
            }}
            #comment_input {{
                background: {t.input_bg}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QPushButton#send_btn {{
                background: {t.accent_blue}; color: #ffffff;
                border: none; border-radius: 8px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton#send_btn:hover {{ background: {t.accent_purple}; }}
            QPushButton#send_btn:disabled {{
                background: {t.dim}40; color: {t.dim};
            }}
            QPushButton#clear_btn {{
                background: {t.error}15; color: {t.error};
                border: 1px solid {t.error}30; border-radius: 8px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton#clear_btn:hover {{ background: {t.error}30; }}

            #history_hint {{
                color: {t.dim}; font-size: 10px; padding: 2px 0 0 0;
                border: none; background: transparent;
            }}

            #status {{
                color: {t.accent_blue}; font-size: 13px; font-weight: bold;
            }}
            QPushButton#stop_btn {{
                background: {t.error}; color: #ffffff;
                border: none; border-radius: 6px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton#stop_btn:hover {{ background: {t.error}cc; }}

            QTextEdit#log {{
                background: {t.panel}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 12px;
                padding: 10px 12px; font-size: 12px;
                selection-background-color: {t.accent_blue}40;
            }}

            QPushButton#action_btn_warn {{
                background: {t.warn}12; color: {t.warn};
                border: 1px solid {t.warn}35; border-radius: 8px;
                padding: 0 18px; font-size: 12px; font-weight: bold;
            }}
            QPushButton#action_btn_warn:hover {{
                background: {t.warn}28; border-color: {t.warn}60;
            }}

            QPushButton#action_btn_dim {{
                background: {t.subtext}12; color: {t.subtext};
                border: 1px solid {t.subtext}35; border-radius: 8px;
                padding: 0 18px; font-size: 12px; font-weight: bold;
            }}
            QPushButton#action_btn_dim:hover {{
                background: {t.subtext}28; border-color: {t.subtext}60;
            }}

            QPushButton {{ font-size: 16px; background: transparent; border: none; }}

            QScrollBar:vertical {{
                background: {t.panel}; width: 6px;
                border-radius: 3px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {t.border}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t.subtext}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}

            QToolTip {{
                background: {t.panel_light}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 6px;
                padding: 4px 8px; font-size: 11px;
            }}
        """)

        # DropZone のテーマも更新
        if hasattr(self, "_drop_zone"):
            self._drop_zone.apply_theme(t)

    def _toggle_theme(self):
        self._theme = self._theme.toggle()
        self._settings.setValue("theme_mode", self._theme.mode)
        self._apply_theme()
        self._update_comment_indicator()
        self._check_ollama()
        self._update_history_hint()

    # ---- ルール管理 ----

    def _open_rules_dialog(self):
        dlg = RulesDialog(self.root_folder, self._theme, self)
        dlg.exec()
        self._update_history_hint()

    # ---- コメントインジケーター ----

    def _update_comment_indicator(self):
        t = self._theme
        text = self._comment_edit.text().strip()
        has_last_files = bool(self._last_batch_undo)
        if text:
            if has_last_files:
                self._comment_badge.setText("✔ 入力済み（送信で再分類 / ドロップで新規分類）")
            else:
                self._comment_badge.setText("✔ 入力済み（ドロップ時にAIへ送信）")
            self._comment_badge.setStyleSheet(
                f"color: {t.success}; font-size: 11px; font-weight: bold; "
                f"border: none; background: transparent;"
            )
            self._comment_clear_btn.setVisible(True)
            self._comment_send_btn.setEnabled(has_last_files)
        else:
            self._comment_badge.setText("任意 — 入力するとAIの分類精度が向上")
            self._comment_badge.setStyleSheet(
                f"color: {t.dim}; font-size: 11px; "
                f"border: none; background: transparent;"
            )
            self._comment_clear_btn.setVisible(False)
            self._comment_send_btn.setEnabled(False)

    def _update_history_hint(self):
        """学習済み件数・ルール件数をヒント表示。"""
        t = self._theme
        rules = load_rules(self.root_folder)
        history = load_history(self.root_folder)
        parts = []
        if rules:
            parts.append(f"⚙ ルール {len(rules)}件")
        if history:
            parts.append(f"📚 学習 {len(history)}件")
        if parts:
            self._history_hint.setText("  |  ".join(parts))
            self._history_hint.setStyleSheet(
                f"color: {t.accent_blue}; font-size: 10px; "
                f"border: none; background: transparent; padding: 2px 0 0 0;"
            )
        else:
            self._history_hint.setText(
                "⚙ からルールを登録するか、分類を重ねるとAIの精度が向上します"
            )
            self._history_hint.setStyleSheet(
                f"color: {t.dim}; font-size: 10px; "
                f"border: none; background: transparent; padding: 2px 0 0 0;"
            )

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

    # ---- Ollama ----

    def _check_ollama(self):
        t = self._theme
        if check_ollama_connection():
            self._ollama_badge.setText("● 接続済み")
            self._ollama_badge.setStyleSheet(
                f"color: {t.success}; font-size: 11px; font-weight: bold;"
            )
        else:
            self._ollama_badge.setText("● 未接続 — Ollama を起動してください")
            self._ollama_badge.setStyleSheet(
                f"color: {t.error}; font-size: 11px; font-weight: bold;"
            )

    # ---- フォルダ ----

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "整理先ルートフォルダを選択", self.root_folder
        )
        if folder:
            self._folder_edit.setText(folder)
            self._save_settings()
            self._refresh_projects()
            self._update_history_hint()

    def _refresh_projects(self):
        projects = scan_projects(self.root_folder)
        subfolder_map = scan_all_subfolders(self.root_folder, projects)

        if projects:
            parts = []
            for p in projects:
                subs = subfolder_map.get(p, [])
                if subs:
                    parts.append(f"{p}（{', '.join(subs)}）")
                else:
                    parts.append(p)
            self._projects_label.setText(
                f"検出フォルダ ({len(projects)}):  " + "、".join(parts)
            )
        else:
            self._projects_label.setText("プロジェクトフォルダが見つかりません")

        self._update_history_hint()

    # ---- ファイルドロップ ----

    def _on_files_dropped(self, files: list[str]):
        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.warning(self, "処理中", "処理中です。完了をお待ちください。")
            return

        self._refresh_projects()

        user_comment = self._comment_edit.text().strip()

        # ルール・コメント直接マッチで処理できるかチェック
        rules = load_rules(self.root_folder)
        projects = scan_projects(self.root_folder)
        subfolder_map = scan_all_subfolders(self.root_folder, projects)
        has_direct = False
        if user_comment:
            has_direct = (
                match_rule(user_comment, rules) is not None
                or match_comment_to_project(user_comment, projects, subfolder_map) is not None
            )

        # 直接マッチできない場合のみ Ollama 必須
        if not has_direct and not check_ollama_connection():
            self._check_ollama()
            self._append_log("❌ Ollama に接続できません。サーバーを起動してください。",
                             self._theme.error)
            return

        self._status_label.setText(f"処理中… (0/{len(files)})")

        self._last_dropped_files = list(files)
        self._last_batch_undo = []

        if user_comment:
            self._append_log(f"💬 コメント反映: {user_comment}", self._theme.accent_purple)

        self._worker_thread = QThread()
        self._worker = SortWorker(
            files, self.root_folder, user_comment, self._theme,
        )
        self._worker.moveToThread(self._worker_thread)

        self._worker.log_signal.connect(self._append_log)
        self._worker.status_signal.connect(self._status_label.setText)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.undo_record.connect(self._record_undo)
        self._worker.history_record.connect(self._save_history)

        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()
        self._stop_btn.setVisible(True)

    def _on_worker_finished(self):
        was_cancelled = self._worker is not None and self._worker._cancelled
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
        self._worker = None
        self._stop_btn.setVisible(False)
        self._stop_btn.setEnabled(True)

        if was_cancelled:
            self._undo_batch(self._last_batch_undo)
            self._last_batch_undo = []
            self._append_log("⏹ 処理を中断し、移動済みファイルを元に戻しました。",
                             self._theme.warn)

        self._check_ollama()
        self._update_history_hint()
        self._update_comment_indicator()

    # ---- 処理停止 ----

    def _stop_processing(self):
        """処理を中断する。ワーカーにキャンセルフラグを立てる。"""
        if self._worker is not None:
            self._worker.cancel()
            self._stop_btn.setEnabled(False)
            self._status_label.setText("停止中…")

    def _undo_batch(self, batch: list[tuple[str, str]]):
        """バッチ内の移動を全て元に戻す。"""
        for moved_to, original_path in reversed(batch):
            moved_path = Path(moved_to)
            if not moved_path.exists():
                continue
            try:
                Path(original_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(moved_path), original_path)
                parent_folder = moved_path.parent
                if parent_folder.is_dir() and not any(parent_folder.iterdir()):
                    parent_folder.rmdir()
                # undo_stack からも除去
                try:
                    self._undo_stack.remove((moved_to, original_path))
                except ValueError:
                    pass
            except Exception:
                pass

    # ---- コメント送信（ドロップ後の再分類） ----

    def _on_comment_send(self):
        """直前にドロップしたファイルを、コメント付きで再分類する。"""
        comment = self._comment_edit.text().strip()
        if not comment or not self._last_batch_undo:
            return

        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.warning(self, "処理中", "処理中です。完了をお待ちください。")
            return

        # 直前バッチのファイルを元に戻す
        restored_files = []
        for moved_to, original_path in reversed(self._last_batch_undo):
            moved_path = Path(moved_to)
            if not moved_path.exists():
                self._append_log(
                    f"⚠️ 再分類スキップ（ファイル不在）: {moved_to}",
                    self._theme.warn,
                )
                continue
            try:
                Path(original_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(moved_path), original_path)
                parent_folder = moved_path.parent
                if parent_folder.is_dir() and not any(parent_folder.iterdir()):
                    parent_folder.rmdir()
                restored_files.append(original_path)
                # undo_stack からも除去
                try:
                    self._undo_stack.remove((moved_to, original_path))
                except ValueError:
                    pass
            except Exception as e:
                self._append_log(f"❌ 元に戻す操作に失敗: {e}", self._theme.error)

        if not restored_files:
            self._append_log("❌ 再分類するファイルがありません。", self._theme.error)
            return

        self._append_log(
            f"🔄 コメント付きで {len(restored_files)} ファイルを再分類します",
            self._theme.accent_blue,
        )
        # 再ドロップと同じ処理を実行
        self._on_files_dropped(restored_files)

    # ---- 履歴保存 ----

    def _save_history(self, comment: str, project: str, subfolder: str):
        save_history_entry(self.root_folder, comment, project, subfolder)

    # ---- 元に戻す ----

    def _record_undo(self, moved_to: str, original_path: str):
        self._undo_stack.append((moved_to, original_path))
        self._last_batch_undo.append((moved_to, original_path))

    def _undo_last(self):
        if not self._undo_stack:
            self._append_log("↩ 戻せる操作がありません。", self._theme.subtext)
            return

        moved_to, original_path = self._undo_stack.pop()
        moved_path = Path(moved_to)

        if not moved_path.exists():
            self._append_log(f"❌ ファイルが見つかりません: {moved_to}",
                             self._theme.error)
            return

        try:
            Path(original_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(moved_path), original_path)
            parent_folder = moved_path.parent
            if parent_folder.is_dir() and not any(parent_folder.iterdir()):
                parent_folder.rmdir()
            self._append_log(
                f"↩ 元に戻しました: {moved_path.name} → {original_path}",
                self._theme.accent_purple,
            )
        except Exception as e:
            self._append_log(f"❌ 元に戻す操作に失敗: {e}", self._theme.error)

    # ---- ログ ----

    def _append_log(self, message: str, color: str = ""):
        t = self._theme
        if not color:
            color = t.text
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_area.append(
            f'<span style="color:{t.dim}">{timestamp}</span>'
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
