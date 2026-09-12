"""Politique de sortie réseau (SSRF) : refus, allowlist, épinglage et redirections.

Aucune résolution DNS ni connexion réelle : résolveur injecté et ``httpx.MockTransport``.
"""

import ipaddress
import gzip
import socket
import zlib

import httpx
import pytest

from acp_api.outbound import (
    OutboundPolicy,
    OutboundPolicyError,
    ParsedTarget,
    PinnedHttpClient,
    blocked_address_reason,
)

PUBLIC_IP = "93.184.216.34"
PUBLIC_IPV6 = "2606:2800:220:1:248:1893:25c8:1946"


def fake_resolver(table: dict[str, list[str]]):
    """Résolveur déterministe imitant la forme des tuples de ``socket.getaddrinfo``."""

    def resolve(host, port=None, *args, **kwargs):
        if host not in table:
            raise socket.gaierror(-2, "Name or service not known")
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, port or 0),
            )
            for address in table[host]
        ]

    return resolve


def failing_resolver(*args, **kwargs):
    raise AssertionError("aucune résolution DNS réelle ne doit avoir lieu")


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="ok")


def _client(handler, policy=None, resolver=None, **kwargs) -> PinnedHttpClient:
    return PinnedHttpClient(
        policy or OutboundPolicy(),
        resolver or fake_resolver({"example.com": [PUBLIC_IP]}),
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


@pytest.fixture
def policy() -> OutboundPolicy:
    return OutboundPolicy()


# --- validate_url -------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/x", "scheme_forbidden"),
        ("file:///etc/passwd", "scheme_forbidden"),
        ("http://example.com/x", "scheme_forbidden"),
        ("http://127.0.0.1:8642/", "scheme_forbidden"),
        ("https://user:pw@example.com/", "userinfo_forbidden"),
        ("https://user@example.com/", "userinfo_forbidden"),
        ("https://example.com/#frag", "invalid_url"),
        ("example.com", "invalid_url"),
        ("https:///path", "invalid_url"),
        ("https://example.com:99999/", "invalid_url"),
        ("https://exa mple.com/", "invalid_url"),
        ("", "invalid_url"),
    ],
)
def test_validate_url_refusals(policy, url: str, code: str):
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.validate_url(url)
    assert excinfo.value.code == code
    assert str(excinfo.value)


def test_validate_url_normalizes_host_and_defaults(policy):
    target = policy.validate_url("https://Bücher.Example/mcp?x=1")
    assert target == ParsedTarget(
        scheme="https", host="xn--bcher-kva.example", port=443, path_query="/mcp?x=1"
    )
    assert policy.validate_url("https://example.com").path_query == "/"
    assert policy.validate_url("https://example.com:8443/a").port == 8443
    assert policy.validate_url("https://[2606:2800:220:1:248:1893:25c8:1946]/x").host == PUBLIC_IPV6


def test_http_is_allowed_only_for_allowlisted_hosts_or_loopback_flag():
    allowlisted = OutboundPolicy(allowlist=["intranet.example"])
    assert allowlisted.validate_url("http://Intranet.example/").scheme == "http"
    with pytest.raises(OutboundPolicyError) as excinfo:
        allowlisted.validate_url("http://other.example/")
    assert excinfo.value.code == "scheme_forbidden"
    loopback = OutboundPolicy(allow_loopback_http=True)
    assert loopback.validate_url("http://127.0.0.1:8642/").port == 8642
    assert loopback.validate_url("http://localhost:8642/").host == "localhost"
    assert loopback.validate_url("http://[::1]:8642/").host == "::1"
    with pytest.raises(OutboundPolicyError):
        loopback.validate_url("http://example.com/")


# --- is_blocked_address ------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "127.8.8.8",
        "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
        "169.254.169.254", "169.254.1.1",
        "100.64.0.1", "100.127.255.255",
        "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
        "::1", "::", "fc00::1", "fd12::1", "fe80::1", "ff02::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
        "2002:0a00:0001::1",  # 6to4 embarquant 10.0.0.1
        "2002:a9fe:a9fe::1",  # 6to4 embarquant 169.254.169.254
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo : client 192.0.2.45
    ],
)
def test_blocked_addresses(policy, address: str):
    reason = policy.is_blocked_address(ipaddress.ip_address(address))
    assert reason is not None and reason


@pytest.mark.parametrize(
    "address",
    [
        PUBLIC_IP, "8.8.8.8", PUBLIC_IPV6,
        "2002:5db8:d822::1",  # 6to4 embarquant 93.184.216.34
        "2001:0:4136:e378:8000:63bf:a247:27dd",  # Teredo : client 93.184.216.34
    ],
)
def test_public_addresses_are_allowed(policy, address: str):
    assert policy.is_blocked_address(ipaddress.ip_address(address)) is None
    assert blocked_address_reason(ipaddress.ip_address(address)) is None


def test_allowlisted_private_address_is_not_blocked():
    policy = OutboundPolicy(allowlist=["10.0.0.0/8", "fd00::/8", "intranet.example"])
    assert policy.is_blocked_address(ipaddress.ip_address("10.1.2.3")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("fd00::1")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("192.168.1.1")) is not None
    assert policy.is_address_allowlisted(ipaddress.ip_address("10.1.2.3")) is True
    assert policy.is_host_allowlisted("Intranet.Example") is True
    assert policy.is_host_allowlisted("other.example") is False
    # La raison brute reste disponible pour l'audit même si l'adresse est allowlistée.
    assert blocked_address_reason(ipaddress.ip_address("10.1.2.3")) == "private"


def test_loopback_flag_unblocks_loopback_addresses_only():
    policy = OutboundPolicy(allow_loopback_http=True)
    assert policy.is_blocked_address(ipaddress.ip_address("127.0.0.1")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("::1")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("10.0.0.1")) is not None


def test_from_environ_parses_allowlist_and_flag():
    policy = OutboundPolicy.from_environ(
        {
            "ACP_OUTBOUND_PRIVATE_ALLOWLIST": " 10.0.0.0/8, Intranet.example ,fd00::/8, 192.168.1.5 ",
            "ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP": "1",
        }
    )
    assert policy.allow_loopback_http is True
    assert policy.is_blocked_address(ipaddress.ip_address("10.1.1.1")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("192.168.1.5")) is None
    assert policy.is_blocked_address(ipaddress.ip_address("192.168.1.6")) is not None
    assert policy.is_host_allowlisted("intranet.example") is True
    default = OutboundPolicy.from_environ({})
    assert default.allow_loopback_http is False and default.allowlist == []
    assert OutboundPolicy.from_environ({"ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP": "0"}).allow_loopback_http is False
    with pytest.raises(ValueError) as excinfo:
        OutboundPolicy.from_environ({"ACP_OUTBOUND_PRIVATE_ALLOWLIST": "not a host!"})
    assert "ACP_OUTBOUND_PRIVATE_ALLOWLIST" in str(excinfo.value)
    with pytest.raises(ValueError) as excinfo:
        OutboundPolicy.from_environ({"ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP": "yes"})
    assert "ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP" in str(excinfo.value)


# --- resolve --------------------------------------------------------------------


def test_resolve_rejects_when_any_address_is_private(policy):
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("mixed.example", fake_resolver({"mixed.example": [PUBLIC_IP, "10.0.0.5"]}))
    assert excinfo.value.code == "host_blocked"
    assert "10.0.0.5" in str(excinfo.value)


def test_resolve_returns_all_public_addresses_deduplicated(policy):
    addresses = policy.resolve(
        "example.com", fake_resolver({"example.com": [PUBLIC_IP, PUBLIC_IP, PUBLIC_IPV6]})
    )
    assert [str(address) for address in addresses] == [PUBLIC_IP, PUBLIC_IPV6]


def test_resolve_ip_literal_never_touches_dns(policy):
    assert policy.resolve(PUBLIC_IP, failing_resolver) == [ipaddress.ip_address(PUBLIC_IP)]
    assert policy.resolve(PUBLIC_IPV6, failing_resolver) == [ipaddress.ip_address(PUBLIC_IPV6)]
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("127.0.0.1", failing_resolver)
    assert excinfo.value.code == "host_blocked"
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("169.254.169.254", failing_resolver)
    assert excinfo.value.code == "host_blocked"


def test_resolve_failure_is_explicit(policy):
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("unknown.example", fake_resolver({}))
    assert excinfo.value.code == "resolution_failed"
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("empty.example", fake_resolver({"empty.example": []}))
    assert excinfo.value.code == "resolution_failed"


def test_resolve_strips_ipv6_scope_identifiers(policy):
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("link.example", fake_resolver({"link.example": ["fe80::1%eth0"]}))
    assert excinfo.value.code == "host_blocked"


# --- PinnedHttpClient ------------------------------------------------------------


def test_request_pins_ip_and_keeps_host_and_sni():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    response = _client(handler).request(
        "POST",
        "https://example.com/mcp?x=1",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        content=b"{}",
    )
    assert response.status_code == 200 and response.json() == {"ok": True}
    request = seen[0]
    assert request.url.host == PUBLIC_IP
    assert request.url.scheme == "https"
    assert request.url.port in (None, 443)
    assert request.url.raw_path == b"/mcp?x=1"
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["accept"] == "application/json"
    assert request.content == b"{}"
    assert request.method == "POST"


def test_non_default_port_is_pinned_and_kept_in_host_header():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    _client(handler).request("GET", "https://example.com:8443/")
    assert seen[0].url.port == 8443
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers["host"] == "example.com:8443"


def test_ipv6_address_is_pinned_with_brackets():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    _client(handler, resolver=fake_resolver({"example.com": [PUBLIC_IPV6]})).request(
        "GET", "https://example.com/"
    )
    assert seen[0].url.host == PUBLIC_IPV6
    assert seen[0].headers["host"] == "example.com"


def test_timeout_is_applied_to_the_request():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    _client(handler, timeout=3.0).request("GET", "https://example.com/")
    assert seen[0].extensions["timeout"]["connect"] == 3.0
    assert seen[0].extensions["timeout"]["read"] == 3.0


def test_blocked_host_never_reaches_the_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("le transport ne doit pas être sollicité")

    client = _client(handler, resolver=fake_resolver({"internal.example": ["10.0.0.5"]}))
    with pytest.raises(OutboundPolicyError) as excinfo:
        client.request("GET", "https://internal.example/")
    assert excinfo.value.code == "host_blocked"
    with pytest.raises(OutboundPolicyError) as excinfo:
        client.request("GET", "http://example.com/")
    assert excinfo.value.code == "scheme_forbidden"
    with pytest.raises(OutboundPolicyError) as excinfo:
        client.request("GET", "https://user:pw@example.com/")
    assert excinfo.value.code == "userinfo_forbidden"


def test_allowlist_use_is_reported_to_the_caller():
    uses: list[tuple[str, str]] = []
    policy = OutboundPolicy(allowlist=["10.0.0.0/8"])
    client = PinnedHttpClient(
        policy,
        fake_resolver({"intranet.example": ["10.1.2.3"], "example.com": [PUBLIC_IP]}),
        transport=httpx.MockTransport(ok_handler),
        on_private_allowlist_used=lambda host, address: uses.append((host, address)),
    )
    assert client.request("GET", "https://intranet.example/").status_code == 200
    assert uses == [("intranet.example", "10.1.2.3")]
    client.request("GET", "https://example.com/")
    assert uses == [("intranet.example", "10.1.2.3")]


def test_hostname_allowlist_entry_makes_private_host_reachable():
    """Un nom d'hôte allowlisté est joignable même s'il résout vers une adresse privée.

    L'exemption est propre à l'hôte : un autre nom résolvant vers la même adresse reste refusé.
    """

    uses: list[tuple[str, str]] = []
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    policy = OutboundPolicy(allowlist=["Intranet.example"])
    resolver = fake_resolver({"intranet.example": ["10.1.2.3"], "other.example": ["10.1.2.3"]})
    # L'adresse seule n'est pas allowlistée : l'exemption ne vaut que pour le nom d'hôte.
    assert policy.is_blocked_address(ipaddress.ip_address("10.1.2.3")) == "private"
    assert policy.resolve("intranet.example", resolver) == [ipaddress.ip_address("10.1.2.3")]
    with pytest.raises(OutboundPolicyError) as excinfo:
        policy.resolve("other.example", resolver)
    assert excinfo.value.code == "host_blocked"

    client = PinnedHttpClient(
        policy,
        resolver,
        transport=httpx.MockTransport(handler),
        on_private_allowlist_used=lambda host, address: uses.append((host, address)),
    )
    assert client.request("GET", "http://intranet.example/").status_code == 200
    assert client.request("GET", "https://intranet.example/").status_code == 200
    assert [(request.url.scheme, request.url.host, request.url.port) for request in seen] == [
        ("http", "10.1.2.3", None),
        ("https", "10.1.2.3", None),
    ]
    assert {request.headers["host"] for request in seen} == {"intranet.example"}
    assert uses == [("intranet.example", "10.1.2.3"), ("intranet.example", "10.1.2.3")]
    with pytest.raises(OutboundPolicyError) as excinfo:
        client.request("GET", "https://other.example/")
    assert excinfo.value.code == "host_blocked"
    assert len(seen) == 2  # l'hôte non allowlisté n'atteint jamais le transport


def test_loopback_http_flag_pins_loopback_and_reports_use():
    uses: list[tuple[str, str]] = []
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client = PinnedHttpClient(
        OutboundPolicy(allow_loopback_http=True),
        failing_resolver,
        transport=httpx.MockTransport(handler),
        on_private_allowlist_used=lambda host, address: uses.append((host, address)),
    )
    client.request("GET", "http://127.0.0.1:8642/health")
    assert seen[0].url.scheme == "http" and seen[0].url.host == "127.0.0.1"
    assert seen[0].url.port == 8642 and seen[0].headers["host"] == "127.0.0.1:8642"
    assert uses == [("127.0.0.1", "127.0.0.1")]


def test_redirect_to_private_address_is_blocked():
    resolver = fake_resolver({"example.com": [PUBLIC_IP], "internal.example": ["10.0.0.9"]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == PUBLIC_IP:
            return httpx.Response(302, headers={"Location": "https://internal.example/secret"})
        raise AssertionError("l'adresse privée ne doit jamais être contactée")

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler, resolver=resolver).request("GET", "https://example.com/start")
    assert excinfo.value.code == "redirect_blocked"
    assert "internal.example" in str(excinfo.value)


@pytest.mark.parametrize(
    "location",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "https://user:pw@example.com/",
        "ftp://example.com/",
        "https://127.0.0.1/",
    ],
)
def test_redirect_to_refused_targets_is_blocked(location: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(301, headers={"Location": location})
        raise AssertionError("la cible de redirection ne doit jamais être contactée")

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler).request("GET", "https://example.com/start")
    assert excinfo.value.code == "redirect_blocked"


def test_relative_redirect_is_followed_after_full_revalidation():
    hits: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append((request.method, str(request.url), request.content))
        if request.url.path == "/start":
            return httpx.Response(303, headers={"Location": "/next?y=2"})
        return httpx.Response(200, text="fin")

    response = _client(handler).request("POST", "https://example.com/start", content=b"x")
    assert response.status_code == 200 and response.text == "fin"
    assert hits == [
        ("POST", f"https://{PUBLIC_IP}/start", b"x"),
        ("GET", f"https://{PUBLIC_IP}/next?y=2", b""),
    ]


def test_307_redirect_preserves_method_and_body():
    hits: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append((request.method, request.content))
        if request.url.path == "/start":
            return httpx.Response(307, headers={"Location": "https://example.com/next"})
        return httpx.Response(200)

    _client(handler).request("POST", "https://example.com/start", content=b"payload")
    assert hits == [("POST", b"payload"), ("POST", b"payload")]


def test_more_than_three_redirects_are_refused():
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        return httpx.Response(302, headers={"Location": f"/hop{len(hits)}"})

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler).request("GET", "https://example.com/start")
    assert excinfo.value.code == "too_many_redirects"
    assert len(hits) == 4  # requête initiale + 3 redirections suivies, la 4e est refusée


def test_three_redirects_are_followed():
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        if len(hits) <= 3:
            return httpx.Response(308, headers={"Location": f"/hop{len(hits)}"})
        return httpx.Response(200, text="arrivé")

    assert _client(handler).request("GET", "https://example.com/start").text == "arrivé"
    assert hits == ["/start", "/hop1", "/hop2", "/hop3"]


def test_redirect_without_location_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler).request("GET", "https://example.com/start")
    assert excinfo.value.code == "redirect_blocked"


SECRET_HEADERS = {
    "Authorization": "Bearer SECRET-VALUE",
    "Proxy-Authorization": "Basic SECRET-PROXY",
    "Cookie": "session=SECRET-COOKIE",
    "X-Api-Key": "SECRET-KEY",
}


def _no_secret_leaked(request: httpx.Request) -> bool:
    return all(b"SECRET" not in value for _, value in request.headers.raw)


def test_cross_origin_redirect_drops_credentials_and_caller_headers():
    """Une redirection vers une autre origine n'emporte jamais les en-têtes sensibles de l'appelant.

    Seuls les en-têtes de négociation (Accept, Content-Type…) sont réémis ; revenir ensuite
    sur l'origine initiale ne restaure pas les identifiants.
    """

    hits: list[httpx.Request] = []
    resolver = fake_resolver({"mcp.example": [PUBLIC_IP], "attacker.example": ["8.8.8.8"]})

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        if request.headers["host"] == "mcp.example" and request.url.path == "/mcp":
            return httpx.Response(302, headers={"Location": "https://attacker.example/collect"})
        if request.headers["host"] == "attacker.example":
            return httpx.Response(307, headers={"Location": "https://mcp.example/back"})
        return httpx.Response(200, text="fin")

    response = _client(handler, resolver=resolver).request(
        "POST",
        "https://mcp.example/mcp",
        headers={**SECRET_HEADERS, "Accept": "application/json", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert response.status_code == 200 and response.text == "fin"
    first, second, third = hits
    assert first.headers["authorization"] == "Bearer SECRET-VALUE"
    assert first.headers["x-api-key"] == "SECRET-KEY"
    assert second.url.host == "8.8.8.8" and second.headers["host"] == "attacker.example"
    assert third.url.host == PUBLIC_IP and third.headers["host"] == "mcp.example"
    for request in (second, third):
        for name in SECRET_HEADERS:
            assert name.lower() not in request.headers
        assert _no_secret_leaked(request)
        assert request.headers["accept"] == "application/json"


@pytest.mark.parametrize(
    "location",
    ["https://example.com:8443/next", "https://cdn.example/next"],
)
def test_port_or_host_change_is_a_different_origin(location: str):
    hits: list[httpx.Request] = []
    resolver = fake_resolver({"example.com": [PUBLIC_IP], "cdn.example": ["8.8.8.8"]})

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        if request.url.path == "/start":
            return httpx.Response(307, headers={"Location": location})
        return httpx.Response(200)

    _client(handler, resolver=resolver).request(
        "POST", "https://example.com/start", headers=SECRET_HEADERS, content=b"p"
    )
    assert len(hits) == 2
    assert "authorization" not in hits[1].headers
    assert "x-api-key" not in hits[1].headers
    assert _no_secret_leaked(hits[1])


@pytest.mark.parametrize(
    "location",
    ["/next", "https://example.com/next", "https://EXAMPLE.com:443/next"],
)
def test_same_origin_redirect_keeps_caller_headers(location: str):
    hits: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        if request.url.path == "/start":
            return httpx.Response(307, headers={"Location": location})
        return httpx.Response(200)

    _client(handler).request("POST", "https://example.com/start", headers=SECRET_HEADERS, content=b"p")
    assert len(hits) == 2
    assert hits[1].headers["authorization"] == "Bearer SECRET-VALUE"
    assert hits[1].headers["x-api-key"] == "SECRET-KEY"
    assert hits[1].headers["cookie"] == "session=SECRET-COOKIE"
    assert hits[1].headers["host"] == "example.com"


def test_streamed_body_larger_than_limit_is_cut():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=iter([b"x" * 1000] * 10))

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler, max_body_bytes=4096).request("GET", "https://example.com/big")
    assert excinfo.value.code == "response_too_large"


def test_declared_content_length_larger_than_limit_is_refused_early():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "999999"}, content=b"x" * 10)

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler, max_body_bytes=4096).request("GET", "https://example.com/big")
    assert excinfo.value.code == "response_too_large"


def test_body_within_limit_is_returned_whole():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"y" * 4096, headers={"X-Test": "1"})

    response = _client(handler, max_body_bytes=4096).request("GET", "https://example.com/ok")
    assert response.content == b"y" * 4096
    assert response.headers["x-test"] == "1"
    assert response.request is not None and response.request.url.host == PUBLIC_IP


@pytest.mark.parametrize(
    ("encoding", "compress"),
    [("gzip", gzip.compress), ("deflate", zlib.compress)],
)
def test_compressed_body_is_decoded_exactly_once(encoding: str, compress):
    raw = b'{"ok": true}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=compress(raw),
            headers={"Content-Encoding": encoding, "Content-Type": "application/json", "X-Test": "1"},
        )

    response = _client(handler).request("GET", "https://example.com/mcp")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.content == raw
    assert "content-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(raw))
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-test"] == "1"


def test_size_cap_applies_to_the_decoded_body():
    compressed = gzip.compress(b"x" * 100_000)
    assert len(compressed) < 4096  # le corps annoncé passe, le corps décodé dépasse

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=compressed, headers={"Content-Encoding": "gzip"})

    with pytest.raises(OutboundPolicyError) as excinfo:
        _client(handler, max_body_bytes=4096).request("GET", "https://example.com/bomb")
    assert excinfo.value.code == "response_too_large"


def test_errors_carry_a_code_and_a_french_message():
    error = OutboundPolicyError("host_blocked", "adresse privée refusée")
    assert isinstance(error, ValueError)
    assert error.code == "host_blocked" and str(error) == "adresse privée refusée"
    with pytest.raises(ValueError):
        OutboundPolicyError("unknown_code", "x")
