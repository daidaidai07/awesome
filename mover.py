"""
ファイル移動モジュール
=====================
日付プレフィックス付きフォルダへのファイル移動、undo対応。
auto-save-downloads.py と file_sorter.py の移動ロジックを統合。
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path


def get_date_prefix_from_filename(filename: str) -> tuple[str, str]:
    """ファイル名から日付プレフィックスとベース名を抽出する。

    Returns:
        (date_prefix, folder_base)
        - YYYYMMDD_ 形式 → YYMMDD に変換
        - YYMMDD_ 形式 → そのまま使用
        - それ以外 → 現在日付のYYMMDD
    """
    stem = Path(filename).stem

    if re.match(r"^\d{8}_", stem):
        # YYYYMMDD_ → YYMMDD
        date_prefix = stem[2:8]
        folder_base = stem[9:]
        return date_prefix, folder_base
    elif re.match(r"^\d{6}_", stem):
        # YYMMDD_
        date_prefix = stem[:6]
        folder_base = stem[7:]
        return date_prefix, folder_base
    else:
        date_prefix = datetime.now().strftime("%y%m%d")
        return date_prefix, stem


def get_file_mod_date(filepath: str) -> str:
    """ファイルの更新日をYYMMDD形式で返す。"""
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%y%m%d")


def move_file_to_project(filepath: str, dest_dir: str) -> str:
    """ファイルまたはフォルダをプロジェクトフォルダへ移動する。
    日付プレフィックス付きサブフォルダを作成。

    - ファイル: YYMMDD_ファイル名/ フォルダを作成してその中に移動
    - フォルダ: YYMMDD_フォルダ名 にリネームして移動

    Returns:
        移動先のパス文字列
    """
    src = Path(filepath)
    date_prefix = get_file_mod_date(filepath)

    if src.is_dir():
        folder_name = f"{date_prefix}_{src.name}"
        target = Path(dest_dir) / folder_name

        if target.exists():
            counter = 2
            while True:
                candidate = Path(dest_dir) / f"{folder_name}_{counter}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1

        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        return str(target)

    # ファイルの場合
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


def move_file_to_watch_dir(filepath: str, watch_dir: str) -> str:
    """ダウンロードフォルダ内で日付フォルダへ移動する（watcher用フォールバック）。

    Returns:
        移動先のパス文字列
    """
    filepath = Path(filepath)
    filename = filepath.name
    date_prefix, folder_base = get_date_prefix_from_filename(filename)

    dest_dir = Path(watch_dir) / f"{date_prefix}_{folder_base}"
    dest_dir.mkdir(exist_ok=True)

    dest_file = dest_dir / filename

    if dest_file.exists():
        counter = 1
        while True:
            dest_file = dest_dir / f"{filepath.stem}_{counter}{filepath.suffix}"
            if not dest_file.exists():
                break
            counter += 1

    shutil.move(str(filepath), str(dest_file))
    return str(dest_file)


def undo_move(moved_to: str, original_path: str) -> bool:
    """移動を元に戻す。成功すればTrue。"""
    moved_path = Path(moved_to)
    if not moved_path.exists():
        return False

    try:
        Path(original_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(moved_path), original_path)
        # 空になった親フォルダを削除
        parent_folder = moved_path.parent
        if parent_folder.is_dir() and not any(parent_folder.iterdir()):
            parent_folder.rmdir()
        return True
    except Exception:
        return False
