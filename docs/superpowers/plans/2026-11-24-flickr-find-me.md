# flickr-find-me Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local CLI that scans a public Flickr album for photos of me and downloads full-size originals of the matches.

**Architecture:** gallery-dl (as a subprocess with `-j`) only *lists* photos and resolves original URLs; we download images ourselves with httpx. InsightFace detects faces and produces embeddings; per-photo embeddings go in SQLite, so re-runs (new threshold, new reference photos, interrupted runs) never re-download. A static HTML report hotlinks Flickr's 1024px images, so no scan images need to stay on disk.

**Tech Stack:** Python 3.11 (managed by uv), gallery-dl, httpx, insightface + onnxruntime (CPU), numpy, opencv-python-headless, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-flickr-find-me-design.md`

## Global Constraints

- No Flickr API key; all Flickr access goes through gallery-dl (it fetches Flickr's public key itself).
- Faces never leave the machine. No cloud services.
- Default scan size 1024px (`--size`), gallery-dl option `-o size-max=<size>`.
- Scan images are deleted after processing unless `--keep-downloads`.
- Originals only for confident matches, plus `--fetch <photo-id>` on demand.
- Face model: InsightFace `buffalo_l`, `det_size=(640, 640)`, CPU provider.
- Default thresholds (cosine similarity): match `0.45`, maybe `0.32`. Both are flags.
- Output dir default `./runs/<album-id>/` containing `cache.sqlite`, `matches/`, `scans/` (temp), `results.html`.
- Commit messages: no `Co-Authored-By` or other attribution trailers.

## Verified facts (checked 2026-11-24)

- `uvx gallery-dl -j -o size-max=1024 <album-url>` lists all 3,537 photos in ~22 s. Output is a JSON array; entries with `[0] == 3` are `[3, url, meta]`. `meta` has `id` (int), `title`, `media` (`"photo"`/`"video"`), `owner.nsid`, `width`, `height`, `album.id`, `album.title`. `url` is the 1024px `_b.jpg`.
- `uvx gallery-dl -j https://www.flickr.com/photos/<nsid>/<id>/` (no size-max) returns the same shape with `label: "Original"` and the `_o.jpg` URL.
- Photo page URL: `https://www.flickr.com/photos/<nsid>/<id>/`.

## Review Focus

1. A reference photo with no detectable face → exit with a clear error naming the file. With several faces → use the largest.
2. An album photo with zero faces → recorded as processed (empty face list), never re-downloaded.
3. A single photo download failing (timeout, 404) → logged and marked `failed`, run continues, retried on next run.
4. Ctrl-C mid-scan → no half-written cache rows. Re-running resumes with unprocessed and failed photos only.
5. Original filenames from titles with `/`, spaces or duplicates → sanitized and suffixed with the photo id, so nothing collides or escapes `matches/`.

Also: `media == "video"` entries are skipped.

---

## File Structure

```
pyproject.toml
src/flickr_find_me/__init__.py
src/flickr_find_me/flickr.py     # gallery-dl wrapper: list album, resolve original URL
src/flickr_find_me/download.py   # httpx download with retry
src/flickr_find_me/cache.py      # SQLite: photos + face embeddings
src/flickr_find_me/faces.py      # InsightFace wrapper
src/flickr_find_me/match.py      # scoring + classification
src/flickr_find_me/report.py     # results.html
src/flickr_find_me/cli.py        # orchestration + argparse
tests/...
```

Shared type (in `flickr.py`):

```python
@dataclass(frozen=True)
class Photo:
    id: str          # str(meta["id"])
    title: str
    page_url: str    # https://www.flickr.com/photos/<nsid>/<id>/
    scan_url: str    # size-capped image URL
```

---

### Task 1: Project scaffold + Flickr listing

**Files:**
- Create: `pyproject.toml`, `.gitignore` (`runs/`, `.venv/`, `__pycache__/`), `src/flickr_find_me/__init__.py`, `src/flickr_find_me/flickr.py`
- Test: `tests/test_flickr.py`, `tests/fixtures/gallery_dl_album.json` (trimmed real output: 2 photos + 1 video entry + one `[2, {...}]` directory entry)

**Interfaces:**
- Produces: `Photo`; `parse_listing(entries: list) -> list[Photo]`; `list_album(album_url: str, size: int) -> list[Photo]`; `original_url(page_url: str) -> str`; `album_id(album_url: str) -> str`.

- [ ] **Step 1:** `git init`; `uv init --package --python 3.11`; add deps `gallery-dl httpx insightface onnxruntime opencv-python-headless numpy`, dev dep `pytest`. Console script `flickr-find-me = "flickr_find_me.cli:main"`.
- [ ] **Step 2: Failing tests**

```python
def test_parse_listing_keeps_photos_only(fixture_entries):
    photos = parse_listing(fixture_entries)
    assert [p.id for p in photos] == ["55649818708", "<second id>"]
    assert photos[0].title == "KC+CNC_NA_2026_TOP12_001"
    assert photos[0].page_url == "https://www.flickr.com/photos/143247548@N03/55649818708/"
    assert photos[0].scan_url.endswith("_b.jpg")

def test_album_id():
    assert album_id("https://www.flickr.com/photos/143247548@N03/albums/72177720336408231") == "72177720336408231"
    assert album_id("https://www.flickr.com/photos/x/albums/123/") == "123"

def test_album_id_rejects_non_album():
    with pytest.raises(ValueError):
        album_id("https://www.flickr.com/photos/143247548@N03/55649818708/")
```

- [ ] **Step 3:** Run `uv run pytest tests/test_flickr.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement. `list_album` runs `[sys.executable, "-m", "gallery_dl", "-j", "-o", f"size-max={size}", album_url]`, then `json.loads` stdout and `parse_listing`. On a non-zero exit, raise `RuntimeError` with stderr. `original_url` runs the same without size-max on the page URL and returns the `url` of the first `[3, ...]` entry.
- [ ] **Step 5:** Run tests. Expected: PASS. Mark a network test `@pytest.mark.network`: `list_album(<KubeCon album>, 1024)` returns 3537 photos. Run it once with `uv run pytest -m network`.
- [ ] **Step 6:** Commit `feat: list Flickr album photos via gallery-dl`.

### Task 2: Download helper

**Files:** Create `src/flickr_find_me/download.py`. Test: `tests/test_download.py`.

**Interfaces:**
- Produces: `download(url: str, dest: Path, client: httpx.Client, retries: int = 3) -> Path`. It writes to `dest.with_suffix(dest.suffix + ".part")` and then renames it, and raises `DownloadError` after the retries run out.

- [ ] **Step 1: Failing tests** (`httpx.MockTransport`):
  - `test_download_writes_file`: a 200 response with bytes `b"abc"` → `dest.read_bytes() == b"abc"`, and no `.part` file is left.
  - `test_download_retries_then_succeeds`: 500, 500, 200 → succeeds, 3 requests made.
  - `test_download_raises_after_retries`: always 404 → `DownloadError`, `dest` doesn't exist.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Back off `0.5 * 2**attempt` seconds between retries (patch `time.sleep` in tests). Use a 30 s timeout and `follow_redirects=True` on the client created in the CLI.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: download helper with retry`.

### Task 3: Cache

**Files:** Create `src/flickr_find_me/cache.py`. Test: `tests/test_cache.py`.

**Interfaces:**
- Consumes: `Photo`.
- Produces: `class Cache(path: Path)` with methods
  - `upsert_photos(photos: list[Photo]) -> None`. Inserts new photos as `status='pending'` and leaves existing statuses alone.
  - `pending() -> list[Photo]`. Status is `pending` or `failed`.
  - `save_faces(photo_id: str, faces: list[Face]) -> None`. Replaces the photo's faces and sets `status='done'` **in a single transaction**.
  - `mark_failed(photo_id: str) -> None`
  - `all_faces() -> dict[str, list[np.ndarray]]`. Covers every `done` photo, including ones with an empty list.
  - `photo(photo_id: str) -> Photo`
  - `counts() -> dict[str, int]`. Counts by status.
- Schema: `photos(id TEXT PK, title, page_url, scan_url, status)` and `faces(photo_id, idx, bbox TEXT json, embedding BLOB float32)`.

- [ ] **Step 1: Failing tests:**
  - `test_upsert_is_idempotent_and_preserves_status`: upsert, `save_faces(id, [])`, upsert again → `counts() == {"done": 1, "pending": 1}`.
  - `test_pending_includes_failed`.
  - `test_embeddings_roundtrip`: a saved 512-d float32 vector comes back from `all_faces()` with `np.allclose`.
  - `test_zero_face_photo_is_done` (Review Focus 2): `save_faces(id, [])` → not in `pending()`, and `all_faces()[id] == []`.
  - `test_save_faces_atomic` (Review Focus 4): make the embedding serialisation raise partway through → the photo is still `pending` and has no face rows.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement with `sqlite3` and `with conn:` transactions.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: sqlite cache for photos and face embeddings`.

### Task 4: Face engine

**Files:** Create `src/flickr_find_me/faces.py`. Test: `tests/test_faces.py`.

**Interfaces:**
- Produces: `@dataclass Face(bbox: tuple[float, float, float, float], embedding: np.ndarray)`, where the embedding is L2-normalised float32 of length 512. `class FaceEngine()` loads `FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])` and calls `prepare(ctx_id=-1, det_size=(640, 640))`. Methods: `detect(image_path: Path) -> list[Face]`, and `reference(image_path: Path) -> np.ndarray`, which returns the largest face by bbox area and raises `NoFaceError(path)` if there are none. `cache.py` imports `Face` from here, so move it here if Task 3 stubbed it.

- [ ] **Step 1: Failing tests**, marked `@pytest.mark.model` (they download about 280 MB of models on first run):
  - `test_detect_group_photo`: write `insightface.data.get_image("t1")` to tmp → `len(detect(p)) >= 5`, and every embedding has norm ≈ 1.
  - `test_reference_no_face_raises` (Review Focus 1): a solid grey 400×400 jpg → `NoFaceError`.
  - `test_reference_picks_largest`: using t1, `reference()` equals the embedding of the max-area face from `detect()`.
  - `test_same_face_scores_high`: the t1 image, and the same image mirrored → the largest face's cosine similarity is > 0.6.
- [ ] **Step 2:** Run `uv run pytest -m model tests/test_faces.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Read images with `cv2.imread`, and treat `None` (unreadable) as zero faces. Use `face.normed_embedding`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: InsightFace wrapper`.

### Task 5: Matching + report

**Files:** Create `src/flickr_find_me/match.py`, `src/flickr_find_me/report.py`. Test: `tests/test_match.py`, `tests/test_report.py`.

**Interfaces:**
- Produces:
  - `best_score(faces: list[np.ndarray], refs: list[np.ndarray]) -> float`. The max dot product over all face×ref pairs, or `0.0` if there are no faces.
  - `@dataclass Result(photo: Photo, score: float, kind: Literal["match", "maybe"])`
  - `classify(all_faces: dict[str, list[np.ndarray]], refs, photos: Callable[[str], Photo], match_t: float, maybe_t: float) -> list[Result]`. Sorted by score descending, and drops anything below `maybe_t`.
  - `render(results: list[Result], out: Path, album_title: str, matches_dir: Path) -> None`

- [ ] **Step 1: Failing tests:**
  - `test_best_score_empty_is_zero`.
  - `test_best_score_takes_max_over_refs`: unit vectors → expected dot.
  - `test_classify_thresholds`: scores 0.6 / 0.4 / 0.2 with `match_t=0.45, maybe_t=0.32` → `[match, maybe]`, sorted.
  - `test_render_html`: one match, one maybe → the file contains two `<img src="<scan_url>"`, the `page_url` links, the score formatted `0.60`, a "Matches" section before "Maybe"; and a match whose original exists in `matches_dir` links to it by relative path. Titles are HTML-escaped (a title of `<b>` renders as `&lt;b&gt;`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. `render` uses an f-string template with `html.escape` and a simple CSS grid. Each card shows the thumbnail (hotlinked `scan_url`), the title, the score, a "View on Flickr" link, and, for maybes, the photo id plus the hint `flickr-find-me ... --fetch <id>`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: scoring and HTML report`.

### Task 6: CLI orchestration

**Files:** Create `src/flickr_find_me/cli.py`. Test: `tests/test_cli.py`.

**Interfaces:**
- Consumes everything above.
- Produces: `main(argv: list[str] | None = None) -> int`, and `original_filename(photo: Photo, ext: str) -> str`.
- Arguments: `album_url` (positional), `--me PATH [PATH ...]` (required), `--size INT=1024`, `--match FLOAT=0.45`, `--maybe FLOAT=0.32`, `--out PATH` (default `runs/<album_id>`), `--keep-downloads`, `--fetch ID [ID ...]`, `--workers INT=8`.

Flow:
1. Compute reference embeddings. On `NoFaceError`, print `No face found in <path>` and return 2.
2. Run `list_album`, then `cache.upsert_photos`.
3. For `cache.pending()`: a `ThreadPoolExecutor(workers)` downloads to `scans/<id>.jpg`, and the main thread runs `engine.detect` as each download completes. Then `save_faces`, and delete the scan unless `--keep-downloads`. A download error leads to `mark_failed` and a warning. Print progress every 50 photos (`done/total, matches so far`).
4. Run `classify`.
5. For each `match` whose original isn't in `matches/`: `original_url`, then `download` into `matches/original_filename(...)`.
6. Run `render`, then print a summary (counts, path to results.html).

`--fetch` skips steps 2–3 and downloads originals for the given ids (looked up via `cache.photo`), then re-renders.

- [ ] **Step 1: Failing tests** (monkeypatch `list_album`, `original_url`, `download`, and `FaceEngine` with fakes that return fixed embeddings):
  - `test_end_to_end_with_fakes`: 3 photos (one with my embedding, one with a stranger's, one with no faces) → `matches/` holds one file, `results.html` exists, the cache reports 3 `done`, and no files remain in `scans/`.
  - `test_resume_skips_done`: run twice → the fake `download` is called 3 times in total, not 6.
  - `test_failed_download_continues` (Review Focus 3): one scan download raises `DownloadError` → the exit code is 0, the other photos are `done`, the failed one is `failed`, and a second run retries only that one.
  - `test_reference_without_face_exits_2` (Review Focus 1).
  - `test_original_filename_sanitized` (Review Focus 5): title `"a/b c"`, id `"9"` → `"a_b_c_9.jpg"`, and an empty title gives `"9.jpg"`.
  - `test_fetch_downloads_given_ids`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. `original_filename` replaces `[^A-Za-z0-9._+-]` with `_`, then appends `_<id>.<ext>`. Catch `KeyboardInterrupt` around the scan loop: print `Interrupted — re-run to resume`, then return 130. A partial `.part` file is harmless.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: all non-network/model tests PASS.
- [ ] **Step 5:** Commit `feat: CLI orchestration`.

### Task 7: Real run + README

**Files:** Create `README.md` (install, usage, flags, how thresholds work, a note that new reference photos also need no re-download).

- [ ] **Step 1:** `uv run pytest -m "network or model" -v`. Expected: PASS.
- [ ] **Step 2:** Smoke test on the real album with a small slice. Add a hidden `--limit N` flag that only processes the first N pending photos, then run `uv run flickr-find-me <KubeCon album> --me <ref> --limit 30`. Expected: 30 photos `done`, and `results.html` opens.
- [ ] **Step 3:** Record the observed scan-image size and seconds per photo in the README.
- [ ] **Step 4:** Commit `docs: README and limit flag`.
