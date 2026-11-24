import json
from pathlib import Path

import pytest

from flickr_find_me.flickr import album_id, list_album, parse_listing

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
    assert len(list_album(KUBECON, 1024)) == 3537
