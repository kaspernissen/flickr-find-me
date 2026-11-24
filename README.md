# flickr-find-me

Find yourself in a Flickr album and download the originals.

Give it a public album link and a few photos of yourself. It checks every photo
in the album and downloads the ones you're in. Face matching runs on your own
machine, so your face isn't uploaded anywhere.

## Run it

Put 3–5 photos of yourself (and nothing else) in a folder, open a terminal
there and run this with any public Flickr album link:

```sh
docker run --rm -t -v "$PWD:/work" ghcr.io/kaspernissen/flickr-find-me \
  "https://www.flickr.com/photos/<user>/albums/<album-id>"
```

When it finishes, open `runs/<album-id>/results.html`. The full-size photos are
in `runs/<album-id>/matches/`.

- It uses every photo in the folder. To pick specific ones, list them after the
  album link.
- If you stop it, run the same command again and it carries on where it left
  off.
- Getting strangers? Raise `--match` (default `0.45`). Missing photos? Lower it.
- Photos it isn't sure about are listed under "Maybe". Download one with
  `--fetch <photo-id>`.
- On Linux, add `--user "$(id -u):$(id -g)"` after `docker run`.

## How it works

1. Lists the album with [gallery-dl](https://github.com/mikf/gallery-dl), so no
   Flickr API key is needed.
2. Downloads each photo at 1024px, finds the faces with
   [InsightFace](https://github.com/deepinsight/insightface) and compares them
   with your photos. Each image is deleted as soon as it's checked.
3. Downloads the full-size original of every match and writes a results page.

The face data is cached, so re-running with a different `--match` or other
photos of you doesn't download anything again.

## Contributing

Issues and pull requests are welcome. You'll need [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run pytest
```

MIT licensed.
