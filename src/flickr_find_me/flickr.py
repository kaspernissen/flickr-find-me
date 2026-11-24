"""Flickr access via gallery-dl (no API key of our own needed)."""

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

_FLICKR_HOSTS = {"flickr.com", "www.flickr.com"}
_USER_RE = re.compile(r"^[A-Za-z0-9@_.-]{1,64}$")
_ID_RE = re.compile(r"^\d{1,25}$")


@dataclass(frozen=True)
class Photo:
    id: str
    title: str
    page_url: str
    scan_url: str


@dataclass(frozen=True)
class Album:
    title: str
    photos: list[Photo]


@dataclass(frozen=True)
class AlbumRef:
    user: str
    id: str

    @property
    def url(self) -> str:
        return f"https://www.flickr.com/photos/{self.user}/albums/{self.id}"


def parse_album_url(album_url: str) -> AlbumRef:
    """Strictly parse a public Flickr album link. Raises ValueError otherwise."""
    bad = ValueError(
        f"Not a Flickr album link: {album_url!r}. "
        "Expected https://www.flickr.com/photos/<user>/albums/<album-id>"
    )
    try:
        parts = urlsplit(album_url.strip())
    except ValueError:
        raise bad from None
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in _FLICKR_HOSTS:
        raise bad
    segs = [s for s in parts.path.split("/") if s]
    if (
        len(segs) < 4
        or segs[0] != "photos"
        or segs[2] not in ("albums", "sets")
        or not _USER_RE.match(segs[1])
        or not _ID_RE.match(segs[3])
    ):
        raise bad
    return AlbumRef(user=segs[1], id=segs[3])


def album_id(album_url: str) -> str:
    return parse_album_url(album_url).id


def is_flickr_image_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and host.endswith(".staticflickr.com")


def parse_listing(entries: list) -> list[Photo]:
    photos = []
    for entry in entries:
        if entry[0] == -1:  # gallery-dl reports extractor errors in-band, exit code 0
            err = entry[1]
            raise RuntimeError(f"gallery-dl: {err.get('error')}: {err.get('message')}")
        if entry[0] != 3:
            continue
        _, url, meta = entry
        if meta.get("media", "photo") != "photo" or not is_flickr_image_url(url):
            continue
        pid = str(meta["id"])
        nsid = meta["owner"]["nsid"]
        if not _ID_RE.match(pid) or not _USER_RE.match(nsid):
            continue
        photos.append(
            Photo(
                id=pid,
                title=meta.get("title") or "",
                page_url=f"https://www.flickr.com/photos/{nsid}/{pid}/",
                scan_url=url,
            )
        )
    return photos


def album_title(entries: list) -> str:
    for entry in entries:
        if entry[0] in (2, 3):
            meta = entry[-1]
            title = meta.get("album", {}).get("title")
            if title:
                return title
    return ""


def _gallery_dl_json(args: list[str]) -> list:
    proc = subprocess.run(
        [sys.executable, "-m", "gallery_dl", "-j", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gallery-dl failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def list_album(album_url: str, size: int) -> Album:
    entries = _gallery_dl_json(["-o", f"size-max={int(size)}", "--", album_url])
    return Album(album_title(entries), parse_listing(entries))


def original_url(page_url: str) -> str:
    for entry in _gallery_dl_json(["--", page_url]):
        if entry[0] == -1:
            raise RuntimeError(f"gallery-dl: {entry[1].get('message')}")
        if entry[0] == 3 and is_flickr_image_url(entry[1]):
            return entry[1]
    raise RuntimeError(f"No image found at {page_url}")
