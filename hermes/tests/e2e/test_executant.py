"""Page « Poste » et page « Questions » de l'étape P6 dans un vrai navigateur, aux formats bureau (1440×900) et
téléphone (390×844), derrière la même pile que la connexion de P2 (bord TLS factice, vrai Authelia, passkey
virtuelle : parcours.py), avec un FAUX EXÉCUTANT (hermes/tests/outils/faux_executant.py, enrôlé par le faux poste)
qui parle acp-machine/1 au vrai tableau de bord.

Parcours :

A. l'exécutant est enrôlé et confirmé (routes du propriétaire appelées par la page connectée), publie l'inventaire
   Linux de l'exemple (régime B), un projet sur le dépôt jetable est lancé, et l'exécutant réclame sa carte
   d'exploration, bat et l'annonce en main ;
B. onglet Poste : « État de l'exécutant Railway », blocs Isolement (régime B mesuré, réseau non coupé, écriture Codex
   refusée), Conditions d'usage, Carte en cours (modèle demandé, statut, dernier battement), Voies fermées, Branches
   prêtes (aucune) ; aucun bouton « Pousser » ;
C. l'exécutant termine en touchant des fichiers de pilotage : la page Questions liste la revue (chemins, diff resté
   sur l'exécutant) ; au bureau, « Refuser » avec un motif renvoie la carte à l'exécutant, qui la reçoit avec le
   motif.

À chaque vue : chaque nœud de texte vient du catalogue français ou d'une donnée de l'API, axe-core sans violation
« serious » ni « critical », au téléphone chaque cible mesure 44 px au moins, et aucune requête ne sort de l'origine
du tableau de bord. Captures (ACP_E2E_CAPTURES=<répertoire>, sous-dossier executant/) : pleine page, refusées si
blanches ou tronquées ; empreintes SHA-256 imprimées.

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e/test_executant.py
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
FAUX_POSTE = "/opt/acp-tests/outils/faux_poste.py"
FAUX = "/opt/acp-tests/outils/faux_executant.py"
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
"""
JS_EN_HAUT = "() => { for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0; }"
JS_API = """async ([methode, chemin, corps]) => {
  const options = {method: methode, credentials: 'include'};
  if (corps !== null) { options.headers = {'Content-Type': 'application/json'}; options.body = JSON.stringify(corps); }
  const r = await fetch(chemin, options);
  let reponse = null;
  try { reponse = await r.json(); } catch (e) { reponse = null; }
  return {code: r.status, corps: reponse};
}"""


def outil(hermes: str, script: str, *arguments: str) -> Dict[str, Any]:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, script, *arguments, verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stdout[-1500:], sortie.stderr[-2000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def simule(hermes: str, *arguments: str) -> None:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments,
                    verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stderr[-2000:])


def api(page, methode: str, chemin: str, corps: Any = None) -> Dict[str, Any]:
    return page.evaluate(JS_API, [methode, f"{P}{chemin}", corps])


def texte_de(page, selecteur: str) -> str:
    return page.inner_text(selecteur).replace(" ", " ")


def zone(id_: str) -> str:
    return f'section[aria-labelledby="{id_}"]'


def test_executant_et_revues_bureau_et_telephone(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = catalogue_francais()
    noms = monter_pile(pile, image_identite, image_tests, empreinte_argon2(image_identite), publier=True,
                       fichiers={"config.yaml": MODELE})
    identite, hermes, port = noms["identite"], noms["hermes"], noms["port"]
    simule(hermes, "reglage", "seuil_hors_ligne_s", "3600")
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "executant") if CAPTURES else None
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

        def verifier(format_: str, racine: str, vue: str, nom_capture: str) -> None:
            p = pages[format_]
            attendre_page_acp(p, racine)
            preuves["formats"][format_]["vues"][vue] = verifier_page_acp(p, racine, format_, catalogue)
            p.evaluate(JS_EN_HAUT)
            captures[format_](p, nom_capture, complete=True)

        # ------------------------------------------------------------ A. exécutant, inventaire Linux, carte en main
        page.goto(f"{URL_HERMES}/poste")
        attendre_page_acp(page, "poste")
        cree = api(page, "POST", "/v1/poste/enrolement", {})
        assert cree["code"] == 201, cree
        enrole = outil(hermes, FAUX_POSTE, "enroler", cree["corps"]["code"], "--nom", "Exécutant Railway")
        confirme = api(page, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                 "empreinte": enrole["empreinte"]})
        assert confirme["code"] == 200, confirme
        assert outil(hermes, FAUX, "inventaire", "--regime", "B")["statut"] == 200
        projet = api(page, "POST", "/v1/projets", {
            "titre": "Outil jetable", "objectif": "Écrire un outil dans le dépôt jetable.", "depot": "jetable",
            "exploration": {"voie": "poste-claude", "modele": "opus", "effort": "low"}})
        assert projet["code"] == 201, projet
        servie = outil(hermes, FAUX, "reclamer", "--voies", "poste-claude", "--attente", "5")["corps"]["carte"]
        assert servie and servie["role"] == "exploration", servie
        assert outil(hermes, FAUX, "envoyer", "battement", "--champs",
                     json.dumps({"note": "Étape 1 : lecture du dépôt."}))["statut"] == 200
        en_cours = f"{servie['tableau']}:{servie['carte']}:{servie['run_id']}"
        outil(hermes, FAUX, "reclamer", "--voies", "poste-claude", "--en-cours", en_cours, "--attente", "5")

        # ------------------------------------------------------------ B. blocs de l'exécutant
        for format_, p in pages.items():
            p.goto(f"{URL_HERMES}/poste")
            attendre_page_acp(p, "poste")
            p.wait_for_selector("#acp-poste-isolement")
            assert "État de l'exécutant Railway" in texte_de(p, zone("acp-poste-etat"))
            isolement = texte_de(p, zone("acp-poste-isolement"))
            assert "B : bac à sable Linux refusé par la plateforme" in isolement and "Non coupé" in isolement
            assert "Refusée" in isolement and "Admise" in isolement
            assert "2026-10-01" in texte_de(p, zone("acp-poste-conditions"))
            carte = texte_de(p, zone("acp-poste-carte-en-cours"))
            assert "opus" in carte and "running" in carte and "Exploration" in carte
            assert "poste-codex" in texte_de(p, zone("acp-poste-voies-fermees"))
            assert "Aucune branche prête." in texte_de(p, zone("acp-poste-branches"))
            assert p.locator('button:has-text("Pousser")').count() == 0
            verifier(format_, "poste", "executant_carte_en_cours", "executant")

        # ------------------------------------------------------------ C. revue des fichiers de pilotage
        metadonnees = {"modele_demande": "opus", "modele_servi": "factice-servi-1", "effort": "low",
                       "palier_demande": "default", "palier_servi": None, "jetons": None, "branche": servie["branche"],
                       "base": "1" * 40, "tete": "2" * 40, "diffstat": {"fichiers": 2, "ajouts": 9, "retraits": 1},
                       "verification": {"etat": "non_executee", "code": None, "duree_s": None, "tentatives": 0,
                                        "raison": "Exploration en lecture seule : aucune vérification."},
                       "pilotage": {"touche": True, "chemins": [".github/workflows/ci.yml", "CLAUDE.md"]},
                       "regime": "B", "session_locale": True}
        revue = outil(hermes, FAUX, "envoyer", "terminer", "--champs",
                      json.dumps({"resume": "Ajout d'un contrôle de CI.", "metadonnees": metadonnees}))
        assert revue["statut"] == 200 and revue["corps"]["etat"] == "review", revue
        for format_, p in pages.items():
            p.goto(f"{URL_HERMES}/projets?vue=questions")
            attendre_page_acp(p, "projets")
            p.wait_for_selector(f'{zone("acp-questions-revues")} li')
            revues = texte_de(p, zone("acp-questions-revues"))
            assert ".github/workflows/ci.yml" in revues and "CLAUDE.md" in revues
            assert "Le diff reste sur l'exécutant" in revues
            verifier(format_, "projets", "revue_pilotage", "revue")
        champ = f"#acp-motif-revue-{servie['carte']}"
        page.fill(champ, "Ne touche pas au workflow de CI.")
        page.click(f'{zone("acp-questions-revues")} >> button:has-text("Refuser")')
        page.wait_for_selector("text=Revue refusée : la carte revient à l'exécutant avec votre motif.")
        resservie = outil(hermes, FAUX, "reclamer", "--voies", "poste-claude", "--attente", "5")["corps"]["carte"]
        assert resservie["carte"] == servie["carte"] and resservie["reprise"] is True
        assert [r["genre"] for r in resservie["reponses"]] == ["refus_revue"]
        preuves["revue_refusee_puis_resservie"] = {"carte": resservie["carte"], "reponses": resservie["reponses"]}

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
        afficher("exécutant et revues en navigateur (Chromium, 1440×900 et 390×844, faux exécutant)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
    if dossier:
        assert len(fichiers) == 2 + 2, sorted(fichiers)
