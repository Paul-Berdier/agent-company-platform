"""Les huit outils du greffon (cahier P4 § 8), leur visibilité, la section de prompt et ``register()``."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import garde_execution as ge
from conftest import en_discussion, en_worker, executer_python, lancer_sans_depot, outil

GREFFON = Path("/opt/hermes/plugins/acp-poste")
HUIT = {"projet_lancer", "projet_planifier", "projet_etat", "poste_etat", "poste_catalogue", "question_repondre",
        "question_escalader", "routage_surcharger"}


class Contexte:
    """Contexte de greffon factice : consigne ce que register() enregistre."""

    def __init__(self):
        self.outils, self.crochets, self.sections = {}, [], []

    def register_tool(self, **k):
        self.outils[k["name"]] = k

    def register_hook(self, nom, rappel):
        self.crochets.append((nom, rappel.__name__))

    def register_system_prompt_section(self, identifiant, contenu, **k):
        self.sections.append((identifiant, k))


def test_huit_outils_jeu_acp_poste_descriptions_francaises(noyau):
    ctx = Contexte()
    noyau.outils.enregistrer(ctx)
    assert set(ctx.outils) == HUIT == set(noyau.outils.SCHEMAS)
    for nom, enregistre in ctx.outils.items():
        assert enregistre["toolset"] == "acp_poste" and enregistre["schema"]["name"] == nom
        description = enregistre["schema"]["description"]
        assert re.search(r"[éèàùêç]", description) and " the " not in description, nom
        assert enregistre["schema"]["parameters"]["additionalProperties"] is False, nom
        assert enregistre["check_fn"] in (noyau.outils.visible_en_discussion, noyau.outils.visible_dans_un_worker,
                                          noyau.outils.toujours_visible)


def test_visibilite_discussion_worker(noyau, monkeypatch):
    from tools.registry import _NO_CACHE_CHECK_FNS

    attendus_discussion = {"projet_lancer", "projet_etat", "poste_etat", "poste_catalogue", "routage_surcharger"}
    attendus_worker = {"projet_planifier", "projet_etat", "poste_etat", "poste_catalogue", "question_repondre",
                       "question_escalader"}
    for nom in HUIT:
        assert noyau.outils.check_fn(nom) in _NO_CACHE_CHECK_FNS, nom  # jamais mis en cache
    en_discussion(monkeypatch)
    assert {n for n in HUIT if noyau.outils.check_fn(n)()} == attendus_discussion
    en_worker(monkeypatch, "acp-x", "t_x")
    assert {n for n in HUIT if noyau.outils.check_fn(n)()} == attendus_worker


@pytest.mark.parametrize("args", [None, [], "texte", 42, {"inconnu": 1}, {"titre": None, "objectif": ["x"]},
                                  {"titre": "t" * 100000, "objectif": "o"}, {"etapes": [None, 1, "x"], "resume": {}},
                                  {"projet": {"x": 1}}, {"question": 1, "reponse": 2, "fondement": 3}])
def test_gestionnaire_ne_leve_jamais(noyau, conn, monkeypatch, args):
    projet = lancer_sans_depot(noyau, conn)
    for contexte in ("discussion", "worker"):
        if contexte == "worker":
            en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
        else:
            en_discussion(monkeypatch)
        for nom in HUIT:
            brut = noyau.outils.GESTIONNAIRES[nom](args, session_id=None, task_id=object())
            reponse = json.loads(brut)
            assert isinstance(reponse, dict) and "ok" in reponse, (nom, brut)
            if not reponse["ok"]:
                assert reponse["message"].startswith(("Refusé par ACP : ", "Aucun modèle", "Échec d'ACP")), reponse
                assert "Traceback" not in reponse["message"] and len(reponse["message"]) < 600


def test_une_exception_interne_rend_un_echec_francais(noyau, conn, monkeypatch):
    en_discussion(monkeypatch)
    monkeypatch.setattr(noyau.presence, "etat_poste", lambda conn: 1 / 0)
    assert outil(noyau, "poste_etat", {}) == {"ok": False, "code": "echec", "message": "Échec d'ACP : la lecture de "
                                              "l'état du poste n'a pas abouti (ZeroDivisionError) ; rien n'a été modifié."}
    monkeypatch.setattr(noyau.projets, "lancer", lambda *a, **k: 1 / 0)
    assert outil(noyau, "projet_lancer", {"titre": "t", "objectif": "o"})["message"] == (
        "Échec d'ACP : le lancement du projet n'a pas abouti (ZeroDivisionError) ; l'état n'est pas connu avec "
        "certitude : consultez projet_etat avant de réessayer.")


# Appels HTTP du noyau : SEULEMENT le transport de l'émetteur (notifications.py), jamais dans un outil.
APPELS_HTTP_DU_NOYAU = {
    "notifications.py: requete = urllib.request.Request(url, data=corps, method=methode, headers=entetes)",
    "notifications.py: with urllib.request.urlopen(requete, timeout=delai, context=contexte) as reponse:  # noqa: S310",
}


def test_aucun_appel_http_dans_les_outils():
    appel = re.compile(r"\bhttpx\.|\brequests\.|\burlopen\(|\burllib\.request\.(urlopen|Request)\b|\baiohttp\b"
                       r"|\bsocket\.(create_connection|socket)\b")
    trouves = set()
    for fichier in sorted((GREFFON / "noyau").glob("*.py")):
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            if not ligne.strip().startswith("#") and appel.search(ligne):
                trouves.add(f"{fichier.name}: {ligne.strip()}")
    assert trouves == APPELS_HTTP_DU_NOYAU
    outils = (GREFFON / "noyau" / "outils.py").read_text(encoding="utf-8")
    assert "notifications" not in re.findall(r"^from \. import (.+)$", outils, re.M)[0]


def test_section_de_prompt_bornee_et_francaise(noyau, conn, monkeypatch):
    en_discussion(monkeypatch)
    discussion = noyau.invite.rendre({})
    assert len(discussion) <= 4000 and "projet_lancer" in discussion and "Ne présentez jamais" in discussion
    projet = lancer_sans_depot(noyau, conn)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    worker = noyau.invite.rendre({})
    assert len(worker) <= 4000
    assert worker.startswith("Carte ACP : rôle « planification » — projet « Veille LLM » (tour 0")
    assert "ne créez JAMAIS de carte" in worker and "poste-codex et poste-claude sont les deux exécutants" in worker
    assert "appelez projet_planifier UNE fois" in worker
    en_worker(monkeypatch, "acp-inconnu", "t_inconnue")
    autre = noyau.invite.rendre({})
    assert autre.startswith("Protocole ACP pour cette carte.") and "Carte ACP : rôle" not in autre
    # Aucune section sur les surfaces qui n'ont pas les outils du greffon (D24) : Hermes l'omet si elle est vide.
    assert noyau.invite.rendre({"platform": "api_server"}) == noyau.invite.rendre({"platform": "cron"}) == ""


def test_exploration_meme_plan_que_la_skill(noyau):
    """La consigne d'exploration (corps de la carte du poste) et la skill acp-exploration donnent les mêmes
    sections, dans le même ordre."""
    skill = Path("/opt/acp/skills/acp/acp-exploration/SKILL.md").read_text(encoding="utf-8")
    titres = [l.strip() for l in skill.splitlines() if l.startswith("## ")]
    sections = list(noyau.textes.SECTIONS_EXPLORATION)
    assert [t for t in titres if t in sections] == sections
    consigne = noyau.textes.CONSIGNE_EXPLORATION
    assert [s for s in sections if s in consigne] == sections
    assert [consigne.index(s) for s in sections] == sorted(consigne.index(s) for s in sections)


def test_register_enregistre_garde_outils_section_et_emetteur(noyau):
    code = r"""
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("acp_test_register", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_register"] = module
spec.loader.exec_module(module)
class Contexte:
    def __init__(self): self.crochets, self.outils, self.sections = [], [], []
    def register_hook(self, nom, rappel): self.crochets.append([nom, rappel.__name__, rappel.__module__])
    def register_tool(self, **k): self.outils.append([k["name"], k["toolset"]])
    def register_system_prompt_section(self, i, c, **k): self.sections.append([i, k["position"], k["max_chars"]])
ctx = Contexte()
module.register(ctx)
resultat = [ctx.crochets, sorted(ctx.outils), ctx.sections, module.garde_execution.ENREGISTRE_DANS_CE_PROCESSUS]
"""
    import os

    crochets, outils, sections, enregistre = executer_python(code, env=dict(os.environ, HERMES_HOME=str(noyau.home)))
    assert crochets == [["pre_tool_call", "garde", "acp_test_register.garde_execution"],
                        ["on_kanban_dispatch_tick", "sur_tick", "acp_test_register.noyau.emetteur"]]
    assert outils == sorted([n, "acp_poste"] for n in HUIT)
    assert sections == [["acp-projets", "after_memory", 4000]] and enregistre is True


def test_la_garde_reste_si_le_noyau_ne_se_charge_pas(noyau, tmp_path):
    """Échec fermé : un noyau qui lève à l'enregistrement laisse la garde d'exécution en place."""
    import os
    import shutil

    copie = tmp_path / "acp-poste"
    shutil.copytree(GREFFON, copie)
    (copie / "noyau" / "outils.py").write_text("raise ImportError('noyau cassé')\n", encoding="utf-8")
    code = f"""
import importlib.util, os, sys
os.environ["ACP_NTFY_JETON"] = "jeton-de-test-acp-p4"
spec = importlib.util.spec_from_file_location("acp_test_casse", {str(copie / '__init__.py')!r},
                                              submodule_search_locations=[{str(copie)!r}])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_casse"] = module
spec.loader.exec_module(module)
class Contexte:
    def __init__(self): self.crochets = []
    def register_hook(self, nom, rappel): self.crochets.append(nom)
    def register_tool(self, **k): pass
    def register_system_prompt_section(self, *a, **k): pass
ctx = Contexte()
module.register(ctx)
resultat = [ctx.crochets, "ACP_NTFY_JETON" in os.environ]
"""
    crochets, jeton_reste = executer_python(code, env=dict(os.environ, HERMES_HOME=str(noyau.home)))
    assert crochets == ["pre_tool_call"] and jeton_reste is False


def test_garde_admet_exactement_les_outils_du_greffon(noyau):
    assert set(ge.OUTILS_ADMIS) >= HUIT and len(ge.OUTILS_ADMIS) == 34
    assert set(noyau.outils.SCHEMAS) == HUIT
    for nom in HUIT:
        assert ge.garde(tool_name=nom, args={}) is None
    assert ge.garde(tool_name="kanban_create", args={})["action"] == "block"
