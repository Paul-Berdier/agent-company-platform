"""Discussion réduite d'ACP (étape P7, part D ; cahier P7 § 9.4, § 13.3) dans un vrai navigateur, derrière la même pile
que la connexion de P2 (bord TLS factice, vrai Authelia, passkey virtuelle : parcours.py), avec le modèle factice qui
appelle l'outil ``clarify``.

1. TÉLÉPHONE (390×844, session ouverte) : onglet « Discussion », « Nouvelle discussion », message « OUTIL:clarify » ; la
   question de Hermes s'affiche (choix en boutons, « recommandé » en français) ; l'adresse a pris la clé stockée de la
   session ; la page est FERMÉE sans répondre (le téléphone se verrouille) ;
2. BUREAU (1440×900) : contexte NEUF, SANS session, porteur de la même passkey ; connexion, puis file Questions : la
   discussion est « En attente d'une réponse » (session.active_list, lecture seule) ; « Ouvrir la discussion » mène à
   la page de discussion, qui reprend la session (session.resume) et y REJOUE la même question (open_requests) ;
3. le bureau choisit « outil.py », « Répondre » : le tour reprend et finit (« fin » du modèle factice) ; l'outil a rendu
   au modèle la réponse du propriétaire.

À chaque vue vérifiée : textes du catalogue ou données de l'API, axe-core sans violation « serious » ni « critical »,
cibles de 44 px au téléphone, aucune requête ni WebSocket hors de l'origine. Captures (ACP_E2E_CAPTURES/discussion/),
empreintes, relevé.

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e/test_discussion.py
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from conftest import CAPTURES, afficher, image, manque
from parcours import (AXE, FORMATS, ajouter_authentificateur, attendre_page_acp, catalogue_francais,
                      fabrique_de_captures, lancer_chromium, se_connecter, verifier_page_acp)
from pile_identite import (ENV_HERMES, EMETTEUR, MOT_DE_PASSE, URL_HERMES, UTILISATEUR, docker, empreinte_argon2,
                           env_identite, spki_du_bord)

PYTHON = "/opt/hermes/.venv/bin/python"
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
MODELE = """\
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
QUESTION = "Quel nom donner au module ?"
JS_EN_HAUT = "() => { for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0; }"
# Ordre des onglets des greffons dans la navigation de Hermes (chemins des liens, dans l'ordre du document).
JS_ONGLETS = """() => [...document.querySelectorAll('a[href]')].map((a) => new URL(a.href).pathname)
  .filter((p) => ['/discussion', '/projets', '/catalogue', '/poste'].includes(p))"""


def attendre(predicat, delai: float, message: str, pas: float = 1.0) -> Any:
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def _monter(pile, image_identite: str, image_tests: str) -> Dict[str, Any]:
    reseau = pile.reseau()
    identite = pile.lancer_identite(image_identite, env_identite(empreinte_argon2(image_identite)), reseau=reseau)
    bord, port = pile.lancer_bord(image_tests, reseau, publier=True)
    hermes = pile.lancer_hermes(image_tests, reseau, env=dict(ENV_HERMES), fichiers={"config.yaml": MODELE})
    docker("exec", "-d", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port", "18080",
           "--journal", JOURNAL_FACTICE)
    attendre(lambda: docker("exec", hermes, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "http://127.0.0.1:18080/v1/models", verifier=False).stdout.strip() == "200",
             60, "le modèle factice ne répond pas", pas=0.5)
    return {"identite": identite, "bord": bord, "port": port, "hermes": hermes}


def _resultats_clarify(hermes: str) -> List[str]:
    brut = docker("exec", hermes, "cat", JOURNAL_FACTICE, verifier=False).stdout
    entrees = [json.loads(l) for l in brut.splitlines() if l.strip()]
    # Un message d'outil au format OpenAI ne porte pas toujours le nom de l'outil : le résultat est reconnu à sa forme.
    return [r["contenu"] for e in entrees for r in e.get("resultats_outils") or []
            if '"user_response"' in (r.get("contenu") or "")]


def _connexion_neuve(page, url: str, cible: str) -> List[str]:
    """Contexte SANS session : l'URL mène au portail ; mot de passe, second facteur par la même passkey, consentement ;
    retour sur la cible gardée par « next ». Rend les URL traversées."""
    traversees: List[str] = []
    page.on("framenavigated", lambda f: traversees.append(f.url) if f == page.main_frame else None)
    page.goto(url)
    page.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/\?flow=openid_connect&flow_id="))
    page.wait_for_selector("#username-textfield")
    page.fill("#username-textfield", UTILISATEUR)
    page.fill("#password-textfield", MOT_DE_PASSE)
    page.click("#sign-in-button")
    page.wait_for_url(re.compile(r"/consent/openid/decision\?flow=openid_connect"))
    page.wait_for_selector("#openid-consent-accept")
    page.click("#openid-consent-accept")
    page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}{re.escape(cible)}"))
    return traversees


def test_discussion_telephone_question_reprise_au_bureau(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = catalogue_francais()
    noms = _monter(pile, image_identite, image_tests)
    identite, hermes, port = noms["identite"], noms["hermes"], noms["port"]
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "discussion") if CAPTURES else None
    preuves: Dict[str, Any] = {"catalogue_francais": len(catalogue), "vues": {}}
    releves_captures: Dict[str, Dict[str, int]] = {}
    fichiers: Dict[str, Path] = {}

    navigateur = lancer_chromium(playwright_sync, port, spki)
    try:
        requetes: Dict[str, List[str]] = {"telephone": [], "bureau": []}
        sockets: Dict[str, List[str]] = {"telephone": [], "bureau": []}

        def verifier(page, format_: str, vue: str, capture, nom: str) -> None:
            attendre_page_acp(page, "discussion" if vue.startswith("discussion") else "projets")
            racine = "discussion" if vue.startswith("discussion") else "projets"
            preuves["vues"][f"{format_}:{vue}"] = verifier_page_acp(page, racine, format_, catalogue)
            page.evaluate(JS_EN_HAUT)
            capture(page, nom, complete=True)

        # ------------------------------------------------------------ 1. téléphone : question posée, page fermée
        telephone = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["telephone"])
        page_tel = telephone.new_page()
        page_tel.set_default_timeout(60_000)
        cdp_tel, auth_tel = ajouter_authentificateur(telephone, page_tel)
        se_connecter(page_tel, cdp_tel, auth_tel, identite)
        capture_tel, produits_tel = fabrique_de_captures(dossier, "telephone-", releves_captures)
        page_tel.on("request", lambda r: requetes["telephone"].append(r.url))
        page_tel.on("websocket", lambda w: sockets["telephone"].append(w.url))
        page_tel.goto(f"{URL_HERMES}/discussion")
        attendre_page_acp(page_tel, "discussion")
        page_tel.wait_for_selector('[data-acp-racine="discussion"] a:has-text("Nouvelle discussion")')
        verifier(page_tel, "telephone", "discussion_liste", capture_tel, "liste")
        page_tel.click('[data-acp-racine="discussion"] a:has-text("Nouvelle discussion")')
        page_tel.wait_for_selector('[data-acp-connexion="prete"]')
        assert "session=nouvelle" in page_tel.url
        page_tel.fill("#acp-discussion-message", "OUTIL:clarify")
        page_tel.click('[data-acp-racine="discussion"] button[type="submit"]:has-text("Envoyer")')
        carte_tel = page_tel.wait_for_selector("[data-acp-clarify]", timeout=180_000)
        assert QUESTION in carte_tel.inner_text().replace(" ", " ")
        cle = re.search(r"[?&]session=([A-Za-z0-9_.:-]+)", page_tel.url).group(1)
        assert cle != "nouvelle"
        preuves["cle_de_session"] = cle
        choix_tel = page_tel.eval_on_selector_all(
            "[data-acp-clarify] button.acp-choix-bouton",
            "(bs) => bs.map((b) => b.innerText.replace(/\\u00a0/g, ' ').trim())")
        preuves["choix_au_telephone"] = choix_tel
        assert choix_tel[0].startswith("outil.py") and "recommandé" in choix_tel[0] and "Recommended" not in choix_tel[0]
        verifier(page_tel, "telephone", "discussion_question", capture_tel, "question")
        [passkey] = cdp_tel.send("WebAuthn.getCredentials", {"authenticatorId": auth_tel})["credentials"]
        page_tel.close()  # le téléphone se verrouille SANS répondre

        # ------------------------------------------------------------ 2. bureau : file Questions, puis la discussion
        bureau = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["bureau"])
        page = bureau.new_page()
        page.set_default_timeout(60_000)
        cdp_bureau, auth_bureau = ajouter_authentificateur(bureau, page)
        cdp_bureau.send("WebAuthn.addCredential", {"authenticatorId": auth_bureau, "credential": {
            k: passkey[k] for k in ("credentialId", "isResidentCredential", "rpId", "privateKey", "userHandle",
                                    "signCount") if k in passkey}})
        capture_bureau, produits_bureau = fabrique_de_captures(dossier, "bureau-", releves_captures)
        page.on("request", lambda r: requetes["bureau"].append(r.url))
        page.on("websocket", lambda w: sockets["bureau"].append(w.url))
        _connexion_neuve(page, f"{URL_HERMES}/projets?vue=questions", "/projets?vue=questions")
        attendre_page_acp(page, "projets")
        lien = page.wait_for_selector(f'#acp-questions-discussions >> xpath=.. >> a[href*="session={cle}"]',
                                      timeout=60_000)
        section = page.inner_text("#acp-questions-discussions >> xpath=..").replace(" ", " ")
        assert "En attente d'une réponse" in section and cle in section
        # Onglet « Discussion » avant « Projets » dans le groupe des greffons (première occurrence : la navigation de
        # Hermes précède le contenu de la page dans le document).
        ordre = page.evaluate(JS_ONGLETS)
        preuves["onglets_des_greffons"] = ordre
        assert "/discussion" in ordre and ordre.index("/discussion") < ordre.index("/projets") < ordre.index("/catalogue")
        verifier(page, "bureau", "questions_discussion_en_attente", capture_bureau, "file-questions")
        lien.click()
        page.wait_for_url(re.compile(rf"/discussion\?session={re.escape(cle)}$"))
        carte = page.wait_for_selector("[data-acp-clarify]", timeout=60_000)
        assert QUESTION in carte.inner_text().replace(" ", " ")
        page.wait_for_selector('[data-acp-connexion="prete"]')
        assert "OUTIL:clarify" in page.inner_text('[data-acp-message="utilisateur"]')
        verifier(page, "bureau", "discussion_question_rejouee", capture_bureau, "question-rejouee")

        # ------------------------------------------------------------ 3. réponse, fin du tour
        page.click('[data-acp-clarify] button.acp-choix-bouton >> nth=0')
        assert page.get_attribute('[data-acp-clarify] button.acp-choix-bouton >> nth=0', "aria-pressed") == "true"
        page.click('[data-acp-clarify] button[type="submit"]:has-text("Répondre")')
        page.wait_for_selector("[data-acp-clarify]", state="detached")
        page.wait_for_function("() => [...document.querySelectorAll('[data-acp-message=\"hermes\"] .acp-bulle__texte')]"
                               ".some((e) => e.textContent.trim() === 'fin')", timeout=120_000)
        verifier(page, "bureau", "discussion_terminee", capture_bureau, "tour-fini")
        resultats = attendre(lambda: [r for r in _resultats_clarify(hermes) if '"user_response": "outil.py"' in r], 60,
                             "le modèle n'a pas reçu la réponse du propriétaire")
        preuves["resultat_clarify_recu_par_le_modele"] = resultats[0]

        # ------------------------------------------------------------ origine : requêtes et WebSocket
        for format_ in ("telephone", "bureau"):
            etrangeres = sorted({u for u in requetes[format_] if not (u.startswith(f"{URL_HERMES}/") or
                                                                     u.startswith(("data:", "blob:", f"{EMETTEUR}/")))})
            preuves[f"requetes_hors_origine_{format_}"] = etrangeres
            assert etrangeres == [], etrangeres
            preuves[f"websockets_{format_}"] = sorted({u.split("?")[0] for u in sockets[format_]})
            assert sockets[format_] and all(u.startswith("wss://hermes-acp.test/api/ws?") for u in sockets[format_]), \
                sockets[format_]
        fichiers = {**produits_tel, **produits_bureau}
        telephone.close()
        bureau.close()
    finally:
        preuves["captures"] = {nom: hashlib.sha256(chemin.read_bytes()).hexdigest()
                               for nom, chemin in sorted(fichiers.items())}
        preuves["captures_releves"] = releves_captures if dossier else {}
        afficher("discussion réduite en navigateur (390×844 → page fermée → 1440×900 sans session → réponse)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        if dossier:
            Path(dossier).mkdir(parents=True, exist_ok=True)
            (Path(dossier) / "releve-discussion.json").write_text(json.dumps(preuves, ensure_ascii=False, indent=2,
                                                                              default=str), encoding="utf-8")
        navigateur.close()
    if dossier:
        assert len(fichiers) == 2 + 3, sorted(fichiers)
