"""Flickr access via gallery-dl (no API key of our own needed)."""

import json
import re
import subprocess
import sys
from dataclasses import dataclass

_ALBUM_RE = re.compile(r"flickr\.com/photos/[^/]+/(?:albums|sets)/(\d+)")


@dataclass(frozen=True)
class Photo:
    id: str
    title: str
    page_url: str
    scan_url: str


def album_id(album_url: str) -> str:
    m = _ALBUM_RE.search(album_url)
    if not m:
        raise ValueError(f"Not a Flickr album URL: {album_url}")
    return m.group(1)


def parse_listing(entries: list) -> list[Photo]:
    photos = []
    for entry in entries:
        if entry[0] == -1:  # gallery-dl reports extractor errors in-band, exit code 0
            err = entry[1]
            raise RuntimeError(f"gallery-dl: {err.get('error')}: {err.get('message')}")
        if entry[0] != 3:
            continue
        _, url, meta = entry
        if meta.get("media", "photo") != "photo":
            continue
        pid = str(meta["id"])
        nsid = meta["owner"]["nsid"]
        photos.append(
            Photo(
                id=pid,
                title=meta.get("title") or "",
                page_url=f"https://www.flickr.com/photos/{nsid}/{pid}/",
                scan_url=url,
            )
        )
    return photos


def _gallery_dl_json(args: list[str]) -> list:
    proc = subprocess.run(
        [sys.executable, "-m", "gallery_dl", "-j", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gallery-dl failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def list_album(album_url: str, size: int) -> list[Photo]:
    return parse_listing(_gallery_dl_json(["-o", f"size-max={size}", album_url]))


def original_url(page_url: str) -> str:
    for entry in _gallery_dl_json([page_url]):
        if entry[0] == 3:
            return entry[1]
    raise RuntimeError(f"No image found at {page_url}")
