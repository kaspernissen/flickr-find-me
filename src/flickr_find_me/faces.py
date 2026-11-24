"""Face detection and embedding with InsightFace."""

from dataclasses import dataclass

import numpy as np


@dataclass
class Face:
    bbox: tuple[float, float, float, float]
    embedding: np.ndarray  # L2-normalised float32, length 512
