# flickr-find-me

Find yourself in a Flickr album and download the originals.

Give it a public album link and a few photos of yourself. It checks every photo
in the album and downloads the ones you're in. Face matching runs on your own
machine, so your face isn't uploaded anywhere.

## Run it

Put 3–5 photos of yourself in a folder, open a terminal there and run this with
any public Flickr album link:

```sh
docker run --rm -v "$PWD:/work" kaspernissen/flickr-find-me \
  "https://www.flickr.com/photos/<user>/albums/<album-id>" \
  --me me1.jpg me2.jpg me3.jpg
```

When it finishes, open `runs/<album-id>/results.html`. The full-size photos are
in `runs/<album-id>/matches/`.

- A 3,500-photo album takes about an hour. If you stop it, run the same command
  again and it carries on where it left off.
- Getting strangers? Raise `--match` (default `0.45`). Missing photos? Lower it.
- Photos it isn't sure about are listed under "Maybe". Download one with
  `--fetch <photo-id>`.
- On Linux, add `--user "$(id -u):$(id -g)"` after `docker run`.

## Contributing

Issues and pull requests are welcome. You'll need [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run pytest
```

MIT licensed.
