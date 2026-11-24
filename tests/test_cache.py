import numpy as np
import pytest

from flickr_find_me.cache import Cache
from flickr_find_me.faces import Face
from flickr_find_me.flickr import Photo


def photo(pid):
    return Photo(pid, f"t{pid}", f"https://flickr/p/{pid}/", f"https://img/{pid}_b.jpg")


def face(vec):
    return Face(bbox=(0.0, 0.0, 10.0, 10.0), embedding=np.asarray(vec, dtype=np.float32))


@pytest.fixture
def cache(tmp_path):
    return Cache(tmp_path / "cache.sqlite")


def test_upsert_is_idempotent_and_preserves_status(cache):
    cache.upsert_photos([photo("1"), photo("2")])
    cache.save_faces("1", [])
    cache.upsert_photos([photo("1"), photo("2")])
    assert cache.counts() == {"done": 1, "pending": 1}


def test_pending_includes_failed(cache):
    cache.upsert_photos([photo("1"), photo("2"), photo("3")])
    cache.mark_failed("1")
    cache.save_faces("2", [])
    assert sorted(p.id for p in cache.pending()) == ["1", "3"]


def test_embeddings_roundtrip(cache):
    vec = np.random.default_rng(0).standard_normal(512).astype(np.float32)
    cache.upsert_photos([photo("1")])
    cache.save_faces("1", [face(vec)])
    got = cache.all_faces()["1"]
    assert len(got) == 1 and np.allclose(got[0], vec)


def test_zero_face_photo_is_done(cache):
    cache.upsert_photos([photo("1")])
    cache.save_faces("1", [])
    assert cache.pending() == []
    assert cache.all_faces() == {"1": []}


def test_save_faces_atomic(cache):
    cache.upsert_photos([photo("1")])
    broken = Face(bbox=(0, 0, 1, 1), embedding=None)
    with pytest.raises(Exception):
        cache.save_faces("1", [face(np.ones(512)), broken])
    assert [p.id for p in cache.pending()] == ["1"]
    assert cache.all_faces() == {}


def test_photo_lookup(cache):
    cache.upsert_photos([photo("7")])
    assert cache.photo("7") == photo("7")
