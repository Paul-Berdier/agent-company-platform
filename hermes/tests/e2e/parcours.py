"""Parcours de connexion partagé par les tests navigateur (hermes/tests/e2e), factorisé depuis le test
de P2 (test_connexion_navigateur.py) : Chromium à travers le bord TLS factice, vrai Authelia,
authentificateur WebAuthn VIRTUEL (CTAP2, vérification de l'utilisateur).

1. https://hermes-acp.test/ renvoie (connexion automatique) vers le portail https://identite-acp.test ;
2. mot de passe, puis enrôlement de la passkey : code à usage unique lu dans /config/notification.txt ;
3. second facteur par la passkey (le compteur de signatures augmente) ;
4. consentement explicite, retour vers Hermes, session ouverte.

Captures (relecture de P3) : chaque capture attend que la page soit rendue (formulaire du portail,
bouton du consentement), est refusée si elle est uniforme (page blanche), et couvre TOUT le contenu :
Hermes fait défiler ses pages dans un conteneur interne, que « full_page » ne déroule pas ; la
fenêtre est agrandie à la hauteur de ce contenu le temps de la capture, puis rétablie.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from conftest import manque
from pile_identite import EMETTEUR, HOTE_HERMES, HOTE_IDENTITE, MOT_DE_PASSE, URL_HERMES, UTILISATEUR, docker

Capture = Callable[[str], None]

# ------------------------------------------------------------------ pages d'ACP (P3, partagé en P4)

RACINE = Path(__file__).resolve().parents[3]
INTERFACE = RACINE / "apps" / "interface"
AXE = INTERFACE / "node_modules" / "axe-core" / "axe.min.js"

FORMATS: Dict[str, dict] = {
    "telephone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True,
                  "device_scale_factor": 2},
    "bureau": {"viewport": {"width": 1440, "height": 900}},
}
PAGES_NATIVES = (("sessions", "/sessions"), ("discussion", "/chat"), ("skills", "/skills"), ("mcp", "/mcp"),
                 ("kanban", "/kanban"), ("configuration", "/config"))
CIBLE_MINIMALE = 44

JS_HORS_CATALOGUE = """(catalogue) => {
  const connus = new Set(catalogue);
  const hors = [];
  for (const racine of document.querySelectorAll('[data-acp-racine]')) {
    const parcours = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
    let noeud;
    while ((noeud = parcours.nextNode())) {
      const texte = (noeud.textContent || '').trim();
      if (!texte || connus.has(texte)) continue;
      if (noeud.parentElement && noeud.parentElement.closest('[data-acp-donnee]')) continue;
      hors.push(texte);
    }
  }
  return hors;
}"""

JS_CIBLES = """(racine) => [...document.querySelectorAll(racine + ' a, ' + racine + ' button, ' + racine
  + ' select, ' + racine + ' summary')].filter((e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden';
  }).map((e) => {
    const r = e.getBoundingClientRect();
    return {texte: (e.textContent || '').trim().slice(0, 40), largeur: Math.round(r.width),
            hauteur: Math.round(r.height)};
  })"""

JS_AXE = """async (selecteur) => {
  const resultat = await axe.run(document.querySelector(selecteur), {resultTypes: ['violations']});
  return resultat.violations.map((v) => ({id: v.id, impact: v.impact, noeuds: v.nodes.length, aide: v.help}));
}"""


def catalogue_francais() -> List[str]:
    node = shutil.which("node")
    if node is None:
        manque("Node.js est introuvable : il exporte le catalogue des chaînes (apps/interface)")
    sortie = subprocess.run([node, "--experimental-strip-types", str(INTERFACE / "outils" / "exporter-chaines.mjs")],
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert sortie.returncode == 0, sortie.stderr
    return sorted({v.strip() for v in json.loads(sortie.stdout).values()})


def attendre_page_acp(page, racine: str) -> None:
    page.wait_for_selector(f'[data-acp-racine="{racine}"] h1')
    # Plus aucun « Chargement… » : toutes les données demandées sont arrivées (ou en erreur, dit).
    page.wait_for_function("(r) => { const e = document.querySelector('[data-acp-racine=\"' + r + '\"]');"
                           " return e && !e.textContent.includes('Chargement'); }", arg=racine)


def verifier_page_acp(page, racine: str, format_: str, catalogue: List[str]) -> Dict[str, object]:
    hors = page.evaluate(JS_HORS_CATALOGUE, catalogue)
    if not page.evaluate("typeof window.axe !== 'undefined'"):
        page.add_script_tag(path=str(AXE))
    violations = page.evaluate(JS_AXE, f'[data-acp-racine="{racine}"]')
    cibles = page.evaluate(JS_CIBLES, f'[data-acp-racine="{racine}"]')
    petites = [c for c in cibles if c["largeur"] < CIBLE_MINIMALE or c["hauteur"] < CIBLE_MINIMALE]
    bilan = {"textes_hors_catalogue": hors, "violations_axe": violations, "cibles": len(cibles),
             "cibles_sous_44px": petites}
    assert hors == [], (racine, format_, hors)
    graves = [v for v in violations if v["impact"] in ("serious", "critical")]
    assert graves == [], (racine, format_, graves)
    if format_ == "telephone":
        assert cibles and petites == [], (racine, petites)
    return bilan


# Plus grand débordement vertical (scrollHeight - clientHeight) des conteneurs défilants de la page.
JS_DEBORDEMENT = """() => {
  let max = 0;
  for (const e of document.querySelectorAll('*')) {
    const style = getComputedStyle(e);
    if (!/(auto|scroll)/.test(style.overflowY) || e.clientHeight === 0) continue;
    max = Math.max(max, e.scrollHeight - e.clientHeight);
  }
  return max;
}"""
HAUTEUR_MAXIMALE = 16_000


def png_uniforme(donnees: bytes) -> bool:
    """Vrai si une capture PNG est d'une seule teinte (page blanche) : les données d'image
    décompressées comptent moins de 8 octets distincts (une page rendue, texte lissé compris, en
    compte des dizaines). Bibliothèque standard seulement."""
    if donnees[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("capture : ce n'est pas un PNG")
    position, idat = 8, b""
    while position < len(donnees):
        (longueur,) = struct.unpack(">I", donnees[position:position + 4])
        if donnees[position + 4:position + 8] == b"IDAT":
            idat += donnees[position + 8:position + 8 + longueur]
        position += 12 + longueur
    return len(set(zlib.decompress(idat))) < 8


def capturer_pleine_page(page, chemin: Path) -> Dict[str, int]:
    """Capture de TOUT le contenu : fenêtre agrandie à la hauteur des conteneurs défilants, puis
    rétablie. Refuse une page blanche ; rend {largeur, hauteur, debordement_restant}."""
    vue = dict(page.viewport_size)
    hauteur = vue["height"]
    try:
        for _ in range(4):
            debordement = int(page.evaluate(JS_DEBORDEMENT))
            if debordement <= 1 or hauteur >= HAUTEUR_MAXIMALE:
                break
            hauteur = min(hauteur + debordement, HAUTEUR_MAXIMALE)
            page.set_viewport_size({"width": vue["width"], "height": hauteur})
            page.wait_for_timeout(300)
        debordement = int(page.evaluate(JS_DEBORDEMENT))
        page.screenshot(path=str(chemin), full_page=True)
    finally:
        page.set_viewport_size(vue)
    if png_uniforme(chemin.read_bytes()):
        raise AssertionError(f"capture {chemin.name} : page uniforme (blanche), prise avant le rendu")
    return {"largeur": vue["width"], "hauteur": hauteur, "debordement_restant": debordement}


def lancer_chromium(playwright, port: int, spki: str):
    """Chromium sans tête : les deux noms mènent au bord publié sur la boucle locale (sans toucher au
    DNS de l'hôte), et seul le certificat du bord est accepté (empreinte SPKI) : WebAuthn est refusé
    sur une page en erreur TLS."""
    return playwright.chromium.launch(headless=True, args=[
        f"--host-resolver-rules=MAP {HOTE_HERMES} 127.0.0.1:{port}, MAP {HOTE_IDENTITE} 127.0.0.1:{port}",
        f"--ignore-certificate-errors-spki-list={spki}"])


def fabrique_de_captures(dossier: Optional[str], prefixe: str = "",
                         releves: Optional[Dict[str, Dict[str, int]]] = None) -> Tuple[Capture, Dict[str, Path]]:
    """(capture(page, nom, complete=False), fichiers produits). Sans dossier, rien n'est écrit.
    ``complete`` : la capture doit couvrir tout le contenu (pages d'ACP), sinon échec ; pour une page
    native, un contenu qui dépasse encore HAUTEUR_MAXIMALE est seulement relevé (``releves``)."""
    compte = [0]
    fichiers: Dict[str, Path] = {}

    def capture(page, nom: str, complete: bool = False) -> None:
        compte[0] += 1
        if not dossier:
            return
        Path(dossier).mkdir(parents=True, exist_ok=True)
        chemin = Path(dossier) / f"{prefixe}{compte[0]:02d}-{nom}.png"
        releve = capturer_pleine_page(page, chemin)
        if releves is not None:
            releves[chemin.name] = releve
        if complete:
            assert releve["debordement_restant"] <= 1, (f"capture {chemin.name} tronquée : un conteneur "
                                                        f"défilant dépasse encore de {releve}")
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
    # Le portail se charge après l'URL (« Chargement… ») : la capture attend son formulaire.
    page.wait_for_selector("#username-textfield")
    capture("portail")
    # 2. Premier facteur, puis enrôlement de la passkey.
    page.fill("#username-textfield", UTILISATEUR)
    page.fill("#password-textfield", MOT_DE_PASSE)
    page.click("#sign-in-button")
    page.wait_for_url(re.compile(r"/2fa/webauthn\?flow=openid_connect"))
    url_second_facteur = page.url
    page.wait_for_selector("#register-link")
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
    page.wait_for_selector("#openid-consent-accept")
    capture("consentement")
    [credential] = cdp.send("WebAuthn.getCredentials", {"authenticatorId": authentificateur})["credentials"]
    preuves["compteur_apres_second_facteur"] = credential["signCount"]
    assert credential["signCount"] > preuves["compteur_apres_enrolement"]
    page.click("#openid-consent-accept")
    page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/"))
    page.wait_for_selector("text=via self-hosted")
    return preuves
