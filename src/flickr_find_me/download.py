"""Image download with retry, size cap and atomic write."""

import time
from pathlib import Path

import httpx

MAX_BYTES = 100 * 1024 * 1024  # far above any Flickr original


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


def _retryable(e: Exception) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        return code == 429 or code >= 500
    return isinstance(e, httpx.TransportError)


def download(
    url: str, dest: Path, client: httpx.Client, retries: int = 3, max_bytes: int = MAX_BYTES
) -> Path:
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                size = 0
                with part.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise DownloadError(f"{url}: too large (over {max_bytes:,} bytes)")
                        f.write(chunk)
            part.replace(dest)
            return dest
        except DownloadError:
            part.unlink(missing_ok=True)
            raise
        except httpx.HTTPError as e:
            part.unlink(missing_ok=True)
            if not _retryable(e) or attempt == retries - 1:
                raise DownloadError(f"{url}: {e}") from e
            time.sleep(0.5 * 2**attempt)
    raise AssertionError("unreachable")
