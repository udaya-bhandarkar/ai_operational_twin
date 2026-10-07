"""Unit tests for web_fetch SSRF guard, size cap, and HTML extraction — no network calls."""
import httpx
import pytest

from tools import web


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://127.0.0.1/admin",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
        "http://0.0.0.0/",
    ],
)
def test_check_url_refuses_non_public(url):
    with pytest.raises(web.UnsafeURLError):
        web.check_url(url)


def test_check_url_refuses_host_with_any_private_address(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34", "10.0.0.1"])
    with pytest.raises(web.UnsafeURLError):
        web.check_url("https://mixed.example/")


def test_check_url_allows_public(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34"])
    web.check_url("https://example.com/page")  # no exception


def _mock_client(monkeypatch, handler):
    monkeypatch.setattr(
        web, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    # example.com is public; everything else resolves for real (localhost → loopback).
    real_resolve = web._resolve
    monkeypatch.setattr(
        web, "_resolve", lambda host: ["93.184.216.34"] if host == "example.com" else real_resolve(host)
    )


def test_redirect_to_internal_address_is_refused(monkeypatch):
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        raise AssertionError("internal host must never be contacted")

    _mock_client(monkeypatch, handler)
    out = web.web_fetch.invoke({"url": "http://example.com/"})
    assert out.startswith("[web_fetch] Refused")


def test_fetch_extracts_text_and_wraps(monkeypatch):
    html = (
        "<html><head><title>Title</title><style>.x{}</style></head><body>"
        "<script>steal()</script><h1>Hello</h1><p>World &amp; more</p></body></html>"
    )
    _mock_client(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-type": "text/html"}, text=html),
    )
    out = web.web_fetch.invoke({"url": "http://example.com/"})
    assert "<<<EXTERNAL_CONTENT>>>" in out
    assert "Hello" in out and "World & more" in out
    assert "steal()" not in out and "<h1>" not in out


def test_fetch_caps_download_size(monkeypatch):
    big = "a" * (web._MAX_BYTES * 3)
    _mock_client(
        monkeypatch,
        lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, text=big),
    )
    _, text = web.fetch_text("http://example.com/")
    assert len(text) == web._MAX_BYTES


def test_fetch_refuses_binary_content(monkeypatch):
    _mock_client(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=b"\x00"
        ),
    )
    assert "Refused" in web.web_fetch.invoke({"url": "http://example.com/file.bin"})


def test_html_to_text_skips_scripts_and_collapses_whitespace():
    text = web.html_to_text("<div>  a \n b </div><script>x=1</script><p>c</p>")
    assert text == "a b\nc"
    assert web.html_to_text("<p>Hello <b>World</b>, <i>again</i></p>") == "Hello World, again"
