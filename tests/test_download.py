import httpx
import pytest

from flickr_find_me import download as dl
from flickr_find_me.download import DownloadError, download


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)


def client_for(statuses):
    calls = []

    def handler(request):
        calls.append(request)
        status = statuses[min(len(calls) - 1, len(statuses) - 1)]
        return httpx.Response(status, content=b"abc" if status == 200 else b"")

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_download_writes_file(tmp_path):
    client, _ = client_for([200])
    dest = tmp_path / "a.jpg"
    assert download("https://x/a.jpg", dest, client) == dest
    assert dest.read_bytes() == b"abc"
    assert not list(tmp_path.glob("*.part"))


def test_download_retries_then_succeeds(tmp_path):
    client, calls = client_for([500, 500, 200])
    download("https://x/a.jpg", tmp_path / "a.jpg", client)
    assert len(calls) == 3


def test_download_raises_after_retries(tmp_path):
    client, _ = client_for([404])
    dest = tmp_path / "a.jpg"
    with pytest.raises(DownloadError):
        download("https://x/a.jpg", dest, client)
    assert not dest.exists()
