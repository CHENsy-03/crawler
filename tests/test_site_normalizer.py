import pytest

from crawler.site.normalizer import SiteNormalizationError, normalize_target_url


@pytest.mark.parametrize("raw,want", [
    ("http://Example.COM:80/a#frag", "http://example.com/a"),
    ("https://Example.com:443/a?x=1", "https://example.com/a?x=1"),
    ("http://example.com:8080/p?q=1", "http://example.com:8080/p?q=1"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com/a?x=1&x=2", "http://example.com/a?x=1&x=2"),
    ("HTTPS://EXAMPLE.COM:443/", "https://example.com/"),
])
def test_normalize_valid(raw, want):
    assert normalize_target_url(raw) == want


@pytest.mark.parametrize("raw", [
    "ftp://example.com/",
    " http://example.com",
    "http://example.com ",
    "http://exa mple.com/",
    "http://user:pass@example.com/",
    "http:///nohost",
    "http://example.com:abc",
    "http://example.com:99999",
    "http://example.com:",
    "https://[::1",
    "http://example.com/\n",
])
def test_normalize_invalid(raw):
    with pytest.raises(SiteNormalizationError):
        normalize_target_url(raw)
