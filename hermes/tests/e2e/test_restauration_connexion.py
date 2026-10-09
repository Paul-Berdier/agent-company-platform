"""R3 — identité restaurée et reconnexion du propriétaire (étape P9, cahier P9 § 3.5), dans un vrai navigateur.

Pile de la vraie identité (pile_identite.py : Authelia, Hermes de test, bord TLS publié), Chromium piloté par
Playwright, authentificateur WebAuthn VIRTUEL :

1. connexion complète (mot de passe, passkey P1, consentement) → session Hermes ;
2. instantané À CHAUD T des volumes ``identite`` (/config) et ``hermes`` (/opt/data) (``docker pause`` des deux) ;
3. APRÈS T : jeton d'accès retiré et page rechargée → jeton de rafraîchissement TOURNÉ (mesuré en P2) ; enrôlement
   d'une seconde passkey P2 (sur un second authentificateur : le premier refuserait, P1 étant exclue), dont on
   prouve qu'elle ouvre une session AVANT la restauration ;
4. arrêt, restauration des deux volumes à T dans des volumes NEUFS, redémarrage (mêmes images, variables, alias) ;
5. MÊME contexte de navigateur : la réponse de Hermes est MESURÉE, jamais supposée (le jeton tourné après T est
   inconnu de la base restaurée : cas jamais mesuré avant ce test) : avec le jeton d'accès encore présent, puis sans
   lui (échange du jeton de rafraîchissement : statut d'Authelia relevé au bord, statut de Hermes). Mesuré au run
   37766187654, puis exigé (la consigne en dépend) : jeton d'accès d'avant encore accepté (200) ; sans lui, Authelia
   répond 400, Hermes efface ses cookies de session et renvoie à /login (401 ``no_cookie``), sans 503 ;
6. déconnexion (``POST /auth/logout``), puis nouvelle connexion avec P1 : ACCEPTÉE (le compteur de l'authentificateur
   dépasse celui de la base restaurée, admis) ; avec P2 seule, dans un contexte neuf : REFUSÉE (enrôlée après T) ;
7. sortie : la consigne exacte « après restauration de l'identité », écrite d'après ces mesures (CONSIGNE).

La station Qt suit la même règle (même Authelia, même jeton de rafraîchissement) ; elle n'est pas rejouée ici.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from conftest import CAPTURES, afficher, image
from parcours import ajouter_authentificateur, capturer_pleine_page, code_a_usage_unique, lancer_chromium, \
    se_connecter
from pile_identite import (EMETTEUR, HOTE_IDENTITE, MOT_DE_PASSE, URL_HERMES, UTILISATEUR, attendre_identite, docker,
                           empreinte_argon2, env_identite, lignes_du_bord, monter_pile, spki_du_bord)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contrat"))

from volumes import Archives, a_chaud, comparer_manifestes, manifeste  # noqa: E402

pytestmark = pytest.mark.restauration

# Consigne écrite d'après la mesure (run 37766187654) : le jeton d'accès émis avant la restauration reste accepté (même
# clé de signature) ; sans lui, Authelia répond 400 au jeton de rafraîchissement tourné après la sauvegarde et Hermes
# efface ses cookies puis renvoie à la connexion ; P1 (enrôlée avant) est acceptée, P2 (enrôlée après) refusée.
CONSIGNE = ("Après restauration de l'identité : chaque appareil (navigateur, téléphone, station Qt) garde sa session "
            "jusqu'à l'expiration de son jeton d'accès (une heure au plus), puis est renvoyé à la connexion ; "
            "déconnectez-vous puis reconnectez-vous sur chacun avec une passkey enrôlée avant la sauvegarde, et "
            "réenrôlez les passkeys créées après la sauvegarde.")
SESSION = ("hermes_session_at", "hermes_session_rt")  # cookies de SESSION de Hermes (pas celui du PKCE de la connexion)
CHAMPS_PASSKEY = ("credentialId", "isResidentCredential", "rpId", "privateKey", "userHandle", "signCount")


def _cookies(contexte, suffixe: str) -> List[dict]:
    return [c for c in contexte.cookies() if c["name"].endswith(suffixe)]


def _volume_de(conteneur: str, destination: str) -> str:
    return docker("inspect", "-f", "{{range .Mounts}}{{if eq .Destination \"" + destination + "\"}}{{.Name}}{{end}}"
                  "{{end}}", conteneur).stdout.strip()


def _obtenir(page, chemin: str) -> list:
    return page.evaluate("async (c) => { const r = await fetch(c, {credentials: 'same-origin'}); "
                         "return [r.status, (await r.text()).slice(0, 160)]; }", chemin)


def _connexion_passkey(page) -> str:
    """Contexte sans session : portail, mot de passe, second facteur par la passkey de l'authentificateur du contexte,
    consentement s'il est demandé. Rend l'URL d'arrivée (Hermes si la passkey est acceptée)."""
    page.goto(f"{URL_HERMES}/")
    page.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/\?flow=openid_connect&flow_id="))
    page.wait_for_selector("#username-textfield")
    page.fill("#username-textfield", UTILISATEUR)
    page.fill("#password-textfield", MOT_DE_PASSE)
    page.click("#sign-in-button")
    try:
        page.wait_for_url(re.compile(rf"(/consent/openid/decision\?flow=openid_connect)|(^{re.escape(URL_HERMES)}/)"),
                          timeout=30_000)
    except Exception:  # noqa: BLE001 — passkey refusée : la page reste sur le second facteur, c'est la mesure
        return page.url
    if "/consent/openid/decision" in page.url:
        page.wait_for_selector("#openid-consent-accept")
        page.click("#openid-consent-accept")
        page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/"))
    page.wait_for_selector("text=via self-hosted")
    return page.url


def test_identite_restauree_reconnexion_mesuree(playwright_sync, pile):
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    empreinte = empreinte_argon2(image_identite)
    noms = monter_pile(pile, image_identite, image_tests, empreinte, publier=True)
    identite, bord, hermes, reseau = (str(noms[k]) for k in ("identite", "bord", "hermes", "reseau"))
    port = int(str(noms["port"]))
    volumes = {"identite": _volume_de(identite, "/config"), "hermes": _volume_de(hermes, "/opt/data")}
    archives = Archives(pile, image_tests)
    preuves: Dict[str, Any] = {"volumes": volumes}
    etape = [0]
    navigateur = lancer_chromium(playwright_sync, port, spki_du_bord(image_tests))
    try:
        contexte = navigateur.new_context(locale="fr-FR")
        page = contexte.new_page()
        page.set_default_timeout(60_000)

        def capture(nom: str, p=page) -> None:
            etape[0] += 1
            if CAPTURES:
                Path(CAPTURES).mkdir(parents=True, exist_ok=True)
                capturer_pleine_page(p, Path(CAPTURES) / f"restauration-{etape[0]:02d}-{nom}.png")

        # 1. Connexion complète avec P1.
        cdp, auth1 = ajouter_authentificateur(contexte, page)
        preuves["P1"] = se_connecter(page, cdp, auth1, str(identite))
        [p1] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth1})["credentials"]
        rt_t = _cookies(contexte, "hermes_session_rt")[0]["value"]
        capture("session-a-t")

        # 2. Instantané à chaud T.
        with a_chaud([str(identite), str(hermes)]):
            manifestes_t = {r: manifeste(image_tests, v) for r, v in volumes.items()}
            for role, volume in volumes.items():
                archives.instantane(volume, f"T-{role}")

        # 3. Après T : jeton de rafraîchissement tourné, seconde passkey P2.
        at = _cookies(contexte, "hermes_session_at")
        contexte.clear_cookies(name=at[0]["name"])
        avant = len(lignes_du_bord(str(bord)))
        recharge = page.reload()
        page.wait_for_selector("text=via self-hosted")
        rt_apres = _cookies(contexte, "hermes_session_rt")[0]["value"]
        echanges = [l["statut"] for l in lignes_du_bord(str(bord))[avant:] if l["chemin"] == "/api/oidc/token"]
        preuves["rotation_apres_T"] = {"page": recharge.status if recharge else None, "echanges_au_jeton": echanges,
                                       "jeton_de_rafraichissement_tourne": rt_apres != rt_t}
        assert echanges == [200] and rt_apres != rt_t
        # P2 : sur un SECOND authentificateur (le premier tient P1, exclue par Authelia à l'enrôlement).
        cdp.send("WebAuthn.removeVirtualAuthenticator", {"authenticatorId": auth1})
        auth2 = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
            "isUserVerified": True, "automaticPresenceSimulation": True}})["authenticatorId"]
        page.goto(f"https://{HOTE_IDENTITE}/settings/two-factor-authentication")
        page.wait_for_selector("#webauthn-credential-add")
        codes_vus = set(re.findall(r"^\s*([A-Z0-9]{8})\s*$", docker("exec", str(identite), "cat",
                                                                       "/config/notification.txt").stdout, re.M))
        page.click("#webauthn-credential-add")
        try:
            page.wait_for_selector("#one-time-code", timeout=10_000)
            page.fill("#one-time-code", code_a_usage_unique(str(identite), codes_vus))
            page.click("#dialog-verify")
        except Exception:  # noqa: BLE001 — élévation déjà acquise : Authelia passe directement à la description
            pass
        page.fill("#webauthn-credential-description", "seconde passkey enrôlée après T")
        page.click("#dialog-next")
        page.wait_for_selector("#webauthn-credential-1-information")
        capture("p2-enrolee")
        [p2] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth2})["credentials"]
        assert p2["credentialId"] != p1["credentialId"]
        # Témoin : P2 seule ouvre une session AVANT la restauration (son refus après sera donc dû à la restauration).
        temoin = navigateur.new_context(locale="fr-FR")
        page_temoin = temoin.new_page()
        page_temoin.set_default_timeout(60_000)
        cdp_t, auth_t = ajouter_authentificateur(temoin, page_temoin)
        cdp_t.send("WebAuthn.addCredential", {"authenticatorId": auth_t,
                                              "credential": {k: p2[k] for k in CHAMPS_PASSKEY if k in p2}})
        arrivee_temoin = _connexion_passkey(page_temoin)
        preuves["P2_avant_restauration"] = {"arrivee": arrivee_temoin.split("?")[0]}
        assert arrivee_temoin.startswith(f"{URL_HERMES}/"), arrivee_temoin
        [p2] = cdp_t.send("WebAuthn.getCredentials", {"authenticatorId": auth_t})["credentials"]
        temoin.close()
        # L'authentificateur du contexte ne garde que P1 : un authentificateur virtuel refuse une seconde passkey
        # résidente du même utilisateur pour le même site (mesuré au run 37763664941 : « An error occurred trying to
        # create the credential »). P2 vit dans le contexte témoin, puis dans le contexte du refus (point 6).
        cdp.send("WebAuthn.removeCredential", {"authenticatorId": auth2, "credentialId": p2["credentialId"]})
        cdp.send("WebAuthn.addCredential", {"authenticatorId": auth2,
                                            "credential": {k: p1[k] for k in CHAMPS_PASSKEY if k in p1}})
        page.goto(f"{URL_HERMES}/")
        page.wait_for_selector("text=via self-hosted")

        # 4. Arrêt, restauration à T dans des volumes neufs, redémarrage.
        for nom in (str(hermes), str(identite)):
            docker("stop", "-t", "90", nom, delai=200)
            docker("rm", "-f", nom, delai=120)
        restaures = {role: archives.volume_restaure(f"T-{role}", f"{role}-T") for role in volumes}
        ecarts = {r: comparer_manifestes(manifestes_t[r], manifeste(image_tests, v)) for r, v in restaures.items()}
        assert ecarts == {"identite": [], "hermes": []}, ecarts
        identite = pile.lancer_identite(image_identite, env_identite(empreinte), reseau=str(reseau),
                                        volume=restaures["identite"])
        attendre_identite(identite)
        hermes = pile.lancer_hermes(image_tests, str(reseau), volume=restaures["hermes"])
        journal_identite = docker("logs", identite, verifier=False)
        assert "secrets de /config/secrets : générés : aucun ;" in journal_identite.stdout + journal_identite.stderr

        # 5. Même contexte : réponse de Hermes MESURÉE, d'abord avec le jeton d'accès présent, puis sans lui.
        avec_at = _obtenir(page, "/api/auth/me")
        at = _cookies(contexte, "hermes_session_at")
        if at:
            contexte.clear_cookies(name=at[0]["name"])
        avant = len(lignes_du_bord(str(bord)))
        rechargement = page.goto(f"{URL_HERMES}/")
        page.wait_for_timeout(3000)
        # /api/auth/me n'a de sens que depuis l'origine de Hermes : renvoyé au portail, la page n'y est plus.
        sans_at = _obtenir(page, "/api/auth/me") if page.url.startswith(f"{URL_HERMES}/") else \
            ["page hors de Hermes", page.url.split("?")[0]]
        echanges = [l["statut"] for l in lignes_du_bord(str(bord))[avant:] if l["chemin"] == "/api/oidc/token"]
        capture("apres-restauration")
        preuves["apres_restauration"] = {
            "api_auth_me_avec_le_jeton_d_acces_d_avant": avec_at,
            "page_sans_jeton_d_acces": {"statut": rechargement.status if rechargement else None,
                                        "url": page.url.split("?")[0]},
            "api_auth_me_sans_jeton_d_acces": sans_at,
            "reponse_d_authelia_au_jeton_tourne_apres_T": echanges,
            "cookies_de_session_restants": sorted(c["name"] for c in contexte.cookies() if c["name"].endswith(SESSION)),
            "autres_cookies_hermes": sorted(c["name"] for c in contexte.cookies() if "hermes_session" in c["name"]
                                            and not c["name"].endswith(SESSION))}
        # La consigne (CONSIGNE) repose sur ces mesures : si elles changent (autre version d'Authelia ou de Hermes),
        # ce test échoue et la consigne est à réécrire d'après la nouvelle mesure.
        assert avec_at[0] == 200, preuves["apres_restauration"]
        assert echanges == [400] and sans_at[0] == 401, preuves["apres_restauration"]
        assert preuves["apres_restauration"]["cookies_de_session_restants"] == [], preuves["apres_restauration"]

        # 6. Déconnexion, puis P1 acceptée ; P2 seule refusée (contexte neuf).
        if page.url.startswith(URL_HERMES):
            page.evaluate("async () => { await fetch('/auth/logout', {method: 'POST', redirect: 'manual'}); }")
        contexte.clear_cookies()
        [p1_avant] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth2})["credentials"]
        arrivee_p1 = _connexion_passkey(page)
        [p1_apres] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth2})["credentials"]
        capture("p1-acceptee")
        preuves["P1_apres_restauration"] = {"arrivee": arrivee_p1.split("?")[0],
                                            "compteur": [p1["signCount"], p1_avant["signCount"], p1_apres["signCount"]]}
        assert arrivee_p1.startswith(f"{URL_HERMES}/"), arrivee_p1
        code_moi, _ = _obtenir(page, "/api/auth/me")
        assert code_moi == 200
        refus = navigateur.new_context(locale="fr-FR")
        page_refus = refus.new_page()
        page_refus.set_default_timeout(60_000)
        cdp_r, auth_r = ajouter_authentificateur(refus, page_refus)
        cdp_r.send("WebAuthn.addCredential", {"authenticatorId": auth_r,
                                              "credential": {k: p2[k] for k in CHAMPS_PASSKEY if k in p2}})
        arrivee_p2 = _connexion_passkey(page_refus)
        page_refus.wait_for_timeout(3000)
        cookies_p2 = [c["name"] for c in refus.cookies() if c["name"].endswith(SESSION)]
        capture("p2-refusee", page_refus)
        preuves["P2_apres_restauration"] = {"arrivee": arrivee_p2.split("?")[0], "cookies_de_session": cookies_p2,
                                            "autres_cookies_hermes": [c["name"] for c in refus.cookies()
                                                                      if "hermes_session" in c["name"]
                                                                      and not c["name"].endswith(SESSION)],
                                            "texte": page_refus.inner_text("body")[:300]}
        assert not arrivee_p2.startswith(f"{URL_HERMES}/") and cookies_p2 == [], preuves["P2_apres_restauration"]
        refus.close()
        preuves["consigne"] = CONSIGNE
    finally:
        afficher("R3 — identité restaurée : reconnexion mesurée (Chromium, WebAuthn virtuel)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
