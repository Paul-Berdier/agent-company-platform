"""Contrat des comptes : ambiguïtés, données temporaires et bornes de la remise."""
from uuid import uuid4
import pytest
from acp_poste_contrat import comptes as C


def observation(**champs):
    return C.Observation(operation_id=str(uuid4()), moteur="claude_code", numero=1,
                         etat="code_disponible", motif="code", defi_id=str(uuid4()),
                         defi_type="claude_oauth_code", verification_url=champs.pop("verification_url", C.URL_CLAUDE + "?state=test"),
                         **champs)


@pytest.mark.parametrize("url", ["http://claude.com/cai/oauth/authorize?x=y", "https://claude.ai/oauth/authorize?x=y",
    "https://claude.com.evil.test/cai/oauth/authorize?x=y", "https://claude.com/cai/oauth/authorize",
    "https://claude.com/cai/oauth/authorize?", "https://claude.com/cai/oauth/authorize?x=y#",
    "https://claude.com/cai/oauth/authorize?x=y#secret", "https://evil@claude.com/cai/oauth/authorize?x=y",
    "https://claude.com:443/cai/oauth/authorize?x=y", "https://claude.com/cai/oauth/authorize/?x=y",
    "https://claude.com/cai/oauth/authorize?x=\nsecret", C.URL_CLAUDE + "?x=" + "a" * C.URL_MAX])
def test_url_claude_reste_stricte(url):
    assert not C.url_claude_valide(url)
    with pytest.raises(ValueError):
        observation(verification_url=url)


def test_defi_claude_ne_contient_pas_code_utilisateur_et_repr_cache_url():
    obs = observation()
    assert obs.defi_type == "claude_oauth_code"
    assert obs.verification_url not in repr(obs)
    with pytest.raises(ValueError):
        observation(code_utilisateur="CODE-INTERDIT")
    with pytest.raises(ValueError):
        C.Observation(operation_id=str(uuid4()), moteur="codex", numero=1, etat="code_disponible", motif="code",
                      defi_id=str(uuid4()), defi_type="claude_oauth_code", verification_url=C.URL_CODEX,
                      code_utilisateur="UNIT-TEST")


@pytest.mark.parametrize("code", ["", "x" * 2049, "é" * 1025, "ab\ncd", "ab\rcd", "ab\tcd", "ab\x00cd",
                                  "ab\x1bcd", "ab\u0085cd", "ab\u2028cd", "ab\u2029cd", "\ud800"])
def test_code_opaque_borne_en_octets_et_une_seule_ligne(code):
    assert not C.code_retour_valide(code)
    with pytest.raises(ValueError):
        C.RetourCode(defi_id=str(uuid4()), soumission_id=str(uuid4()), code=code)


def test_code_opaque_non_normalise_et_absent_repr():
    code = " CODE-FACTICE#state "
    valeur = C.RetourCode(defi_id=str(uuid4()), soumission_id=str(uuid4()), code=code)
    assert valeur.code == code and code not in repr(valeur)
    assert C.code_retour_valide("é" * 1024)
    with pytest.raises(ValueError):
        C.Commande(id=str(uuid4()), moteur="codex", action="fournir_code", limite_attente_le=100, retour_code=valeur)
    with pytest.raises(ValueError):
        C.Commande(id=str(uuid4()), moteur="claude_code", action="attendre", limite_attente_le=100, retour_code=valeur)
    with pytest.raises(ValueError):
        C.Commande(id=str(uuid4()), moteur="claude_code", action="fournir_code", limite_attente_le=100)


def test_compte_confirme_independant_annulation_et_ack_sans_defi_affichable():
    ids = {"defi_id": str(uuid4()), "soumission_id": str(uuid4())}
    obs = C.Observation(operation_id=str(uuid4()), moteur="claude_code", numero=2,
                        etat="annulee", motif="annulee", compte_connecte=True, code_transmis=ids)
    assert obs.defi_id is None and obs.code_transmis.defi_id == ids["defi_id"]
    with pytest.raises(ValueError):
        C.Observation(operation_id=str(uuid4()), moteur="claude_code", numero=2, etat="connecte", motif="connecte")
    with pytest.raises(ValueError):
        C.Observation(operation_id=str(uuid4()), moteur="codex", numero=2,
                      etat="verification", motif="verification", code_transmis=ids)
    with pytest.raises(ValueError):
        C.Reponse(protocole="acp-comptes/1")
