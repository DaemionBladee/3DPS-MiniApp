"""Browser evidence checks, never identity or authorization from an opaque origin.

Absent Fetch Metadata/Referer is supported for embedded clients. The caller must
still verify a one-use Telegram proof for JSON login, or session-bound CSRF for
EVERY other opaque-origin mutation. No CORS permission is granted here.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers

from app.core.errors import AuthError


def same_origin_referer(value: str, expected: str) -> bool:
    # Reject inputs URL parsers might silently repair. Never log the URL: a
    # malformed referrer can itself contain credentials or signed launch data.
    if "\\" in value or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return False
    try:
        actual, trusted = urlsplit(value), urlsplit(expected)
        return (
            actual.scheme in {"https", "http"}
            and actual.scheme == trusted.scheme
            and actual.hostname == trusted.hostname
            and actual.username is None
            and actual.password is None
            and not actual.fragment
            and (
                actual.port if actual.port is not None else 443 if actual.scheme == "https" else 80
            )
            == (
                trusted.port
                if trusted.port is not None
                else 443
                if trusted.scheme == "https"
                else 80
            )
        )
    except ValueError:
        return False


def check_browser_headers(headers: Headers, expected: str, *, unsafe: bool) -> bool:
    """Return whether Origin is explicitly null, AFTER rejecting hostile evidence.

    This return value is a compatibility classification, not a trust decision.
    An absent Origin remains forbidden on unsafe requests. Non-null Origins must
    match configured PUBLIC_BASE_URL exactly, never Host/forwarded headers.
    """
    for name in ("origin", "referer", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"):
        if len(headers.getlist(name)) > 1:
            raise AuthError(403, "browser_headers_invalid", "Open this action from the Mini App.")
    site = headers.get("sec-fetch-site")
    if site is not None and not (site == "same-origin" or site == "none" and not unsafe):
        raise AuthError(403, "fetch_metadata_invalid", "Open this action from the Mini App.")
    if unsafe:
        mode, destination = headers.get("sec-fetch-mode"), headers.get("sec-fetch-dest")
        if (mode is not None and mode not in {"cors", "same-origin"}) or (
            destination is not None and destination != "empty"
        ):
            raise AuthError(403, "fetch_metadata_invalid", "Open this action from the Mini App.")
    origin = headers.get("origin")
    if (unsafe and origin is None) or (origin is not None and origin not in {expected, "null"}):
        raise AuthError(403, "origin_invalid", "Open this action from the Mini App.")
    referer = headers.get("referer")
    if referer is not None and not same_origin_referer(referer, expected):
        raise AuthError(403, "origin_invalid", "Open this action from the Mini App.")
    return origin == "null"
