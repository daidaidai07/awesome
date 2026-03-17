"""
設定管理モジュール
=================
projects.yaml の読み込み、フォルダスキャン、アプリケーション設定を管理する。
"""

import os
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
APP_NAME = "ダウンロード自動仕分けツール"
APP_VERSION = "1.0.0"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 60
UNKNOWN_DIR = "_未分類"
HISTORY_FILE = "_分類履歴.json"
RULES_FILE = "_分類ルール.json"
CONFIG_FILE = "projects.yaml"

SKIP_EXTENSIONS = {".crdownload", ".part", ".tmp"}

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# projects.yaml 読み込み
# ---------------------------------------------------------------------------

def load_projects_yaml(config_path: str | None = None) -> dict:
    """projects.yaml を読み込む。ファイルが無い場合やyamlが無い場合はデフォルト値を返す。"""
    if config_path is None:
        config_path = str(Path(__file__).parent / CONFIG_FILE)

    defaults = {
        "root_folder": str(Path.home() / "Desktop"),
        "watch_folder": str(Path.home() / "Downloads"),
        "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        "projects": [],
    }

    if not HAS_YAML:
        return defaults

    path = Path(config_path)
    if not path.exists():
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return defaults
    except Exception:
        return defaults

    result = dict(defaults)
    if "root_folder" in data and data["root_folder"]:
        result["root_folder"] = str(data["root_folder"])
    if "watch_folder" in data and data["watch_folder"]:
        result["watch_folder"] = str(data["watch_folder"])
    elif "watch_folder" not in data or data["watch_folder"] is None:
        result["watch_folder"] = str(Path.home() / "Downloads")
    if "confidence_threshold" in data:
        try:
            result["confidence_threshold"] = float(data["confidence_threshold"])
        except (ValueError, TypeError):
            pass
    if "projects" in data and isinstance(data["projects"], list):
        result["projects"] = data["projects"]

    return result


def get_project_keywords(config: dict) -> dict[str, list[str]]:
    """projects.yaml から {プロジェクト名: [キーワード一覧]} のマップを返す。"""
    result = {}
    for proj in config.get("projects", []):
        name = proj.get("name", "")
        keywords = proj.get("keywords", [])
        if name and keywords:
            result[name] = [str(k) for k in keywords]
    return result


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
