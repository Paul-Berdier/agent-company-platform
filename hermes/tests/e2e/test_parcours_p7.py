"""Preuve « parcours » de l'étape P7 (cahier P7 § 13.3 ; corrections K2, K12, K23) dans un vrai navigateur, derrière la
même pile que la connexion de P2 (bord TLS factice, vrai Authelia, passkey virtuelle : parcours.py), avec le FAUX
EXÉCUTANT de P6 (outils/faux_executant.py), le modèle factice à scénarios et un faux ntfy en HTTPS.

1. TÉLÉPHONE (390×844, session ouverte) : enrôle l'exécutant (routes du propriétaire), lance un projet sur le dépôt
   jetable depuis le formulaire (« Qui répond » : moi), puis FERME la page ;
2. l'exécutant réclame l'exploration et pose une question : le faux ntfy reçoit la notification, dont l'en-tête
   ``Click`` est le lien profond ``https://hermes-acp.test/projets?vue=questions&q=<id>`` ;
3. BUREAU (1440×900) : contexte NEUF, SANS session (le cas du téléphone dont la session a expiré) ; un
   authentificateur porteur de la MÊME passkey ; l'URL ``Click`` mène au portail, puis, une fois connecté, sur la
   question elle-même (la porte d'authentification garde chemin et requête, ``next`` : K2), marquée (aria-current) ;
   « Répondre » ;
4. la carte repart ; l'exécutant reprend le fil (``reprise: true``), la planification (modèle factice) pose une
   implémentation, l'exécutant la termine (branche rapportée), la synthèse suit, puis la carte d'intégration ; le
   projet passe « Terminé » sur la page du bureau SANS rechargement ni sondage : chaque relecture du détail suit une
   trame du flux (journal des trames de l'onglet), la relecture de sûreté étant portée à 30 min pour ce test (K23) ;
   notification ``integration`` (K12) ;
5. le téléphone, rouvert, montre « Terminé ».

À chaque vue vérifiée : textes du catalogue ou données de l'API, axe-core sans violation « serious » ni « critical »,
cibles de 44 px au téléphone, aucune requête hors de l'origine. Captures (ACP_E2E_CAPTURES/p7/), empreintes, et relevé
des événements (trames du flux, requêtes du faux ntfy, journal du projet).

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e/test_parcours_p7.py
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from conftest import CAPTURES, afficher, image, manque
from parcours import (AXE, FORMATS, ajouter_authentificateur, attendre_page_acp, catalogue_francais,
                      fabrique_de_captures, lancer_chromium, se_connecter, verifier_page_acp)
from pile_identite import (ENV_HERMES, MOT_DE_PASSE, URL_HERMES, UTILISATEUR, EMETTEUR, docker, empreinte_argon2,
                           env_identite, spki_du_bord)

PYTHON = "/opt/hermes/.venv/bin/python"
P = "/api/plugins/acp-poste"
FAUX_POSTE = "/opt/acp-tests/outils/faux_poste.py"
FAUX = "/opt/acp-tests/outils/faux_executant.py"
SCENARIOS = "/tmp/acp-scenarios.json"
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
JOURNAL_NTFY = "/tmp/ntfy-parcours-e2e.jsonl"
MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
ENV = dict(ENV_HERMES, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test",
           ACP_NTFY_SUJET="acp_sujet_parcours_e2e_p7", ACP_NTFY_JETON="jeton-de-test-parcours-e2e")
TITRE = "Parcours téléphone"
QUESTION = "Quel nom donner au module principal ?"
REPONSE = "outil.py, sans dépendance externe."
PLAN = {"resume": "Une implémentation, puis la synthèse.", "decisions": ["Module unique outil.py"],
        "etapes": [{"ref": "e1", "titre": "Écrire outil.py", "classe": "implementation", "voie": "poste-claude",
                    "modele": "opus", "effort": "low",
                    "relecture": False, "consigne": "Écrire outil.py selon la réponse du propriétaire."}]}
JS_EN_HAUT = "() => { for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0; }"
JS_API = """async ([methode, chemin, corps]) => {
  const options = {method: methode, credentials: 'include'};
  if (corps !== null) { options.headers = {'Content-Type': 'application/json'}; options.body = JSON.stringify(corps); }
  const r = await fetch(chemin, options);
  let reponse = null;
  try { reponse = await r.json(); } catch (e) { reponse = null; }
  return {code: r.status, corps: reponse};
}"""
# Relecture de sûreté portée à 30 min (K23) : sans elle, une relecture « de sûreté » pourrait se glisser dans le compte.
INIT_RELECTURE = ("window.__ACP_FLUX_REGLAGES__ = { relectureSureteMs: 1800000 };"
                  " performance.setResourceTimingBufferSize(20000);")
JS_TRAMES = "() => { const f = window.__ACP_FLUX__ && window.__ACP_FLUX__.v1; return f ? f.trames() : null; }"
JS_MODE = "() => { const f = window.__ACP_FLUX__ && window.__ACP_FLUX__.v1; return f ? f.etat().mode : null; }"
JS_LECTURES = """(chemin) => performance.getEntriesByType('resource')
  .filter((e) => new URL(e.name).pathname === chemin)
  .map((e) => ({t: e.startTime, fin: e.responseEnd, nom: e.name}))"""


def lectures_sans_trame(lectures: List[Dict[str, Any]], trames: List[Dict[str, Any]], sujets: Set[str],
                        gestes: List[float]) -> List[Dict[str, Any]]:
    """Lectures (après la première, le montage) qui ne suivent ni une trame du flux de moins de 2 s (« etat », ou
    « changement » d'un sujet suivi), ni un geste du propriétaire de moins de 2 s (fin de sa requête d'écriture) : un
    sondage déguisé. Relecture finale de P7 (constat tests-4 c) : appliqué aussi à la liste et à la file."""
    sans_trame = []
    for rang, lecture in enumerate(lectures[1:], 1):
        t = lecture["t"]
        if any(0 <= t - g <= 2_000 for g in gestes):
            continue
        if not any(x["t"] <= t and t - x["t"] <= 2_000 and (x["evenement"] == "etat" or sujets & set(x["sujets"]))
                   for x in trames):
            sans_trame.append({"rang": rang, "t": round(t)})
    return sans_trame


def _appel(nom: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"outil": "tool_call", "arguments": {"calls": [{"name": nom, "arguments": arguments or {}}]}}


SCENARIOS_PARCOURS = {
    f"rôle « planification » — projet « {TITRE} »": {
        "dans": "systeme", "etapes": [{"outil": "kanban_show", "arguments": {}}, _appel("projet_planifier", PLAN)],
        "resume_final": "Plan posé : une implémentation."},
    f"rôle « synthese » — projet « {TITRE} »": {
        "dans": "systeme", "etapes": [_appel("projet_etat")], "resume_final": "Conclusion : outil.py écrit."},
}


def outil(hermes: str, script: str, *arguments: str) -> Dict[str, Any]:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, script, *arguments, verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stdout[-1500:], sortie.stderr[-2000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def reclamer(hermes: str, voies: str = "poste-claude") -> Optional[Dict[str, Any]]:
    reponse = outil(hermes, FAUX, "reclamer", "--voies", voies, "--attente", "5")
    assert reponse["statut"] == 200, reponse
    return reponse["corps"]["carte"]


def envoyer(hermes: str, route: str, **champs) -> Dict[str, Any]:
    return outil(hermes, FAUX, "envoyer", route, "--champs", json.dumps(champs, ensure_ascii=False))


def simule(hermes: str, *arguments: str) -> None:
    sortie = docker("exec", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments,
                    verifier=False, delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stderr[-2000:])


def api(page, methode: str, chemin: str, corps: Any = None) -> Dict[str, Any]:
    return page.evaluate(JS_API, [methode, f"{P}{chemin}", corps])


def notifications(ntfy: str) -> List[Dict[str, Any]]:
    brut = docker("exec", ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def attendre(predicat: Callable[[], Any], delai: float, message: str, pas: float = 2.0) -> Any:
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def texte_de(page, selecteur: str) -> str:
    return page.inner_text(selecteur).replace(" ", " ")


def _monter(pile, image_identite: str, image_tests: str) -> Dict[str, Any]:
    reseau = pile.reseau()
    identite = pile.lancer_identite(image_identite, env_identite(empreinte_argon2(image_identite)), reseau=reseau)
    bord, port = pile.lancer_bord(image_tests, reseau, publier=True)
    ntfy = pile.nom("ntfy")
    pile.conteneurs.append(ntfy)
    docker("run", "-d", "--name", ntfy, "--network", reseau, "--network-alias", "ntfy.acp.test", "--entrypoint", PYTHON,
           image_tests, "/opt/acp-tests/outils/notif_factice.py", "--port", "443", "--certificat",
           "/opt/acp-tests/ac/ntfy.pem", "--cle", "/opt/acp-tests/ac/ntfy.key", "--journal", JOURNAL_NTFY)
    hermes = pile.lancer_hermes(image_tests, reseau, env=ENV, fichiers={"config.yaml": MODELE})
    return {"identite": identite, "bord": bord, "port": port, "ntfy": ntfy, "hermes": hermes}


def _attendre_passerelle(hermes: str) -> None:
    def branchee():
        sortie = docker("exec", hermes, "curl", "-s", "http://127.0.0.1:9119/api/status", verifier=False).stdout
        try:
            statut = json.loads(sortie)
        except ValueError:
            return False
        serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
        return bool(statut.get("gateway_running")) and serveur.get("state") == "connected"

    attendre(branchee, 180, "la passerelle de Hermes n'est pas branchée")


def _demarrer_modele(hermes: str) -> None:
    docker("exec", "-i", "-u", "hermes", hermes, "sh", "-c", f"cat > {SCENARIOS}",
           entree=json.dumps(SCENARIOS_PARCOURS, ensure_ascii=False))
    docker("exec", "-d", "-u", "hermes", hermes, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port", "18080",
           "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre(lambda: docker("exec", hermes, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "http://127.0.0.1:18080/v1/models", verifier=False).stdout.strip() == "200",
             60, "le modèle factice ne répond pas", pas=0.5)


def _connexion_neuve(page, url: str) -> List[str]:
    """Contexte SANS session : l'URL de la notification mène au portail ; mot de passe, second facteur par la MÊME
    passkey (authentificateur virtuel du contexte), consentement ; retour sur la cible. Rend les URL traversées."""
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
    page.wait_for_url(re.compile(rf"^{re.escape(URL_HERMES)}/projets\?"))
    return traversees


def test_parcours_telephone_question_bureau_projet_termine(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = catalogue_francais()
    noms = _monter(pile, image_identite, image_tests)
    identite, hermes, ntfy, port = noms["identite"], noms["hermes"], noms["ntfy"], noms["port"]
    _attendre_passerelle(hermes)
    _demarrer_modele(hermes)
    for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", "3600")):
        simule(hermes, "reglage", cle, valeur)
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "p7") if CAPTURES else None
    preuves: Dict[str, Any] = {"catalogue_francais": len(catalogue), "vues": {}}
    releves_captures: Dict[str, Dict[str, int]] = {}
    fichiers: Dict[str, Path] = {}

    navigateur = lancer_chromium(playwright_sync, port, spki)
    try:
        # ------------------------------------------------------------ 1. téléphone : exécutant, projet lancé
        telephone = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["telephone"])
        page_tel = telephone.new_page()
        page_tel.set_default_timeout(60_000)
        cdp_tel, auth_tel = ajouter_authentificateur(telephone, page_tel)
        se_connecter(page_tel, cdp_tel, auth_tel, identite)
        capture_tel, produits_tel = fabrique_de_captures(dossier, "telephone-", releves_captures)
        requetes: Dict[str, List[str]] = {"telephone": [], "bureau": []}
        page_tel.on("request", lambda r: requetes["telephone"].append(r.url))

        def verifier(page, format_: str, racine: str, vue: str, capture, nom: str) -> None:
            attendre_page_acp(page, racine)
            preuves["vues"][f"{format_}:{vue}"] = verifier_page_acp(page, racine, format_, catalogue)
            page.evaluate(JS_EN_HAUT)
            capture(page, nom, complete=True)

        page_tel.goto(f"{URL_HERMES}/poste")
        attendre_page_acp(page_tel, "poste")
        cree = api(page_tel, "POST", "/v1/poste/enrolement", {})
        assert cree["code"] == 201, cree
        enrole = outil(hermes, FAUX_POSTE, "enroler", cree["corps"]["code"], "--nom", "Exécutant Railway")
        confirme = api(page_tel, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                     "empreinte": enrole["empreinte"]})
        assert confirme["code"] == 200, confirme
        assert outil(hermes, FAUX, "inventaire", "--regime", "B")["statut"] == 200
        page_tel.goto(f"{URL_HERMES}/projets?vue=nouveau")
        attendre_page_acp(page_tel, "projets")
        page_tel.wait_for_selector("#acp-projet-depot:not([disabled])")
        page_tel.fill("#acp-projet-titre-champ", TITRE)
        page_tel.fill("#acp-projet-objectif", "Écrire outil.py dans le dépôt jetable.")
        page_tel.select_option("#acp-projet-profil", "base")
        page_tel.select_option("#acp-projet-depot", "jetable")
        page_tel.wait_for_selector("#acp-projet-voie")
        page_tel.select_option("#acp-projet-voie", "poste-claude")
        # Le relevé de Claude ne désigne aucun modèle par défaut : la page exige un choix (aucun modèle inventé).
        page_tel.select_option("#acp-projet-modele", "opus")
        page_tel.select_option("#acp-projet-effort", "low")
        page_tel.check('input[name="acp-projet-reponses"][value="proprietaire"]')
        verifier(page_tel, "telephone", "projets", "nouveau_projet", capture_tel, "nouveau-projet")
        page_tel.click('button[type="submit"]:has-text("Lancer le projet")')
        page_tel.wait_for_url(re.compile(r"[?&]projet=p_[0-9a-f]{12}"))
        identifiant = re.search(r"[?&]projet=(p_[0-9a-f]{12})", page_tel.url).group(1)
        page_tel.wait_for_selector("#acp-projet-titre")
        verifier(page_tel, "telephone", "projets", "projet_lance", capture_tel, "projet-lance")
        # La passkey de l'authentificateur virtuel du téléphone (lié à SA page) est relevée avant de fermer la page :
        # le bureau en recevra une copie (même compte, autre appareil enregistré à l'identique).
        [passkey] = cdp_tel.send("WebAuthn.getCredentials", {"authenticatorId": auth_tel})["credentials"]
        page_tel.close()  # le téléphone se verrouille : plus aucune page ouverte
        preuves["projet"] = identifiant

        # ------------------------------------------------------------ 2. question de l'exécutant, notification
        exploration = reclamer(hermes)
        assert exploration and exploration["role"] == "exploration", exploration
        posee = envoyer(hermes, "question", texte=QUESTION, contexte="Le dépôt ne contient encore aucun module.")
        assert posee["statut"] == 200 and posee["corps"]["etat"] == "escaladee", posee
        question = posee["corps"]["question"]
        recue = attendre(lambda: [n for n in notifications(ntfy) if "une question attend votre réponse" in n["corps"]],
                         90, "notification « question » non reçue par le faux ntfy")
        lien = recue[0]["click"]
        assert lien == f"{URL_HERMES}/projets?vue=questions&q={question}", lien
        assert "#" not in lien and QUESTION not in lien
        preuves["notification_question"] = {k: recue[0][k] for k in ("corps", "click", "priority", "title")}

        # ------------------------------------------------------------ 3. bureau : contexte neuf, SANS session
        bureau = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["bureau"])
        bureau.add_init_script(INIT_RELECTURE)
        page = bureau.new_page()
        page.set_default_timeout(60_000)
        assert [c for c in bureau.cookies() if "hermes_session" in c["name"]] == []
        cdp_bureau, auth_bureau = ajouter_authentificateur(bureau, page)
        cdp_bureau.send("WebAuthn.addCredential", {"authenticatorId": auth_bureau, "credential": {
            k: passkey[k] for k in ("credentialId", "isResidentCredential", "rpId", "privateKey", "userHandle",
                                    "signCount") if k in passkey}})
        capture_bureau, produits_bureau = fabrique_de_captures(dossier, "bureau-", releves_captures)
        page.on("request", lambda r: requetes["bureau"].append(r.url))
        traversees = _connexion_neuve(page, lien)
        preuves["connexion_par_le_lien"] = {"traversees": [u.split("&flow_id=")[0][:160] for u in traversees],
                                            "arrivee": page.url}
        assert any(u.startswith(f"{EMETTEUR}/") for u in traversees)
        assert re.search(rf"[?&]vue=questions&q={question}(&|$)", page.url), page.url  # cible gardée par « next »
        attendre_page_acp(page, "projets")
        cible = page.wait_for_selector(f'li[aria-current="true"]:has(#acp-reponse-{question})')
        assert QUESTION in cible.inner_text().replace(" ", " ")
        verifier(page, "bureau", "projets", "question_ciblee", capture_bureau, "question-ciblee")
        page.wait_for_selector('[data-acp-temps-reel="temps_reel"]', timeout=20_000)
        page.fill(f"#acp-reponse-{question}", REPONSE)
        page.click(f'form:has(#acp-reponse-{question}) button[type="submit"]')
        # La question répondue quitte la file à la relecture ; le message tiré de la réponse de l'API reste annoncé par
        # la section, et la cible que la page vient de traiter n'est pas « déjà traitée » (relecture finale de P7).
        page.wait_for_selector(f"#acp-reponse-{question}", state="detached")
        annonce = page.wait_for_selector('section:has(#acp-questions-ouvertes) [role="status"]:has-text("Réponse envoyée")')
        preuves["message_de_la_reponse"] = " ".join(annonce.inner_text().replace(" ", " ").split())
        assert preuves["message_de_la_reponse"] == "Réponse envoyée : la carte reprend.", preuves["message_de_la_reponse"]
        assert page.locator('[data-acp-racine="projets"] [role="status"]:has-text("déjà été traitée")').count() == 0
        # Vers le détail du projet, DANS la page (aucun rechargement) : onglet « Projets », puis le projet. Chaque
        # changement de vue est un geste qui relit la page (instant noté pour le relevé des lectures, plus bas).
        clics = [page.evaluate("() => performance.now()")]
        page.click('.acp-onglet >> nth=0')
        page.wait_for_selector("#acp-projets-poste")
        clics.append(page.evaluate("() => performance.now()"))
        page.click(f'[data-acp-racine="projets"] a[href$="projet={identifiant}"]')
        page.wait_for_selector("#acp-projet-titre")
        navigation = page.evaluate("() => performance.getEntriesByType('navigation').length")

        # ------------------------------------------------------------ 4. reprise, implémentation, intégration
        reprise = attendre(lambda: reclamer(hermes), 60, "carte non resservie après la réponse")
        assert reprise["carte"] == exploration["carte"] and reprise["reprise"] is True
        assert [r["texte"] for r in reprise["reponses"]] == [REPONSE]
        assert envoyer(hermes, "terminer", resume="## Structure\nUn module : outil.py.")["corps"]["etat"] == "done"
        implementation = attendre(lambda: reclamer(hermes), 300, "implémentation jamais servie", pas=3)
        assert implementation["role"] == "implementation", implementation
        assert envoyer(hermes, "terminer", resume="outil.py écrit et vérifié.")["corps"]["etat"] == "done"
        integration = attendre(lambda: reclamer(hermes, "poste-claude,poste-integration"), 300,
                               "intégration jamais servie", pas=3)
        assert integration["role"] == "integration" and integration["branches_a_integrer"] == [implementation["branche"]]
        assert envoyer(hermes, "terminer", resume="Branche intégrée, vérification réussie.")["corps"]["etat"] == "done"
        debut = time.monotonic()
        page.wait_for_selector('section[aria-labelledby="acp-projet-titre"] .acp-pastille:text-is("Terminé")',
                               timeout=120_000)
        preuves["termine_vu_au_bureau_s"] = round(time.monotonic() - debut, 1)
        assert page.evaluate("() => performance.getEntriesByType('navigation').length") == navigation  # aucun rechargement
        detail = api(page, "GET", f"/v1/projets/{identifiant}")["corps"]["projet"]
        assert detail["etat"] == "termine"
        preuves["journal_du_projet"] = [{k: j.get(k) for k in ("quand", "acteur", "action", "cible")}
                                        for j in detail.get("journal", [])]
        preuves["cartes"] = [(c["role"], c["statut"], c["voie"]) for c in detail["cartes"]]
        # Chaque lecture du détail suit une trame (« etat » à l'ouverture d'un flux, ou « changement » de « projets ») :
        # aucune n'est un sondage. La première est le montage de la vue (geste du propriétaire).
        trames = page.evaluate(JS_TRAMES) or []
        lectures = page.evaluate(JS_LECTURES, f"{P}/v1/projets/{identifiant}")
        assert page.evaluate(JS_MODE) == "temps_reel"
        sans_trame = []
        for rang, lecture in enumerate(lectures[1:], 1):
            precedentes = [t for t in trames if t["t"] <= lecture["t"] and lecture["t"] - t["t"] <= 2_000
                           and (t["evenement"] == "etat" or "projets" in t["sujets"])]
            if not precedentes:
                sans_trame.append({"rang": rang, "t": round(lecture["t"])})
        preuves["releve_temps_reel"] = {
            "lectures_du_detail": len(lectures), "lectures_sans_trame": sans_trame,
            "trames": [{"t": round(t["t"]), "evenement": t["evenement"], "sujets": t["sujets"]} for t in trames[-40:]]}
        assert len(lectures) >= 2 and sans_trame == [], preuves["releve_temps_reel"]
        # Relecture finale de P7 (constat tests-4 c) : la liste des projets et la file Questions, relues sur la même page,
        # ne sondent pas non plus ; seuls la trame d'un de leurs sujets ou le geste « Répondre » les font relire.
        reponses = [g["fin"] for g in page.evaluate(JS_LECTURES, f"{P}/v1/questions/{question}/reponse")]
        gestes = reponses + clics
        listes = {}
        for chemin, sujets in ((f"{P}/v1/projets", {"projets", "questions", "poste", "notifications", "pause"}),
                               (f"{P}/v1/questions", {"questions", "projets", "discussions"})):
            vues = page.evaluate(JS_LECTURES, chemin)
            listes[chemin] = {"lectures": len(vues), "sans_trame": lectures_sans_trame(vues, trames, sujets, gestes)}
        preuves["releve_temps_reel"]["listes"] = listes
        assert reponses and all(v["lectures"] >= 2 and v["sans_trame"] == [] for v in listes.values()), listes
        verifier(page, "bureau", "projets", "projet_termine", capture_bureau, "projet-termine")

        # ------------------------------------------------------------ 5. le téléphone, rouvert, montre « Terminé »
        page_tel = telephone.new_page()
        page_tel.set_default_timeout(60_000)
        page_tel.on("request", lambda r: requetes["telephone"].append(r.url))
        page_tel.goto(f"{URL_HERMES}/projets?projet={identifiant}")
        page_tel.wait_for_selector('section[aria-labelledby="acp-projet-titre"] .acp-pastille:text-is("Terminé")')
        verifier(page_tel, "telephone", "projets", "projet_termine", capture_tel, "projet-termine")

        # ------------------------------------------------------------ notifications et origine
        finales = attendre(lambda: (lambda n: n if any("prête sur l'exécutant" in x["corps"] for x in n) else None)(
            [x for x in notifications(ntfy) if f"« {TITRE} »" in x["corps"]]), 90, "notification « integration »")
        preuves["notifications_du_projet"] = [{k: n[k] for k in ("corps", "click")} for n in finales]
        assert [n["click"] for n in finales if "prête sur l'exécutant" in n["corps"]] == [
            f"{URL_HERMES}/projets?projet={identifiant}"]
        assert len([n for n in finales if "une question attend votre réponse" in n["corps"]]) == 1
        assert not any("cartes faites" in n["corps"] for n in finales)  # K12 : « integration », pas « termine »
        for format_, liste in requetes.items():
            etrangeres = sorted({u for u in liste if not (u.startswith(f"{URL_HERMES}/") or
                                                          u.startswith(("data:", "blob:", f"{EMETTEUR}/")))})
            preuves[f"requetes_hors_origine_{format_}"] = etrangeres
            assert etrangeres == [], etrangeres
        fichiers = {**produits_tel, **produits_bureau}
        telephone.close()
        bureau.close()
    finally:
        preuves["captures"] = {nom: hashlib.sha256(chemin.read_bytes()).hexdigest()
                               for nom, chemin in sorted(fichiers.items())}
        preuves["captures_releves"] = releves_captures if dossier else {}
        afficher("parcours P7 en navigateur (390×844 → notification → 1440×900 sans session → terminé)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        if dossier:
            Path(dossier).mkdir(parents=True, exist_ok=True)
            (Path(dossier) / "releve-parcours.json").write_text(json.dumps(preuves, ensure_ascii=False, indent=2,
                                                                            default=str), encoding="utf-8")
        navigateur.close()
    if dossier:
        assert len(fichiers) == 3 + 2, sorted(fichiers)
