import json
from pathlib import Path

import pytest

from flickr_find_me import flickr
from flickr_find_me.flickr import album_id, album_title, list_album, parse_album_url, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "gallery_dl_album.json"
KUBECON = "https://www.flickr.com/photos/143247548@N03/albums/72177720336408231"


@pytest.fixture
def fixture_entries():
    return json.loads(FIXTURE.read_text())


def test_parse_listing_keeps_photos_only(fixture_entries):
    photos = parse_listing(fixture_entries)
    assert [p.id for p in photos] == ["55649818708", "55650110745"]
    assert photos[0].title == "KC+CNC_NA_2026_TOP12_001"
    assert photos[0].page_url == "https://www.flickr.com/photos/143247548@N03/55649818708/"
    assert photos[0].scan_url.endswith("_b.jpg")


def test_album_id():
    assert album_id(KUBECON) == "72177720336408231"
    assert album_id("https://www.flickr.com/photos/x/albums/123/") == "123"


def test_album_id_rejects_non_album():
    with pytest.raises(ValueError):
        album_id("https://www.flickr.com/photos/143247548@N03/55649818708/")


@pytest.mark.network
def test_list_album_real():
    album = list_album(KUBECON, 1024)
    assert len(album.photos) == 3537
    assert album.title == "KubeCon + CloudNativeCon North America 2026"


def test_parse_listing_raises_on_gallery_dl_error():
    entries = [[-1, {"error": "NotFoundError", "message": "Requested album could not be found"}]]
    with pytest.raises(RuntimeError, match="Requested album could not be found"):
        parse_listing(entries)


def test_album_title(fixture_entries):
    assert album_title(fixture_entries) == "KubeCon + CloudNativeCon North America 2026"
    assert album_title([]) == ""


@pytest.mark.parametrize("url", [
    KUBECON,
    KUBECON + "/",
    KUBECON + "?foo=1",
    KUBECON + "/with/55656716269",
    "http://flickr.com/photos/143247548@N03/sets/72177720336408231",
    "  " + KUBECON + "  ",
])
def test_parse_album_url_canonicalizes(url):
    ref = parse_album_url(url)
    assert ref.id == "72177720336408231"
    assert ref.url == "https://www.flickr.com/photos/143247548@N03/albums/72177720336408231"


@pytest.mark.parametrize("url", [
    "https://evil.com/?x=flickr.com/photos/a/albums/1",
    "https://flickr.com.evil.com/photos/a/albums/1",
    "--exec=rm https://www.flickr.com/photos/a/albums/1",
    "ftp://www.flickr.com/photos/a/albums/1",
    "https://www.flickr.com/photos/a/albums/abc",
    "https://www.flickr.com/photos/a b/albums/1",
    "https://www.flickr.com/photos/a/55649818708/",
    "",
])
def test_parse_album_url_rejects(url):
    with pytest.raises(ValueError):
        parse_album_url(url)


def test_gallery_dl_gets_url_after_double_dash(monkeypatch):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, "[]", ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Proc()

    monkeypatch.setattr(flickr.subprocess, "run", fake_run)
    list_album(KUBECON, 1024)
    assert seen["cmd"][-2:] == ["--", KUBECON]


def test_parse_listing_skips_non_flickr_image_urls(fixture_entries):
    fixture_entries[1][1] = "https://evil.example/x.jpg"
    assert [p.id for p in parse_listing(fixture_entries)] == ["55650110745"]


@pytest.mark.parametrize("url,ok", [
    ("https://live.staticflickr.com/65535/1_a_b.jpg", True),
    ("https://farm66.staticflickr.com/1_a_o.jpg", True),
    ("http://live.staticflickr.com/1.jpg", False),
    ("https://staticflickr.com.evil.com/1.jpg", False),
    ("https://evil.com/staticflickr.com/1.jpg", False),
])
def test_is_flickr_image_url(url, ok):
    assert flickr.is_flickr_image_url(url) is ok
