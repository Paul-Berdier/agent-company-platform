"""Une carte dans l'exécutant (cahier P6 § 6) avec de FAUX agents (``faux_agents.py``) et un dépôt « distant » local.

Hermes est remplacé par une fonction d'envoi qui enregistre chaque requête (validée par le contrat dans
``Protocole.envoyer``, éprouvé à part) et rend des réponses du contrat. Les faux CLI ne prouvent que la plomberie.
Le test marqué ``RACINE_LINUX`` lance l'agent sous son UID dédié (``setpriv``) : conteneur de test seulement.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acp_poste import execution as module_execution
from acp_poste.balayage import RAISON_SECRET
from acp_poste.depots import Depots
from acp_poste.execution import VERIF_NON_EXECUTEE, Execution, LanceurAgents
from acp_poste.garde_quota import Budget, QuotasClaude
from acp_poste.journal import Journal
from acp_poste.plateforme.linux import EmplacementsLinux
from acp_poste.politique import analyser_executant
from acp_poste.protocole import HermesIndisponible, RefusAvantEnvoi
from acp_poste.sortie import FileSortie
from acp_poste_contrat import machine as contrat

ICI = Path(__file__).resolve().parent
RACINE_DEPOT = ICI.parents[2]
PYTHON = str(Path(sys.executable).resolve())
FAUX = str(ICI / "faux_agents.py")
POSIX = pytest.mark.skipif(os.name != "posix", reason="liens symboliques et droits POSIX")
RACINE_LINUX = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="exige Linux et root (agent sous son UID par setpriv) : conteneur de test de P6 seulement")
EXEMPLES = RACINE_DEPOT / "hermes" / "tests" / "outils" / "fixtures_machine"
ISOLEMENT_B = {"regime": "B", "bwrap": "refuse", "proc_neuf": False, "reseau_coupe": False, "uid_separes": True,
               "codex_sans_bac_a_sable": "refuse", "ecriture_admise": {"codex": False, "claude": True},
               "raison": "Régime B : bubblewrap refusé par la plateforme.", "sonde_le": "2026-10-01T10:00:00Z"}
ISOLEMENT_A = dict(ISOLEMENT_B, regime="A", bwrap="fonctionne", reseau_coupe=True,
                   ecriture_admise={"codex": True, "claude": True}, raison=None)
VERIF_FICHIER = [PYTHON, "-c", "import pathlib,sys; sys.exit(0 if pathlib.Path('nouveau.py').read_text()"
                                ".strip() == 'X = 1' else 3)"]


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c",
                           "commit.gpgsign=false", "-c", "init.defaultBranch=main", *argv], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


class Hermes:
    """Faux greffon : enregistre les envois, rend les réponses du contrat (ou celles qu'un test impose)."""

    def __init__(self) -> None:
        self.envois: list[tuple[str, dict]] = []
        self.battement = {"valide": True, "pause": False, "annuler": False}
        self.panne: Exception | None = None

    def envoyer(self, route: str, corps: dict):
        contrat.valider(getattr(contrat, contrat.MODELES_P6[f"{contrat.PREFIXE_ROUTES}/{route}"][0]), corps,
                        quoi=f"Envoi {route}")
        if self.panne is not None and route != "battement":
            raise self.panne
        self.envois.append((route, corps))
        if route == "battement":
            return contrat.ReponseBattement.model_validate(self.battement)
        reponses = {"terminer": ("ReponseTerminer", {"etat": "done"}),
                    "question": ("ReponseQuestion", {"question": "q_0123456789ab", "etat": "ouverte"}),
                    "bloquer": ("ReponseBloquer", {"etat": "bloquee"}),
                    "reprendre": ("ReponseReprise", {"etat": "rendue"}), "arret": ("ReponseReprise", {"etat": "rendue"})}
        modele, document = reponses[route]
        return getattr(contrat, modele).model_validate(document)

    def issues(self) -> list[tuple[str, dict]]:
        return [(r, c) for r, c in self.envois if r != "battement"]


class Banc:
    def __init__(self, racine: Path, *, isolement=None, depot: dict | None = None) -> None:
        self.racine = racine
        self.distant = racine / "distant"
        self.distant.mkdir(parents=True)
        _git(self.distant, "init", "-q")
        (self.distant / "README.md").write_text("Dépôt jetable\n", encoding="utf-8")
        (self.distant / "nouveau.py").write_text("X = 0\n", encoding="utf-8")
        _git(self.distant, "add", "-A")
        _git(self.distant, "commit", "-qm", "initial")
        self.emplacements = EmplacementsLinux.de_test(racine)
        texte = (RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8").replace(
            'origine = "https://<libellé-hermes>.up.railway.app"', 'origine = "https://hermes-acp-test.up.railway.app"')
        texte += ('\n[depots.jetable]\nurl = "https://github.com/proprietaire-factice/jetable.git"\n'
                  'acces = "jeton_lecture"\nverification = ["true"]\nverification_sans_bac_a_sable = true\n')
        politique = analyser_executant(texte.encode("utf-8"), self.emplacements)
        valeurs = {"url": str(self.distant), "acces": "public", "verification": tuple(VERIF_FICHIER)}
        valeurs.update(depot or {})
        depot_politique = dataclasses.replace(politique.depot("jetable"), **valeurs)
        self.politique = dataclasses.replace(politique, depots=(depot_politique,))
        self.depots = Depots(racine_depots=self.emplacements.depots, racine_espaces=self.emplacements.espaces,
                             racine_bundles=self.emplacements.bundles, protocoles=("https", "file"), droits=False)
        self.coffre = _Coffre({"jeton-claude": "sk-ant-oat01-" + "c" * 40})
        self.hermes = Hermes()
        self.scenario = racine / "scenario.json"
        self.journal_agents = racine / "agents.jsonl"
        self.isolement = isolement or ISOLEMENT_B
        self.execution = Execution(
            politique=self.politique, emplacements=self.emplacements, depots=self.depots, coffre=self.coffre,
            journal=Journal(racine / "journal"), sortie=FileSortie(self.emplacements.sortie),
            envoyer=self.hermes.envoyer, lanceur=LanceurAgents(), isolement=self.isolement,
            quotas_claude=QuotasClaude(self.emplacements.quotas_claude),
            budget=Budget(self.emplacements.compteurs, cartes_par_jour=20, heures_par_jour=8),
            executables={"codex": [PYTHON, "-I", FAUX, str(self.scenario), "codex"],
                         "claude": [PYTHON, "-I", FAUX, str(self.scenario), "claude"]},
            intervalle_battement_s=0.2, grace_s=1.0)

    def jouer(self, *executions: dict) -> None:
        self.scenario.write_text(json.dumps({"executions": list(executions), "journal": str(self.journal_agents),
                                             "compteur": str(self.racine / "compteur")}), encoding="utf-8")
        (self.racine / "compteur").unlink(missing_ok=True)

    def invocations(self) -> list[dict]:
        if not self.journal_agents.exists():
            return []
        return [json.loads(l) for l in self.journal_agents.read_text(encoding="utf-8").splitlines()]

    def carte(self, **changements) -> contrat.DemandeCarte:
        carte = json.loads((EXEMPLES / "reclamer_reponse_carte.json").read_text(encoding="utf-8"))["carte"]
        carte.update({"branche_depart": None, "parents": []})
        carte.update(changements)
        if "carte" in changements:
            carte.setdefault("branche", f"hermes/{changements['carte']}")
            if changements.get("role") != "integration":
                carte["branche"] = f"hermes/{changements['carte']}"
        return contrat.DemandeCarte.model_validate(carte)

    def executer(self, demande, arret=None):
        return asyncio.run(self.execution.executer(demande, arret))


class _Coffre:
    def __init__(self, valeurs):
        self.valeurs = dict(valeurs)

    def lire(self, usage):
        return self.valeurs.get(usage)


@pytest.fixture
def banc(tmp_path) -> Banc:
    return Banc(tmp_path / "banc")


ECRIT = {"ecrire": {"nouveau.py": "X = 1\n"}}


# ------------------------------------------------------------------ chemin nominal


def test_claude_implementation_verifiee_et_terminee(banc):
    banc.jouer(dict(ECRIT, session="s-claude-1", modele="claude-sonnet-5"))
    issue = banc.executer(banc.carte())
    assert issue.route == "terminer" and issue.envoyee
    corps = issue.corps
    assert corps["issue"] == "termine" and corps["resume"] == "Travail fait par le faux agent."
    m = corps["metadonnees"]
    assert m["modele_demande"] == "sonnet" and m["modele_servi"] == "claude-sonnet-5" and m["effort"] == "medium"
    assert m["palier_demande"] == "default" and m["palier_servi"] is None and m["regime"] == "B"
    assert m["verification"] == {"etat": "reussie", "code": 0, "duree_s": m["verification"]["duree_s"],
                                 "tentatives": 1, "raison": None}
    assert m["diffstat"] == {"fichiers": 1, "ajouts": 1, "retraits": 1} and m["pilotage"] == {"touche": False,
                                                                                               "chemins": []}
    assert m["jetons"] == {"entree": 900, "sortie": 40, "cache": 100} and m["session_locale"] is True
    nu = banc.depots.nu("jetable")
    assert banc.depots.sha(nu, "refs/heads/hermes/t_ab12cd34") == m["tete"] != m["base"]
    message = subprocess.run(["git", f"--git-dir={nu}", "log", "-1", "--format=%an%n%B", m["tete"]],
                             capture_output=True, text=True, check=True).stdout
    assert message.startswith("ACP exécutant\nimplementation(t_ab12cd34): Travail fait") and "Co-Authored" not in message
    # Commandes imposées, consigne par l'entrée standard, jeton dans l'environnement de Claude seulement.
    appel = banc.invocations()[0]
    assert appel["outil"] == "claude" and "--restricted" in appel["argv"] and appel["jeton"] is True
    assert "Ajouter la commande « compter »" in appel["stdin"] and "Ajouter la commande" not in " ".join(appel["argv"])
    assert "CLAUDE_CODE_SKIP_PROMPT_HISTORY" not in appel["noms"]
    # Premier battement aussitôt ; file de sortie vide ; carte oubliée ; budget compté.
    assert banc.hermes.envois[0][0] == "battement"
    assert banc.execution.sortie.en_attente() == [] and banc.execution.carte_en_main() is None
    assert banc.execution.budget.etat()["cartes"] == 1


def test_verification_en_echec_puis_reprise_du_fil(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 2\n"}, "session": "s-1"}, dict(ECRIT, session="s-1"))
    issue = banc.executer(banc.carte())
    m = issue.corps["metadonnees"]
    assert issue.route == "terminer" and m["verification"]["etat"] == "reussie" and m["verification"]["tentatives"] == 2
    seconde = banc.invocations()[1]
    assert seconde["argv"][-2:] == ["--resume", "s-1"] and "La vérification a échoué (code 3)" in seconde["stdin"]


def test_verification_echouee_au_dela_des_reprises(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 2\n"}})
    issue = banc.executer(banc.carte())
    v = issue.corps["metadonnees"]["verification"]
    assert v["etat"] == "echouee" and v["code"] == 3 and v["tentatives"] == 3
    assert issue.corps["resume"].startswith("Vérification en échec : ")
    assert len([i for i in banc.invocations() if i["outil"] == "claude"]) == 3


def test_regime_b_sans_accord_verification_non_executee(tmp_path):
    banc = Banc(tmp_path / "banc", depot={"verification_sans_bac_a_sable": False})
    banc.jouer(ECRIT)
    issue = banc.executer(banc.carte())
    assert issue.route == "terminer"
    assert issue.corps["metadonnees"]["verification"] == {"etat": "non_executee", "tentatives": 0,
                                                          "raison": VERIF_NON_EXECUTEE}
    # Ni préparation ni vérification lancées : seul l'agent a tourné.
    assert [i["outil"] for i in banc.invocations()] == ["claude"]


# ------------------------------------------------------------------ contrôles (§ 6.6)


def test_fichiers_de_pilotage_en_revue(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "CLAUDE.md.": "consignes", "sous/AGENTS.md": "x"}})
    m = banc.executer(banc.carte()).corps["metadonnees"]
    # Windows retire le point final à la création du fichier : le faux y écrit donc « CLAUDE.md ».
    attendu = "CLAUDE.md." if os.name == "posix" else "CLAUDE.md"
    assert m["pilotage"]["touche"] is True and sorted(m["pilotage"]["chemins"]) == [attendu, "sous/AGENTS.md"]


def test_secret_quarantaine_et_rien_d_envoye(banc):
    secret = "sk-ant-api03-" + "s" * 40
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "config.py": f"CLE = '{secret}'\n"}})
    issue = banc.executer(banc.carte())
    assert issue.route == "bloquer" and issue.corps["genre"] == "secret" and issue.corps["raison"] == RAISON_SECRET
    assert secret not in json.dumps(banc.hermes.envois)
    assert banc.depots.branche_existe("jetable", "quarantaine/t_ab12cd34")
    assert not banc.depots.branche_existe("jetable", "hermes/t_ab12cd34")
    assert secret not in (banc.racine / "journal" / "poste.jsonl").read_text(encoding="utf-8")


def test_jeton_claude_exact_dans_le_diff(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "fuite.txt": banc.coffre.lire("jeton-claude")}})
    assert banc.executer(banc.carte()).corps["genre"] == "secret"


def test_question_apres_commit_wip(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n"},
                "sortie": {"issue": "question", "resume": "Deux options.", "question": "Garder Python 3.11 ?",
                           "verdict": None, "corrections": None}})
    issue = banc.executer(banc.carte())
    assert issue.route == "question" and issue.corps["texte"] == "Garder Python 3.11 ?"
    tete = banc.depots.sha(banc.depots.nu("jetable"), "refs/heads/hermes/t_ab12cd34")
    message = subprocess.run(["git", f"--git-dir={banc.depots.nu('jetable')}", "log", "-1", "--format=%s", tete],
                             capture_output=True, text=True, check=True).stdout.strip()
    assert message == "wip: question (t_ab12cd34)"


# ------------------------------------------------------------------ arrêts et blocages


def test_modele_servi_different_de_la_resolution(banc):
    banc.jouer(dict(ECRIT, modele="claude-opus-5-5", attendre_s=5))
    issue = banc.executer(banc.carte())
    assert issue.route == "bloquer" and issue.corps["genre"] == "capacite"
    assert "Modèle servi claude-opus-5-5 différent de la résolution documentée claude-sonnet-5" in issue.corps["raison"]


@pytest.mark.parametrize("servi, bloquee", [("claude-sonnet-5-5", True), ("claude-sonnet-5-1", True),
                                            ("claude-sonnet-5-20260915", False), ("claude-sonnet-5", False)])
def test_seul_un_suffixe_de_date_est_admis(banc, servi, bloquee):
    """Un modèle d'une autre version (« -5-5 ») n'est jamais pris pour un identifiant daté de l'alias documenté."""
    banc.jouer(dict(ECRIT, modele=servi))
    issue = banc.executer(banc.carte())
    if bloquee:
        assert issue.route == "bloquer" and f"Modèle servi {servi} différent" in issue.corps["raison"]
    else:
        assert issue.route == "terminer", issue.corps


def test_outil_d_execution_refuse(banc):
    banc.jouer(dict(ECRIT, outils=["Read", "Bash"], attendre_s=5))
    issue = banc.executer(banc.carte())
    assert issue.corps["genre"] == "capacite" and "Bash" in issue.corps["raison"]


def test_limite_claude_atteinte_quota_puis_voie_fermee(banc):
    remise = int(datetime.now(UTC).timestamp()) + 7200
    banc.jouer(dict(ECRIT, limite={"status": "rejected", "resetsAt": remise}))
    issue = banc.executer(banc.carte())
    assert issue.route == "bloquer" and issue.corps["genre"] == "quota"
    assert issue.corps["reprise_le"] == datetime.fromtimestamp(remise, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert banc.execution.voies_ouvertes()["poste-claude"] is not None


def test_reclamation_perdue_au_battement(banc):
    banc.hermes.battement = {"valide": False, "pause": False, "annuler": False}
    banc.jouer(dict(ECRIT, attendre_s=30))
    issue = banc.executer(banc.carte())
    assert issue.route == "reprendre" and issue.corps["motif"] == "reclamation_perdue"
    # La carte reste « en main » : le service l'annonce dans carte_en_cours pour qu'elle revienne à cet exécutant.
    assert banc.execution.carte_en_main()["carte"] == "t_ab12cd34"


def test_annulation_au_battement(banc):
    banc.hermes.battement = {"valide": True, "pause": True, "annuler": True}
    banc.jouer(dict(ECRIT, attendre_s=30))
    issue = banc.executer(banc.carte())
    assert issue.route == "arret" and issue.corps["motif"] == "annulee"


def test_arret_du_service_commit_wip_puis_arret(banc):
    banc.jouer(dict(ECRIT, attendre_s=30))

    async def scenario():
        arret = asyncio.Event()
        tache = asyncio.create_task(banc.execution.executer(banc.carte(), arret))
        await asyncio.sleep(1.5)
        arret.set()
        return await tache

    issue = asyncio.run(scenario())
    assert issue.route == "arret" and issue.corps["motif"] == "sigterm"


def test_duree_maximale_bloque(banc, monkeypatch):
    class Horloge:
        def __init__(self):
            self.t = 0.0

        def monotonic(self):
            self.t += 30.0
            return self.t

    monkeypatch.setattr(module_execution, "time", Horloge())
    banc.jouer(dict(ECRIT, attendre_s=30))
    issue = banc.executer(banc.carte(duree_max_s=60))
    assert issue.route == "bloquer" and issue.corps["genre"] == "duree"


def test_deux_arrets_memoire(banc):
    banc.jouer(dict(ECRIT, code=137))
    premiere = banc.executer(banc.carte())
    assert premiere.route == "reprendre" and premiere.corps["motif"] == "redemarrage"
    seconde = banc.executer(banc.carte(reprise=True))
    assert seconde.route == "bloquer" and seconde.corps["genre"] == "memoire"


def test_depot_inconnu_et_codex_ferme_en_regime_b(banc):
    issue = banc.executer(banc.carte(depot_alias="autre"))
    assert issue.corps["genre"] == "politique" and "absent de la politique" in issue.corps["raison"]
    issue = banc.executer(banc.carte(voie="poste-codex", modele="gpt-test"))
    assert issue.corps["genre"] == "capacite" and "poste-codex fermée" in issue.corps["raison"]
    assert banc.invocations() == []


def test_issue_gardee_en_file_si_hermes_injoignable(banc):
    banc.jouer(ECRIT)
    banc.hermes.panne = HermesIndisponible("Hermes indisponible (HTTP 503) : nouvel essai plus tard.", statut=503)
    issue = banc.executer(banc.carte())
    assert issue.route == "terminer" and not issue.envoyee
    attente = banc.execution.sortie.en_attente()
    assert len(attente) == 1 and FileSortie.lire(attente[0])[0] == "terminer"


# ------------------------------------------------------------------ Codex (régime A), reprise, relecture, intégration


def test_codex_regime_a_commandes_et_verification_sous_codex_sandbox(tmp_path):
    banc = Banc(tmp_path / "banc", isolement=ISOLEMENT_A, depot={"acces": "jeton_lecture"})
    banc.depots.jeton_lecture = lambda: "github_pat_" + "f" * 30
    banc.jouer(dict(ECRIT, session="thread-1"))
    issue = banc.executer(banc.carte(voie="poste-codex", modele="gpt-test", effort="high"))
    assert issue.route == "terminer", issue.corps
    m = issue.corps["metadonnees"]
    assert m["modele_servi"] is None and m["verification"]["etat"] == "reussie" and m["regime"] == "A"
    agent, sandbox = [i for i in banc.invocations() if i["outil"] == "codex"][0], \
        [i for i in banc.invocations() if i["outil"] == "codex-sandbox"][0]
    assert agent["argv"][:2] == ["exec", "--json"] and agent["argv"][-1] == "-"
    # Profil nommé imposé, SANS --sandbox (qui le ferait ignorer par Codex 0.156.1) : identifiants interdits.
    assert "--sandbox" not in agent["argv"] and 'default_permissions="acp_agent"' in agent["argv"]
    profil = next(a for a in agent["argv"] if a.startswith("permissions.acp_agent.filesystem="))
    assert '"/donnees/codex"="deny"' in profil and '":project_roots"="write"' in profil
    assert 'model_reasoning_effort="high"' in agent["argv"] and "CODEX_HOME" in agent["noms"]
    assert agent["jeton"] is False and "Ajouter la commande" in agent["stdin"]
    assert sandbox["argv"][:5] == ["sandbox", "-P", "acp_verif", "-C", sandbox["argv"][4]]


def test_codex_refuse_sur_un_depot_public(tmp_path):
    banc = Banc(tmp_path / "banc", isolement=ISOLEMENT_A)
    issue = banc.executer(banc.carte(voie="poste-codex", modele="gpt-test"))
    assert issue.corps["genre"] == "politique" and "D83" in issue.corps["raison"]


def test_reprise_du_fil_avec_les_reponses(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n"}, "session": "s-9",
                "sortie": {"issue": "question", "resume": "?", "question": "Quelle base ?", "verdict": None,
                           "corrections": None}},
               dict(ECRIT, session="s-9"))
    assert banc.executer(banc.carte()).route == "question"
    reponse = {"genre": "question", "question": "q_0123456789ab", "texte": "Garde main.",
               "repondu_par": "proprietaire", "le": "2026-10-02T10:00:00Z"}
    issue = banc.executer(banc.carte(run_id=18, reprise=True, reponses=[reponse]))
    assert issue.route == "terminer" and issue.corps["metadonnees"]["session_locale"] is True
    seconde = banc.invocations()[1]
    assert seconde["argv"][-2:] == ["--resume", "s-9"]
    assert "Reprise de la carte t_ab12cd34" in seconde["stdin"] and "Garde main." in seconde["stdin"]


RELECTURE = {"modele": "claude-opus-5-5", "lire_texte": ["{add_dir}/diff.patch", "nouveau.py"],
             "sortie": {"issue": "termine", "resume": "Relu.", "question": None, "verdict": "corrections",
                        "corrections": "Ajouter un test."}}


def _lectures_du_relecteur(banc) -> dict[str, str]:
    return {i["texte"]: i["contenu"] for i in banc.invocations() if "texte" in i}


def test_relecture_lit_le_diff_et_rend_des_corrections(banc):
    """Haute (relecture de P6) : la relecture est servie par Hermes SANS branche de départ (greffon : ``None`` pour
    une relecture) ; son worktree partait de ``origin/<base>`` et ne contenait pas le code relu. Il part désormais de
    la branche relue, et le relecteur lit vraiment le diff ET le code relu."""
    banc.jouer(ECRIT)
    assert banc.executer(banc.carte()).route == "terminer"
    banc.jouer(RELECTURE)
    issue = banc.executer(banc.carte(carte="t_cd34ef56", role="relecture", carte_relue="t_ab12cd34",
                                     branche_depart=None, modele="opus"))
    assert issue.route == "terminer" and issue.corps["verdict"] == "corrections"
    assert issue.corps["corrections"] == "Ajouter un test."
    appel = [i for i in banc.invocations() if i.get("outil") == "claude"][-1]
    assert appel["argv"][appel["argv"].index("--tools") + 1] == "Read,Glob,Grep"
    assert "diff.patch" in appel["stdin"] and issue.corps["metadonnees"]["verification"]["etat"] == "non_executee"
    lectures = _lectures_du_relecteur(banc)
    assert "+X = 1" in lectures["{add_dir}/diff.patch"] and "-X = 0" in lectures["{add_dir}/diff.patch"]
    assert lectures["nouveau.py"] == "X = 1\n"
    # Rien n'a changé pendant la relecture : sa branche porte le code relu, sans commit de plus.
    m = issue.corps["metadonnees"]
    assert m["diffstat"] == {"fichiers": 0, "ajouts": 0, "retraits": 0} and m["pilotage"]["touche"] is False


def test_relecture_d_une_branche_absente_bloquee(banc):
    """Branche relue absente de l'exécutant : carte bloquée, avec la raison, plutôt qu'une relecture à l'aveugle."""
    banc.jouer(RELECTURE)
    issue = banc.executer(banc.carte(carte="t_cd34ef56", role="relecture", carte_relue="t_99999999",
                                     branche_depart=None, modele="opus"))
    assert issue.route == "bloquer" and issue.corps["genre"] == "capacite"
    assert "hermes/t_99999999 absente de l'exécutant" in issue.corps["raison"]
    assert not [i for i in banc.invocations() if i.get("outil") == "claude"]


def test_integration_fusionne_et_bloque_sur_conflit(banc):
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "a.txt": "a\n"}})
    assert banc.executer(banc.carte(carte="t_aaaa1111")).route == "terminer"
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "b.txt": "b\n"}})
    assert banc.executer(banc.carte(carte="t_bbbb2222")).route == "terminer"
    integration = dict(carte="t_cccc3333", role="integration", voie="poste-integration", modele=None, effort=None,
                       palier=None, branche="hermes/projet-demo",
                       branches_a_integrer=["hermes/t_aaaa1111", "hermes/t_bbbb2222"])
    issue = banc.executer(banc.carte(**integration))
    assert issue.route == "terminer" and issue.corps["metadonnees"]["branche"] == "hermes/projet-demo"
    assert issue.corps["metadonnees"]["verification"]["etat"] == "reussie"
    assert banc.depots.sha(banc.depots.nu("jetable"), "refs/heads/hermes/projet-demo") == \
        issue.corps["metadonnees"]["tete"]
    banc.jouer({"ecrire": {"README.md": "version d\n"}})
    banc.executer(banc.carte(carte="t_dddd4444"))
    banc.jouer({"ecrire": {"README.md": "version e\n"}})
    banc.executer(banc.carte(carte="t_eeee5555"))
    conflit = banc.executer(banc.carte(**dict(integration, carte="t_ffff6666", branche="hermes/projet-autre",
                                              branches_a_integrer=["hermes/t_dddd4444", "hermes/t_eeee5555"])))
    assert conflit.route == "bloquer" and conflit.corps["genre"] == "capacite"
    assert "Conflit d'intégration : README.md" in conflit.corps["raison"]


# ------------------------------------------------------------------ UID dédiés (conteneur, root)


@RACINE_LINUX
def test_agent_sous_son_uid_ecrit_le_worktree_sans_lire_les_secrets():
    from acp_poste.plateforme.linux import IDENTITES, CoffreFichiers

    racine = Path(tempfile.mkdtemp(prefix="acp-uid-", dir="/tmp"))
    os.chmod(racine, 0o755)
    banc = Banc(racine / "banc")
    os.chmod(racine / "banc", 0o755)
    banc.depots.droits = True
    banc.execution.lanceur = LanceurAgents(identites=dict(IDENTITES), droits=True)
    coffre = CoffreFichiers(banc.emplacements.secrets)
    coffre.ecrire("jeton-machine", "acpm_" + "m" * 43)
    coffre.ecrire("jeton-claude", "sk-ant-oat01-" + "c" * 40)
    banc.execution.coffre = coffre
    for chemin in (banc.emplacements.donnees, banc.emplacements.tmp.parent, banc.emplacements.tmp):
        chemin.mkdir(parents=True, exist_ok=True)
        os.chmod(chemin, 0o755)
    os.chmod(banc.emplacements.acp, 0o700)
    banc.jouer(dict(ECRIT, lire=[str(banc.emplacements.secrets / "jeton-machine"), "/proc/1/environ"]))
    os.chmod(banc.scenario, 0o644)
    # Journal et compteur du faux agent : inscriptibles par l'UID de l'agent (le dossier du banc est à root).
    for fichier in (banc.journal_agents, banc.racine / "compteur"):
        fichier.write_text("", encoding="utf-8")
        os.chmod(fichier, 0o666)
    issue = banc.executer(banc.carte())
    assert issue.route == "terminer", issue.corps.get("raison")
    appel = next(i for i in banc.invocations() if i.get("outil") == "claude")
    assert appel["uid"] == 10002
    lectures = {i["lecture"]: i["issue"] for i in banc.invocations() if "lecture" in i}
    assert set(lectures.values()) == {"refusé"}
    worktree = banc.depots.espace("jetable", "t_ab12cd34")
    assert (os.stat(worktree).st_uid, os.stat(worktree).st_mode & 0o777) == (0, 0o700)


@RACINE_LINUX
def test_relecture_sous_uid_lit_le_diff_et_le_code_relu():
    """Haute (relecture de P6) : sous les VRAIS UID, ``diff.patch`` était écrit par root en 0640 root:root dans un
    dossier root:acp-travail 0750 : illisible par acp-claude (10002) et acp-codex (10001). Il appartient désormais au
    groupe acp-travail ; l'agent, lancé sous son UID par setpriv, le lit, ainsi que le code relu."""
    from acp_poste.plateforme.linux import IDENTITES, CoffreFichiers

    racine = Path(tempfile.mkdtemp(prefix="acp-uid-", dir="/tmp"))
    os.chmod(racine, 0o755)
    banc = Banc(racine / "banc")
    os.chmod(racine / "banc", 0o755)
    banc.depots.droits = True
    banc.execution.lanceur = LanceurAgents(identites=dict(IDENTITES), droits=True)
    coffre = CoffreFichiers(banc.emplacements.secrets)
    coffre.ecrire("jeton-claude", "sk-ant-oat01-" + "c" * 40)
    banc.execution.coffre = coffre
    for chemin in (banc.emplacements.donnees, banc.emplacements.tmp.parent, banc.emplacements.tmp):
        chemin.mkdir(parents=True, exist_ok=True)
        os.chmod(chemin, 0o755)
    os.chmod(banc.emplacements.acp, 0o700)

    def jouer(*executions):
        banc.jouer(*executions)
        os.chmod(banc.scenario, 0o644)
        for fichier in (banc.journal_agents, banc.racine / "compteur"):
            if not fichier.exists():
                fichier.write_text("", encoding="utf-8")
            os.chmod(fichier, 0o666)

    jouer(ECRIT)
    assert banc.executer(banc.carte()).route == "terminer"
    jouer(RELECTURE)
    issue = banc.executer(banc.carte(carte="t_cd34ef56", role="relecture", carte_relue="t_ab12cd34",
                                     branche_depart=None, modele="opus"))
    assert issue.route == "terminer", issue.corps.get("raison")
    appel = [i for i in banc.invocations() if i.get("outil") == "claude"][-1]
    assert appel["uid"] == 10002
    lectures = _lectures_du_relecteur(banc)
    assert "+X = 1" in lectures["{add_dir}/diff.patch"], lectures
    assert lectures["nouveau.py"] == "X = 1\n"


# ------------------------------------------------------------------ chemins posés par un agent (relecture de P6)


@POSIX
def test_dossier_de_tentative_piege_par_un_lien_refuse(banc, tmp_path):
    """Moyenne (relecture de P6) : /tmp/acp est inscriptible par le groupe des agents. Un lien posé à la place du
    dossier d'une carte était SUIVI par root (``mkdir(exist_ok=True)``, ``chown``, ``chmod``) : mode de la cible changé,
    dossiers créés dedans. Il est désormais refusé ; rien n'est suivi ni lancé."""
    cible = tmp_path / "cible"
    cible.mkdir()
    os.chmod(cible, 0o700)
    banc.emplacements.tmp.mkdir(parents=True, exist_ok=True)
    (banc.emplacements.tmp / "t_ab12cd34").symlink_to(cible, target_is_directory=True)
    banc.jouer(ECRIT)
    issue = banc.executer(banc.carte())
    assert issue.route == "bloquer" and issue.corps["genre"] == "capacite", issue.corps
    assert "piégé" in issue.corps["raison"]
    assert stat.S_IMODE(os.stat(cible).st_mode) == 0o700 and list(cible.iterdir()) == []
    assert not [i for i in banc.invocations() if i.get("outil")]


@POSIX
def test_reponse_de_codex_en_lien_jamais_suivie(tmp_path):
    """Basse (relecture de P6) : root lisait ``reponse.json`` (dossier de acp-codex) par ``read_text`` : un lien y
    était suivi, et le fichier visé devenait la sortie de la carte. Il est désormais refusé (fichier ordinaire exigé,
    lu sans suivre de lien, 64 Kio au plus) : carte bloquée, rien du fichier visé n'est envoyé."""
    banc = Banc(tmp_path / "banc", isolement=ISOLEMENT_A, depot={"acces": "jeton_lecture"})
    banc.depots.jeton_lecture = lambda: "github_pat_" + "f" * 30
    piege = tmp_path / "piege.json"
    piege.write_text(json.dumps({"issue": "termine", "resume": "Lu par root au travers d'un lien.", "question": None,
                                 "verdict": None, "corrections": None}), encoding="utf-8")
    banc.jouer(dict(ECRIT, reponse_lien=str(piege)))
    issue = banc.executer(banc.carte(voie="poste-codex", modele="gpt-test", effort="high"))
    assert issue.route == "bloquer" and issue.corps["genre"] == "capacite", issue.corps
    assert "Lu par root" not in json.dumps(banc.hermes.envois, ensure_ascii=False)


def test_base_perdue_retrouvee_par_l_ancetre_commun(banc):
    banc.jouer(ECRIT)
    premiere = banc.executer(banc.carte()).corps["metadonnees"]
    # État local perdu (volume restauré) et branche de base avancée entre-temps.
    (banc.emplacements.sessions / "t_ab12cd34.json").unlink()
    (banc.distant / "README.md").write_text("Avancé\n", encoding="utf-8")
    _git(banc.distant, "commit", "-qam", "avance")
    banc.jouer({"ecrire": {"nouveau.py": "X = 1\n", "suite.txt": "s\n"}})
    seconde = banc.executer(banc.carte(run_id=18)).corps["metadonnees"]
    assert seconde["base"] == premiere["base"]
    assert seconde["diffstat"]["fichiers"] == 2  # nouveau.py et suite.txt, jamais README.md de la base


def test_nul_dans_la_sortie_de_l_agent_retire_avant_commit_et_envoi(banc):
    """Relecture de P6 : un NUL dans le résumé faisait lever ValueError au commit (titre tiré du résumé), hors de toute
    reprise : la carte restait réclamée jusqu'à son échéance, puis était resservie. Retiré à la validation."""
    banc.jouer(dict(ECRIT, sortie={"issue": "termine", "resume": "Travail fait.\x00", "question": None,
                                   "verdict": None, "corrections": None}))
    issue = banc.executer(banc.carte())
    assert issue.route == "terminer" and issue.envoyee and issue.corps["resume"] == "Travail fait."
    sujet = _git(banc.depots.nu("jetable"), "log", "-1", "--format=%s", "hermes/t_ab12cd34")
    assert sujet == "implementation(t_ab12cd34): Travail fait."


def test_issue_refusee_avant_l_envoi_devient_un_blocage(banc):
    """Une issue que le contrat refuse côté exécutant (cas résiduel) est rangée dans sortie/refusees et Hermes reçoit
    un ``bloquer(capacite)`` composé ici, sans rien du contenu refusé, au lieu d'attendre l'échéance."""
    banc.jouer(ECRIT)
    envoyer = banc.execution.envoyer

    def refuser_terminer(route, corps):
        if route == "terminer":
            raise RefusAvantEnvoi("Envoi « terminer » refusé par le contrat : test. Rien n'a été envoyé.")
        return envoyer(route, corps)

    banc.execution.envoyer = refuser_terminer
    issue = banc.executer(banc.carte())
    assert issue.route == "bloquer" and issue.envoyee and issue.corps["genre"] == "capacite"
    assert "refusée par le contrat de l'exécutant avant l'envoi" in issue.corps["raison"]
    assert banc.execution.sortie.en_attente() == []
    assert len(list((banc.emplacements.sortie / "refusees").iterdir())) == 1


def test_commande_de_verification_introuvable_sans_reprise_de_l_agent(tmp_path):
    """Relecture de P6 : avec la forme « uv » de executant.toml (uv absent de l'image), chaque carte finissait en
    « Vérification en échec » après deux reprises inutiles de l'agent (quota consommé), raison vide. Code 127 : état
    dit, raison donnée, aucune reprise."""
    banc = Banc(tmp_path / "banc", depot={"verification": ("outil-absent-acp", "run", "-q")})
    banc.jouer(ECRIT)
    issue = banc.executer(banc.carte())
    v = issue.corps["metadonnees"]["verification"]
    assert issue.route == "terminer" and (v["etat"], v["code"], v["tentatives"]) == ("echouee", 127, 1), v
    assert v["raison"].startswith("Commande de vérification introuvable sur l'exécutant (code 127)")
    assert issue.corps["resume"].startswith("Vérification impossible (outil introuvable sur l'exécutant) : ")
    assert len([i for i in banc.invocations() if i.get("outil") == "claude"]) == 1


def test_preparation_introuvable_dite_sans_verification_ni_reprise(tmp_path):
    banc = Banc(tmp_path / "banc", depot={"preparation": ("outil-absent-acp", "sync", "--frozen")})
    banc.jouer(ECRIT)
    issue = banc.executer(banc.carte())
    v = issue.corps["metadonnees"]["verification"]
    assert (v["etat"], v["code"], v["tentatives"]) == ("echouee", 127, 0), v
    assert v["raison"].startswith("Préparation des dépendances introuvable sur l'exécutant (code 127)")
    assert len([i for i in banc.invocations() if i.get("outil") == "claude"]) == 1
    # Préparation non marquée faite : elle sera retentée à la reprise, après correction de la politique.
    assert not banc.execution.session("t_ab12cd34").get("prepare")
