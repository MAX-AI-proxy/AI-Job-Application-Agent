"""Gemeinsame URL-Identität für Stellen, Bewerbungen und Statuspflege."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {'fbclid', 'gclid', 'msclkid'}


def canonical_url(url: str) -> str:
    """Entferne Tracking, erhalte stellenidentifizierende URL-Bestandteile."""
    if not isinstance(url, str) or not url.strip():
        return ''
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        if scheme not in {'http', 'https'} or not parts.hostname:
            return ''
        if parts.username is not None or parts.password is not None:
            return ''
        host = parts.hostname.lower()
        if any(character.isspace() for character in host):
            return ''
        port = parts.port
    except ValueError:
        return ''
    if ':' in host:
        host = f'[{host}]'
    if port is not None and (scheme, port) not in {('http', 80), ('https', 443)}:
        host += f':{port}'
    parameters = [
        (name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not name.lower().startswith('utm_')
        and name.lower() not in TRACKING_PARAMETERS
    ]
    # Pfad, Schema, Parameterreihenfolge und Fragment nicht pauschal gleichsetzen.
    return urlunsplit((scheme, host, parts.path or '/', urlencode(parameters), parts.fragment))


def urls_match(left: str, right: str) -> bool:
    canonical_left = canonical_url(left)
    return bool(canonical_left) and canonical_left == canonical_url(right)


def distinct_urls(left: str, right: str) -> bool:
    canonical_left, canonical_right = canonical_url(left), canonical_url(right)
    return bool(canonical_left and canonical_right) and canonical_left != canonical_right
