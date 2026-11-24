import numpy as np

from flickr_find_me.flickr import Photo
from flickr_find_me.match import best_score, classify


def unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_best_score_empty_is_zero():
    assert best_score([], [unit(1, 0)]) == 0.0


def test_best_score_takes_max_over_refs():
    faces = [unit(1, 0), unit(0, 1)]
    refs = [unit(1, 1), unit(1, 0)]
    assert abs(best_score(faces, refs) - 1.0) < 1e-6


def test_classify_thresholds():
    ref = unit(1, 0)
    # cos(theta) = score for a unit vector at angle theta from ref
    def at(score):
        return np.array([score, np.sqrt(1 - score**2)], dtype=np.float32)

    faces = {"a": [at(0.4)], "b": [at(0.6)], "c": [at(0.2)], "d": []}
    results = classify(faces, [ref], lambda pid: Photo(pid, pid, "p", "s"), 0.45, 0.32)
    assert [(r.photo.id, r.kind) for r in results] == [("b", "match"), ("a", "maybe")]
    assert abs(results[0].score - 0.6) < 1e-5
