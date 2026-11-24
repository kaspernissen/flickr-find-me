# flickr-find-me

Find every photo of you in a public Flickr album and download the originals.

Everything runs locally: gallery-dl lists the album (no Flickr API key needed),
InsightFace detects and compares faces on your machine.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

The face model (~280 MB) downloads to `~/.insightface` on first run.

## Use

```sh
uv run flickr-find-me \
  "https://www.flickr.com/photos/143247548@N03/albums/72177720336408231" \
  --me me1.jpg me2.jpg me3.jpg
```

Use 3–5 reference photos of yourself with different angles and lighting. In
each one, the tool uses the largest face.

Output goes to `runs/<album-id>/`:

- `results.html`: matches and "maybe" matches, sorted by score, linking to Flickr
- `matches/`: full-size originals of the confident matches
- `cache.sqlite`: face data for every scanned photo

Scan images are deleted once they've been checked.

### Flags

| Flag | Default | |
|---|---|---|
| `--size` | 1024 | Scan image size in px. Larger finds smaller faces but downloads more. |
| `--match` | 0.45 | Similarity threshold for a confident match (originals downloaded) |
| `--maybe` | 0.32 | Lower threshold for the "maybe" section |
| `--fetch ID…` | | Download originals of specific photos (e.g. confirmed maybes) |
| `--keep-downloads` | off | Keep the scan images |
| `--out` | `runs/<album-id>` | Output directory |
| `--workers` | 8 | Parallel downloads |

### Re-runs are cheap

The tool caches each photo's face data, so a re-run never downloads the scan
images again. You can:

- change `--match` / `--maybe`,
- add or swap `--me` reference photos,
- Ctrl-C at any time and re-run to resume. Failed downloads are retried.

Only a different `--size` needs a fresh output dir (`--out`) to rescan.

## Measured on KubeCon NA 2026 (3,537 photos)

- Listing the album: ~22 s
- Scan images at 1024px: ~180 KB each, so ~0.6 GB downloaded in total, kept only briefly
- Face detection: ~1.2 s per photo on Apple Silicon CPU, so about an hour for the album
- Originals: ~2–3.5 MB each

## Tests

```sh
uv run pytest                      # fast unit tests
uv run pytest -m "network or model"  # hits Flickr / loads the face model
```
