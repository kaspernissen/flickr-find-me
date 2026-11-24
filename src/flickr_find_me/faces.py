"""Face detection and embedding with InsightFace."""

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Face:
    bbox: tuple[float, float, float, float]
    embedding: np.ndarray  # L2-normalised float32, length 512


class NoFaceError(Exception):
    def __init__(self, path: Path):
        super().__init__(f"No face found in {path}")
        self.path = path


class UnreadableImageError(Exception):
    def __init__(self, path: Path):
        super().__init__(f"Cannot read image {path}")
        self.path = path


class FaceEngine:
    def __init__(self) -> None:
        from insightface.app import FaceAnalysis

        root = os.environ.get("FLICKR_FIND_ME_MODELS", "~/.insightface")
        self._app = FaceAnalysis(name="buffalo_l", root=root, providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1, det_size=(640, 640))

    def detect(self, image_path: Path) -> list[Face]:
        import cv2

        img = cv2.imread(str(image_path))
        if img is None:
            raise UnreadableImageError(image_path)
        return [
            Face(
                bbox=tuple(float(v) for v in f.bbox),
                embedding=np.asarray(f.normed_embedding, dtype=np.float32),
            )
            for f in self._app.get(img)
        ]

    def reference(self, image_path: Path) -> np.ndarray:
        faces = self.detect(image_path)
        if not faces:
            raise NoFaceError(image_path)

        def area(f: Face) -> float:
            x1, y1, x2, y2 = f.bbox
            return (x2 - x1) * (y2 - y1)

        return max(faces, key=area).embedding
