"""Parcours de connexion partagé par les tests navigateur (hermes/tests/e2e), factorisé depuis le test
de P2 (test_connexion_navigateur.py) : Chromium à travers le bord TLS factice, vrai Authelia,
authentificateur WebAuthn VIRTUEL (CTAP2, vérification de l'utilisateur).

1. https://hermes-acp.test/ renvoie (connexion automatique) vers le portail https://identite-acp.test ;
2. mot de passe, puis enrôlement de la passkey : code à usage unique lu dans /config/notification.txt ;
3. second facteur par la passkey (le compteur de signatures augmente) ;
4. consentement explicite, retour vers Hermes, session ouverte.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from pile_identite import EMETTEUR, HOTE_HERMES, HOTE_IDENTITE, MOT_DE_PASSE, URL_HERMES, UTILISATEUR, docker

Capture = Callable[[str], None]


def lancer_chromium(playwright, port: int, spki: str):
    """Chromium sans tête : les deux noms mènent au bord publié sur la boucle locale (sans toucher au
    DNS de l'hôte), et seul le certificat du bord est accepté (empreinte SPKI) : WebAuthn est refusé
    sur une page en erreur TLS."""
    return playwright.chromium.launch(headless=True, args=[
        f"--host-resolver-rules=MAP {HOTE_HERMES} 127.0.0.1:{port}, MAP {HOTE_IDENTITE} 127.0.0.1:{port}",
        f"--ignore-certificate-errors-spki-list={spki}"])


def fabrique_de_captures(dossier: Optional[str], prefixe: str = "") -> Tuple[Capture, Dict[str, Path]]:
    """(capture(page, nom), fichiers produits). Sans dossier, rien n'est écrit."""
    compte = [0]
    fichiers: Dict[str, Path] = {}

    def capture(page, nom: str) -> None:
        compte[0] += 1
        if not dossier:
            return
        Path(dossier).mkdir(parents=True, exist_ok=True)
        chemin = Path(dossier) / f"{prefixe}{compte[0]:02d}-{nom}.png"
        page.screenshot(path=str(chemin), full_page=True)
        fichiers[chemin.name] = chemin

    return capture, fichiers


def code_a_usage_unique(identite: str, deja_vus: set, delai: float = 60) -> str:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        texte = docker("exec", identite, "cat", "/config/notification.txt", verifier=False).stdout
        codes = [c for c in re.findall(r"^\s*([A-Z0-9]{8})\s*$", texte, re.M) if c not in deja_vus]
        if codes:
            return codes[-1]
        time.sleep(1)
    raise AssertionError("aucun code à usage unique dans /config/notification.txt")


def ajouter_authentificateur(contexte, page):
    """(session CDP, identifiant) d'un authentificateur WebAuthn virtuel attaché à la page."""
    cdp = contexte.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    identifiant = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
        "isUserVerified": True, "automaticPresenceSimulation": True}})["authenticatorId"]
    return cdp, identifiant


def se_connecter(page, cdp, authentificateur: str, identite: str,
                 capture: Callable[[str], None] = lambda nom: None) -> Dict[str, object]:
    """Étapes 1 à 4 ; rend les preuves de la passkey. La page finit sur le tableau de bord de Hermes."""
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
    page.fill("#one-time-code", code_a_usage_unique(identite, set()))
    page.click("#dialog-verify")
    page.fill("#webauthn-credential-description", "authentificateur virtuel de test")
    page.click("#dialog-next")
    page.wait_for_selector("#webauthn-credential-0-information")
    capture("passkey-enrolee")
    [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
    preuves: Dict[str, object] = {"rpId": credential["rpId"], "resident": credential["isResidentCredential"],
                                  "compteur_apres_enrolement": credential["signCount"]}
    assert credential["rpId"] == HOTE_IDENTITE
    # 3. Second facteur par la passkey, 4. consentement explicite, retour vers Hermes.
    page.goto(url_second_facteur)
    page.wait_for_url(re.compile(r"/consent/openid/decision\?flow=openid_connect"))
    capture("consentement")
    [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
    preuves["compteur_apres_second_facteur"] = credential["signCount"]
    assert credential["signCount"] > preuves["compteur_apres_enrolement"]
    page.click("#openid-consent-accept")
    page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/"))
    page.wait_for_selector("text=via self-hosted")
    return preuves
