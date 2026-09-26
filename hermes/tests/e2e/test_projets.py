"""Page « Projets » d'ACP (greffon acp-projets, étape P4) dans un vrai navigateur, aux formats téléphone
(390×844) et bureau (1440×900), derrière la même pile que la connexion de P2 (bord TLS factice, vrai
Authelia, passkey virtuelle : parcours.py), avec le MODÈLE FACTICE à scénarios et un POSTE SIMULÉ
(hermes/tests/outils/poste_simule.py, fonctions du greffon et API kanban : les routes machine sont P5-P6).

Parcours « lancer un projet → questions → avancement », à chaque format :

A. sans inventaire du poste : l'onglet « Projets » existe (groupe des greffons de Hermes) ; formulaire
   « Nouveau projet » : champ Dépôt DÉSACTIVÉ avec « Aucun dépôt connu… » ; lancement d'un projet sans
   dépôt ; détail : « Modèle servi : Non observé », « Poste : Non configuré » ; « Mettre en pause » puis
   « Reprendre » (état relu par l'API) ;
B. relevé FACTICE déposé par le poste simulé, présence du poste : projet SUR DÉPÔT (exploration choisie
   dans le relevé, questions au propriétaire) ; le poste simulé réclame l'exploration et pose une
   question ; la page Questions la montre et le propriétaire y RÉPOND (question fermée et carte reprise,
   relus par l'API) ;
C. le poste simulé termine les explorations : chaque projet avance jusqu'à « Terminé » (planification,
   étape Hermes et synthèse jouées par le modèle factice) ; liste et détail montrent l'avancement.
Puis, au format bureau : pause générale avec confirmation, bandeau, « Reprendre » (relu par l'API).

À chaque vue : chaque nœud de texte vient du catalogue français ou d'une donnée de l'API, axe-core sans
violation « serious » ni « critical », au téléphone chaque cible mesure 44 px au moins, et aucune
requête ne sort de l'origine du tableau de bord. Captures (ACP_E2E_CAPTURES=<répertoire>, sous-dossier
projets/) : pleine page, refusées si blanches ou tronquées ; empreintes SHA-256 imprimées.

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from conftest import CAPTURES, afficher, image, manque
from parcours import (AXE, FORMATS, attendre_page_acp, catalogue_francais, fabrique_de_captures, lancer_chromium,
                      ajouter_authentificateur, se_connecter, verifier_page_acp)
from pile_identite import URL_HERMES, docker, empreinte_argon2, monter_pile, spki_du_bord

PYTHON = "/opt/hermes/.venv/bin/python"
P = "/api/plugins/acp-poste"
SCENARIOS = "/tmp/acp-scenarios.json"
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
# Même configuration que le contrat P4 (hermes/tests/contrat/test_projets_contrat.py) : modèle factice,
# répartiteur toutes les 5 s.
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
TITRES = {
    "telephone": {"sans_depot": "Veille téléphone", "sur_depot": "Outil téléphone"},
    "bureau": {"sans_depot": "Veille bureau", "sur_depot": "Outil bureau"},
}
QUESTION = "Quelle version de Python viser ?"
REPONSE = "Python 3.12, sans dépendance externe."
GROUPE_GREFFONS = '[aria-labelledby="hermes-sidebar-plugin-nav-heading"]'
JS_EN_HAUT = "() => { for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0; }"

JS_API = """async ([methode, chemin]) => {
  const r = await fetch(chemin, {method: methode, credentials: 'include'});
  let corps = null;
  try { corps = await r.json(); } catch (e) { corps = null; }
  return {code: r.status, corps};
}"""


def appel(nom: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Étape de scénario : un outil du greffon, différé par Hermes, appelé par le pont tool_call."""
    return {"outil": "tool_call", "arguments": {"calls": [{"name": nom, "arguments": arguments or {}}]}}


def scenario(etapes: List[Dict[str, Any]], resume: str) -> Dict[str, Any]:
    return {"dans": "systeme", "etapes": etapes, "resume_final": resume}


PLAN = {"resume": "Une recherche, puis la synthèse.", "decisions": ["Sources de moins d'un an"],
        "etapes": [{"ref": "e1", "titre": "Chercher les modèles", "classe": "recherche_web",
                    "consigne": "Recenser les modèles publiés ce mois."}]}


def scenarios() -> Dict[str, Any]:
    tous: Dict[str, Any] = {}
    for titres in TITRES.values():
        for cle, titre in titres.items():
            etapes = [{"outil": "kanban_show", "arguments": {}}]
            if cle == "sans_depot":
                etapes.append(appel("poste_catalogue"))
            tous[f"rôle « planification » — projet « {titre} »"] = scenario(
                etapes + [appel("projet_planifier", PLAN)], "Plan posé : une recherche.")
            tous[f"rôle « hermes » — projet « {titre} »"] = scenario(
                [{"outil": "kanban_show", "arguments": {}}], "Recherche faite (témoin).")
            tous[f"rôle « synthese » — projet « {titre} »"] = scenario(
                [appel("projet_etat")], "Conclusion : la recherche est faite.")
    return tous


def simule(hermes: str, *arguments: str) -> Dict[str, Any]:
    """Poste SIMULÉ (outils/poste_simule.py), sous l'uid hermes, avec le HERMES_HOME du conteneur."""
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments,
                    verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def attendre(predicat: Callable[[], Any], delai: float, message: str, pas: float = 2.0) -> Any:
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def _demarrer_modele_factice(hermes: str) -> None:
    docker("exec", "-i", "-u", "hermes", hermes, "sh", "-c", f"cat > {SCENARIOS}",
           entree=json.dumps(scenarios(), ensure_ascii=False))
    lu = docker("exec", hermes, "cat", SCENARIOS).stdout
    assert json.loads(lu) == scenarios(), "fichier de scénarios du modèle factice mal écrit"
    docker("exec", "-d", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port", "18080",
           "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre(lambda: docker("exec", hermes, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "http://127.0.0.1:18080/v1/models", verifier=False).stdout.strip() == "200",
             60, "le modèle factice ne répond pas sur 127.0.0.1:18080", pas=0.5)


def _attendre_passerelle(hermes: str) -> None:
    """Le répartiteur kanban tourne dans la passerelle (dispatch_in_gateway) : elle doit être branchée."""
    def branchee():
        sortie = docker("exec", hermes, "curl", "-s", "http://127.0.0.1:9119/api/status", verifier=False).stdout
        try:
            statut = json.loads(sortie)
        except ValueError:
            return False
        serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
        return bool(statut.get("gateway_running")) and serveur.get("state") == "connected"

    attendre(branchee, 180, "la passerelle de Hermes n'est pas branchée")


def api(page, chemin: str) -> Dict[str, Any]:
    """GET d'une route d'acp-poste DEPUIS la page (cookie de session du navigateur) : l'état relu est celui
    que le serveur tient, pas celui que la page affiche."""
    return page.evaluate(JS_API, ["GET", f"{P}{chemin}"])


def _detail(page, identifiant: str) -> Dict[str, Any]:
    reponse = api(page, f"/v1/projets/{identifiant}")
    assert reponse["code"] == 200, reponse
    return reponse["corps"]["projet"]


def _valeur_de_ligne(page, libelle: str) -> str:
    """Valeur (dd) de la première ligne « libellé — valeur » de la page Projets qui porte ce libellé."""
    ligne = page.locator('[data-acp-racine="projets"] .acp-ligne').filter(
        has=page.locator("dt", has_text=re.compile(rf"^{re.escape(libelle)}$")))
    return ligne.first.locator("dd").inner_text().strip()


def _identifiant_de_l_adresse(page) -> str:
    trouve = re.search(r"[?&]projet=(p_[0-9a-f]{12})", page.url)
    assert trouve, page.url
    return trouve.group(1)


def _lancer_depuis_le_formulaire(page, titre: str, objectif: str, *, profil: str, depot: Optional[str],
                                 voie: Optional[str], moi: bool) -> str:
    page.fill("#acp-projet-titre-champ", titre)
    page.fill("#acp-projet-objectif", objectif)
    page.select_option("#acp-projet-profil", profil)
    if moi:
        page.check('input[name="acp-projet-reponses"][value="proprietaire"]')
    if depot:
        page.select_option("#acp-projet-depot", depot)
        page.wait_for_selector("#acp-projet-voie")
        if voie:
            page.select_option("#acp-projet-voie", voie)
    page.click('button[type="submit"]:has-text("Lancer le projet")')
    page.wait_for_url(re.compile(r"[?&]projet=p_[0-9a-f]{12}"))
    page.wait_for_selector("#acp-projet-titre")
    attendre_page_acp(page, "projets")
    return _identifiant_de_l_adresse(page)


def test_page_projets_telephone_et_bureau(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = catalogue_francais()
    noms = monter_pile(pile, image_identite, image_tests, empreinte_argon2(image_identite), publier=True,
                       fichiers={"config.yaml": MODELE})
    identite, hermes, port = noms["identite"], noms["hermes"], noms["port"]
    _attendre_passerelle(hermes)
    _demarrer_modele_factice(hermes)
    # Réglages de test du greffon (poste simulé) : passes de l'émetteur toutes les 5 s, poste « en ligne »
    # pendant tout le test, assez de projets actifs pour les deux formats.
    for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", "3600"), ("projets_actifs_max", "10")):
        simule(hermes, "reglage", cle, valeur)
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "projets") if CAPTURES else None
    preuves: Dict[str, Any] = {"catalogue_francais": len(catalogue), "formats": {}}
    releves_captures: Dict[str, Dict[str, int]] = {}
    fichiers: Dict[str, Path] = {}
    projets: Dict[str, Dict[str, str]] = {f: {} for f in FORMATS}

    navigateur = lancer_chromium(playwright_sync, port, spki)
    try:
        bureau = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["bureau"])
        page_bureau = bureau.new_page()
        page_bureau.set_default_timeout(60_000)
        cdp, authentificateur = ajouter_authentificateur(bureau, page_bureau)
        se_connecter(page_bureau, cdp, authentificateur, identite)
        telephone = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris",
                                           storage_state=bureau.storage_state(), **FORMATS["telephone"])
        page_tel = telephone.new_page()
        page_tel.set_default_timeout(60_000)
        pages = {"telephone": page_tel, "bureau": page_bureau}
        captures: Dict[str, Callable[..., None]] = {}
        produits: Dict[str, Dict[str, Path]] = {}
        for format_ in pages:
            captures[format_], produits[format_] = fabrique_de_captures(dossier, f"{format_}-", releves_captures)
            preuves["formats"][format_] = {"vues": {}}
        requetes: Dict[str, List[str]] = {f: [] for f in FORMATS}
        for format_, page in pages.items():
            page.on("request", lambda r, liste=requetes[format_]: liste.append(r.url))

        def verifier(format_: str, vue: str, nom_capture: str) -> None:
            page = pages[format_]
            attendre_page_acp(page, "projets")
            preuves["formats"][format_]["vues"][vue] = verifier_page_acp(page, "projets", format_, catalogue)
            # Un clic a pu faire défiler le conteneur de Hermes : la capture part du haut de la page.
            page.evaluate(JS_EN_HAUT)
            captures[format_](page, nom_capture, complete=True)

        # ------------------------------------------------------------ A. sans inventaire du poste
        for format_, page in pages.items():
            titres = TITRES[format_]
            page.goto(f"{URL_HERMES}/projets")
            attendre_page_acp(page, "projets")
            assert page.inner_text('[data-acp-racine="projets"] h1') == "Projets"
            if format_ == "bureau":
                # Onglet de la navigation de Hermes, dans le groupe des greffons, AVANT le Catalogue.
                liens = page.eval_on_selector_all(f"{GROUPE_GREFFONS} a", "els => els.map(e => e.getAttribute('href'))")
                preuves["groupe_des_greffons"] = liens
                assert "/projets" in liens and liens.index("/projets") < liens.index("/catalogue"), liens
            poste = page.inner_text("#acp-projets-poste >> xpath=..")
            assert "Non configuré" in poste and "Le poste n'a jamais été vu" in poste, poste
            notifications = page.inner_text("#acp-projets-notifications >> xpath=..")
            assert "Notifications non configurées" in notifications, notifications
            assert page.is_disabled('button:has-text("Envoyer une notification de test")')
            verifier(format_, "liste", "projets-liste")

            page.click('.acp-onglet:has-text("Nouveau projet")')
            page.wait_for_selector("#acp-projet-titre-champ")
            attendre_page_acp(page, "projets")
            assert page.is_disabled("#acp-projet-depot")
            assert "Aucun dépôt connu : le poste n'a encore publié aucun inventaire (étape P5)." in \
                page.inner_text('[data-acp-racine="projets"]').replace(" ", " ")
            assert page.locator("#acp-projet-voie").count() == 0
            verifier(format_, "nouveau_sans_inventaire", "nouveau-projet-sans-inventaire")

            identifiant = _lancer_depuis_le_formulaire(
                page, titres["sans_depot"], "Recenser les modèles de langage publiés ce mois.", profil="recherche",
                depot=None, voie=None, moi=False)
            projets[format_]["sans_depot"] = identifiant
            detail = _detail(page, identifiant)
            assert (detail["titre"], detail["depot"], detail["profil"], detail["origine"]) == (
                titres["sans_depot"], None, "recherche", "tableau_de_bord")
            page.wait_for_selector('.acp-ligne dt:text-is("Modèle servi")')
            assert _valeur_de_ligne(page, "Modèle servi") == "Non observé"
            assert _valeur_de_ligne(page, "Poste") == "Non configuré"
            verifier(format_, "detail", "projet-detail")

            page.click('button:has-text("Mettre en pause")')
            page.wait_for_selector('section[aria-labelledby="acp-projet-titre"] button:has-text("Reprendre")')
            assert _detail(page, identifiant)["etat"] == "en_pause"
            page.evaluate(JS_EN_HAUT)
            captures[format_](page, "projet-en-pause", complete=True)
            page.click('section[aria-labelledby="acp-projet-titre"] button:has-text("Reprendre")')
            page.wait_for_selector('section[aria-labelledby="acp-projet-titre"] button:has-text("Mettre en pause")')
            assert _detail(page, identifiant)["etat"] == "actif"
            preuves["formats"][format_]["pause_puis_reprise"] = "en_pause puis actif (relus par l'API)"

        # ------------------------------------------------------------ B. relevé factice, projet sur dépôt, question
        for voie in ("poste-codex", "poste-claude"):
            releve = {"voie": voie, "source": "releve_factice", "version_cli": "0.0.0-factice",
                      "releve_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                      "modeles": [{"id": f"factice-{voie[6:]}-1", "isDefault": True,
                                   "supportedReasoningEfforts": ["low", "medium", "max"],
                                   "defaultReasoningEffort": "medium", "serviceTiers": ["default"]}],
                      "depots": [{"alias": "jetable"}]}
            simule(hermes, "releve-factice", json.dumps(releve))
        simule(hermes, "presence", "poste-simule")

        for format_, page in pages.items():
            titres = TITRES[format_]
            page.goto(f"{URL_HERMES}/projets?vue=nouveau")
            attendre_page_acp(page, "projets")
            page.wait_for_selector("#acp-projet-depot:not([disabled])")
            texte = page.inner_text('[data-acp-racine="projets"]').replace(" ", " ")
            assert "Relevé factice : ces modèles viennent d'un relevé de test, pas de votre poste." in texte
            page.select_option("#acp-projet-depot", "jetable")
            page.wait_for_selector("#acp-projet-voie")
            efforts = page.eval_on_selector_all("#acp-projet-effort option", "els => els.map(e => e.value)")
            assert efforts == ["", "low", "medium"], efforts  # « max » relevé mais interdit (D39)
            verifier(format_, "nouveau_avec_releve", "nouveau-projet-sur-depot")
            identifiant = _lancer_depuis_le_formulaire(
                page, titres["sur_depot"], "Écrire outil.py dans le dépôt jetable.", profil="base", depot="jetable",
                voie="poste-claude", moi=True)
            projets[format_]["sur_depot"] = identifiant
            detail = _detail(page, identifiant)
            exploration = next(c for c in detail["cartes"] if c["role"] == "exploration")
            assert (exploration["voie"], exploration["modele"], detail["reponses"]) == (
                "poste-claude", "factice-claude-1", "proprietaire")
            assert _valeur_de_ligne(page, "Poste") == "En ligne"
            verifier(format_, "detail_sur_depot", "projet-sur-depot")

            # Le poste simulé réclame l'exploration et pose une question (politique « Moi » : escaladée).
            simule(hermes, "reclamer", detail["tableau"], exploration["carte"])
            posee = simule(hermes, "question", detail["tableau"], exploration["carte"], QUESTION)
            assert posee["etat"] == "escaladee", posee
            question = posee["question"]
            page.click('.acp-onglet:has-text("Questions")')
            page.wait_for_selector(f"#acp-reponse-{question}")
            attendre_page_acp(page, "projets")
            assert QUESTION in page.inner_text("#acp-questions-ouvertes >> xpath=..").replace(" ", " ")
            verifier(format_, "questions", "questions")
            page.fill(f"#acp-reponse-{question}", REPONSE)
            page.click(f'form:has(#acp-reponse-{question}) button[type="submit"]')
            page.wait_for_selector(f"#acp-reponse-{question}", state="detached")
            ouvertes = api(page, "/v1/questions")["corps"]["questions"]
            assert question not in [q["id"] for q in ouvertes], ouvertes
            carte = next(c for c in _detail(page, identifiant)["cartes"] if c["role"] == "exploration")
            assert carte["statut"] == "ready", carte  # reprise après la réponse
            preuves["formats"][format_]["question"] = {"id": question, "repondue_depuis_la_page": True,
                                                       "carte_apres_reponse": carte["statut"]}
            verifier(format_, "questions_repondues", "questions-repondues")

        # ------------------------------------------------------------ C. avancement jusqu'au bout
        for format_, page in pages.items():
            detail = _detail(page, projets[format_]["sur_depot"])
            exploration = next(c for c in detail["cartes"] if c["role"] == "exploration")
            simule(hermes, "reclamer", detail["tableau"], exploration["carte"])
            simule(hermes, "terminer", detail["tableau"], exploration["carte"],
                   "Carte du dépôt : un seul module, tests par pytest.")
        tous = [(f, cle, i) for f, d in projets.items() for cle, i in d.items()]

        vus: List[Any] = []

        def termines():
            details = {i: _detail(page_bureau, i) for _, _, i in tous}
            vus[:] = [{i: (d["etat"], [(c["role"], c["statut"]) for c in d["cartes"]]) for i, d in details.items()}]
            etats = {i: d["etat"] for i, d in details.items()}
            return etats if set(etats.values()) == {"termine"} else None

        debut = time.monotonic()
        try:
            etats = attendre(termines, 480, "les projets ne sont pas arrivés au bout", pas=5)
        except AssertionError as exc:
            raise AssertionError(f"{exc} ; cartes : {vus}") from None
        preuves["projets_termines_en_s"] = round(time.monotonic() - debut, 1)
        preuves["projets"] = etats
        for format_, page in pages.items():
            page.goto(f"{URL_HERMES}/projets")
            attendre_page_acp(page, "projets")
            page.wait_for_selector(".acp-projet")
            cartes = page.locator(".acp-projet")
            assert cartes.count() == 4, cartes.count()
            texte = page.inner_text('[data-acp-racine="projets"]').replace(" ", " ")
            assert texte.count("Terminé") >= 4, texte
            verifier(format_, "liste_terminee", "projets-termines")
            page.goto(f"{URL_HERMES}/projets?projet={projets[format_]['sur_depot']}")
            page.wait_for_selector("#acp-projet-titre")
            attendre_page_acp(page, "projets")
            fini = _detail(page, projets[format_]["sur_depot"])
            assert [c["statut"] for c in fini["cartes"]] == ["done"] * len(fini["cartes"]), fini["cartes"]
            assert {c["role"] for c in fini["cartes"]} == {"exploration", "planification", "hermes", "synthese"}
            assert _valeur_de_ligne(page, "Cartes faites").replace(" ", " ").startswith(
                f"{len(fini['cartes'])} sur {len(fini['cartes'])}")
            preuves["formats"][format_]["avancement"] = {c["role"]: c["statut"] for c in fini["cartes"]}
            verifier(format_, "detail_termine", "projet-termine")

        # ------------------------------------------------------------ pause générale (bureau)
        page = page_bureau
        page.goto(f"{URL_HERMES}/projets")
        attendre_page_acp(page, "projets")
        page.click('#acp-projets-pause >> xpath=.. >> button:has-text("Pause générale")')
        page.wait_for_selector('button:has-text("Confirmer la pause générale")')
        assert api(page, "/v1/projets")["corps"]["pause_generale"] is None  # rien avant la confirmation
        page.click('button:has-text("Confirmer la pause générale")')
        page.wait_for_selector("[data-acp-pause]")
        pause = api(page, "/v1/projets")["corps"]["pause_generale"]
        assert pause and pause["reason"].startswith("ACP : pause du propriétaire"), pause
        verifier("bureau", "pause_generale", "pause-generale")
        page.click("[data-acp-pause] button:has-text(\"Reprendre\")")
        page.wait_for_selector("[data-acp-pause]", state="detached")
        assert api(page, "/v1/projets")["corps"]["pause_generale"] is None
        preuves["pause_generale"] = "confirmée, bandeau, puis reprise (relues par l'API)"

        for format_ in FORMATS:
            etrangeres = sorted({u for u in requetes[format_]
                                 if not (u.startswith(f"{URL_HERMES}/") or u.startswith(("data:", "blob:")))})
            preuves["formats"][format_]["requetes"] = len(requetes[format_])
            preuves["formats"][format_]["requetes_hors_origine"] = etrangeres
            assert requetes[format_] and etrangeres == [], etrangeres
        fichiers = {**produits["telephone"], **produits["bureau"]}
        telephone.close()
    finally:
        preuves["captures"] = {nom: hashlib.sha256(chemin.read_bytes()).hexdigest()
                               for nom, chemin in sorted(fichiers.items())}
        preuves["captures_releves"] = releves_captures if dossier else {}
        afficher("page Projets en navigateur (Chromium, 390×844 et 1440×900, modèle factice, poste simulé)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
    if dossier:
        # Par format : liste, nouveau (×2), détail, en pause, sur dépôt, questions (×2), terminés, terminé ;
        # plus la pause générale au bureau.
        assert len(fichiers) == 2 * 10 + 1, sorted(fichiers)
