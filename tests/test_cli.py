import numpy as np
import pytest

from flickr_find_me import cli
from flickr_find_me.download import DownloadError
from flickr_find_me.faces import Face, NoFaceError
from flickr_find_me.flickr import Photo

ALBUM = "https://www.flickr.com/photos/o/albums/42"
ME = np.array([1, 0], dtype=np.float32)
STRANGER = np.array([0, 1], dtype=np.float32)
FACES = {"1": [ME, STRANGER], "2": [STRANGER], "3": []}


class FakeEngine:
    def detect(self, path):
        return [Face((0, 0, 1, 1), e) for e in FACES[path.stem]]

    def reference(self, path):
        if "noface" in path.name:
            raise NoFaceError(path)
        return ME


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = {"scan": [], "orig": []}
    fail_once = set()

    def fake_download(url, dest, client, retries=3):
        kind = "orig" if url.startswith("orig:") else "scan"
        calls[kind].append(url)
        if url in fail_once:
            fail_once.discard(url)
            raise DownloadError(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest

    photos = [Photo(i, f"title {i}", f"https://flickr/p/{i}/", f"scan:{i}") for i in "123"]
    monkeypatch.setattr(cli, "list_album", lambda url, size: photos)
    monkeypatch.setattr(cli, "original_url", lambda page: f"orig:{page}x.jpg")
    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "FaceEngine", FakeEngine)
    ref = tmp_path / "me.jpg"
    ref.write_bytes(b"x")
    out = tmp_path / "run"
    args = [ALBUM, "--me", str(ref), "--out", str(out)]
    return args, out, calls, fail_once


def test_end_to_end_with_fakes(env):
    args, out, calls, _ = env
    assert cli.main(args) == 0
    assert [p.name for p in (out / "matches").iterdir()] == ["title_1_1.jpg"]
    assert (out / "results.html").exists()
    assert cli.Cache(out / "cache.sqlite").counts() == {"done": 3}
    assert list((out / "scans").iterdir()) == []


def test_keep_downloads(env):
    args, out, _, _ = env
    cli.main(args + ["--keep-downloads"])
    assert len(list((out / "scans").iterdir())) == 3


def test_resume_skips_done(env):
    args, _, calls, _ = env
    cli.main(args)
    cli.main(args)
    assert len(calls["scan"]) == 3
    assert len(calls["orig"]) == 1  # original not re-downloaded either


def test_failed_download_continues(env):
    args, out, calls, fail_once = env
    fail_once.add("scan:2")
    assert cli.main(args) == 0
    cache = cli.Cache(out / "cache.sqlite")
    assert cache.counts() == {"done": 2, "failed": 1}
    calls["scan"].clear()
    cli.main(args)
    assert calls["scan"] == ["scan:2"]


def test_reference_without_face_exits_2(env, tmp_path, capsys):
    args, *_ = env
    bad = tmp_path / "noface.jpg"
    bad.write_bytes(b"x")
    args[2] = str(bad)
    assert cli.main(args) == 2
    assert "No face found in" in capsys.readouterr().err


def test_original_filename_sanitized():
    assert cli.original_filename(Photo("9", "a/b c", "", ""), "jpg") == "a_b_c_9.jpg"
    assert cli.original_filename(Photo("9", "", "", ""), "jpg") == "9.jpg"
    assert cli.original_filename(Photo("9", "../x", "", ""), "jpg") == ".._x_9.jpg"


def test_fetch_downloads_given_ids(env):
    args, out, calls, _ = env
    cli.main(args)
    calls["scan"].clear()
    assert cli.main(args + ["--fetch", "2"]) == 0
    assert calls["scan"] == []
    assert (out / "matches" / "title_2_2.jpg").exists()


def test_limit_processes_first_n(env):
    args, out, calls, _ = env
    cli.main(args + ["--limit", "2"])
    assert len(calls["scan"]) == 2


def test_partial_original_is_not_treated_as_existing(env):
    args, out, calls, _ = env
    (out / "matches").mkdir(parents=True)
    (out / "matches" / "title_1_1.jpg.part").write_bytes(b"half")
    cli.main(args)
    assert len(calls["orig"]) == 1
    assert (out / "matches" / "title_1_1.jpg").exists()
