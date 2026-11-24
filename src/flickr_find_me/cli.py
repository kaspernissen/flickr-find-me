"""flickr-find-me: find photos of yourself in a Flickr album."""

import argparse
import re
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import httpx
from tqdm import tqdm

from .cache import Cache
from .download import DownloadError, download, make_client
from .faces import FaceEngine, NoFaceError, UnreadableImageError
from .flickr import Photo, list_album, original_url, parse_album_url
from .match import best_score, classify
from .report import render


def original_filename(photo: Photo, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._+-]", "_", photo.title)[:150]
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
    except Exception as e:  # one bad original must not abort the run or the report
        print(f"Could not download the original of {photo.title or photo.id}: {e}", file=sys.stderr)
        return None


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _bounded(kind, lo, hi):
    def parse(text: str):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a valid number") from None
        if not (lo <= value <= hi):  # also rejects NaN
            raise argparse.ArgumentTypeError(f"must be between {lo} and {hi}")
        return value

    return parse


def _photo_id(text: str) -> str:
    if not re.fullmatch(r"\d{1,25}", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a Flickr photo id (digits only)")
    return text


def _check_reference_images(paths: list[Path]) -> str | None:
    """Return an error message for the first unusable reference image, if any."""
    for p in paths:
        if not p.is_file():
            return f"Photo not found: {p}"
        if p.suffix.lower() not in IMAGE_SUFFIXES:
            return f"Not a supported image (.jpg, .jpeg, .png, .webp): {p}"
    return None


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else plural or word + 's'}"


def _reference_images(given: list[Path]) -> list[Path]:
    if given:
        return given
    return sorted(p for p in Path.cwd().iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def _scan(cache: Cache, engine, scans: Path, client, refs, match_t: float,
          workers: int, keep: bool, limit: int | None) -> int:
    """Scan pending photos. Returns the number that failed."""
    todo = cache.pending()
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        return 0
    failed = found = 0
    window = workers * 2  # bound how many scan images sit on disk at once
    # The match count lives in `desc` so tqdm doesn't add its ", " postfix separator.
    bar = tqdm(
        total=len(todo), desc="0 matches", unit="photo", dynamic_ncols=True,
        bar_format="Scanning {bar} {n_fmt}/{total_fmt}  {elapsed}<{remaining} · {desc}",
    )
    with bar, ThreadPoolExecutor(workers) as pool:
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
            path = scans / f"{photo.id}.jpg"
            try:
                fut.result()
                faces = engine.detect(path)
            except Exception:  # mark this photo failed (retried next run), keep going
                cache.mark_failed(photo.id)
                failed += 1
                faces = None
            finally:
                if not keep:
                    path.unlink(missing_ok=True)
            if faces is not None:
                cache.save_faces(photo.id, faces)
                if best_score([f.embedding for f in faces], refs) >= match_t:
                    found += 1
                    bar.set_description_str(_plural(found, "match", "matches"), refresh=False)
            bar.update(1)
    return failed


def _summary(results, out: Path, matches: Path, report: Path, failed: int) -> None:
    hits = [r for r in results if r.kind == "match"]
    maybes = len(results) - len(hits)
    print()
    if hits:
        extra = f" (+{maybes} {'maybe' if maybes == 1 else 'maybes'})" if maybes else ""
        print(f"Found you in {_plural(len(hits), 'photo')}{extra}")
        for r in hits[:3]:
            print(f"  {r.score:.2f}  {r.photo.title or r.photo.id}")
        if len(hits) > 3:
            print(f"  … {len(hits) - 3} more")
    elif maybes:
        print(f"No sure matches, but {_plural(maybes, 'possible match', 'possible matches')}. Check the results page.")
    else:
        print("No photos of you found.")
    print()
    n_files = sum(1 for p in matches.iterdir() if p.suffix != ".part") if matches.exists() else 0
    if n_files:
        print(f"Originals: {matches}/  ({_plural(n_files, 'file')})")
    print(f"Results:   {report}")
    if failed:
        print(f"{_plural(failed, 'photo')} failed to download. Run again to retry them.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="flickr-find-me",
        description="Find yourself in a Flickr album and download the originals.",
    )
    ap.add_argument("album_url", help="public Flickr album link")
    ap.add_argument("images", nargs="*", type=Path,
                    help="photos of you (default: all images in the current folder)")
    ap.add_argument("--me", nargs="+", type=Path, default=[], help=argparse.SUPPRESS)
    ap.add_argument("--size", type=_bounded(int, 100, 4096), default=1024,
                    help="scan image size in px (default 1024)")
    ap.add_argument("--match", type=_bounded(float, 0.0, 1.0), default=0.45,
                    help="match threshold, 0–1 (default 0.45)")
    ap.add_argument("--maybe", type=_bounded(float, 0.0, 1.0), default=0.32,
                    help="maybe threshold, 0–1 (default 0.32)")
    ap.add_argument("--out", type=Path, help="output dir (default runs/<album-id>)")
    ap.add_argument("--keep-downloads", action="store_true", help="keep scan images")
    ap.add_argument("--fetch", nargs="+", metavar="ID", type=_photo_id,
                    help="download originals of these photo ids")
    ap.add_argument("--workers", type=_bounded(int, 1, 32), default=8)
    ap.add_argument("--limit", type=_bounded(int, 1, 10**9), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.maybe > args.match:
        ap.error("--maybe must not be higher than --match")

    try:
        ref = parse_album_url(args.album_url)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    aid = ref.id
    ref_paths = _reference_images(args.images + args.me)
    if not ref_paths:
        print(
            f"No photos of you found in {Path.cwd()}. Put a few .jpg or .png photos of "
            "yourself there, or list them after the album link.",
            file=sys.stderr,
        )
        return 2
    if problem := _check_reference_images(ref_paths):
        print(problem, file=sys.stderr)
        return 2

    out = args.out or Path("runs") / aid
    scans, matches = out / "scans", out / "matches"
    scans.mkdir(parents=True, exist_ok=True)
    matches.mkdir(parents=True, exist_ok=True)
    cache = Cache(out / "cache.sqlite")

    def load_refs():
        engine = FaceEngine()
        return engine, [engine.reference(p) for p in ref_paths]

    failed = 0
    with make_client() as client:
        if args.fetch:
            title = cache.get_meta("album_title") or f"Flickr album {aid}"
            try:
                engine, refs = load_refs()
            except (NoFaceError, UnreadableImageError) as e:
                print(e, file=sys.stderr)
                return 2
            for pid in args.fetch:
                try:
                    photo = cache.photo(pid)
                except KeyError:
                    print(f"Unknown photo id {pid}", file=sys.stderr)
                    continue
                _fetch_original(photo, matches, client)
        else:
            try:
                album = list_album(ref.url, args.size)
            except RuntimeError as e:
                print(f"Could not list album: {e}", file=sys.stderr)
                return 2
            if not album.photos:
                print("The album has no photos (or is not public).", file=sys.stderr)
                return 2
            try:
                engine, refs = load_refs()
            except (NoFaceError, UnreadableImageError) as e:
                print(e, file=sys.stderr)
                return 2
            title = album.title or f"Flickr album {aid}"
            cache.set_meta("album_title", title)
            cache.upsert_photos(album.photos)
            already = cache.counts().get("done", 0)

            print(f"flickr-find-me · {title}")
            print(f"✓ {_plural(len(refs), 'reference photo')}")
            scanned = f" · {already:,} already scanned" if already else ""
            print(f"✓ {_plural(len(album.photos), 'photo')} in album{scanned}")
            try:
                failed = _scan(cache, engine, scans, client, refs, args.match,
                               args.workers, args.keep_downloads, args.limit)
            except KeyboardInterrupt:
                print("\nStopped. Run the same command again to carry on.", file=sys.stderr)
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
    render(results, report, title, matches, originals)
    _summary(results, out, matches, report, failed)
    return 0
