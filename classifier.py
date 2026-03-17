"""
3層分類ロジック
===============
1. ルールマッチ（キーワードベース即判定）
2. コメント直接マッチ（プロジェクト名/サブフォルダ名の部分一致）
3. Ollama AI判定（confidence付き）

file_sorter.py のコア分類ロジックをベースに、confidence対応を追加。
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from config import (
    HISTORY_FILE,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
    RULES_FILE,
    get_project_keywords,
)


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


def save_history_entry(root: str, filename: str, project: str, subfolder: str,
                       comment: str = "", method: str = ""):
    """分類結果を履歴に追記する。直近100件を保持。"""
    history = load_history(root)
    entry = {
        "filename": filename,
        "project": project,
        "subfolder": subfolder,
        "method": method,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if comment:
        entry["comment"] = comment.strip()
    history.append(entry)
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
        comment = h.get("comment", h.get("filename", ""))
        lines.append(
            f"  「{comment}」→ {h['project']}/{h.get('subfolder', '')}"
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


# ---------------------------------------------------------------------------
# 第1層: ルールマッチ
# ---------------------------------------------------------------------------

def match_rule(text: str, rules: list[dict]) -> dict | None:
    """テキスト（ファイル名またはコメント）に一致するルールを返す。"""
    if not text.strip():
        return None
    text_lower = text.strip().lower()
    for rule in rules:
        keyword = rule.get("keyword", "").strip().lower()
        if keyword and keyword in text_lower:
            return rule
    return None


def match_rule_with_yaml_keywords(filename: str, yaml_config: dict,
                                  projects: list[str]) -> dict | None:
    """projects.yaml のキーワード定義を使ってルールマッチする。"""
    keyword_map = get_project_keywords(yaml_config)
    if not keyword_map:
        return None
    filename_lower = filename.lower()
    for proj_name, keywords in keyword_map.items():
        if proj_name not in projects:
            continue
        for kw in keywords:
            if kw.lower() in filename_lower:
                return {"project": proj_name, "subfolder": "", "keyword": kw}
    return None


# ---------------------------------------------------------------------------
# 第2層: コメント/ファイル名 直接マッチ
# ---------------------------------------------------------------------------

def match_comment_to_project(
    text: str, projects: list[str], subfolder_map: dict[str, list[str]],
) -> dict | None:
    """テキストにプロジェクト名やサブフォルダ名が含まれていれば直接マッチする。"""
    if not text.strip():
        return None
    text_clean = text.strip()

    # 完全一致
    for p in projects:
        if text_clean == p:
            subs = subfolder_map.get(p, [])
            return {"project": p, "subfolder": subs[0] if subs else ""}

    # 部分一致（長い名前を先にチェック）
    sorted_projects = sorted(projects, key=len, reverse=True)
    for p in sorted_projects:
        if len(p) >= 2 and p in text_clean:
            subs = subfolder_map.get(p, [])
            matched_sub = ""
            for s in sorted(subs, key=len, reverse=True):
                if len(s) >= 2 and s in text_clean:
                    matched_sub = s
                    break
            if not matched_sub and subs:
                matched_sub = subs[0]
            return {"project": p, "subfolder": matched_sub}

    return None


# ---------------------------------------------------------------------------
# 第3層: Ollama AI判定（confidence付き）
# ---------------------------------------------------------------------------

def build_prompt(
    filename: str,
    projects: list[str],
    subfolder_map: dict[str, list[str]],
    user_comment: str = "",
    history_context: str = "",
) -> str:
    """Ollama用プロンプトを構築する。confidence付きJSON回答を要求。"""
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

    comment_section = ""
    if user_comment.strip():
        comment_section = f"""
## ユーザーからの補足コメント（分類の最重要ヒント）
{user_comment.strip()}
"""

    history_section = ""
    if history_context.strip():
        history_section = f"""
## 過去の分類パターン（参考にして一貫した分類をすること）
{history_context}
"""

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
2. コメントの内容からファイルの用途を推測し、最も適切なフォルダを選ぶ
3. 過去の分類パターンがある場合、同様のコメントには同じ分類先を使う
4. projectには上記の既存プロジェクトフォルダのいずれか、または "unknown" を指定
5. subfolderには、そのプロジェクト内に実際に存在するサブフォルダ名を正確に指定すること
   - 存在するサブフォルダ: {subfolder_list}
6. confidenceは分類の確信度を0.0〜1.0で指定すること
   - ファイル名やコメントから明確に判断できる → 0.8〜1.0
   - ある程度推測できる → 0.5〜0.7
   - ほぼ判断できない → 0.0〜0.4

## 回答形式（JSONのみ・余計な文字禁止）
{{"project": "プロジェクト名またはunknown", "subfolder": "サブフォルダ名", "confidence": 0.0〜1.0}}"""


def call_ollama(prompt: str) -> dict | None:
    """Ollama API を呼び出し、confidence付きJSON をパースして返す。"""
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
        result = json.loads(json_match.group())
        # confidence が無い場合はデフォルト値を設定
        if "confidence" not in result:
            result["confidence"] = 0.5
        else:
            try:
                result["confidence"] = float(result["confidence"])
            except (ValueError, TypeError):
                result["confidence"] = 0.5
        return result
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
# 統合分類関数（3層判定チェーン）
# ---------------------------------------------------------------------------

def classify_file(
    filename: str,
    root_folder: str,
    projects: list[str],
    subfolder_map: dict[str, list[str]],
    yaml_config: dict | None = None,
    user_comment: str = "",
) -> dict:
    """ファイルを3層で判定し、結果を返す。

    Returns:
        {
            "project": str,
            "subfolder": str,
            "confidence": float,
            "method": str,  # "ルール", "YAML", "コメント直接", "AI", "不明"
        }
    """
    rules = load_rules(root_folder)

    # 第1層: ルールマッチ（ファイル名でチェック）
    matched = match_rule(filename, rules)
    if matched:
        return {
            "project": matched.get("project", "unknown"),
            "subfolder": matched.get("subfolder", ""),
            "confidence": 1.0,
            "method": "ルール",
        }

    # 第1層補助: コメントでもルールマッチ
    if user_comment:
        matched = match_rule(user_comment, rules)
        if matched:
            return {
                "project": matched.get("project", "unknown"),
                "subfolder": matched.get("subfolder", ""),
                "confidence": 1.0,
                "method": "ルール",
            }

    # 第1層補助: YAML キーワードマッチ
    if yaml_config:
        matched = match_rule_with_yaml_keywords(filename, yaml_config, projects)
        if matched:
            return {
                "project": matched["project"],
                "subfolder": matched.get("subfolder", ""),
                "confidence": 0.9,
                "method": "YAML",
            }

    # 第2層: コメント直接マッチ（コメントがある場合のみ）
    if user_comment:
        comment_match = match_comment_to_project(
            user_comment, projects, subfolder_map
        )
        if comment_match:
            return {
                "project": comment_match["project"],
                "subfolder": comment_match.get("subfolder", ""),
                "confidence": 0.95,
                "method": "コメント直接",
            }

    # 第2層補助: ファイル名でプロジェクト名マッチ
    name_match = match_comment_to_project(filename, projects, subfolder_map)
    if name_match:
        return {
            "project": name_match["project"],
            "subfolder": name_match.get("subfolder", ""),
            "confidence": 0.85,
            "method": "ファイル名直接",
        }

    # 第3層: Ollama AI判定
    history_context = build_history_context(root_folder)
    prompt = build_prompt(
        filename, projects, subfolder_map, user_comment, history_context
    )
    result = call_ollama(prompt)

    if result is None:
        return {
            "project": "unknown",
            "subfolder": "",
            "confidence": 0.0,
            "method": "不明",
        }

    return {
        "project": result.get("project", "unknown"),
        "subfolder": result.get("subfolder", ""),
        "confidence": result.get("confidence", 0.5),
        "method": "AI",
    }
