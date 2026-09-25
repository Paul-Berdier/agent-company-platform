"""Interface française d'ACP dans un vrai navigateur (étape P3), aux formats téléphone (390×844) et
bureau (1440×900), locale fr-FR, fuseau Europe/Paris, derrière la même pile que la connexion de P2
(bord TLS factice, vrai Authelia, passkey virtuelle : parcours.py).

Vérifié, aux deux formats :
- « / » affiche l'Accueil d'ACP (greffon acp-interface, tab.override) ; logotype « ACP » ;
- <html lang="fr"> et localStorage["hermes-locale"] == "fr" ; « en » forcé puis page rechargée :
  retour au français (verrou, décision D10) ;
- l'onglet « Catalogue » (greffon acp-catalogue) ;
- variable --color-primary = accent.primary des jetons (thème « acp » généré) ;
- AUCUNE requête hors de l'origine du tableau de bord une fois la session ouverte (aucune police,
  aucun script, aucune image externe) ;
- chaque nœud de texte sous [data-acp-racine] appartient au catalogue français
  (apps/interface/src/chaines.ts, exporté par outils/exporter-chaines.mjs) ou à un élément
  data-acp-donnee (valeur venue de l'API) ;
- axe-core (apps/interface/node_modules/axe-core, verrou npm) : aucune violation « serious » ni
  « critical » sur l'Accueil et le Catalogue ;
- au format téléphone, chaque cible (lien, bouton, liste, repli) des deux pages mesure 44 px au moins.
Puis : SOUL.md retouché et conteneur redémarré ⇒ la bannière signale la persona divergente.

Captures (ACP_E2E_CAPTURES=<répertoire>, sous-dossier interface/) : portail Authelia, Accueil,
Catalogue, Sessions, Discussion (/chat), Skills, MCP, Kanban, Configuration, aux deux formats ;
leurs empreintes SHA-256 sont imprimées. Les pages natives de Hermes sont CAPTURÉES, pas vérifiées :
leurs chaînes restées en anglais sont comptées par apps/interface/outils/decompte-traductions.mjs.

Lancement : ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… python -m pytest -s -v -rA hermes/tests/e2e
Prérequis : npm ci --ignore-scripts --prefix apps/interface (axe-core) et Node ≥ 22.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List

from conftest import CAPTURES, afficher, image, manque
from parcours import ajouter_authentificateur, fabrique_de_captures, lancer_chromium, se_connecter
from pile_identite import EMETTEUR, URL_HERMES, docker, empreinte_argon2, monter_pile, spki_du_bord

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


def _catalogue_francais() -> List[str]:
    node = shutil.which("node")
    if node is None:
        manque("Node.js est introuvable : il exporte le catalogue des chaînes (apps/interface)")
    sortie = subprocess.run([node, "--experimental-strip-types", str(INTERFACE / "outils" / "exporter-chaines.mjs")],
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert sortie.returncode == 0, sortie.stderr
    return sorted({v.strip() for v in json.loads(sortie.stdout).values()})


def _primaire_des_jetons() -> str:
    jetons = json.loads((RACINE / "design" / "tokens" / "colors.json").read_text(encoding="utf-8"))
    return jetons["tokens"]["accent.primary"]["dark"].lower()


def _attendre_hermes(nom: str, delai: float = 300) -> None:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        code = docker("exec", nom, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                      "http://127.0.0.1:9119/api/status", verifier=False).stdout.strip()
        if code == "200":
            return
        time.sleep(2)
    raise AssertionError("tableau de bord de Hermes injoignable après redémarrage")


def _attendre_page_acp(page, racine: str) -> None:
    page.wait_for_selector(f'[data-acp-racine="{racine}"] h1')
    # Plus aucun « Chargement… » : toutes les données demandées sont arrivées (ou en erreur, dit).
    page.wait_for_function("(r) => { const e = document.querySelector('[data-acp-racine=\"' + r + '\"]');"
                           " return e && !e.textContent.includes('Chargement'); }", arg=racine)


def _verifier_page_acp(page, racine: str, format_: str, catalogue: List[str]) -> Dict[str, object]:
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


def test_interface_francaise_telephone_et_bureau(playwright_sync, pile):
    if not AXE.is_file():
        manque(f"axe-core absent ({AXE}) : npm ci --ignore-scripts --prefix apps/interface")
    image_tests = image("ACP_IMAGE_TESTS")
    image_identite = image("ACP_IMAGE_IDENTITE")
    catalogue = _catalogue_francais()
    primaire = _primaire_des_jetons()
    noms = monter_pile(pile, image_identite, image_tests, empreinte_argon2(image_identite), publier=True)
    identite, hermes, port = noms["identite"], noms["hermes"], noms["port"]
    spki = spki_du_bord(image_tests)
    dossier = str(Path(CAPTURES) / "interface") if CAPTURES else None
    preuves: Dict[str, object] = {"catalogue_francais": len(catalogue), "formats": {}}
    fichiers: Dict[str, Path] = {}

    navigateur = lancer_chromium(playwright_sync, port, spki)
    try:
        # Connexion une seule fois (format bureau) ; la session est reprise au format téléphone.
        bureau = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["bureau"])
        page_bureau = bureau.new_page()
        page_bureau.set_default_timeout(60_000)
        capture_bureau, fichiers_bureau = fabrique_de_captures(dossier, "bureau-")
        cdp, authentificateur = ajouter_authentificateur(bureau, page_bureau)
        se_connecter(page_bureau, cdp, authentificateur, identite,
                     lambda nom: capture_bureau(page_bureau, "portail-authelia") if nom == "portail" else None)
        etat = bureau.storage_state()

        # Portail d'Authelia au format téléphone (sans session).
        capture_tel, fichiers_tel = fabrique_de_captures(dossier, "telephone-")
        anonyme = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", **FORMATS["telephone"])
        page_anonyme = anonyme.new_page()
        page_anonyme.goto(f"{URL_HERMES}/")
        page_anonyme.wait_for_url(re.compile(rf"^{re.escape(EMETTEUR)}/"))
        page_anonyme.wait_for_selector("#username-textfield")
        capture_tel(page_anonyme, "portail-authelia")
        anonyme.close()

        for format_ in ("telephone", "bureau"):
            if format_ == "bureau":
                contexte, page, capture = bureau, page_bureau, capture_bureau
            else:
                contexte = navigateur.new_context(locale="fr-FR", timezone_id="Europe/Paris", storage_state=etat,
                                                  **FORMATS["telephone"])
                page = contexte.new_page()
                page.set_default_timeout(60_000)
                capture = capture_tel
            requetes: List[str] = []
            page.on("request", lambda r, liste=requetes: liste.append(r.url))
            bilan: Dict[str, object] = {}

            # Accueil sur « / », en français.
            page.goto(f"{URL_HERMES}/")
            _attendre_page_acp(page, "accueil")
            page.wait_for_function("document.documentElement.lang === 'fr' "
                                   "&& localStorage.getItem('hermes-locale') === 'fr'")
            # Hermes ajoute « ?profile=default » à l'URL ; le chemin reste « / ».
            assert urllib.parse.urlsplit(page.url).path == "/", page.url
            assert page.inner_text('[data-acp-racine="accueil"] h1') == "Accueil"
            assert page.text_content('[data-acp-racine="marque"] a') == "ACP"
            bilan["primaire"] = page.evaluate(
                "getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim()")
            assert str(bilan["primaire"]).lower() == primaire, bilan["primaire"]
            bilan["accueil"] = _verifier_page_acp(page, "accueil", format_, catalogue)
            # Étape P3 (seconde partie) : résumé du catalogue servi par /v1/meta (16 skills d'ACP actives).
            carte_catalogue = page.inner_text("#acp-accueil-catalogue >> xpath=..")
            bilan["accueil_catalogue"] = carte_catalogue
            assert re.search(r"(?<!\d)16(?!\d).*(?<!\d)16(?!\d)", carte_catalogue, re.S), carte_catalogue
            capture(page, "accueil")

            # Verrou : « en » forcé, page rechargée ⇒ retour au français.
            page.evaluate("localStorage.setItem('hermes-locale', 'en')")
            page.reload()
            _attendre_page_acp(page, "accueil")
            page.wait_for_function("document.documentElement.lang === 'fr' "
                                   "&& localStorage.getItem('hermes-locale') === 'fr'", timeout=15_000)
            bilan["verrou"] = "en forcé puis rechargé : retour à fr"

            # Onglet « Catalogue ».
            # Lien de la navigation de Hermes (hors de nos pages : l'Accueil a aussi ses liens).
            assert page.locator('nav a[href="/catalogue"]', has_text="Catalogue").count() == 1
            page.goto(f"{URL_HERMES}/catalogue")
            _attendre_page_acp(page, "catalogue")
            assert page.inner_text('[data-acp-racine="catalogue"] h1') == "Catalogue"
            # Étape P3 (seconde partie) : la route /v1/catalogue d'acp-poste est servie ; chaque skill
            # d'ACP est affichée, avec son état vu par le chargeur de Hermes.
            page.wait_for_selector("#acp-catalogue-skills >> xpath=.. >> li.acp-entree")
            bilan["catalogue_route_v1"] = ("indisponible" if page.locator(
                '[data-acp-racine="catalogue"] .acp-erreur').count() else "servie")
            assert bilan["catalogue_route_v1"] == "servie"
            entrees = page.locator("#acp-catalogue-skills >> xpath=.. >> li.acp-entree")
            bilan["catalogue_entrees"] = entrees.count()
            assert entrees.count() == 26, entrees.count()  # 16 livrées dans l'image + 10 candidates pour le poste
            texte_catalogue = page.inner_text('[data-acp-racine="catalogue"]')
            assert "acp-redaction" in texte_catalogue and "context7" in texte_catalogue
            bilan["catalogue"] = _verifier_page_acp(page, "catalogue", format_, catalogue)
            capture(page, "catalogue")

            # Pages natives de Hermes : capturées seulement.
            for nom, chemin in PAGES_NATIVES:
                page.goto(f"{URL_HERMES}{chemin}")
                page.wait_for_load_state("load")
                page.wait_for_timeout(2_500)
                capture(page, nom)

            etrangeres = sorted({u for u in requetes
                                 if not (u.startswith(f"{URL_HERMES}/") or u.startswith(("data:", "blob:")))})
            bilan["requetes"] = len(requetes)
            bilan["requetes_hors_origine"] = etrangeres
            assert requetes and etrangeres == [], etrangeres
            preuves["formats"][format_] = bilan
            if format_ == "telephone":
                contexte.close()

        # SOUL.md retouché par le propriétaire, conteneur redémarré ⇒ bannière « persona divergente ».
        docker("exec", "-u", "hermes", hermes, "sh", "-c", "printf 'Persona retouchée par le propriétaire.\\n' "
               "> /opt/data/SOUL.md")
        docker("restart", hermes, delai=240)
        _attendre_hermes(hermes)
        page = page_bureau
        page.goto(f"{URL_HERMES}/")
        page.wait_for_selector('[data-acp-racine="alertes"] li')
        _attendre_page_acp(page, "accueil")
        banniere = page.inner_text('[data-acp-racine="alertes"]')
        persona = page.inner_text("#acp-accueil-persona >> xpath=..")
        preuves["banniere_persona_divergente"] = {"banniere": banniere, "carte": persona}
        assert "SOUL.md a été modifié par le propriétaire" in banniere
        assert "Modifiée par le propriétaire" in persona
        assert page.evaluate(JS_HORS_CATALOGUE, catalogue) == []
        capture_bureau(page, "banniere-persona-divergente")
        fichiers = {**fichiers_tel, **fichiers_bureau}
    finally:
        empreintes = {nom: hashlib.sha256(chemin.read_bytes()).hexdigest() for nom, chemin in sorted(fichiers.items())}
        preuves["captures"] = empreintes
        afficher("interface française en navigateur (Chromium, 390×844 et 1440×900)",
                 json.dumps(preuves, ensure_ascii=False, indent=2, default=str))
        navigateur.close()
    if dossier:
        assert len(fichiers) == 2 * (1 + 2 + len(PAGES_NATIVES)) + 1, sorted(fichiers)
