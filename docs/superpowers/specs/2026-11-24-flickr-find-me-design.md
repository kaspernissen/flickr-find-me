# flickr-find-me — design

## Intent

Find every photo of me in a public Flickr event album (first target: CNCF's
"KubeCon + CloudNativeCon North America 2026", 3,537 photos,
https://www.flickr.com/photos/143247548@N03/albums/72177720336408231), and end
up with full-resolution originals of those photos. Personal tool, run locally.

## Goals

- Input: one Flickr album URL + 3–5 reference photos of me.
- Output: originals of confident matches in `matches/`, and `results.html`
  listing confident and "maybe" matches sorted by score, each with a thumbnail
  and a link back to the Flickr photo page.
- Light on disk and bandwidth: scan small, download originals only for matches.
- Works for any public album, so it can be re-used for future events.

## Non-goals

- Searching across multiple albums or a whole photostream.
- A web UI, or use by other attendees.
- Cloud face services.

## Anti-goals

- Sending my face to a third party.
- Leaving ~30 GB of originals on disk.
- Requiring a Flickr API key (free accounts can no longer create one).

## Constraints

- macOS, Python, CPU-only is fine.
- Flickr API keys need Flickr Pro, so photo listing/downloading goes through
  gallery-dl, which ships its own Flickr access.

## Approaches considered

1. **gallery-dl for fetching (chosen).** Maintained, supports Flickr albums,
   no key needed, supports a max-size cap. Trade-off: dependency on a
   third-party project.
2. **Official Flickr API with my own key.** Most reliable, but needs Flickr
   Pro (paid) and the key dies when Pro lapses.
3. **Own scraper / headless browser.** No dependency, but fragile; rejected.

Face matching: **InsightFace** (local, ONNX, CPU) chosen over dlib/face_recognition
(worse on small/off-angle faces) and cloud services (cost, privacy).

## Decided design

- CLI: `flickr-find-me <album-url> --me <ref images...>`.
- **Reference embeddings:** detect the single largest face in each reference
  image, embed it; error if a reference has no face.
- **Scan pass:** fetch album photos via gallery-dl at max 1024px (`--size`
  flag to change). For each photo: detect faces, embed, compare to reference
  embeddings (cosine similarity, best over references), then delete the scan
  image unless `--keep-downloads`.
- **Cache:** per-photo face embeddings + metadata (photo id, title, page URL)
  stored locally, so re-scoring with a new threshold needs no download and an
  interrupted run resumes where it stopped.
- **Thresholds:** a "match" threshold and a lower "maybe" threshold, both
  flags. Matches get a saved 1024px thumbnail or face crop for the results page;
  "maybe" photos keep their 1024px image so I can judge them by eye.
- **Originals pass:** for each confident match, download the original via
  gallery-dl into `matches/`, named after the Flickr title.
- **`--fetch <photo-id>`:** download the original of a specific photo (for
  confirmed "maybe"s).
- **Report:** static `results.html`, matches then maybes, sorted by score.

## Left to the builder

- Exact threshold defaults (calibrate on this album).
- Cache format (SQLite or JSON/npz), project layout, packaging.
- How gallery-dl is driven (subprocess vs Python API) and how scan-size and
  original-size downloads are configured.
- Concurrency of the scan.
