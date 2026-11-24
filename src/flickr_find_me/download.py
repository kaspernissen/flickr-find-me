"""Image download with retry and atomic write."""

import time
from pathlib import Path

import httpx


class DownloadError(Exception):
    pass


def make_client() -> httpx.Client:
    # Flickr's image CDN answers httpx's default client with 502s; a client
    # that names itself is served normally.
    return httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "flickr-find-me/0.1"},
    )


def download(url: str, dest: Path, client: httpx.Client, retries: int = 3) -> Path:
    part = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            part.write_bytes(resp.content)
            part.replace(dest)
            return dest
        except httpx.HTTPError as e:
            last = e
            if attempt < retries - 1:
                time.sleep(0.5 * 2**attempt)
    part.unlink(missing_ok=True)
    raise DownloadError(f"{url}: {last}")
