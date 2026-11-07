#!/usr/bin/env python3
"""Misskey ドライブの全ファイルをフォルダ構造を保ったままダウンロードする。

標準ライブラリのみ使用 (Python 3.8+)。

使い方:
    export MISSKEY_TOKEN=xxxxxxxx          # 権限: 「ドライブを見る」(read:drive)
    python misskey_drive_download.py                 # ./misskey-drive に保存
    python misskey_drive_download.py -o D:/backup    # 保存先を指定
    python misskey_drive_download.py --host misskey.io

再実行時は保存済みのファイルをスキップするため、中断後の再開が可能。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ===== 設定 =====
DEFAULT_HOST = "misskey.dev"
DEFAULT_OUTPUT = "misskey-drive"
PAGE_LIMIT = 100  # API の最大値
REQUEST_INTERVAL = 0.5  # API 呼び出し間隔 (秒)。レート制限対策
MAX_RETRIES = 5
USER_AGENT = "misskey-drive-downloader/1.0"


# ===== API =====
class MisskeyClient:
    def __init__(self, host: str, token: str):
        self.base = f"https://{host}/api"
        self.token = token

    def call(self, endpoint: str, params: dict) -> list:
        """API を呼び出す。429/5xx は待機してリトライする。"""
        body = json.dumps({"i": self.token, **params}).encode()
        for attempt in range(1, MAX_RETRIES + 1):
            req = urllib.request.Request(
                f"{self.base}/{endpoint}",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as res:
                    time.sleep(REQUEST_INTERVAL)
                    return json.load(res)
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    wait = 2 ** attempt
                    print(f"  ! {endpoint}: HTTP {e.code}, {wait}秒後に再試行", file=sys.stderr)
                    time.sleep(wait)
                    continue
                detail = e.read().decode(errors="replace")
                raise SystemExit(f"API エラー {endpoint}: HTTP {e.code}\n{detail}")
        raise SystemExit(f"API エラー {endpoint}: リトライ上限に達しました")

    def paginate(self, endpoint: str, params: dict):
        """untilId を使って全件を取得する。"""
        until_id = None
        while True:
            page_params = {**params, "limit": PAGE_LIMIT}
            if until_id:
                page_params["untilId"] = until_id
            items = self.call(endpoint, page_params)
            if not items:
                return
            yield from items
            until_id = items[-1]["id"]

    def folders(self, folder_id):
        return self.paginate("drive/folders", {"folderId": folder_id})

    def files(self, folder_id):
        return self.paginate("drive/files", {"folderId": folder_id})


# ===== ファイル名 =====
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.IGNORECASE)


def safe_name(name: str, fallback: str) -> str:
    """Windows でも使えるファイル名に変換する。"""
    name = _INVALID_CHARS.sub("_", name or "").strip().rstrip(". ")
    if not name:
        name = fallback
    if _RESERVED.match(name):
        name = f"_{name}"
    return name


def unique_names(items: list, used: set) -> dict:
    """同一フォルダ内の重複名に ID を付与し、{id: 名前} を返す。used は共有・更新される。"""
    result = {}
    for item in items:
        name = safe_name(item["name"], item["id"])
        if name.lower() in used:
            stem, ext = os.path.splitext(name)
            name = f"{stem}_{item['id']}{ext}"
        used.add(name.lower())
        result[item["id"]] = name
    return result


# ===== ダウンロード =====
def download(url: str, dest: Path) -> bool:
    """ファイルを保存する。既に存在すればスキップして False を返す。

    保存は .part 経由のリネームで行うため、存在するファイルは完全なものとみなす。
    """
    if dest.exists():
        return False
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as res, open(tmp, "wb") as out:
                while chunk := res.read(1024 * 256):
                    out.write(chunk)
            tmp.replace(dest)
            return True
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            # 404 等の 4xx (429 以外) は再試行しても回復しないため即失敗とする
            permanent = isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429
            if permanent or attempt == MAX_RETRIES:
                tmp.unlink(missing_ok=True)
                raise
            wait = 2 ** attempt
            print(f"  ! 再試行 ({e}) {wait}秒後", file=sys.stderr)
            time.sleep(wait)
    return False


# ===== 走査 =====
class Stats:
    def __init__(self):
        self.downloaded = 0
        self.skipped = 0
        self.failed = []  # (パス, エラー)


def walk(client: MisskeyClient, folder_id, local_dir: Path, stats: Stats, dry_run: bool):
    """フォルダを再帰的に辿り、ファイルを保存する。folder_id=None はルート。"""
    if not dry_run:
        local_dir.mkdir(parents=True, exist_ok=True)
    folders = list(client.folders(folder_id))
    files = list(client.files(folder_id))

    used = set()
    folder_names = unique_names(folders, used)
    file_names = unique_names(files, used)

    for f in files:
        dest = local_dir / file_names[f["id"]]
        if dry_run:
            print(f"[dry-run] {dest} ({f['size']} bytes)")
            continue
        try:
            if download(f["url"], dest):
                stats.downloaded += 1
                print(f"保存: {dest}")
            else:
                stats.skipped += 1
        except Exception as e:  # noqa: BLE001  1件の失敗で全体を止めない
            stats.failed.append((dest, e))
            print(f"  ! 失敗: {dest}: {e}", file=sys.stderr)

    for folder in folders:
        walk(client, folder["id"], local_dir / folder_names[folder["id"]], stats, dry_run)


# ===== エントリポイント =====
def main():
    # 絵文字等を含むファイル名の表示で、コンソールの文字コード (cp932 等) により落ちないようにする
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser(description="Misskey ドライブの全ファイルをダウンロードする")
    parser.add_argument("--host", default=os.environ.get("MISSKEY_HOST", DEFAULT_HOST),
                        help=f"インスタンスのホスト名 (既定: {DEFAULT_HOST})")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                        help=f"保存先ディレクトリ (既定: ./{DEFAULT_OUTPUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="ダウンロードせず対象一覧のみ表示")
    args = parser.parse_args()

    token = os.environ.get("MISSKEY_TOKEN")
    if not token:
        raise SystemExit("環境変数 MISSKEY_TOKEN にアクセストークンを設定してください")

    client = MisskeyClient(args.host, token)
    stats = Stats()
    out = Path(args.output)
    print(f"{args.host} のドライブを {out.resolve()} へ保存します")
    walk(client, None, out, stats, args.dry_run)

    print(f"\n完了: 保存 {stats.downloaded} / スキップ {stats.skipped} / 失敗 {len(stats.failed)}")
    for path, err in stats.failed:
        print(f"  失敗: {path}: {err}", file=sys.stderr)
    sys.exit(1 if stats.failed else 0)


if __name__ == "__main__":
    main()
