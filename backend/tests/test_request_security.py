"""Origin comparison and ambiguous/hostile browser evidence are fail-closed."""

import pytest
from starlette.datastructures import Headers

from app.core.errors import AuthError
from app.core.request_security import check_browser_headers, same_origin_referer

ORIGIN = "https://miniapp.example"


@pytest.mark.parametrize(
    "value",
    [
        ORIGIN + "/app",
        ORIGIN + ":443/app?tab=files",
        "https://MINIAPP.example/app",
    ],
)
def test_same_origin_referer_compares_scheme_host_and_effective_port(value):
    assert same_origin_referer(value, ORIGIN)


@pytest.mark.parametrize(
    "value",
    [
        "null",
        "",
        "/app",
        "https://miniapp.example.attacker.example/",
        "http://miniapp.example/",
        "https://miniapp.example:8443/",
        "https://miniapp.example:0/",
        "https://miniapp.example:bad/",
        "https://miniapp.example@attacker.example/",
        "https://attacker@miniapp.example/",
        "https://miniapp.example\\@attacker.example/",
        " https://miniapp.example/",
        "https://miniapp.example/\n",
        "https://miniapp.example/#fragment",
        "https://[invalid/",
        "https://miniapp.example\t.attacker.example/",
    ],
)
def test_referer_must_not_be_prefix_matched_or_silently_repaired(value):
    assert not same_origin_referer(value, ORIGIN)


@pytest.mark.parametrize(
    "name,first,second",
    [
        ("Origin", "null", ORIGIN),
        ("Origin", ORIGIN, "https://attacker.example"),
        ("Referer", ORIGIN + "/app", "https://attacker.example/"),
        ("Sec-Fetch-Site", "same-origin", "cross-site"),
        ("Sec-Fetch-Mode", "cors", "no-cors"),
        ("Sec-Fetch-Dest", "empty", "iframe"),
    ],
)
def test_duplicate_security_headers_are_rejected(name, first, second):
    raw = [(name.lower().encode(), first.encode()), (name.lower().encode(), second.encode())]
    if name != "Origin":
        raw.append((b"origin", b"null"))
    headers = Headers(raw=raw)
    with pytest.raises(AuthError) as error:
        check_browser_headers(headers, ORIGIN, unsafe=True)
    assert error.value.status == 403
    assert error.value.code == "browser_headers_invalid"


@pytest.mark.parametrize("value", ["NULL", "null, https://miniapp.example", ORIGIN + "/", ""])
def test_opaque_origin_classification_is_narrow(value):
    with pytest.raises(AuthError):
        check_browser_headers(Headers({"Origin": value}), ORIGIN, unsafe=True)


def test_missing_origin_is_not_included_in_webview_write_compatibility():
    with pytest.raises(AuthError):
        check_browser_headers(
            Headers({"Referer": ORIGIN + "/app", "Sec-Fetch-Site": "same-origin"}),
            ORIGIN,
            unsafe=True,
        )


def test_none_fetch_site_is_only_a_read_navigation_not_a_write_permission():
    assert not check_browser_headers(Headers({"Sec-Fetch-Site": "none"}), ORIGIN, unsafe=False)
    with pytest.raises(AuthError):
        check_browser_headers(
            Headers({"Origin": "null", "Sec-Fetch-Site": "none"}), ORIGIN, unsafe=True
        )
