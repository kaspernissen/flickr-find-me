import numpy as np
import pytest

from flickr_find_me import cli
from flickr_find_me.download import DownloadError
from flickr_find_me.faces import Face, NoFaceError
from flickr_find_me.flickr import Album, Photo

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
    monkeypatch.setattr(cli, "list_album", lambda url, size: Album("Test Album", photos))
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


def test_empty_album_exits_2(env, monkeypatch, capsys):
    args, *_ = env
    monkeypatch.setattr(cli, "list_album", lambda url, size: Album("Empty", []))
    assert cli.main(args) == 2
    assert "no photos" in capsys.readouterr().err.lower()


def test_listing_error_exits_2(env, monkeypatch, capsys):
    args, *_ = env

    def boom(url, size):
        raise RuntimeError("gallery-dl: Requested album could not be found")

    monkeypatch.setattr(cli, "list_album", boom)
    assert cli.main(args) == 2
    assert "could not be found" in capsys.readouterr().err


def test_detect_error_marks_failed_and_continues(env, monkeypatch):
    args, out, _, _ = env

    class Flaky(FakeEngine):
        def detect(self, path):
            if path.stem == "2":
                raise ValueError("corrupt image")
            return super().detect(path)

    monkeypatch.setattr(cli, "FaceEngine", Flaky)
    assert cli.main(args) == 0
    assert cli.Cache(out / "cache.sqlite").counts() == {"done": 2, "failed": 1}
    assert (out / "results.html").exists()


def test_original_error_does_not_abort(env, monkeypatch):
    args, out, _, _ = env

    def bad(page):
        raise OSError("File name too long")

    monkeypatch.setattr(cli, "original_url", bad)
    assert cli.main(args) == 0
    assert (out / "results.html").exists()


def test_original_filename_truncates_long_titles():
    name = cli.original_filename(Photo("55649818708", "x" * 400, "", ""), "jpg")
    assert len(name.encode()) <= 200
    assert name.endswith("_55649818708.jpg")


def test_positional_images(env):
    args, out, _, _ = env
    assert cli.main([ALBUM, args[2], "--out", str(out)]) == 0
    assert (out / "results.html").exists()


def test_default_uses_images_in_current_folder(env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # contains me.jpg
    assert cli.main([ALBUM]) == 0
    assert (tmp_path / "runs" / "42" / "results.html").exists()


def test_no_images_exits_2(env, tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert cli.main([ALBUM]) == 2
    assert "No photos of you" in capsys.readouterr().err


def test_summary_output(env, capsys):
    args, *_ = env
    cli.main(args)
    out, err = capsys.readouterr()
    assert "Test Album" in out
    assert "Found you in 1 photo" in out
    assert "title 1" in out
    assert "Results:" in out
    assert "warning" not in err.lower()
    assert "{" not in out  # no raw dicts


def test_failed_download_reported_once(env, capsys):
    args, _, _, fail_once = env
    fail_once.add("scan:2")
    cli.main(args)
    out = capsys.readouterr().out
    assert "1 photo failed to download" in out


def test_report_uses_album_title(env):
    args, out, _, _ = env
    cli.main(args)
    assert "Test Album" in (out / "results.html").read_text()


@pytest.fixture
def no_network_or_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should have failed before this")

    monkeypatch.setattr(cli, "list_album", boom)
    monkeypatch.setattr(cli, "FaceEngine", boom)


def test_bad_album_url_fails_fast(no_network_or_model, capsys):
    assert cli.main(["https://evil.com/?flickr.com/photos/a/albums/1", "me.jpg"]) == 2
    assert "Flickr album" in capsys.readouterr().err


def test_missing_reference_file_fails_fast(no_network_or_model, tmp_path, capsys):
    assert cli.main([ALBUM, str(tmp_path / "nope.jpg")]) == 2
    assert "nope.jpg" in capsys.readouterr().err


def test_non_image_reference_fails_fast(no_network_or_model, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("hi")
    assert cli.main([ALBUM, str(notes)]) == 2
    assert "notes.txt" in capsys.readouterr().err


@pytest.mark.parametrize("flags", [
    ["--match", "1.5"],
    ["--match", "-0.1"],
    ["--maybe", "nan"],
    ["--match", "0.3", "--maybe", "0.4"],
    ["--size", "50"],
    ["--size", "10000"],
    ["--workers", "0"],
    ["--workers", "100"],
    ["--fetch", "abc"],
    ["--fetch", "../1"],
    ["--limit", "0"],
])
def test_bad_flags_rejected(no_network_or_model, tmp_path, flags):
    me = tmp_path / "me.jpg"
    me.write_bytes(b"x")
    with pytest.raises(SystemExit) as e:
        cli.main([ALBUM, str(me), *flags])
    assert e.value.code == 2


def test_listing_error_fails_before_model_loads(env, monkeypatch):
    args, *_ = env

    def boom(url, size):
        raise RuntimeError("gallery-dl: NotFoundError: Requested album could not be found")

    def no_model():
        raise AssertionError("model loaded before album was listed")

    monkeypatch.setattr(cli, "list_album", boom)
    monkeypatch.setattr(cli, "FaceEngine", no_model)
    assert cli.main(args) == 2
