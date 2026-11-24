"""Scoring album faces against reference embeddings."""

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np

from .flickr import Photo


@dataclass
class Result:
    photo: Photo
    score: float
    kind: Literal["match", "maybe"]


def best_score(faces: list[np.ndarray], refs: list[np.ndarray]) -> float:
    if not faces or not refs:
        return 0.0
    return float((np.stack(faces) @ np.stack(refs).T).max())


def classify(
    all_faces: dict[str, list[np.ndarray]],
    refs: list[np.ndarray],
    photos: Callable[[str], Photo],
    match_t: float,
    maybe_t: float,
) -> list[Result]:
    results = []
    for pid, faces in all_faces.items():
        score = best_score(faces, refs)
        if score >= match_t:
            results.append(Result(photos(pid), score, "match"))
        elif score >= maybe_t:
            results.append(Result(photos(pid), score, "maybe"))
    return sorted(results, key=lambda r: r.score, reverse=True)
