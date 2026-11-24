"""Static HTML results page."""

import os
from html import escape
from pathlib import Path

from .match import Result

_CSS = """
body{font-family:system-ui,sans-serif;margin:0;padding:24px;background:#fafafa;color:#222}
h1{font-size:22px}h2{font-size:18px;margin-top:32px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.card{background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px #0002}
.card img{width:100%;aspect-ratio:3/2;object-fit:cover;display:block}
.meta{padding:8px 12px;font-size:13px;line-height:1.5}
.score{font-weight:600}code{font-size:11px;background:#eee;padding:1px 4px;border-radius:3px}
"""


def _card(r: Result, link_base: str | None) -> str:
    p = r.photo
    links = [f'<a href="{escape(p.page_url)}">View on Flickr</a>']
    if link_base:
        links.append(f'<a href="{escape(link_base)}">Original</a>')
    hint = f"<br><code>--fetch {escape(p.id)}</code>" if r.kind == "maybe" else ""
    return (
        f'<div class="card"><a href="{escape(p.page_url)}">'
        f'<img src="{escape(p.scan_url)}" loading="lazy" alt=""></a>'
        f'<div class="meta">{escape(p.title)}<br>'
        f'<span class="score">{r.score:.2f}</span> · {" · ".join(links)}{hint}</div></div>'
    )


def render(
    results: list[Result],
    out: Path,
    album_title: str,
    matches_dir: Path,
    originals: dict[str, str],
) -> None:
    """originals maps photo id -> filename inside matches_dir."""
    rel = os.path.relpath(matches_dir, out.parent)

    def link(r: Result) -> str | None:
        name = originals.get(r.photo.id)
        if name and (matches_dir / name).exists():
            return f"{rel}/{name}"
        return None

    sections = []
    for kind, heading in (("match", "Matches"), ("maybe", "Maybe")):
        rs = [r for r in results if r.kind == kind]
        cards = "".join(_card(r, link(r)) for r in rs) or "<p>None.</p>"
        sections.append(f"<h2>{heading} ({len(rs)})</h2><div class='grid'>{cards}</div>")
    out.write_text(
        f"<!doctype html><meta charset='utf-8'><title>{escape(album_title)} — matches</title>"
        f"<style>{_CSS}</style><h1>{escape(album_title)}</h1>{''.join(sections)}"
    )
