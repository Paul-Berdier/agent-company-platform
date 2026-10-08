"""Boucle de l'exécutant Linux (cahier P6 § 6.1, § 6.4, § 7.6) contre un faux protocole en mémoire, de faux CLI
(sondes P5 : ``faux_codex.py``, ``faux_claude.py`` ; cartes : ``faux_agents.py``) et un dépôt « distant » local.

POSIX seulement : l'exécutant est Linux (droits 0644/0755 de ``executant.toml``, coffre en fichiers 0600). Sans root
(CI Linux), les agents tournent sous le compte du test ; le conteneur de test les lance aussi ainsi (identités vides) :
le changement d'UID est éprouvé à part (``test_execution.py``, ``test_plateforme.py``).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from acp_poste.contexte import Contexte
from acp_poste.depots import Depots
from acp_poste.plateforme.linux import CoffreFichiers, EmplacementsLinux
from acp_poste.protocole import JetonRefuse, PosteRevoque, Protocole
from acp_poste.service import Repli
from acp_poste.service_executant import ServiceExecutant, servir_executant
from acp_poste.sortie import FileSortie, nouvel_id_envoi
from acp_poste_contrat import machine as contrat
from acp_poste_contrat.inventaire import valider_inventaire

pytestmark = pytest.mark.skipif(os.name != "posix", reason="exécutant Linux (droits POSIX, coffre 0600)")

ICI = Path(__file__).resolve().parent
RACINE_DEPOT = ICI.parents[2]
PYTHON = str(Path(sys.executable).resolve())
JETON = "acpm_" + "e" * 43
EXEMPLES = RACINE_DEPOT / "hermes" / "tests" / "outils" / "fixtures_machine"
ISOLEMENT_B = {"regime": "B", "bwrap": "refuse", "proc_neuf": False, "reseau_coupe": False, "uid_separes": True,
               "codex_sans_bac_a_sable": "refuse", "ecriture_admise": {"codex": False, "claude": True},
               "raison": "Régime B : bubblewrap refusé par la plateforme.", "sonde_le": "2026-10-01T10:00:00Z"}


def _maintenant() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class FauxProtocole:
    """``reclamer``, ``publier`` et les six routes, en mémoire ; chaque corps est validé par le contrat."""

    def __init__(self) -> None:
        self.appels: list[tuple[str, dict | None]] = []
        self.cartes: list[dict] = []
        self.pannes: list[Exception] = []
        self.client = SimpleNamespace(interrompre=lambda: None)
        self.inventaires: list[dict] = []

    def reclamer(self, jeton, *, acquittes, attente_max_s, politique_valide, execution=None):
        time.sleep(0.05)
        self.appels.append(("reclamer", execution))
        if self.pannes:
            raise self.pannes.pop(0)
        carte = None
        demandee = bool(self.cartes) and execution is not None and execution["peut_executer"] and \
            self.cartes[0]["voie"] in execution["voies_disponibles"]
        if demandee and not execution.get("carte_en_cours"):
            carte = self.cartes.pop(0)
        return contrat.ReponseReclamer.model_validate({
            "maintenant": _maintenant(), "etat_machine": "actif", "pause_reclamations": False, "ordres": [],
            "carte": carte, "remplace": False, "prochaine_attente_s": 0})

    def publier(self, jeton, inventaire):
        valider_inventaire(inventaire)
        self.inventaires.append(inventaire)
        return contrat.ReponseInventaire.model_validate({"recu_le": _maintenant(), "releves": {"poste-claude": 1}})

    def envoyer(self, jeton, route, corps):
        modele, reponse, _borne = contrat.MODELES_P6[f"{contrat.PREFIXE_ROUTES}/{route}"]
        contrat.valider(getattr(contrat, modele), corps, quoi=route)
        self.appels.append((route, corps))
        documents = {"battement": {"valide": True, "pause": False, "annuler": False}, "terminer": {"etat": "done"},
                     "question": {"question": "q_0123456789ab", "etat": "ouverte"}, "bloquer": {"etat": "bloquee"},
                     "reprendre": {"etat": "rendue"}, "arret": {"etat": "rendue"}}
        return getattr(contrat, reponse).model_validate(documents[route])

    def routes(self) -> list[str]:
        return [r for r, _c in self.appels]


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "-c",
                    "init.defaultBranch=main", *argv], cwd=cwd, check=True, capture_output=True)


class Banc:
    def __init__(self, racine: Path, poste) -> None:
        self.racine = racine
        self.emplacements = EmplacementsLinux.de_test(racine)
        self.distant = racine / "distant"
        self.distant.mkdir(parents=True)
        _git(self.distant, "init", "-q")
        (self.distant / "nouveau.py").write_text("X = 0\n", encoding="utf-8")
        _git(self.distant, "add", "-A")
        _git(self.distant, "commit", "-qm", "initial")
        texte = (RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8").replace(
            'origine = "https://<libellé-hermes>.up.railway.app"', 'origine = "https://hermes-acp-test.up.railway.app"')
        texte += ('\n[depots.jetable]\nurl = "https://github.com/proprietaire-factice/jetable.git"\nacces = "public"\n'
                  f'verification = ["{PYTHON}", "-c", "import sys; sys.exit(0)"]\n'
                  'verification_sans_bac_a_sable = true\n')
        # Binaires des CLI : fichiers de la racine jetable (0755, au compte du test) ; les sondes et les cartes
        # lancent les faux CLI injectés, jamais ces fichiers.
        for binaire in (self.emplacements.codex_par_defaut, self.emplacements.claude_par_defaut):
            binaire.parent.mkdir(parents=True, exist_ok=True)
            binaire.write_bytes(b"binaire factice")
            os.chmod(binaire, 0o755)
            os.chmod(binaire.parent, 0o755)
        texte = texte.replace('"/opt/acp/outils/codex/codex"', f'"{self.emplacements.codex_par_defaut}"')
        texte = texte.replace('"/opt/acp/outils/claude/claude"', f'"{self.emplacements.claude_par_defaut}"')
        texte = texte.replace('home = "/donnees/codex"', f'home = "{self.emplacements.codex_home}"')
        texte = texte.replace('config_dir = "/donnees/claude"', f'config_dir = "{self.emplacements.claude_config}"')
        politique = self.emplacements.politique
        politique.parent.mkdir(parents=True)
        politique.write_text(texte, encoding="utf-8")
        os.chmod(politique, 0o444)
        os.chmod(politique.parent, 0o755)
        self.coffre = CoffreFichiers(self.emplacements.secrets)
        self.coffre.ecrire("jeton-claude", "sk-ant-oat01-" + "c" * 40)
        self.protocole = FauxProtocole()
        poste.scenario_claude = {"version": "2.1.283 (Claude Code)", "code_auth": 0}
        self.lanceurs = poste.lanceurs()
        self.scenario = racine / "scenario.json"
        self.scenario.write_text(json.dumps({"executions": [{"ecrire": {"nouveau.py": "X = 1\n"}}],
                                             "journal": str(racine / "agents.jsonl"),
                                             "compteur": str(racine / "compteur")}), encoding="utf-8")
        self.arret = asyncio.Event()
        distant = self.distant

        class DepotsLocaux(Depots):
            def recuperer(self, depot):
                return super().recuperer(dataclasses.replace(depot, url=str(distant)))

            def visibilite(self, depot, **options):
                # Étape P7 : mesure contre le dépôt LOCAL (aucun appel réseau ; lu sans identifiant : « public »).
                return super().visibilite(dataclasses.replace(depot, url=str(distant)), **options)

        self.fabrique_depots = lambda pol: DepotsLocaux(
            racine_depots=self.emplacements.depots, racine_espaces=self.emplacements.espaces,
            racine_bundles=self.emplacements.bundles, protocoles=("https", "file"), droits=False)

    def contexte(self) -> Contexte:
        return Contexte(emplacements=self.emplacements, coffre=self.coffre, lanceurs=self.lanceurs,
                        plateforme="linux",
                        infos_plateforme=lambda: {"plateforme": "linux", "hote": "pc", "noyau": "6.1.0",
                                                  "windows": None})

    def servir(self, **options):
        defaut = dict(sonde=lambda c, p, j: dict(ISOLEMENT_B), controles_systeme=False, proprietaire=os.geteuid(),
                      signaux=False, arret=self.arret, relecture_jeton_s=0.1, attente_jeton_refuse_s=0.3,
                      repli=lambda: Repli(maximum=0.2), protocole=self.protocole,
                      fabrique_depots=self.fabrique_depots, intervalle_battement_s=0.2,
                      executables={"claude": [PYTHON, "-I", str(ICI / "faux_agents.py"), str(self.scenario),
                                              "claude"]})
        defaut.update(options)
        return servir_executant(self.contexte(), **defaut)

    def carte(self, **changements) -> dict:
        carte = json.loads((EXEMPLES / "reclamer_reponse_carte.json").read_text(encoding="utf-8"))["carte"]
        carte.update({"branche_depart": None, "parents": []})
        carte.update(changements)
        return carte


async def _jusqu_a(predicat, delai_s: float = 20.0) -> bool:
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        if predicat():
            return True
        await asyncio.sleep(0.05)
    return predicat()


@pytest.fixture
def banc(tmp_path, poste) -> Banc:
    return Banc(tmp_path / "exec", poste)


# ------------------------------------------------------------------ enrôlement, révocation, jeton refusé (§ 7.6)


async def test_attente_d_enrolement_sans_sortie_ni_requete(banc, capfd):
    tache = asyncio.create_task(banc.servir())
    await asyncio.sleep(0.6)
    assert not tache.done() and banc.protocole.appels == []
    lignes = (banc.emplacements.journal / "poste.jsonl").read_text(encoding="utf-8")
    assert lignes.count("non_enrole") == 1 and "railway ssh" in lignes
    # Relecture de P6 : l'attente se lit AUSSI dans les journaux du conteneur (Railway), une fois au début.
    assert capfd.readouterr().err.count("[acp] Exécutant non enrôlé") == 1
    banc.coffre.ecrire("jeton-machine", JETON)
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    assert await asyncio.wait_for(tache, 10) == 0


async def test_revocation_retour_a_l_attente_sans_sortie(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.protocole.pannes = [PosteRevoque("Poste révoqué sur la page Poste.", statut=401, code="poste_revoque")]
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: not banc.coffre.present("jeton-machine"))
    nombre = len(banc.protocole.appels)
    await asyncio.sleep(0.6)
    assert not tache.done() and len(banc.protocole.appels) == nombre
    banc.arret.set()
    assert await asyncio.wait_for(tache, 10) == 0


async def test_jeton_refuse_garde_et_reessaie(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.protocole.pannes = [JetonRefuse("Jeton machine refusé.", statut=401)]
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: len([r for r in banc.protocole.routes() if r == "reclamer"]) >= 2)
    assert banc.coffre.present("jeton-machine") and not tache.done()
    banc.arret.set()
    assert await asyncio.wait_for(tache, 10) == 0


# ------------------------------------------------------------------ une carte de bout en bout


async def test_sondes_puis_carte_claude_executee(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.protocole.cartes = [banc.carte()]
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "terminer" in banc.protocole.routes(), 60)
    banc.arret.set()
    assert await asyncio.wait_for(tache, 30) == 0
    annonces = [e for r, e in banc.protocole.appels if r == "reclamer"]
    # Avant toute sonde, seule l'intégration (aucune CLI d'agent) est ouverte ; la voie Claude s'ouvre après la sonde.
    assert annonces[0]["peut_executer"] is True and annonces[0]["voies_disponibles"] == ["poste-integration"]
    servie = next(e for e in annonces if "poste-claude" in e["voies_disponibles"])
    assert servie["voies_disponibles"] == ["poste-claude", "poste-integration"]
    assert servie["espace_libre_mio"] is not None and servie["carte_en_cours"] is None
    inventaire = banc.protocole.inventaires[0]
    assert inventaire["poste"]["plateforme"] == "linux" and inventaire["isolement_linux"]["regime"] == "B"
    # Étape P7 : visibilité MESURÉE du dépôt publiée dès le premier inventaire (dépôt local lu sans identifiant).
    depot = inventaire["depots"][0]
    assert {k: depot[k] for k in ("alias", "visibilite", "lecture")} == {"alias": "jetable", "visibilite": "public",
                                                                         "lecture": "ok"}
    assert depot["verifie_le"].endswith("Z") and all(r["depots"] == inventaire["depots"]
                                                     for r in inventaire["releves"])
    claude = next(r for r in inventaire["releves"] if r["voie"] == "poste-claude")
    assert claude["compteurs"][0]["source"] == "claude_code_rate_limit_event"
    terminer = next(c for r, c in banc.protocole.appels if r == "terminer")
    assert terminer["metadonnees"]["verification"]["etat"] == "reussie"
    etat = json.loads(banc.emplacements.etat_service.read_text(encoding="utf-8"))
    assert etat["execution"]["regime"] == "B"


async def test_arret_pendant_une_carte(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.scenario.write_text(json.dumps({"executions": [{"attendre_s": 60}],
                                         "journal": str(banc.racine / "agents.jsonl"),
                                         "compteur": str(banc.racine / "compteur")}), encoding="utf-8")
    banc.protocole.cartes = [banc.carte()]
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "battement" in banc.protocole.routes(), 60)
    debut = time.monotonic()
    banc.arret.set()
    assert await asyncio.wait_for(tache, 60) == 0
    assert time.monotonic() - debut < 30
    arret = next(c for r, c in banc.protocole.appels if r == "arret")
    assert arret["motif"] == "sigterm"
    en_main = json.loads(banc.emplacements.carte.read_text(encoding="utf-8"))
    assert en_main["etape"] == "arretee"


def _raisons_annoncees(banc: Banc) -> list[str]:
    """Raison écrite dans l'état du service au moment de CHAQUE réclamation (l'annonce de ``reclamer`` ne porte que
    ``peut_executer`` : sa raison est écrite par ``calculer_annonce``, juste avant l'appel)."""
    raisons: list[str] = []
    reclamer = banc.protocole.reclamer

    def reclamer_et_noter(jeton, **options):
        etat = json.loads(banc.emplacements.etat_service.read_text(encoding="utf-8"))
        raisons.append(etat["execution"]["raison"])
        return reclamer(jeton, **options)

    banc.protocole.reclamer = reclamer_et_noter
    return raisons


def _annonces(banc: Banc) -> list[dict]:
    return [e for r, e in banc.protocole.appels if r == "reclamer" and e is not None]


async def test_pause_locale_aucune_execution(banc):
    """Relecture finale de P7 (constat tests-2, échec de la CI 36996679349) : la raison est lue AVANT l'arrêt. Lue après,
    elle dépendait du moment où l'arrêt tombait : pendant la file de sortie, l'annonce suivante dit — à raison —
    « Arrêt de l'exécutant en cours. » (l'arrêt prime sur la pause locale)."""
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.emplacements.pause_locale.parent.mkdir(parents=True, exist_ok=True)
    banc.emplacements.pause_locale.write_text("pause", encoding="utf-8")
    raisons = _raisons_annoncees(banc)
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: len(banc.protocole.routes()) >= 3)
    avant = list(raisons)
    assert len(avant) >= 3 and all(r.startswith("Pause locale") for r in avant)
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    assert all(e["peut_executer"] is False for e in _annonces(banc))
    assert banc.protocole.inventaires == []  # aucune sonde en pause


async def test_pause_locale_puis_arret_pendant_la_file_de_sortie(banc, monkeypatch):
    """Le cas exact de la CI 36996679349, rendu déterministe : l'arrêt tombe PENDANT la file de sortie (après le test
    d'arrêt d'entrée de la boucle). Aucune carte n'est demandée ; les réclamations d'avant disent la pause, et celle qui
    suit éventuellement dit l'arrêt, qui prime sur la pause locale."""
    banc.coffre.ecrire("jeton-machine", JETON)
    banc.emplacements.pause_locale.parent.mkdir(parents=True, exist_ok=True)
    banc.emplacements.pause_locale.write_text("pause", encoding="utf-8")
    raisons = _raisons_annoncees(banc)
    boucle = asyncio.get_running_loop()
    rejouer = FileSortie.rejouer

    def rejouer_puis_arreter(self, envoi):
        resultat = rejouer(self, envoi)
        if len(raisons) >= 3 and not banc.arret.is_set():
            boucle.call_soon_threadsafe(banc.arret.set)  # rejouer tourne dans un fil (asyncio.to_thread)
            time.sleep(0.2)  # l'arrêt est posé avant la fin de la file de sortie
        return resultat

    monkeypatch.setattr(FileSortie, "rejouer", rejouer_puis_arreter)
    tache = asyncio.create_task(banc.servir())
    await asyncio.wait_for(tache, 20)
    assert len(raisons) >= 3 and all(e["peut_executer"] is False for e in _annonces(banc))
    pause = [r for r in raisons if r.startswith("Pause locale")]
    arret = [r for r in raisons if r == "Arrêt de l'exécutant en cours."]
    assert len(pause) >= 3 and len(arret) <= 1 and pause + arret == raisons
    assert banc.protocole.inventaires == []


# ------------------------------------------------------------------ redémarrage et file de sortie (§ 5.9, § 6.4)


def _carte_en_main(banc: Banc, etape: str) -> None:
    banc.emplacements.etat.mkdir(parents=True, exist_ok=True)
    banc.emplacements.carte.write_text(json.dumps({
        "tableau": "acp-outil-jetable-3f2a", "carte": "t_ab12cd34", "run_id": 17, "voie": "poste-claude",
        "role": "implementation", "depot_alias": "jetable", "etape": etape}), encoding="utf-8")


async def test_file_rejouee_avant_reclamer_puis_reprise_au_demarrage(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    corps = json.loads((EXEMPLES / "bloquer_requete.json").read_text(encoding="utf-8"))
    corps["id_envoi"] = nouvel_id_envoi()
    FileSortie(banc.emplacements.sortie).deposer("bloquer", corps)
    _carte_en_main(banc, "agent")
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    routes = banc.protocole.routes()
    assert routes[:3] == ["bloquer", "reprendre", "reclamer"]
    reprendre = next(c for r, c in banc.protocole.appels if r == "reprendre")
    assert reprendre["motif"] == "redemarrage"
    annonce = next(e for r, e in banc.protocole.appels if r == "reclamer")
    assert annonce["carte_en_cours"] == {"tableau": "acp-outil-jetable-3f2a", "carte": "t_ab12cd34", "run_id": 17}


async def test_second_arret_brutal_bloque_en_memoire(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    _carte_en_main(banc, "agent")
    banc.emplacements.sessions.mkdir(parents=True, exist_ok=True)
    (banc.emplacements.sessions / "t_ab12cd34.json").write_text(json.dumps({"oom": 1}), encoding="utf-8")
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    bloquer = next(c for r, c in banc.protocole.appels if r == "bloquer")
    assert bloquer["genre"] == "memoire" and not banc.emplacements.carte.exists()


async def test_carte_rendue_proprement_pas_de_reprise(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    _carte_en_main(banc, "arretee")
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    assert "reprendre" not in banc.protocole.routes() and "bloquer" not in banc.protocole.routes()


# ------------------------------------------------------------------ démarrage refusé


async def test_politique_au_gabarit_refusee_code_2(banc, capsys):
    politique = banc.emplacements.politique
    os.chmod(politique, 0o644)
    politique.write_text((RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8"),
                         encoding="utf-8")
    assert await banc.servir() == 2
    assert "gabarit" in capsys.readouterr().err


async def test_politique_modifiable_refusee_code_2(banc, capsys):
    os.chmod(banc.emplacements.politique, 0o666)
    assert await banc.servir() == 2
    assert "modifiable" in capsys.readouterr().err


async def test_arret_brutal_pendant_la_preparation_reprend_sans_compter(banc):
    banc.coffre.ecrire("jeton-machine", JETON)
    _carte_en_main(banc, "preparation")
    banc.emplacements.sessions.mkdir(parents=True, exist_ok=True)
    (banc.emplacements.sessions / "t_ab12cd34.json").write_text(json.dumps({"oom": 1}), encoding="utf-8")
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    assert "reprendre" in banc.protocole.routes() and "bloquer" not in banc.protocole.routes()
    session = json.loads((banc.emplacements.sessions / "t_ab12cd34.json").read_text(encoding="utf-8"))
    assert session["oom"] == 1


async def test_issue_hors_contrat_en_file_ne_bloque_plus_les_reclamations(banc):
    """Relecture de P6 (reproduction de la relecture) : une question avec un NUL, refusée par le contrat AVANT l'envoi
    (vrai ``Protocole.envoyer``), restait en tête de la file : plus aucun ``reclamer``. Elle est rangée dans
    sortie/refusees, journalisée, et les réclamations reprennent."""

    class ClientJamaisAppele:
        def echanger(self, *_a, **_k):
            raise AssertionError("le contrat aurait dû refuser avant l'envoi")

        def interrompre(self):
            pass

    banc.coffre.ecrire("jeton-machine", JETON)
    banc.protocole.envoyer = Protocole(ClientJamaisAppele()).envoyer
    corps = json.loads((EXEMPLES / "question_requete.json").read_text(encoding="utf-8"))
    corps["id_envoi"] = nouvel_id_envoi()
    corps["texte"] = "Quelle base ?\x00"
    FileSortie(banc.emplacements.sortie).deposer("question", corps)
    tache = asyncio.create_task(banc.servir())
    reclame = await _jusqu_a(lambda: "reclamer" in banc.protocole.routes(), delai_s=15.0)
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    assert reclame
    assert FileSortie(banc.emplacements.sortie).en_attente() == []
    assert len(list(banc.emplacements.sortie_refusees.iterdir())) == 1
    journal = "".join(f.read_text(encoding="utf-8") for f in banc.emplacements.journal.glob("*"))
    assert "issue_hors_contrat" in journal and "NUL" in journal


def test_verdict_de_la_sonde_dans_les_journaux_du_conteneur(banc, capfd, monkeypatch):
    """Relecture de P6 : le verdict de la sonde du démarrage n'allait qu'au journal du volume ; il est aussi écrit sur
    stderr (journaux de Railway), sans secret."""
    from acp_poste import service_executant as module
    from acp_poste.journal import Journal
    from acp_poste.politique import charger

    contexte = banc.contexte()
    politique = charger(contexte.emplacements)
    verdict = {"regime": "B", "bwrap": "refuse", "proc_neuf": False, "reseau_coupe": False, "uid_separes": True,
               "raison": "Régime B : bubblewrap refusé par la plateforme."}
    monkeypatch.setattr(module, "sonder", lambda **_options: {"sonde_le": "2026-10-01T12:00:00Z", "verdict": verdict,
                                                               "releves": []})
    bloc = module.faire_sonde(contexte, politique, Journal(contexte.emplacements.journal))
    assert bloc["regime"] == "B"
    assert ("[acp] Sonde de plateforme : régime B, bubblewrap refuse, UID séparés : oui. Régime B : bubblewrap refusé "
            "par la plateforme.") in capfd.readouterr().err



async def test_purge_quotidienne_sans_toucher_la_carte_en_main(banc):
    """Relecture de P6 : la purge du disque est faite par l'exécutant lui-même (une fois par 24 h, hors carte) ;
    le worktree de la carte en main est gardé."""
    import time

    banc.coffre.ecrire("jeton-machine", JETON)
    _carte_en_main(banc, "rendue")
    espaces = banc.emplacements.espaces / "jetable"
    for nom in ("t_ancien01", "t_ab12cd34"):
        (espaces / nom).mkdir(parents=True)
        os.utime(espaces / nom, (time.time() - 30 * 86400,) * 2)
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: "reclamer" in banc.protocole.routes())
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    assert not (espaces / "t_ancien01").exists() and (espaces / "t_ab12cd34").exists()
    journal = (banc.emplacements.journal / "poste.jsonl").read_text(encoding="utf-8")
    assert "Purge du disque : 1 worktree(s)" in journal



async def test_echeance_du_jeton_claude_publiee_et_annoncee(banc, capfd):
    """Relecture de P6 : rien ne prévenait de l'expiration du jeton Claude (setup-token : un an). L'exécutant publie
    l'échéance ESTIMÉE (dépôt + 365 jours) dans son inventaire et l'annonce dans ses journaux à 30 jours."""
    import time
    from datetime import UTC, datetime, timedelta

    banc.coffre.ecrire("jeton-machine", JETON)
    depose = time.time() - 340 * 86400
    os.utime(banc.emplacements.secrets / "claude-oauth", (depose, depose))
    tache = asyncio.create_task(banc.servir())
    assert await _jusqu_a(lambda: banc.protocole.inventaires, 30)
    banc.arret.set()
    await asyncio.wait_for(tache, 10)
    attendue = (datetime.fromtimestamp(depose, UTC) + timedelta(days=365)).date().isoformat()
    assert banc.protocole.inventaires[0]["connexions"]["claude_echeance"] == attendue
    assert f"[acp] Jeton Claude de l'exécutant : expiration estimée le {attendue}" in capfd.readouterr().err
