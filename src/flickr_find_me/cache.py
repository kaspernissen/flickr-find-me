"""SQLite cache of album photos and their face embeddings."""

import json
import sqlite3
from pathlib import Path

import numpy as np

from .faces import Face
from .flickr import Photo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY, title TEXT, page_url TEXT, scan_url TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS faces (
    photo_id TEXT, idx INTEGER, bbox TEXT, embedding BLOB,
    PRIMARY KEY (photo_id, idx)
);
"""


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)

    def upsert_photos(self, photos: list[Photo]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO photos VALUES (?, ?, ?, ?, 'pending') "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                "page_url=excluded.page_url, scan_url=excluded.scan_url",
                [(p.id, p.title, p.page_url, p.scan_url) for p in photos],
            )

    def pending(self) -> list[Photo]:
        rows = self.conn.execute(
            "SELECT id, title, page_url, scan_url FROM photos "
            "WHERE status IN ('pending', 'failed') ORDER BY id"
        )
        return [Photo(*r) for r in rows]

    def save_faces(self, photo_id: str, faces: list[Face]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM faces WHERE photo_id = ?", (photo_id,))
            for i, f in enumerate(faces):
                self.conn.execute(
                    "INSERT INTO faces VALUES (?, ?, ?, ?)",
                    (
                        photo_id,
                        i,
                        json.dumps([float(x) for x in f.bbox]),
                        f.embedding.astype(np.float32).tobytes(),
                    ),
                )
            self.conn.execute("UPDATE photos SET status = 'done' WHERE id = ?", (photo_id,))

    def mark_failed(self, photo_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE photos SET status = 'failed' WHERE id = ?", (photo_id,))

    def all_faces(self) -> dict[str, list[np.ndarray]]:
        out: dict[str, list[np.ndarray]] = {
            r[0]: [] for r in self.conn.execute("SELECT id FROM photos WHERE status = 'done'")
        }
        for pid, blob in self.conn.execute(
            "SELECT f.photo_id, f.embedding FROM faces f JOIN photos p ON p.id = f.photo_id "
            "WHERE p.status = 'done' ORDER BY f.photo_id, f.idx"
        ):
            out[pid].append(np.frombuffer(blob, dtype=np.float32))
        return out

    def photo(self, photo_id: str) -> Photo:
        row = self.conn.execute(
            "SELECT id, title, page_url, scan_url FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if row is None:
            raise KeyError(photo_id)
        return Photo(*row)

    def counts(self) -> dict[str, int]:
        return dict(self.conn.execute("SELECT status, COUNT(*) FROM photos GROUP BY status"))
