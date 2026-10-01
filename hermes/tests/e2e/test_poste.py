"""Page « Poste » d'ACP (greffon acp-poste-vues, étape P5) dans un vrai navigateur, aux formats bureau (1440×900)
et téléphone (390×844), derrière la même pile que la connexion de P2 (bord TLS factice, vrai Authelia, passkey
virtuelle : parcours.py), avec un FAUX POSTE (hermes/tests/outils/faux_poste.py) qui parle le protocole
acp-machine/1 au vrai tableau de bord.

Parcours, au format bureau :

A. poste non configuré : onglet « Poste » dans le groupe des greffons, après « Projets » ; Routage « Inconnu » ;
B. « Générer un code d'enrôlement » : le code s'affiche une fois ; après un changement de vue, il n'est plus
   dans le DOM ; le faux poste s'enrôle avec ce code ;
C. « À confirmer » : l'empreinte annoncée par la page est celle que le faux poste a recalculée ; une empreinte
   fausse est refusée (message de l'API tel quel) ; la bonne confirme ; le faux poste attend : « En ligne » ;
D. inventaire publié : cartes de l'état (compte dédié, bac à sable, connexions, dépôts) ; Routage : badges
   « Relevé du compte » et « Alias documentés », suggestion appliquée puis table validée (relue par l'API),
   entrée refusée rendue telle quelle ; Quotas : jauges et seuil.
Puis, au téléphone, les trois vues en ligne.

À chaque vue : chaque nœud de texte vient du catalogue français ou d'une donnée de l'API, axe-core sans
violation « serious » ni « critical », au téléphone chaque cible mesure 44 px au moins, et aucune requête ne
sort de l'origine du tableau de bord. Captures (ACP_E2E_CAPTURES=<répertoire>, sous-dossier poste/) : pleine
page, refusées si blanches ou tronquées ; empreintes SHA-256 imprimées.

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e/test_poste.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from conftest import CAPTURES, afficher, image, manque
from parcours import (AXE, FORMATS, attendre_page_acp, catalogue_francais, fabrique_de_captures, lancer_chromium,
                      ajouter_authentificateur, se_connecter, verifier_page_acp)
from pile_identite import URL_HERMES, docker, empreinte_argon2, monter_pile, spki_du_bord

PYTHON = "/opt/hermes/.venv/bin/python"
P = "/api/plugins/acp-poste"
FAUX = "/opt/acp-tests/outils/faux_poste.py"
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
"""
GROUPE_GREFFONS = '[aria-labelledby="hermes-sidebar-plugin-nav-heading"]'
JS_EN_HAUT = "() => { for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0; }"
JS_API = """async ([methode, chemin]) => {
  const r = await fetch(chemin, {method: methode, credentials: 'include'});
  let corps = null;
  try { corps = await r.json(); } catch (e) { corps = null; }
  return {code: r.status, corps};
}"""
RACINE = '[data-acp-racine="poste"]'


def faux(hermes: str, *arguments: str) -> Dict[str, Any]:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, FAUX, *arguments, verifier=False, delai=120)
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def simule(hermes: str, *arguments: str) -> None:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments,
                    verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stderr[-2000:])


def api(page, chemin: str) -> Dict[str, Any]:
    return page.evaluate(JS_API, ["GET", f"{P}{chemin}"])


def texte_de(page, selecteur: str) -> str:
    return page.inner_text(selecteur).replace(" ", " ")


def test_page_poste_bureau_et_telephone(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = catalogue_francais()
    noms = monter_pile(pile, image_identite, image_tests, empreinte_argon2(image_identite), publier=True,
                       fichiers={"config.yaml": MODELE})
    identite, hermes, port = noms["identite"], noms["hermes"], noms["port"]
    # Le poste reste « en ligne » pendant tout le test (une seule réclamation au début de chaque étape).
    simule(hermes, "reglage", "seuil_hors_ligne_s", "3600")
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "poste") if CAPTURES else None
    preuves: Dict[str, Any] = {"catalogue_francais": len(catalogue), "formats": {}}
    releves_captures: Dict[str, Dict[str, int]] = {}
    fichiers: Dict[str, Path] = {}

    navigateur = lancer_chromium(playwright_sync, port, spki)
    try:
        bureau = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["bureau"])
        page = bureau.new_page()
        page.set_default_timeout(60_000)
        cdp, authentificateur = ajouter_authentificateur(bureau, page)
        se_connecter(page, cdp, authentificateur, identite)
        telephone = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris",
                                           storage_state=bureau.storage_state(), **FORMATS["telephone"])
        page_tel = telephone.new_page()
        page_tel.set_default_timeout(60_000)
        pages = {"bureau": page, "telephone": page_tel}
        captures: Dict[str, Callable[..., None]] = {}
        produits: Dict[str, Dict[str, Path]] = {}
        requetes: Dict[str, List[str]] = {f: [] for f in pages}
        for format_, p in pages.items():
            captures[format_], produits[format_] = fabrique_de_captures(dossier, f"{format_}-", releves_captures)
            preuves["formats"][format_] = {"vues": {}}
            p.on("request", lambda r, liste=requetes[format_]: liste.append(r.url))

        def verifier(format_: str, vue: str, nom_capture: str) -> None:
            p = pages[format_]
            attendre_page_acp(p, "poste")
            preuves["formats"][format_]["vues"][vue] = verifier_page_acp(p, "poste", format_, catalogue)
            p.evaluate(JS_EN_HAUT)
            captures[format_](p, nom_capture, complete=True)

        # ------------------------------------------------------------ A. non configuré
        page.goto(f"{URL_HERMES}/poste")
        attendre_page_acp(page, "poste")
        assert page.inner_text(f"{RACINE} h1") == "Poste"
        liens = page.eval_on_selector_all(f"{GROUPE_GREFFONS} a", "els => els.map(e => e.getAttribute('href'))")
        preuves["groupe_des_greffons"] = liens
        assert "/poste" in liens and liens.index("/projets") < liens.index("/poste"), liens
        assert "Non configuré" in texte_de(page, "#acp-poste-etat >> xpath=..")
        verifier("bureau", "etat_non_configure", "poste-non-configure")
        page.click(f'{RACINE} a.acp-onglet:has-text("Routage")')
        page.wait_for_selector("#acp-poste-listes")
        attendre_page_acp(page, "poste")
        assert texte_de(page, "#acp-poste-listes >> xpath=..").count("Inconnu") >= 2
        verifier("bureau", "routage_inconnu", "routage-inconnu")

        # ------------------------------------------------------------ B. code à usage unique
        page.click(f'{RACINE} a.acp-onglet:has-text("Poste")')
        attendre_page_acp(page, "poste")
        page.click('button:has-text("Générer un code d\'enrôlement")')
        page.wait_for_selector("[data-acp-code]")
        code = page.inner_text("[data-acp-code] .acp-code__valeur").strip()
        assert code.startswith("acpe_") and len(code) == 48
        assert '& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" enroler' in texte_de(page, "[data-acp-code]")  # décision D68
        verifier("bureau", "code_enrolement", "poste-code")
        page.click(f'{RACINE} a.acp-onglet:has-text("Quotas")')
        attendre_page_acp(page, "poste")
        page.click(f'{RACINE} a.acp-onglet:has-text("Poste")')
        attendre_page_acp(page, "poste")
        assert page.locator("[data-acp-code]").count() == 0 and code not in page.content()
        preuves["code_oublie_apres_changement_de_vue"] = True
        enrole = faux(hermes, "enroler", code, "--nom", "Poste de navigateur")
        assert enrole["statut"] == 201 and enrole["empreinte"] == enrole["empreinte_recalculee"], enrole

        # ------------------------------------------------------------ C. confirmation
        page.reload()
        attendre_page_acp(page, "poste")
        page.wait_for_selector("#acp-poste-confirmation")
        assert "À confirmer" in texte_de(page, "#acp-poste-etat >> xpath=..")
        assert enrole["empreinte"] in texte_de(page, "#acp-poste-confirmation >> xpath=..")
        verifier("bureau", "a_confirmer", "poste-a-confirmer")
        page.fill("#acp-poste-empreinte", "0000-0000")
        page.click('#acp-poste-confirmation >> xpath=.. >> button:has-text("Confirmer le poste")')
        page.wait_for_selector('#acp-poste-confirmation >> xpath=.. >> [role="alert"]')
        assert "L'empreinte saisie ne correspond pas à celle du poste enrôlé" in texte_de(
            page, '#acp-poste-confirmation >> xpath=.. >> [role="alert"]')
        page.fill("#acp-poste-empreinte", enrole["empreinte"].lower())
        page.click('#acp-poste-confirmation >> xpath=.. >> button:has-text("Confirmer le poste")')
        page.wait_for_selector("text=Poste confirmé")
        assert api(page, "/v1/poste")["corps"]["machine"]["machine"]["etat"] == "actif"
        assert faux(hermes, "reclamer", "--attente", "5")["statut"] == 200
        assert faux(hermes, "inventaire")["statut"] == 200

        # ------------------------------------------------------------ D. en ligne : état, routage, quotas
        for format_, p in pages.items():
            p.goto(f"{URL_HERMES}/poste")
            attendre_page_acp(p, "poste")
            p.wait_for_selector("#acp-poste-bac")
            etat = texte_de(p, "#acp-poste-etat >> xpath=..")
            assert "En ligne" in etat, etat
            assert "Compte dédié acp-poste" in texte_de(p, "#acp-poste-compte >> xpath=..")
            assert "elevated" in texte_de(p, "#acp-poste-bac >> xpath=..")
            connexions = texte_de(p, "#acp-poste-connexions >> xpath=..")
            assert "Compte ChatGPT" in connexions and "Jeton reconnu" in connexions
            assert "jetable" in texte_de(p, "#acp-poste-depots >> xpath=..")
            verifier(format_, "etat_en_ligne", "poste-en-ligne")

            p.goto(f"{URL_HERMES}/poste?vue=routage")
            attendre_page_acp(p, "poste")
            p.wait_for_selector("#acp-routage-implementation")
            listes = texte_de(p, "#acp-poste-listes >> xpath=..")
            assert "Relevé du compte" in listes and "Alias documentés" in listes and "opus[1m]" in listes
            if format_ == "bureau":
                classe = "#acp-routage-implementation >> xpath=.."
                p.click(f'{classe} >> button:has-text("Appliquer la suggestion")')
                p.click('button:has-text("Valider la table")')
                p.wait_for_selector("text=Table validée.")
                table = api(p, "/v1/routage")["corps"]["classes"]["implementation"]
                assert table["etat"] == "validee" and table["entrees"][0]["modele"] == "factice-codex-1", table
                relecture = "#acp-routage-relecture >> xpath=.."
                p.click(f'{relecture} >> button:has-text("Ajouter une entrée")')
                p.select_option("#acp-routage-relecture-0-voie", "poste-claude")
                p.select_option("#acp-routage-relecture-0-modele", "opus")
                p.select_option("#acp-routage-relecture-0-effort", "max")
                p.click('button:has-text("Valider la table")')
                p.wait_for_selector("text=Entrées refusées")
                refus = texte_de(p, "#acp-poste-table >> xpath=..")
                assert "l'effort « max » est interdit par défaut" in refus, refus
                preuves["table"] = {"validee": table["entrees"], "refus_rendu": "effort « max » interdit"}
                p.reload()
                attendre_page_acp(p, "poste")
                p.wait_for_selector("#acp-routage-implementation")
            verifier(format_, "routage", "routage")

            p.goto(f"{URL_HERMES}/poste?vue=quotas")
            attendre_page_acp(p, "poste")
            p.wait_for_selector('[role="meter"]')
            jauges = p.eval_on_selector_all('#acp-quotas-poste-codex >> xpath=.. >> [role="meter"]',
                                            "els => els.map(e => e.getAttribute('aria-valuenow'))")
            assert jauges == ["41", "12"], jauges
            assert "90 %" in texte_de(p, "#acp-quotas-poste-codex >> xpath=..")
            verifier(format_, "quotas", "quotas")

        for format_ in pages:
            etrangeres = sorted({u for u in requetes[format_]
                                 if not (u.startswith(f"{URL_HERMES}/") or u.startswith(("data:", "blob:")))})
            preuves["formats"][format_]["requetes"] = len(requetes[format_])
            preuves["formats"][format_]["requetes_hors_origine"] = etrangeres
            assert requetes[format_] and etrangeres == [], etrangeres
        fichiers = {**produits["bureau"], **produits["telephone"]}
        telephone.close()
    finally:
        preuves["captures"] = {nom: hashlib.sha256(chemin.read_bytes()).hexdigest()
                               for nom, chemin in sorted(fichiers.items())}
        preuves["captures_releves"] = releves_captures if dossier else {}
        afficher("page Poste en navigateur (Chromium, 1440×900 et 390×844, faux poste)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
    if dossier:
        # Bureau : non configuré, routage inconnu, code, à confirmer, en ligne, routage, quotas ; téléphone : les
        # trois vues en ligne.
        assert len(fichiers) == 7 + 3, sorted(fichiers)
