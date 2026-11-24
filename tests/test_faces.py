import cv2
import numpy as np
import pytest

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def engine():
    from flickr_find_me.faces import FaceEngine

    return FaceEngine()


@pytest.fixture(scope="module")
def group_photo(tmp_path_factory):
    from insightface.data import get_image

    p = tmp_path_factory.mktemp("img") / "t1.jpg"
    cv2.imwrite(str(p), get_image("t1"))
    return p


def area(f):
    x1, y1, x2, y2 = f.bbox
    return (x2 - x1) * (y2 - y1)


def test_detect_group_photo(engine, group_photo):
    faces = engine.detect(group_photo)
    assert len(faces) >= 5
    for f in faces:
        assert f.embedding.shape == (512,)
        assert abs(np.linalg.norm(f.embedding) - 1) < 1e-3


def test_reference_no_face_raises(engine, tmp_path):
    from flickr_find_me.faces import NoFaceError

    p = tmp_path / "grey.jpg"
    cv2.imwrite(str(p), np.full((400, 400, 3), 128, np.uint8))
    with pytest.raises(NoFaceError):
        engine.reference(p)


def test_reference_picks_largest(engine, group_photo):
    largest = max(engine.detect(group_photo), key=area)
    assert np.allclose(engine.reference(group_photo), largest.embedding)


def test_same_face_scores_high(engine, group_photo, tmp_path):
    mirrored = tmp_path / "mirror.jpg"
    cv2.imwrite(str(mirrored), cv2.flip(cv2.imread(str(group_photo)), 1))
    assert float(engine.reference(group_photo) @ engine.reference(mirrored)) > 0.6


def test_unreadable_image_raises(engine, tmp_path):
    from flickr_find_me.faces import UnreadableImageError

    p = tmp_path / "junk.jpg"
    p.write_bytes(b"<html>502</html>")
    with pytest.raises(UnreadableImageError):
        engine.detect(p)


def test_engine_is_quiet(capfd, group_photo):
    import warnings

    from flickr_find_me.faces import FaceEngine

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        FaceEngine().detect(group_photo)
    out, err = capfd.readouterr()
    assert out == "" and err == ""
    assert not [w for w in caught if issubclass(w.category, FutureWarning)]
