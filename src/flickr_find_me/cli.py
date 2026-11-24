"""flickr-find-me: find photos of yourself in a Flickr album."""

import argparse
import re
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import httpx

from .cache import Cache
from .download import DownloadError, download
from .faces import FaceEngine, NoFaceError
from .flickr import Photo, album_id, list_album, original_url
from .match import classify
from .report import render


def original_filename(photo: Photo, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._+-]", "_", photo.title)
    return f"{stem}_{photo.id}.{ext}" if stem else f"{photo.id}.{ext}"


def _existing_original(matches: Path, photo_id: str) -> Path | None:
    for pattern in (f"*_{photo_id}.*", f"{photo_id}.*"):
        for p in sorted(matches.glob(pattern)):
            if p.suffix != ".part":
                return p
    return None


def _fetch_original(photo: Photo, matches: Path, client: httpx.Client) -> Path | None:
    existing = _existing_original(matches, photo.id)
    if existing:
        return existing
    try:
        url = original_url(photo.page_url)
        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        return download(url, matches / original_filename(photo, ext), client)
    except (DownloadError, RuntimeError) as e:
        print(f"warning: could not fetch original of {photo.id}: {e}", file=sys.stderr)
        return None


def _scan(cache: Cache, engine, scans: Path, client, workers: int, keep: bool, limit: int | None) -> None:
    todo = cache.pending()
    if limit is not None:
        todo = todo[:limit]
    total, done = len(todo), 0
    print(f"Scanning {total} photos…")
    window = workers * 2  # bound how many scan images sit on disk at once
    with ThreadPoolExecutor(workers) as pool:
        it = iter(todo)
        inflight: list[tuple[Photo, Future]] = []

        def submit_next() -> None:
            p = next(it, None)
            if p is not None:
                inflight.append((p, pool.submit(download, p.scan_url, scans / f"{p.id}.jpg", client)))

        for _ in range(window):
            submit_next()
        while inflight:
            photo, fut = inflight.pop(0)
            submit_next()
            try:
                path = fut.result()
            except DownloadError as e:
                print(f"warning: {e}", file=sys.stderr)
                cache.mark_failed(photo.id)
                continue
            cache.save_faces(photo.id, engine.detect(path))
            if not keep:
                path.unlink(missing_ok=True)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{total}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flickr-find-me", description=__doc__)
    ap.add_argument("album_url")
    ap.add_argument("--me", nargs="+", required=True, type=Path, help="reference photos of you")
    ap.add_argument("--size", type=int, default=1024, help="scan image size in px (default 1024)")
    ap.add_argument("--match", type=float, default=0.45, help="match threshold (default 0.45)")
    ap.add_argument("--maybe", type=float, default=0.32, help="maybe threshold (default 0.32)")
    ap.add_argument("--out", type=Path, help="output dir (default runs/<album-id>)")
    ap.add_argument("--keep-downloads", action="store_true", help="keep scan images")
    ap.add_argument("--fetch", nargs="+", metavar="ID", help="download originals of these photo ids")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    try:
        aid = album_id(args.album_url)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    out = args.out or Path("runs") / aid
    scans, matches = out / "scans", out / "matches"
    scans.mkdir(parents=True, exist_ok=True)
    matches.mkdir(parents=True, exist_ok=True)

    engine = FaceEngine()
    try:
        refs = [engine.reference(p) for p in args.me]
    except NoFaceError as e:
        print(e, file=sys.stderr)
        return 2

    cache = Cache(out / "cache.sqlite")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        if args.fetch:
            for pid in args.fetch:
                try:
                    photo = cache.photo(pid)
                except KeyError:
                    print(f"warning: unknown photo id {pid}", file=sys.stderr)
                    continue
                _fetch_original(photo, matches, client)
        else:
            cache.upsert_photos(list_album(args.album_url, args.size))
            try:
                _scan(cache, engine, scans, client, args.workers, args.keep_downloads, args.limit)
            except KeyboardInterrupt:
                print("\nInterrupted — re-run to resume", file=sys.stderr)
                return 130

        results = classify(cache.all_faces(), refs, cache.photo, args.match, args.maybe)
        if not args.fetch:
            for r in results:
                if r.kind == "match":
                    _fetch_original(r.photo, matches, client)

    originals = {}
    for r in results:
        found = _existing_original(matches, r.photo.id)
        if found:
            originals[r.photo.id] = found.name
    report = out / "results.html"
    render(results, report, f"Flickr album {aid}", matches, originals)

    n_match = sum(r.kind == "match" for r in results)
    print(f"{cache.counts()} · {n_match} matches, {len(results) - n_match} maybes")
    print(f"Report: {report.resolve()}")
    return 0
