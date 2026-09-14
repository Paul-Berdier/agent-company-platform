"""Jetons signés des liens de livrables.

Un lien est borné dans le temps, lié à un artefact **et** à un utilisateur, et
révocable. La vérification compare en temps constant, accepte les clés encore en
rotation et refuse tout le reste avec un message explicite — jamais un plantage.
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Literal

import pytest

from acp_api import signing
from acp_api.signing import (
    ARTIFACT_SIGNING_KEYS_ENV,
    DEFAULT_LINK_TTL_SECONDS,
    MAX_LINK_TTL_SECONDS,
    MIN_SIGNING_KEY_CHARS,
    TOKEN_VERSION,
    ArtifactSigningNotConfigured,
    ArtifactTokenExpired,
    ArtifactTokenInvalid,
    generate_signing_key,
    load_signing_keys,
    sign_artifact_token,
    signing_key_id,
    token_hash,
    verify_artifact_token,
)

ARTIFACT = "22222222-2222-2222-2222-222222222222"
OTHER_ARTIFACT = "99999999-9999-9999-9999-999999999999"
USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "88888888-8888-8888-8888-888888888888"

KEY = "cle-de-signature-de-test-numero-un-0123456789"
ROTATED_KEY = "cle-de-signature-de-test-numero-deux-987654321"
RETIRED_KEY = "cle-de-signature-retiree-du-service-abcdefghij"

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
EXPIRES = NOW + timedelta(minutes=5)


def _token(
    key: str = KEY,
    *,
    artifact: str = ARTIFACT,
    user: str = USER,
    purpose: Literal["download", "preview"] = "download",
) -> str:
    return sign_artifact_token(artifact, user, EXPIRES, key, purpose=purpose)


# --- chargement des clés ------------------------------------------------------


def test_keys_are_read_in_rotation_order():
    environ = {ARTIFACT_SIGNING_KEYS_ENV: f" {KEY} , {ROTATED_KEY} "}
    assert load_signing_keys(environ) == [KEY, ROTATED_KEY]


def test_an_absent_key_is_reported_as_not_configured():
    with pytest.raises(ArtifactSigningNotConfigured) as excinfo:
        load_signing_keys({})
    message = str(excinfo.value)
    assert "non configuré" in message
    assert ARTIFACT_SIGNING_KEYS_ENV in message


def test_an_empty_key_list_is_reported_as_not_configured():
    with pytest.raises(ArtifactSigningNotConfigured):
        load_signing_keys({ARTIFACT_SIGNING_KEYS_ENV: " , ,"})


def test_a_too_short_key_is_refused_rather_than_accepted_silently():
    with pytest.raises(ArtifactSigningNotConfigured) as excinfo:
        load_signing_keys({ARTIFACT_SIGNING_KEYS_ENV: "trop-courte"})
    assert str(MIN_SIGNING_KEY_CHARS) in str(excinfo.value)


def test_a_generated_key_is_accepted():
    generated = generate_signing_key()
    assert load_signing_keys({ARTIFACT_SIGNING_KEYS_ENV: generated}) == [generated]


def test_key_id_identifies_a_key_without_revealing_it():
    identifier = signing_key_id(KEY)
    assert KEY not in identifier
    assert identifier != signing_key_id(ROTATED_KEY)
    assert identifier == signing_key_id(KEY)


# --- signature ----------------------------------------------------------------


def test_the_token_has_the_documented_format():
    token = _token()
    parts = token.split(".")
    assert len(parts) == 6
    assert parts[0] == TOKEN_VERSION == "v2"
    assert parts[1] == ARTIFACT
    assert int(parts[2]) == int(EXPIRES.timestamp())
    assert parts[3] == "download"
    assert len(parts[4]) >= 16 and "=" not in parts[4]
    assert parts[5] and "=" not in parts[5]
    assert USER not in token


def test_two_tokens_with_the_same_claims_are_distinct():
    assert _token() != _token()


def test_a_valid_token_verifies_and_returns_its_claims():
    claims = verify_artifact_token(
        _token(), [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW
    )
    assert claims.artifact_id == ARTIFACT
    assert claims.user_id == USER
    assert claims.expires_at == EXPIRES
    assert claims.key_id == signing_key_id(KEY)
    assert claims.purpose == "download"


def test_a_legacy_v1_token_still_verifies():
    expiry = int(EXPIRES.timestamp())
    message = f"v1.{ARTIFACT}.{USER}.{expiry}".encode("utf-8")
    digest = hmac.new(KEY.encode("utf-8"), message, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    token = f"v1.{ARTIFACT}.{expiry}.{signature}"

    claims = verify_artifact_token(
        token, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW
    )

    assert claims.expires_at == EXPIRES
    assert claims.key_id == signing_key_id(KEY)
    assert claims.purpose == "download"


def test_signing_requires_an_aware_expiry():
    with pytest.raises(ValueError):
        sign_artifact_token(ARTIFACT, USER, datetime(2026, 9, 12, 10, 0), KEY)


@pytest.mark.parametrize("identifier", ["", "avec.point", "x" * 200])
def test_signing_refuses_an_unusable_identifier(identifier: str):
    with pytest.raises(ValueError):
        sign_artifact_token(identifier, USER, EXPIRES, KEY)
    with pytest.raises(ValueError):
        sign_artifact_token(ARTIFACT, identifier, EXPIRES, KEY)


def test_signing_without_a_key_is_reported_as_not_configured():
    with pytest.raises(ArtifactSigningNotConfigured):
        sign_artifact_token(ARTIFACT, USER, EXPIRES, "")


def test_signing_refuses_an_unknown_purpose():
    with pytest.raises(ValueError):
        sign_artifact_token(
            ARTIFACT, USER, EXPIRES, KEY, purpose="other"  # type: ignore[arg-type]
        )


def test_verifying_without_a_key_is_reported_as_not_configured():
    with pytest.raises(ArtifactSigningNotConfigured) as excinfo:
        verify_artifact_token(_token(), [], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    assert "non configuré" in str(excinfo.value)


# --- refus --------------------------------------------------------------------


def test_an_expired_token_is_refused_as_expired():
    with pytest.raises(ArtifactTokenExpired):
        verify_artifact_token(
            _token(),
            [KEY],
            artifact_id=ARTIFACT,
            user_id=USER,
            now=EXPIRES + timedelta(seconds=1),
        )


def test_a_token_expiring_exactly_now_is_refused():
    with pytest.raises(ArtifactTokenExpired):
        verify_artifact_token(
            _token(), [KEY], artifact_id=ARTIFACT, user_id=USER, now=EXPIRES
        )


def test_a_token_signed_by_a_retired_key_is_refused():
    token = _token(RETIRED_KEY)
    with pytest.raises(ArtifactTokenInvalid) as excinfo:
        verify_artifact_token(
            token, [KEY, ROTATED_KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW
        )
    assert not isinstance(excinfo.value, ArtifactTokenExpired)


def test_a_key_still_in_rotation_keeps_verifying():
    token = _token(ROTATED_KEY)
    claims = verify_artifact_token(
        token, [KEY, ROTATED_KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW
    )
    assert claims.key_id == signing_key_id(ROTATED_KEY)


def test_a_tampered_signature_is_refused():
    token = _token()
    head, signature = token.rsplit(".", 1)
    altered = "b" if signature[0] != "b" else "c"
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(
            f"{head}.{altered}{signature[1:]}",
            [KEY],
            artifact_id=ARTIFACT,
            user_id=USER,
            now=NOW,
        )


def test_a_tampered_expiry_is_refused():
    version, artifact, _, purpose, nonce, signature = _token().split(".")
    forged = (
        f"{version}.{artifact}.{int(EXPIRES.timestamp()) + 86400}."
        f"{purpose}.{nonce}.{signature}"
    )
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(
            forged,
            [KEY],
            artifact_id=ARTIFACT,
            user_id=USER,
            now=EXPIRES + timedelta(hours=1),
        )


def test_a_token_bound_to_another_artifact_is_refused():
    token = _token(artifact=OTHER_ARTIFACT)
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(token, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)


def test_swapping_the_artifact_in_the_token_is_refused():
    version, _, expiry, purpose, nonce, signature = _token().split(".")
    forged = f"{version}.{OTHER_ARTIFACT}.{expiry}.{purpose}.{nonce}.{signature}"
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(
            forged, [KEY], artifact_id=OTHER_ARTIFACT, user_id=USER, now=NOW
        )


def test_a_token_bound_to_another_user_is_refused():
    token = _token(user=OTHER_USER)
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(token, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)


def test_swapping_the_purpose_is_refused():
    version, artifact, expiry, _, nonce, signature = _token().split(".")
    forged = f"{version}.{artifact}.{expiry}.preview.{nonce}.{signature}"
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(
            forged, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW
        )


@pytest.mark.parametrize(
    "token",
    [
        "",
        "v1",
        "v1.artefact.1789200000",
        "v2." + ARTIFACT + ".1789200000.signature",
        f"v1.{ARTIFACT}.pas-un-entier.signature",
        f"v1.{ARTIFACT}.1789200000.signature.en-trop",
        "v1..1789200000.signature",
        # Signature non ASCII : « ?token=v1.<id>.<exp>.%C3%A9AAAA » suffit à la
        # produire depuis la chaîne de requête, sans authentification.
        f"v1.{ARTIFACT}.1789200000.éAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        f"v1.{ARTIFACT}.1789200000.é",
        # Caractère de remplacement : ce que produit un octet UTF-8 invalide
        # percent-encodé puis décodé par le serveur.
        f"v1.{ARTIFACT}.1789200000.�AAAA",
        # Substitut isolé : décodage « surrogateescape » d'une requête malformée.
        f"v1.{ARTIFACT}.1789200000.\ud800AAAA",
    ],
)
def test_a_malformed_token_is_refused_without_crashing(token: str):
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(token, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    # La route calcule aussi l'empreinte pour retrouver le lien : elle doit rendre une
    # valeur qui ne correspondra à aucune ligne, jamais lever sur une entrée de requête.
    assert len(token_hash(token)) == 64


def test_a_non_ascii_signature_is_refused_and_never_raises_type_error():
    """``hmac.compare_digest`` refuse les ``str`` non ASCII.

    Sans garde, la comparaison lève un ``TypeError`` — donc un 500 — sur une
    valeur de chaîne de requête non authentifiée. Le refus doit rester un
    ``ArtifactTokenInvalid`` comme pour n'importe quel autre jeton illisible.
    """

    forged = (
        f"{TOKEN_VERSION}.{ARTIFACT}.1789200000.download.{'A' * 24}.é"
        + "A" * 42
    )
    with pytest.raises(ArtifactTokenInvalid) as excinfo:
        verify_artifact_token(forged, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    assert not isinstance(excinfo.value, ArtifactTokenExpired)


def test_a_non_ascii_signature_is_refused_before_any_comparison(monkeypatch):
    """Le refus précède la boucle de rotation : aucune clé n'est sollicitée."""

    calls: list[int] = []
    original = hmac.compare_digest
    monkeypatch.setattr(
        signing.hmac,
        "compare_digest",
        lambda left, right: (calls.append(1), original(left, right))[1],
    )
    forged = (
        f"{TOKEN_VERSION}.{ARTIFACT}.1789200000.download.{'A' * 24}.é"
        + "A" * 42
    )
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(forged, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    assert calls == []


def test_a_non_ascii_artifact_segment_is_refused_without_crashing():
    """Le segment d'artefact non ASCII est refusé avant toute comparaison HMAC."""

    forged = (
        f"{TOKEN_VERSION}.artefact-é.1789200000.download.{'A' * 24}.AAAA"
    )
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(
            forged, [KEY], artifact_id="artefact-é", user_id=USER, now=NOW
        )


def test_an_oversized_token_is_refused_before_any_hashing(monkeypatch):
    """Un jeton absurde ne doit pas coûter une empreinte par clé en rotation."""

    calls: list[int] = []
    original = hmac.compare_digest
    monkeypatch.setattr(
        signing.hmac,
        "compare_digest",
        lambda left, right: (calls.append(1), original(left, right))[1],
    )
    forged = f"v1.{ARTIFACT}.1789200000." + "A" * 10_000
    with pytest.raises(ArtifactTokenInvalid):
        verify_artifact_token(forged, [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    assert calls == []


def test_the_comparison_is_constant_time(monkeypatch):
    calls: list[int] = []
    original = hmac.compare_digest

    def counting(left, right):
        calls.append(1)
        return original(left, right)

    monkeypatch.setattr(signing.hmac, "compare_digest", counting)
    verify_artifact_token(_token(), [KEY], artifact_id=ARTIFACT, user_id=USER, now=NOW)
    assert calls


# --- empreinte stockée --------------------------------------------------------


def test_token_hash_is_a_sha256_that_never_contains_the_token():
    token = _token()
    digest = token_hash(token)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert token not in digest
    assert digest == token_hash(token)
    assert digest != token_hash(_token(artifact=OTHER_ARTIFACT))


# --- bornes de durée ----------------------------------------------------------


def test_link_ttl_bounds_are_the_documented_ones():
    assert DEFAULT_LINK_TTL_SECONDS == 300
    assert MAX_LINK_TTL_SECONDS == 900
