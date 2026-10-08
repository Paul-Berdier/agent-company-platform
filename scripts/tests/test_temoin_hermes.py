"""Témoin de montée de version de Hermes (scripts/temoin_hermes.py et job « temoin » d'image.yml, cahier P9 § 5.5).

Aucun Docker ici : l'exécuteur de commandes est INJECTÉ (``FauxDocker`` joue la sonde de démarrage, ``git status``
et ``git show``). Prouvé : le périmètre de l'écriture (seulement les épingles fortes), la lecture des variables
réclamées par la garde de démarrage (forme du message de hermes/image/acp_demarrage.py), la sonde (démarre, arrêt,
passerelle non branchée, délai, nettoyage même en échec), la lecture des rapports JUnit, le tableau des écarts
(verdict, contrôles non lancés, anomalies, diagnostic hors verdict, échappement), et la forme du job « temoin »
(déclenché seulement à la main, entrée validée, aucun contrôle qui arrête les suivants, borne jamais touchée)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pytest

RACINE = Path(__file__).resolve().parents[2]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module  # dataclasses : le module doit être enregistré avant son exécution
    spec.loader.exec_module(module)
    return module


th = _charger("temoin_hermes", RACINE / "scripts" / "temoin_hermes.py")
mh = th.mh


def _resultat(code: int = 0, sortie: str = "", erreur: str = ""):
    return mh.Resultat(code, sortie.encode("utf-8"), erreur.encode("utf-8"))


# =========================================================================== périmètre de l'écriture


class FauxGit:
    def __init__(self, statut: str = "", code: int = 0, epingle: Optional[str] = None):
        self.statut, self.code, self.epingle = statut, code, epingle
        self.appels: List[List[str]] = []

    def __call__(self, arguments: Sequence[str], delai: int):
        self.appels.append(list(arguments))
        if arguments[:1] == ["git"] and "status" in arguments:
            assert "--untracked-files=all" in arguments and "-z" in arguments
            return _resultat(self.code, self.statut, "fatal: pas un dépôt" if self.code else "")
        if arguments[:1] == ["git"] and "show" in arguments:
            assert arguments[-1] == f"HEAD:{mh.EPINGLE}"
            return _resultat(0 if self.epingle is not None else 128, self.epingle or "")
        raise AssertionError(f"commande inattendue : {arguments}")


def test_perimetre_seulement_les_epingles_fortes():
    statut = "".join(f" M {f}\0" for f in mh.EPINGLES_FORTES[:8])
    lignes: List[str] = []
    assert th.perimetre(RACINE, FauxGit(statut), lignes.append) == 0
    assert lignes[0].startswith("Fichiers modifiés par l'écriture (8) : ")
    assert lignes[-1].startswith("Seulement des épingles fortes : 8 fichier(s) sur les 9")


def test_perimetre_signale_un_fichier_hors_des_epingles_fortes():
    statut = f" M {mh.EPINGLE}\0 M hermes/plugins/acp-poste/plugin.yaml\0?? hermes/contrat/nouveau.txt\0"
    lignes: List[str] = []
    assert th.perimetre(RACINE, FauxGit(statut), lignes.append) == 1
    assert lignes[-1] == ("Hors des épingles fortes (défaut de l'outil) : hermes/contrat/nouveau.txt, "
                          "hermes/plugins/acp-poste/plugin.yaml.")


def test_perimetre_renommage_compte_les_deux_chemins():
    statut = f"R  {mh.OPENRPC}\0hermes/contrat/ancien.json\0"
    assert th.fichiers_modifies(RACINE, FauxGit(statut)) == sorted([mh.OPENRPC, "hermes/contrat/ancien.json"])
    assert th.perimetre(RACINE, FauxGit(statut), lambda _l: None) == 1


def test_perimetre_vide_et_refus():
    lignes: List[str] = []
    assert th.perimetre(RACINE, FauxGit(""), lignes.append) == 0
    assert lignes == ["Aucun fichier modifié par l'écriture (étiquette témoin égale à l'épinglée : aucune valeur ne "
                      "change)."]
    with pytest.raises(th.Refus, match="git status a échoué"):
        th.perimetre(RACINE, FauxGit("", code=128), lambda _l: None)


def test_etiquette_epinglee_lue_dans_le_commit():
    assert th.etiquette_epinglee(RACINE, FauxGit(epingle="# x\nHERMES_TAG=v2026.9.24\n")) == "v2026.9.24"
    with pytest.raises(th.Refus):
        th.etiquette_epinglee(RACINE, FauxGit(epingle=None))
    with pytest.raises(th.Refus, match="HERMES_TAG introuvable"):
        th.etiquette_epinglee(RACINE, FauxGit(epingle="HERMES_VERSION=0.21.5\n"))


# =========================================================================== variables réclamées par la garde


def test_variables_reclamees_suit_le_message_de_la_garde():
    """Le motif lit le message tel que la garde de démarrage l'écrit (source relue, pas recopiée)."""
    source = (RACINE / "hermes" / "image" / "acp_demarrage.py").read_text(encoding="utf-8")
    assert ('f"la variable {nom} manque ; l\'image la fixe à « {attendu} »."' in source), \
        "message de la garde changé : mettre à jour RECLAMATION de scripts/temoin_hermes.py"
    imposees = re.search(r'"XDG_RUNTIME_DIR": \("([^"]+)", True\)', source)
    assert imposees, "XDG_RUNTIME_DIR n'est plus une valeur imposée par l'image"
    journal = (f"[acp] commit déployé : inconnu\n[acp] REFUS : la variable XDG_RUNTIME_DIR manque ; l'image la fixe "
               f"à « {imposees.group(1)} ».\n[acp] REFUS : la variable HERMES_TUI_DIR manque ; l'image la fixe à "
               f"« /opt/hermes/ui-tui ».\n/run/s6/basedir/scripts/rc.init: fatal: hook /opt/acp/bin/acp-gardes exited 1\n")
    assert th.variables_reclamees(journal) == {"XDG_RUNTIME_DIR": "/tmp/hermes-runtime",
                                               "HERMES_TUI_DIR": "/opt/hermes/ui-tui"}


def test_variables_reclamees_ignore_toute_autre_forme():
    journal = ("la variable PATH manque ; l'image la fixe à « /bin; rm -rf / ».\n"
               "la variable minuscule manque ; l'image la fixe à « /x ».\n"
               "la variable VIDE manque ; l'image la fixe à «  ».\n"
               "la variable HERMES_HOME vaut « /x » ; seule la valeur « /opt/data » est admise.\n")
    assert th.variables_reclamees(journal) == {}


# =========================================================================== sonde de démarrage


class FauxDocker:
    """Exécuteur injecté : un conteneur qui démarre (ou non) selon le scénario ; horloge simulée."""

    def __init__(self, *, arret_au: Optional[int] = None, pret_au: Optional[int] = None,
                 passerelle_au: Optional[int] = None, echec: Optional[str] = None):
        self.arret_au, self.pret_au, self.passerelle_au, self.echec = arret_au, pret_au, passerelle_au, echec
        self.temps = 0.0
        self.appels: List[List[str]] = []

    def attendre(self, secondes: float) -> None:
        self.temps += secondes

    def horloge(self) -> float:
        return self.temps

    def __call__(self, arguments: Sequence[str], delai: int):
        a = list(arguments)
        self.appels.append(a)
        assert a[0] == "docker"
        if self.echec and a[1] == self.echec:
            return _resultat(1, "", f"Error: {self.echec} impossible")
        if a[1] in ("volume", "rm"):
            return _resultat(0, a[-1])
        if a[1] == "run":
            return _resultat(0, "id-du-conteneur" if "-d" in a else "")
        if a[1] == "inspect":
            if self.arret_au is not None and self.temps >= self.arret_au:
                return _resultat(0, "false 1\n")
            return _resultat(0, "true 0\n")
        if a[1] == "exec":
            commande = a[3:]
            if commande[:2] == ["curl", "-s"] and "-w" in commande:
                pret = self.pret_au is not None and self.temps >= self.pret_au
                return _resultat(0, "200" if pret else "000")
            if commande[:2] == ["curl", "-s"]:
                branchee = self.passerelle_au is not None and self.temps >= self.passerelle_au
                return _resultat(0, json.dumps({
                    "version": "0.21.4", "release_date": "2026.9.21", "config_version": 0,
                    "latest_config_version": 45, "gateway_running": branchee, "gateway_state": "running",
                    "gateway_platforms": {"api_server": {"state": "connected" if branchee else "connecting"}}}))
            if commande[:1] == ["cat"]:
                return _resultat(0, '{"catalogue": {"etat": "applique"}}')
            if commande[:2] == ["sh", "-c"]:
                return _resultat(0, "WARNING hermes_cli.plugins: Plugin 'acp-poste' skipped: requires hermes "
                                    ">=0.21.5, running 0.21.4\n")
        if a[1] == "logs":
            return _resultat(0, "[acp] commit déployé : inconnu\n[config-migrate] WARNING: This config predates "
                                "version 12\nligne ordinaire\n", "[acp] REFUS : exemple\n")
        raise AssertionError(f"commande inattendue : {a}")

    def nettoyages(self) -> List[List[str]]:
        return [a for a in self.appels if a[1:3] in (["rm", "-f"], ["volume", "rm"])]


def _sonder(faux: FauxDocker, **options):
    lignes: List[str] = []
    code, journal = th.sonder("acp-hermes:temoin", "acp-contrat-temoin-sonde", faux, attendre=faux.attendre,
                              horloge=faux.horloge, sortie=lignes.append, **options)
    return code, journal, lignes


def test_sonde_conteneur_arrete_par_la_garde():
    faux = FauxDocker(arret_au=6)
    code, journal, lignes = _sonder(faux)
    assert code == 1
    assert lignes[0] == "Démarre : non (conteneur arrêté après 6 s, code 1)."
    assert "[acp] REFUS : exemple" in journal
    assert any("[config-migrate] WARNING" in l for l in lignes) and not any("ligne ordinaire" in l for l in lignes)
    lancement = next(a for a in faux.appels if a[1] == "run" and "-d" in a)
    assert lancement[-1] == "acp-hermes:temoin" and "mcp.context7.com:127.0.0.1" in lancement
    assert [lancement[i + 1] for i, v in enumerate(lancement) if v == "-e"] == [
        f"{k}={v}" for k, v in th.ENV_SONDE.items()]
    assert faux.nettoyages() == [["docker", "rm", "-f", "-v", "acp-contrat-temoin-sonde-hermes"],
                                 ["docker", "volume", "rm", "-f", "acp-contrat-temoin-sonde-vol"]]


def test_sonde_demarre_puis_passerelle_branchee():
    faux = FauxDocker(pret_au=10, passerelle_au=20)
    code, _journal, lignes = _sonder(faux)
    assert code == 0
    assert lignes[0] == "Démarre : oui (/api/status 200 en 10 s ; passerelle et api_server branchés)."
    assert lignes[1].startswith("/api/status : version='0.21.4', release_date='2026.9.21', config_version=0, "
                                "latest_config_version=45, gateway_running=True")
    assert any("Plugin 'acp-poste' skipped" in l for l in lignes)
    assert len(faux.nettoyages()) == 2


def test_sonde_passerelle_jamais_branchee():
    faux = FauxDocker(pret_au=4)
    code, _journal, lignes = _sonder(faux, delai_passerelle=30)
    assert code == 1
    assert lignes[0] == ("Démarre : non (tableau de bord prêt en 4 s, mais passerelle ou api_server non branchés "
                         "après 30 s).")


def test_sonde_tableau_de_bord_injoignable():
    faux = FauxDocker()
    code, _journal, lignes = _sonder(faux, delai_pret=20)
    assert code == 1 and lignes[0] == "Démarre : non (tableau de bord injoignable après 20 s)."
    assert len(faux.nettoyages()) == 2


def test_sonde_variables_ajoutees_et_prefixe_controle():
    faux = FauxDocker(arret_au=0)
    _sonder(faux, variables={"XDG_RUNTIME_DIR": "/tmp/hermes-runtime"})
    lancement = next(a for a in faux.appels if a[1] == "run" and "-d" in a)
    assert "XDG_RUNTIME_DIR=/tmp/hermes-runtime" in lancement
    with pytest.raises(th.Refus, match="Préfixe"):
        th.sonder("img", "autre-prefixe", faux)


def test_sonde_echec_de_docker_refus_et_nettoyage():
    faux = FauxDocker(echec="run")
    with pytest.raises(th.Refus, match="docker run"):
        _sonder(faux)
    assert len(faux.nettoyages()) == 2


def test_main_sonde_diagnostic_sans_objet(tmp_path, capsys):
    journal = tmp_path / "sonde-conteneur.txt"
    journal.write_text("[acp] REFUS : la variable HERMES_HOME vaut « /x » ; seule la valeur « /opt/data » est admise.\n",
                       encoding="utf-8")
    faux = FauxDocker()
    code = th.main(["sonde", "--image", "img", "--prefixe", "acp-contrat-temoin-diag", "--variables-de", str(journal)],
                   executer=faux)
    assert code == 0 and faux.appels == []
    assert "Diagnostic sans objet" in capsys.readouterr().out


# =========================================================================== rapports JUnit et tableau


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="5">
<testcase classname="test_catalogue" name="test_ok" time="0.1"/>
<testcase classname="test_catalogue" name="test_ok_2" time="0.1"/>
<testcase classname="test_catalogue" name="test_config_semee" time="0.2">
  <failure message="AssertionError: version de schéma 0, alors que Hermes connaît la version 45&#10;assert 0 == 45">trace</failure>
</testcase>
<testcase classname="test_contrat_image" name="test_pid1" time="0.2"><error message="">
le conteneur | s'est arrêté
suite</error></testcase>
<testcase classname="test_x" name="test_ignore"><skipped message="Linux seulement"/></testcase>
</testsuite></testsuites>
"""


def _dossier(tmp_path: Path, junits: Dict[str, str], journaux: Dict[str, str]) -> Path:
    (tmp_path / "junit").mkdir()
    (tmp_path / "journaux").mkdir()
    for nom, texte in junits.items():
        (tmp_path / "junit" / nom).write_text(texte, encoding="utf-8")
    for nom, texte in journaux.items():
        (tmp_path / "journaux" / f"{nom}.txt").write_text(texte, encoding="utf-8")
    return tmp_path


def _etapes(**issues: str) -> Dict[str, dict]:
    etapes = {"etiquette": {"outcome": "success", "conclusion": "success", "outputs": {}}}
    for controle in th.CONTROLES:
        issue = issues.get(controle.id, "success")
        etapes[controle.id] = {"outcome": issue, "conclusion": "success", "outputs": {}}
    return etapes


JUNIT_VERT = ('<testsuites><testsuite tests="2"><testcase classname="a" name="t1"/><testcase classname="a" name="t2"/>'
              '</testsuite></testsuites>')


def test_lire_junit_compte_et_raisons(tmp_path):
    chemin = tmp_path / "r.xml"
    chemin.write_text(JUNIT, encoding="utf-8")
    suite = th.lire_junit(chemin)
    assert (suite.reussis, suite.ignores, suite.total) == (2, 1, 5)
    assert suite.echecs == [("test_catalogue::test_config_semee",
                             "AssertionError: version de schéma 0, alors que Hermes connaît la version 45")]
    assert suite.erreurs == [("test_contrat_image::test_pid1", "le conteneur | s'est arrêté")]
    chemin.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(th.Refus, match="illisible"):
        th.lire_junit(chemin)


def test_tableau_tout_vert(tmp_path):
    dossier = _dossier(tmp_path, {c.junit: JUNIT_VERT for c in th.CONTROLES if c.junit},
                       {"ecrire": "Épingles fortes réécrites pour v2026.9.24 : aucun changement.\n"})
    texte, code = th.tableau(_etapes(sonde_diag="skipped"), dossier, "v2026.9.24", "v2026.9.24")
    assert code == 0
    assert "**Verdict : aucun écart** : les 16 contrôles comptés ont réussi." in texte
    assert "| 1 | Écriture de l'épinglage témoin (`monter_hermes.py ecrire`) | réussi | Épingles fortes réécrites" in texte
    assert "hors verdict (non lancé)" in texte


def test_tableau_echecs_non_lances_et_tests_en_echec(tmp_path):
    dossier = _dossier(tmp_path, {"pytest-image.xml": JUNIT, "depot.xml": JUNIT_VERT},
                       {"sonde": "Démarre : non (conteneur arrêté après 6 s, code 1).\n[acp] REFUS : la variable "
                                 "XDG_RUNTIME_DIR manque ; l'image la fixe à « /tmp/hermes-runtime ».\nautre\n",
                        "sonde_diag": "Variables ajoutées (diagnostic, hors verdict) : XDG_RUNTIME_DIR=/tmp/x\n"
                                      "Démarre : oui (/api/status 200 en 9 s ; passerelle et api_server branchés).\n",
                        "verifier": "1 écart(s) :\n- hermes/plugins/acp-poste/plugin.yaml : requires_hermes >=0.21.5 "
                                    "exclut Hermes 0.21.4\n"})
    etapes = _etapes(sonde="failure", sonde_diag="success", pytest_image="failure", contrat="skipped",
                     verifier="failure")
    texte, code = th.tableau(etapes, dossier, "v2026.9.21", "v2026.9.24")
    assert code == 1
    assert texte.startswith("## Témoin de montée de Hermes : v2026.9.21 (épinglée : v2026.9.24)\n")
    assert "**Verdict : 4 écart(s) ou anomalie(s)** sur 16 contrôles comptés" in texte
    ligne_sonde = next(l for l in texte.splitlines() if "Démarrage de l'image ACP" in l)
    assert "**ÉCHEC**" in ligne_sonde and "XDG_RUNTIME_DIR manque" in ligne_sonde and "autre" not in ligne_sonde
    ligne_diag = next(l for l in texte.splitlines() if "Diagnostic HORS VERDICT" in l)
    assert "hors verdict (réussi)" in ligne_diag and "Démarre : oui" in ligne_diag
    ligne_contrat = next(l for l in texte.splitlines() if l.startswith("| 17 |"))
    assert "non lancé" in ligne_contrat
    assert "requires_hermes &gt;=0.21.5 exclut Hermes 0.21.4" in texte
    assert "### pytest dans l'image de test : 2 réussis, 1 en échec, 1 en erreur, 1 ignorés" in texte
    assert ("| échec | test_catalogue::test_config_semee | AssertionError: version de schéma 0, alors que Hermes "
            "connaît la version 45 |") in texte
    assert "| erreur | test_contrat_image::test_pid1 | le conteneur \\| s'est arrêté |" in texte
    assert "Raisons les plus fréquentes" in texte


def test_tableau_anomalies_rapport_absent_ou_vide_et_incoherence(tmp_path):
    vide = '<testsuites><testsuite tests="0"></testsuite></testsuites>'
    dossier = _dossier(tmp_path, {"pytest-image.xml": vide, "contrat.xml": JUNIT}, {})
    texte, code = th.tableau(_etapes(), dossier, "v2026.9.21", "v2026.9.24")
    assert code == 1
    assert "ANOMALIE : rapport JUnit depot.xml absent" in texte
    assert "ANOMALIE : aucun test exécuté (rapport vide)" in texte
    assert "étape réussie malgré des tests en échec (incohérent)" in texte


def test_tableau_etiquette_hors_forme_jamais_recopiee_et_etape_inconnue(tmp_path):
    dossier = _dossier(tmp_path, {}, {})
    etapes = _etapes()
    etapes["etiquette"]["outcome"] = "failure"
    for controle in th.CONTROLES:
        etapes[controle.id]["outcome"] = "skipped"
    etapes["nouvelle_etape"] = {"outcome": "success"}
    texte, code = th.tableau(etapes, dossier, "v1 | <script>", "v2026.9.24")
    assert code == 1
    assert "<script>" not in texte and "(étiquette refusée : hors forme vAAAA.M.J)" in texte
    assert "préalable « etiquette » : **ÉCHEC**" in texte
    assert "| 18 | Étape « nouvelle_etape » (hors de la liste des contrôles) | réussi |" in texte


def test_main_tableau(tmp_path, monkeypatch, capsys):
    dossier = _dossier(tmp_path, {c.junit: JUNIT_VERT for c in th.CONTROLES if c.junit}, {})
    monkeypatch.setenv("ETAPES_TEST", json.dumps(_etapes(sonde_diag="skipped")))
    sortie = tmp_path / "tableau.md"
    faux = FauxGit(epingle="HERMES_TAG=v2026.9.24\n")
    code = th.main(["tableau", "--etapes-env", "ETAPES_TEST", "--dossier", str(dossier), "--etiquette=v2026.9.24",
                    "--sortie", str(sortie)], executer=faux)
    assert code == 0 and sortie.read_text(encoding="utf-8") in capsys.readouterr().out
    monkeypatch.setenv("ETAPES_TEST", "[1, 2]")
    assert th.main(["tableau", "--etapes-env", "ETAPES_TEST", "--dossier", str(dossier), "--etiquette=v1"],
                   executer=faux) == 2
    monkeypatch.delenv("ETAPES_TEST")
    assert th.main(["tableau", "--etapes-env", "ETAPES_TEST", "--dossier", str(dossier), "--etiquette=v1"],
                   executer=faux) == 2


# =========================================================================== job « temoin » d'image.yml


def _job_temoin() -> str:
    flux = (RACINE / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    bloc = flux[flux.index("\njobs:\n") + len("\njobs:\n"):]
    morceaux = re.split(r"^  ([A-Za-z0-9_-]+):\n", bloc, flags=re.M)
    return dict(zip(morceaux[1::2], morceaux[2::2]))["temoin"]


def _etapes_du_job(texte: str) -> List[str]:
    return re.split(r"\n(?=      - (?:name|uses): )", texte)[1:]


def test_image_yml_declare_l_entree_et_ne_lance_le_temoin_qu_a_la_main():
    flux = (RACINE / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    entree = flux[flux.index("  workflow_dispatch:\n"):flux.index("  pull_request:\n")]
    assert "    inputs:\n      temoin_etiquette:\n" in entree and 'default: ""' in entree and "type: string" in entree
    job = _job_temoin()
    assert "    if: github.event_name == 'workflow_dispatch' && inputs.temoin_etiquette != ''\n" in job
    # L'entrée n'est lue qu'une fois, comme variable d'environnement ; jamais interpolée dans un script.
    assert job.count("${{ inputs.temoin_etiquette }}") == 1
    assert "      TEMOIN_ETIQUETTE: ${{ inputs.temoin_etiquette }}\n" in job
    validation = next(e for e in _etapes_du_job(job) if "id: etiquette" in e)
    assert r'[[ "$TEMOIN_ETIQUETTE" =~ ^v[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,2}$ ]]' in validation
    assert "exit 2" in validation


def test_image_yml_chaque_controle_du_tableau_est_une_etape_qui_n_arrete_pas_les_suivantes():
    job = _job_temoin()
    etapes = _etapes_du_job(job)
    identifiants = [m.group(1) for e in etapes for m in [re.search(r"^        id: (\S+)$", e, re.M)] if m]
    assert sorted(identifiants) == sorted([c.id for c in th.CONTROLES] + list(th.ETAPES_PREALABLES))
    for etape in etapes:
        m = re.search(r"^        id: (\S+)$", etape, re.M)
        if not m or m.group(1) in th.ETAPES_PREALABLES:
            continue
        if m.group(1) == "ecrire":
            # Un échec de l'écriture arrête tout : les contrôles prouveraient l'épinglée sous le nom du témoin.
            assert "\n        continue-on-error:" not in etape
            assert 'grep -qx "HERMES_TAG=${TEMOIN_ETIQUETTE}" hermes/contrat/HERMES_VERSION' in etape
        else:
            assert "        continue-on-error: true\n" in etape, m.group(1)
    # Ordre : étiquette, écriture, périmètre avant toute autre étape.
    assert identifiants[:3] == ["etiquette", "ecrire", "perimetre"]


def test_image_yml_le_tableau_et_l_artefact_tournent_toujours_et_la_borne_n_est_jamais_touchee():
    job = _job_temoin()
    etapes = _etapes_du_job(job)
    tableau = next(e for e in etapes if "scripts/temoin_hermes.py tableau" in e)
    assert "        if: always()\n" in tableau and "ETAPES: ${{ toJSON(steps) }}" in tableau
    assert '--etiquette="$TEMOIN_ETIQUETTE"' in tableau and '>> "$GITHUB_STEP_SUMMARY"' in tableau
    assert 'exit "$code"' in tableau
    artefact = next(e for e in etapes if "actions/upload-artifact" in e)
    assert "        if: always()\n" in artefact and "path: /tmp/temoin" in artefact
    assert etapes.index(tableau) < etapes.index(artefact) < len(etapes) - 1
    assert etapes[-1].startswith("      - name: Aucun conteneur, volume ni réseau de test ne reste")
    # La borne du greffon n'est ni lue pour être réécrite ni modifiée : aucune commande ne touche plugin.yaml.
    commandes = "\n".join(l for l in job.splitlines() if not l.strip().startswith("#"))
    assert "plugin.yaml" not in commandes and "sed -i" not in commandes
    assert "requires_hermes" not in commandes
    # Mêmes tests de contrat que le job « image » (restauration et montée ont leurs jobs).
    assert 'python -m pytest -s -v -rA hermes/tests/contrat -m "not restauration and not montee"' in job
    assert "timeout-minutes: 150" in job
