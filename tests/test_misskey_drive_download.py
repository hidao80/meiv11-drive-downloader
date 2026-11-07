"""misskey_drive_download.py のテスト。ネットワークには接続しない。"""

import io
import json
import urllib.error
from pathlib import Path

import pytest

import misskey_drive_download as mdd


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """待機処理を無効化し、呼び出された秒数を記録する。"""
    calls = []
    monkeypatch.setattr(mdd.time, "sleep", calls.append)
    return calls


def http_error(code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.test", code, "error", {}, io.BytesIO(body))


def fake_urlopen(monkeypatch, responses):
    """urlopen を差し替える。responses の要素が例外なら送出し、bytes なら応答として返す。"""
    requests = []
    queue = list(responses)

    def _urlopen(req, timeout=None):
        requests.append(req)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(item)

    monkeypatch.setattr(mdd.urllib.request, "urlopen", _urlopen)
    return requests


# ===== safe_name =====
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("photo.png", "photo.png"),
        ('a<b>:c"d/e\\f|g?h*i.txt', "a_b__c_d_e_f_g_h_i.txt"),
        ("tab\there", "tab_here"),
        ("  trailing. . ", "trailing"),
        ("con", "_con"),
        ("NUL.txt", "_NUL.txt"),
        ("com1.log", "_com1.log"),
        ("console.txt", "console.txt"),
        ("日本語ファイル.jpg", "日本語ファイル.jpg"),
    ],
)
def test_safe_name(name, expected):
    assert mdd.safe_name(name, "fallback") == expected


@pytest.mark.parametrize("name", ["", None, "...", "   "])
def test_safe_name_fallback(name):
    assert mdd.safe_name(name, "abc123") == "abc123"


# ===== unique_names =====
def test_unique_names_case_insensitive_duplicates():
    items = [{"id": "1", "name": "a.txt"}, {"id": "2", "name": "A.TXT"}]
    assert mdd.unique_names(items, set()) == {"1": "a.txt", "2": "A_2.TXT"}


def test_unique_names_shares_used_set_between_folders_and_files():
    used = set()
    folders = mdd.unique_names([{"id": "f1", "name": "data"}], used)
    files = mdd.unique_names([{"id": "x1", "name": "data"}], used)
    assert folders == {"f1": "data"}
    assert files == {"x1": "data_x1"}


def test_unique_names_sanitized_collision():
    items = [{"id": "1", "name": "a?b"}, {"id": "2", "name": "a*b"}]
    assert mdd.unique_names(items, set()) == {"1": "a_b", "2": "a_b_2"}


# ===== MisskeyClient =====
def test_call_sends_token_and_params(monkeypatch):
    requests = fake_urlopen(monkeypatch, [b'[{"id": "1"}]'])
    client = mdd.MisskeyClient("example.test", "TOKEN")

    assert client.call("drive/files", {"folderId": None}) == [{"id": "1"}]

    req = requests[0]
    assert req.full_url == "https://example.test/api/drive/files"
    assert req.get_method() == "POST"
    assert json.loads(req.data) == {"i": "TOKEN", "folderId": None}


@pytest.mark.parametrize("code", [429, 500, 503])
def test_call_retries_on_rate_limit_and_server_error(monkeypatch, no_sleep, code):
    requests = fake_urlopen(monkeypatch, [http_error(code), b"[]"])
    client = mdd.MisskeyClient("example.test", "TOKEN")

    assert client.call("drive/files", {}) == []
    assert len(requests) == 2
    assert 2 in no_sleep  # 1回目の再試行待機 (2 ** 1 秒)


def test_call_client_error_exits_with_detail(monkeypatch):
    requests = fake_urlopen(monkeypatch, [http_error(401, b"invalid token")])
    client = mdd.MisskeyClient("example.test", "TOKEN")

    with pytest.raises(SystemExit, match="HTTP 401[\\s\\S]*invalid token"):
        client.call("drive/files", {})
    assert len(requests) == 1


def test_call_gives_up_after_max_retries(monkeypatch):
    requests = fake_urlopen(monkeypatch, [http_error(500)] * mdd.MAX_RETRIES)
    client = mdd.MisskeyClient("example.test", "TOKEN")

    with pytest.raises(SystemExit, match="リトライ上限"):
        client.call("drive/files", {})
    assert len(requests) == mdd.MAX_RETRIES


def test_paginate_uses_until_id(monkeypatch):
    pages = [[{"id": "3"}, {"id": "2"}], [{"id": "1"}], []]
    calls = []

    def fake_call(endpoint, params):
        calls.append((endpoint, params))
        return pages[len(calls) - 1]

    client = mdd.MisskeyClient("example.test", "TOKEN")
    monkeypatch.setattr(client, "call", fake_call)

    assert [i["id"] for i in client.files("folder")] == ["3", "2", "1"]
    assert calls == [
        ("drive/files", {"folderId": "folder", "limit": mdd.PAGE_LIMIT}),
        ("drive/files", {"folderId": "folder", "limit": mdd.PAGE_LIMIT, "untilId": "2"}),
        ("drive/files", {"folderId": "folder", "limit": mdd.PAGE_LIMIT, "untilId": "1"}),
    ]


def test_folders_endpoint(monkeypatch):
    client = mdd.MisskeyClient("example.test", "TOKEN")
    calls = []
    monkeypatch.setattr(client, "call", lambda endpoint, params: calls.append(endpoint) or [])

    assert list(client.folders(None)) == []
    assert calls == ["drive/folders"]


# ===== download =====
def test_download_saves_file(monkeypatch, tmp_path):
    fake_urlopen(monkeypatch, [b"hello"])
    dest = tmp_path / "a.txt"

    assert mdd.download("https://example.test/a", dest) is True
    assert dest.read_bytes() == b"hello"
    assert not (tmp_path / "a.txt.part").exists()


def test_download_skips_existing_file(monkeypatch, tmp_path):
    requests = fake_urlopen(monkeypatch, [])
    dest = tmp_path / "a.txt"
    dest.write_bytes(b"old")

    assert mdd.download("https://example.test/a", dest) is False
    assert dest.read_bytes() == b"old"
    assert requests == []


def test_download_retries_transient_error(monkeypatch, tmp_path):
    requests = fake_urlopen(monkeypatch, [urllib.error.URLError("timeout"), http_error(503), b"ok"])
    dest = tmp_path / "a.txt"

    assert mdd.download("https://example.test/a", dest) is True
    assert dest.read_bytes() == b"ok"
    assert len(requests) == 3


@pytest.mark.parametrize("code", [403, 404])
def test_download_permanent_error_fails_immediately(monkeypatch, tmp_path, code):
    requests = fake_urlopen(monkeypatch, [http_error(code)])
    dest = tmp_path / "a.txt"

    with pytest.raises(urllib.error.HTTPError):
        mdd.download("https://example.test/a", dest)
    assert len(requests) == 1
    assert not dest.exists()
    assert not (tmp_path / "a.txt.part").exists()


def test_download_gives_up_after_max_retries(monkeypatch, tmp_path):
    requests = fake_urlopen(monkeypatch, [ConnectionError("reset")] * mdd.MAX_RETRIES)
    dest = tmp_path / "a.txt"

    with pytest.raises(ConnectionError):
        mdd.download("https://example.test/a", dest)
    assert len(requests) == mdd.MAX_RETRIES
    assert not dest.exists()


# ===== walk =====
class FakeClient:
    """フォルダ ID ごとにフォルダ・ファイル一覧を返すスタブ。"""

    def __init__(self, folders: dict, files: dict):
        self._folders = folders
        self._files = files

    def folders(self, folder_id):
        return iter(self._folders.get(folder_id, []))

    def files(self, folder_id):
        return iter(self._files.get(folder_id, []))


def make_file(id_, name, size=1):
    return {"id": id_, "name": name, "url": f"https://example.test/{id_}", "size": size}


@pytest.fixture
def drive():
    return FakeClient(
        folders={None: [{"id": "f1", "name": "sub"}]},
        files={
            None: [make_file("1", "a.txt"), make_file("2", "sub")],
            "f1": [make_file("3", "b.txt")],
        },
    )


def test_walk_downloads_tree(monkeypatch, tmp_path, drive):
    saved = {}

    def fake_download(url, dest: Path):
        saved[dest.relative_to(tmp_path).as_posix()] = url
        dest.write_bytes(b"x")
        return True

    monkeypatch.setattr(mdd, "download", fake_download)
    stats = mdd.Stats()

    mdd.walk(drive, None, tmp_path, stats, dry_run=False)

    assert saved == {
        "a.txt": "https://example.test/1",
        "sub_2": "https://example.test/2",  # フォルダ名と衝突したファイル
        "sub/b.txt": "https://example.test/3",
    }
    assert (stats.downloaded, stats.skipped, stats.failed) == (3, 0, [])


def test_walk_counts_skipped_and_continues_after_failure(monkeypatch, tmp_path, drive):
    def fake_download(url, dest: Path):
        if dest.name == "a.txt":
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return dest.name == "b.txt"

    monkeypatch.setattr(mdd, "download", fake_download)
    stats = mdd.Stats()

    mdd.walk(drive, None, tmp_path, stats, dry_run=False)

    assert stats.downloaded == 1
    assert stats.skipped == 1
    assert [p.name for p, _ in stats.failed] == ["a.txt"]


def test_walk_dry_run_writes_nothing(monkeypatch, tmp_path, drive, capsys):
    monkeypatch.setattr(mdd, "download", pytest.fail)
    out = tmp_path / "out"

    mdd.walk(drive, None, out, mdd.Stats(), dry_run=True)

    assert not out.exists()
    stdout = capsys.readouterr().out
    assert stdout.count("[dry-run]") == 3


# ===== main =====
def test_main_requires_token(monkeypatch):
    monkeypatch.delenv("MISSKEY_TOKEN", raising=False)
    monkeypatch.setattr(mdd.sys, "argv", ["prog"])

    with pytest.raises(SystemExit, match="MISSKEY_TOKEN"):
        mdd.main()


@pytest.mark.parametrize(("failed", "exit_code"), [([], 0), ([("x", Exception("e"))], 1)])
def test_main_exit_code(monkeypatch, tmp_path, failed, exit_code):
    received = {}

    def fake_walk(client, folder_id, local_dir, stats, dry_run):
        received.update(host=client.base, folder_id=folder_id, local_dir=local_dir, dry_run=dry_run)
        stats.failed.extend(failed)

    monkeypatch.setenv("MISSKEY_TOKEN", "TOKEN")
    monkeypatch.setattr(mdd.sys, "argv", ["prog", "--host", "example.test", "-o", str(tmp_path), "--dry-run"])
    monkeypatch.setattr(mdd, "walk", fake_walk)

    with pytest.raises(SystemExit) as exc:
        mdd.main()

    assert exc.value.code == exit_code
    assert received == {
        "host": "https://example.test/api",
        "folder_id": None,
        "local_dir": tmp_path,
        "dry_run": True,
    }
