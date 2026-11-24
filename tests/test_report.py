from flickr_find_me.flickr import Photo
from flickr_find_me.match import Result
from flickr_find_me.report import render


def test_render_html(tmp_path):
    matches_dir = tmp_path / "matches"
    matches_dir.mkdir()
    (matches_dir / "m_1.jpg").write_bytes(b"x")
    results = [
        Result(Photo("1", "m", "https://flickr/p/1/", "https://img/1_b.jpg"), 0.6, "match"),
        Result(Photo("2", "<b>", "https://flickr/p/2/", "https://img/2_b.jpg"), 0.4, "maybe"),
    ]
    out = tmp_path / "results.html"
    render(results, out, "KubeCon", matches_dir, {"1": "m_1.jpg"})
    html = out.read_text()
    assert html.count('<img src="https://img/') == 2
    assert 'href="https://flickr/p/1/"' in html and 'href="https://flickr/p/2/"' in html
    assert "0.60" in html
    assert html.index("Matches") < html.index("Maybe")
    assert 'href="matches/m_1.jpg"' in html
    assert "&lt;b&gt;" in html and "<b>" not in html
    assert "--fetch 2" in html
