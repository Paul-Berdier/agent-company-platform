"""Parcours COMPLET de connexion au tableau de bord Hermes, dans un vrai navigateur (Chromium piloté
par Playwright), à travers le bord TLS factice qui imite Railway, face au vrai fournisseur Authelia
de l'image identite/ (pile décrite dans hermes/tests/contrat/pile_identite.py).

Parcours, avec un authentificateur WebAuthn VIRTUEL (protocole CTAP2, vérification de l'utilisateur) :
1. https://hermes-acp.test/ renvoie (connexion automatique) vers le portail https://identite-acp.test ;
2. mot de passe, puis enrôlement de la passkey : code à usage unique lu dans /config/notification.txt
   (notifieur « filesystem », comme le propriétaire le lira par railway ssh), description, création ;
3. second facteur par la passkey (assertion réelle : le compteur de signatures augmente) ;
4. consentement explicite (imposé par offline_access), retour vers Hermes, session ouverte ;
   mesure réseau de la méta (ce que voit Hermes derrière le bord) ;
5. RAFRAÎCHISSEMENT : le cookie du jeton d'accès est retiré, la page rechargée ; Hermes échange le
   jeton de rafraîchissement auprès d'Authelia, qui DOIT réémettre un id_token (sans quoi Hermes
   répond 503) : nouvelle session, jeton de rafraîchissement tourné ;
6. PKCE exigé : une demande « plain » ou sans défi est refusée par Authelia même session ouverte ;
7. RÉVOCATION : déconnexion ; Hermes révoque le jeton de rafraîchissement auprès d'Authelia ; réinjecté,
   il n'ouvre plus aucune session ;
8. REFUS d'un autre identifiant : le portail refuse, aucune session Hermes.

Lancement (images construites comme pour les tests de contrat) :
  ACP_IMAGE_TESTS=acp-hermes-tests:ci ACP_IMAGE_IDENTITE=acp-identite:ci \\
      python -m pytest -s -v -rA hermes/tests/e2e
Dépendances : hermes/tests/requirements-e2e.txt (hachés vérifiés) et Chromium de Playwright
(révision 1234 pour playwright 1.62.0). ACP_E2E_OBLIGATOIRE=1 (la CI) change toute absence de
Playwright ou de Chromium en ÉCHEC ; sans elle (poste local), le test est IGNORÉ avec la raison exacte.
ACP_E2E_CAPTURES=<répertoire> y dépose les captures d'écran de chaque étape.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contrat"))

from pile_identite import (  # noqa: E402
    CLIENT,
    EMETTEUR,
    HOTE_HERMES,
    HOTE_IDENTITE,
    MOT_DE_PASSE,
    URL_HERMES,
    UTILISATEUR,
    Pile,
    docker,
    empreinte_argon2,
    lignes_du_bord,
    monter_pile,
    spki_du_bord,
)

OBLIGATOIRE = os.environ.get("ACP_E2E_OBLIGATOIRE", "").strip() == "1"
CAPTURES = os.environ.get("ACP_E2E_CAPTURES", "").strip()


def afficher(titre: str, texte: str) -> None:
    print(f"\n===== {titre} =====\n{texte.rstrip()}\n", flush=True)


def _manque(raison: str) -> None:
    if OBLIGATOIRE:
        pytest.fail(f"{raison} (ACP_E2E_OBLIGATOIRE=1 : l'absence est un échec, jamais un test ignoré)", pytrace=False)
    pytest.skip(raison)


def _image(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        pytest.fail(f"{nom} n'est pas défini : ce test exige les images construites.", pytrace=False)
    return valeur


@pytest.fixture(scope="module")
def playwright_sync():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _manque(f"Playwright n'est pas installé ({exc}) : pip install --require-hashes -r "
                f"hermes/tests/requirements-e2e.txt")
    with sync_playwright() as p:
        executable = Path(p.chromium.executable_path)
        if not executable.exists():
            _manque(f"Chromium de Playwright absent ({executable}) : rien n'est téléchargé par ce test")
        yield p


@pytest.fixture(scope="module")
def pile():
    p = Pile()
    yield p
    p.nettoyer()


def _jwt(jeton: str) -> dict:
    charge = jeton.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)))


def _cookies(contexte, suffixe: str) -> List[dict]:
    return [c for c in contexte.cookies() if c["name"].endswith(suffixe)]


def _code_a_usage_unique(identite: str, deja_vus: set, delai: float = 60) -> str:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        texte = docker("exec", identite, "cat", "/config/notification.txt", verifier=False).stdout
        codes = [c for c in re.findall(r"^\s*([A-Z0-9]{8})\s*$", texte, re.M) if c not in deja_vus]
        if codes:
            return codes[-1]
        time.sleep(1)
    raise AssertionError("aucun code à usage unique dans /config/notification.txt")


def test_connexion_complete_rafraichissement_et_refus(playwright_sync, pile):
    image_tests = _image("ACP_IMAGE_TESTS")
    image_identite = _image("ACP_IMAGE_IDENTITE")
    empreinte = empreinte_argon2(image_identite)
    noms = monter_pile(pile, image_identite, image_tests, empreinte, publier=True)
    identite, bord, hermes, port = noms["identite"], noms["bord"], noms["hermes"], noms["port"]
    ip_bord = docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", bord).stdout.strip()
    spki = spki_du_bord(image_tests)
    preuves: Dict[str, object] = {"port_du_bord_sur_l_hote": port, "ip_du_bord": ip_bord}
    etape = [0]

    navigateur = playwright_sync.chromium.launch(headless=True, args=[
        # Les deux noms mènent au bord publié sur la boucle locale, sans toucher au DNS de l'hôte ;
        # le navigateur garde les URL https://hermes-acp.test et https://identite-acp.test (port 443).
        f"--host-resolver-rules=MAP {HOTE_HERMES} 127.0.0.1:{port}, MAP {HOTE_IDENTITE} 127.0.0.1:{port}",
        # Confiance au SEUL certificat du bord (empreinte SPKI), sans erreur de certificat : WebAuthn
        # est refusé sur une page en erreur TLS.
        f"--ignore-certificate-errors-spki-list={spki}"])
    try:
        contexte = navigateur.new_context(locale="fr-FR")
        page = contexte.new_page()
        page.set_default_timeout(60_000)

        def capture(nom: str, p=page) -> None:
            etape[0] += 1
            if CAPTURES:
                Path(CAPTURES).mkdir(parents=True, exist_ok=True)
                p.screenshot(path=str(Path(CAPTURES) / f"{etape[0]:02d}-{nom}.png"), full_page=True)

        def obtenir(chemin: str, p=page) -> list:
            return p.evaluate("async (c) => { const r = await fetch(c, {credentials: 'same-origin'}); "
                              "return [r.status, await r.text()]; }", chemin)

        cdp = contexte.new_cdp_session(page)
        cdp.send("WebAuthn.enable")
        authentificateur = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
            "isUserVerified": True, "automaticPresenceSimulation": True}})["authenticatorId"]

        # 1. Hermes renvoie vers le portail du fournisseur.
        page.goto(f"{URL_HERMES}/")
        page.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/\?flow=openid_connect&flow_id="))
        capture("portail")
        # 2. Premier facteur, puis enrôlement de la passkey.
        page.fill("#username-textfield", UTILISATEUR)
        page.fill("#password-textfield", MOT_DE_PASSE)
        page.click("#sign-in-button")
        page.wait_for_url(re.compile(r"/2fa/webauthn\?flow=openid_connect"))
        url_second_facteur = page.url
        capture("second-facteur-sans-appareil")
        page.click("#register-link")
        page.click("#webauthn-credential-add")
        page.wait_for_selector("#one-time-code")
        code = _code_a_usage_unique(identite, set())
        page.fill("#one-time-code", code)
        page.click("#dialog-verify")
        page.fill("#webauthn-credential-description", "authentificateur virtuel de test")
        page.click("#dialog-next")
        page.wait_for_selector("#webauthn-credential-0-information")
        capture("passkey-enrolee")
        [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
        preuves["passkey"] = {"rpId": credential["rpId"], "resident": credential["isResidentCredential"],
                              "compteur_apres_enrolement": credential["signCount"]}
        assert credential["rpId"] == HOTE_IDENTITE
        # 3. Second facteur par la passkey, 4. consentement explicite, retour vers Hermes.
        page.goto(url_second_facteur)
        page.wait_for_url(re.compile(r"/consent/openid/decision\?flow=openid_connect"))
        capture("consentement")
        [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
        preuves["passkey"]["compteur_apres_second_facteur"] = credential["signCount"]
        assert credential["signCount"] > preuves["passkey"]["compteur_apres_enrolement"]
        page.click("#openid-consent-accept")
        page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/"))
        page.wait_for_selector("text=via self-hosted")
        capture("tableau-de-bord")
        code_moi, corps_moi = obtenir("/api/auth/me")
        moi = json.loads(corps_moi)
        at = _cookies(contexte, "hermes_session_at")
        rt = _cookies(contexte, "hermes_session_rt")
        session_authelia = [c for c in contexte.cookies() if c["name"] == "authelia_session"]
        jeton = _jwt(at[0]["value"])
        code_meta, corps_meta = obtenir("/api/plugins/acp-poste/v1/meta")
        meta = json.loads(corps_meta)
        preuves["session"] = {"moi": moi, "claims": {k: jeton.get(k) for k in ("iss", "aud", "amr", "name", "email")},
                              "cookies_hermes": [{k: c[k] for k in ("name", "secure", "httpOnly", "sameSite")}
                                                 for c in at + rt],
                              "cookie_authelia": [{k: c[k] for k in ("domain", "secure", "httpOnly", "sameSite")}
                                                  for c in session_authelia],
                              "meta_reseau": meta.get("reseau"),
                              "meta_alertes_reseau": [a for a in meta.get("alertes", []) if "http" in a]}
        assert code_moi == 200 and moi["email"] == "proprietaire@acp.test" and moi["provider"] == "self-hosted"
        assert moi["display_name"] == "Propriétaire d'ACP"
        assert jeton["iss"] == EMETTEUR and jeton["aud"] == [CLIENT] and "mfa" in jeton["amr"]
        assert at and rt and all(c["httpOnly"] and c["sameSite"] == "Lax" for c in at + rt)
        assert session_authelia and session_authelia[0]["secure"] and session_authelia[0]["httpOnly"]
        assert code_meta == 200
        reseau = meta["reseau"]
        assert reseau["schema_vu"] == "http" and reseau["pair"] == ip_bord and reseau["hote"] == HOTE_HERMES
        assert reseau["entetes_transmis"] == {"x-forwarded-for": False, "x-forwarded-proto": True,
                                              "x-forwarded-host": True, "x-real-ip": True, "x-railway-edge": True}

        # 5. Rafraîchissement : jeton d'accès retiré, la page se recharge sans 503.
        ancien_at, ancien_rt = at[0]["value"], rt[0]["value"]
        avant = len(lignes_du_bord(bord))
        contexte.clear_cookies(name=at[0]["name"])
        reponse = page.reload()
        page.wait_for_selector("text=via self-hosted")
        capture("apres-rafraichissement")
        nouvel_at, nouveau_rt = _cookies(contexte, "hermes_session_at"), _cookies(contexte, "hermes_session_rt")
        echanges = [l for l in lignes_du_bord(bord)[avant:] if l["chemin"] == "/api/oidc/token"]
        code_moi2, _ = obtenir("/api/auth/me")
        preuves["rafraichissement"] = {"statut_de_la_page": reponse.status if reponse else None,
                                       "echanges_au_jeton": [(l["pair"], l["statut"]) for l in echanges],
                                       "id_token_reemis": bool(nouvel_at) and nouvel_at[0]["value"] != ancien_at,
                                       "jeton_de_rafraichissement_tourne": bool(nouveau_rt) and
                                       nouveau_rt[0]["value"] != ancien_rt,
                                       "iat": [jeton["iat"], _jwt(nouvel_at[0]["value"])["iat"] if nouvel_at else None],
                                       "api_auth_me": code_moi2}
        assert reponse is not None and reponse.status == 200
        assert [l["statut"] for l in echanges] == [200]
        assert nouvel_at and nouvel_at[0]["value"] != ancien_at
        assert _jwt(nouvel_at[0]["value"])["iss"] == EMETTEUR
        assert nouveau_rt and nouveau_rt[0]["value"] != ancien_rt
        assert code_moi2 == 200

        # 6. PKCE exigé, même session ouverte chez le fournisseur.
        def autorisation(**modifications) -> str:
            verificateur = secrets.token_urlsafe(48)
            parametres = {"response_type": "code", "client_id": CLIENT, "redirect_uri": f"{URL_HERMES}/auth/callback",
                          "scope": "openid profile email offline_access", "state": "etat-e2e",
                          "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(
                              verificateur.encode()).digest()).rstrip(b"=").decode(),
                          "code_challenge_method": "S256"}
            for cle, valeur in modifications.items():
                if valeur is None:
                    parametres.pop(cle, None)
                else:
                    parametres[cle] = valeur
            return f"{EMETTEUR}/api/oidc/authorization?{urllib.parse.urlencode(parametres)}"

        pkce: Dict[str, str] = {}
        for cas, url in (("plain", autorisation(code_challenge_method="plain", code_challenge="a" * 64)),
                         ("absent", autorisation(code_challenge=None, code_challenge_method=None))):
            page.goto(url)
            page.wait_for_url(re.compile(r"/consent/openid/decision"))
            page.click("#openid-consent-accept")
            page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/auth/callback\?"))
            capture(f"pkce-{cas}")
            pkce[cas] = page.url
            requete = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)
            assert requete.get("error") == ["invalid_request"] and "code" not in requete, (cas, page.url)
        preuves["pkce"] = {k: urllib.parse.unquote_plus(v)[:220] for k, v in pkce.items()}

        # 7. Révocation à la déconnexion.
        page.goto(f"{URL_HERMES}/")
        page.wait_for_selector("text=via self-hosted")
        rt_avant = _cookies(contexte, "hermes_session_rt")[0]
        avant = len(lignes_du_bord(bord))
        page.evaluate("async () => { await fetch('/auth/logout', {method: 'POST', redirect: 'manual'}); }")
        restants = [c["name"] for c in contexte.cookies() if c["name"].endswith(("hermes_session_at", "hermes_session_rt"))]
        revocations = [l for l in lignes_du_bord(bord)[avant:] if l["chemin"] == "/api/oidc/revocation"]
        contexte.add_cookies([{"name": rt_avant["name"], "value": rt_avant["value"], "domain": HOTE_HERMES,
                               "path": "/"}])
        avant_reinjection = len(lignes_du_bord(bord))
        code_moi3, corps_moi3 = obtenir("/api/auth/me")
        reessais = [l for l in lignes_du_bord(bord)[avant_reinjection:] if l["chemin"] == "/api/oidc/token"]
        preuves["revocation"] = {"cookies_restants": restants,
                                 "revocation": [(l["pair"], l["statut"]) for l in revocations],
                                 "jeton_revoque_reinjecte": {"api_auth_me": [code_moi3, corps_moi3[:120]],
                                                             "echange_au_jeton": [l["statut"] for l in reessais]}}
        assert restants == []
        assert [l["statut"] for l in revocations] == [200]
        # Mesuré sur 4.39.28 : Authelia répond 500 (détection de réutilisation) au lieu de 400
        # invalid_grant, et Hermes traduit tout statut autre que 400 en 503 SANS effacer ses cookies
        # (docs/refonte/identite.md, limites). L'essentiel : aucune session ne renaît.
        assert code_moi3 in (401, 503)
        assert reessais and all(l["statut"] != 200 for l in reessais)

        # 8. Un autre identifiant est refusé par le portail ; aucune session Hermes.
        autre = navigateur.new_context(locale="fr-FR")
        page_autre = autre.new_page()
        page_autre.set_default_timeout(60_000)
        page_autre.goto(f"{URL_HERMES}/")
        page_autre.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/\?flow=openid_connect"))
        page_autre.fill("#username-textfield", "intrus")
        page_autre.fill("#password-textfield", MOT_DE_PASSE)
        page_autre.click("#sign-in-button")
        page_autre.wait_for_selector("text=Nom d'utilisateur ou mot de passe incorrect")
        capture("autre-identifiant-refuse", page_autre)
        preuves["autre_identifiant"] = {"url": page_autre.url.split("&flow_id=")[0],
                                        "cookies_hermes": [c["name"] for c in autre.cookies()
                                                           if c["name"].endswith(("hermes_session_at",
                                                                                  "hermes_session_rt"))]}
        assert page_autre.url.startswith(f"{EMETTEUR}/")
        assert preuves["autre_identifiant"]["cookies_hermes"] == []
        autre.close()
    finally:
        afficher("parcours de connexion en navigateur (Chromium, WebAuthn virtuel)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
