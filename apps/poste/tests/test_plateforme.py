"""Couche plateforme (cahier P6 § 7.1, § 7.4, § 7.5 ; décision D76).

Les tests marqués ``RACINE_LINUX`` changent d'UID (``setpriv``) ou de propriétaire (``chown``) : ils exigent Linux
et root (conteneur de test de la partie 2, image de l'exécutant ensuite) et sont **ignorés, avec leur raison**,
ailleurs (CI Linux sans root, Windows).
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import pytest

from acp_poste import plateforme
from acp_poste.coffre import CoffreErreur
from acp_poste.contexte import Contexte
from acp_poste.plateforme.linux import (
    IDENTITES,
    ArretUid,
    CoffreFichiers,
    EmplacementsLinux,
    Identite,
    PlateformeLinux,
    arreter_agent,
    environnement_agent,
    prefixe_setpriv,
    processus_de_l_uid,
)
from acp_poste.plateforme.windows import PlateformeWindows

POSIX = pytest.mark.skipif(os.name != "posix", reason="droits POSIX (0600, propriétaire) : Linux seulement")
RACINE_LINUX = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="exige Linux et root (changement d'UID par setpriv, chown) : conteneur de test de P6 seulement")
UID_TEST = 10099
IDENTITE_TEST = Identite("acp-test", UID_TEST, UID_TEST, PurePosixPath("/nonexistent"))


# ------------------------------------------------------------------ choix de la plateforme


def test_choix_par_sys_platform_seulement(monkeypatch):
    assert plateforme.nom_courant("win32") == "windows"
    assert plateforme.nom_courant("linux") == "linux"
    with pytest.raises(plateforme.PlateformeIndisponible, match="non pris en charge"):
        plateforme.nom_courant("darwin")
    # Aucune variable d'environnement ne change le choix.
    monkeypatch.setenv("ACP_PLATEFORME", "linux")
    monkeypatch.setenv("ACP_POSTE_PLATEFORME", "windows")
    attendu = "windows" if sys.platform == "win32" else "linux"
    assert plateforme.nom_courant() == attendu


def test_annonce_contraire_refusee():
    assert plateforme.verifier_annonce("linux", plateforme_systeme="linux") == "linux"
    assert plateforme.verifier_annonce(None, plateforme_systeme="win32") == "windows"
    with pytest.raises(plateforme.PlateformeIndisponible, match="différente de la plateforme réelle"):
        plateforme.verifier_annonce("linux", plateforme_systeme="win32")


def test_courante_rend_la_bonne_classe():
    assert isinstance(plateforme.courante("win32"), PlateformeWindows)
    assert isinstance(plateforme.courante("linux"), PlateformeLinux)


# ------------------------------------------------------------------ Linux : hôte, emplacements, identités


def test_hote_railway_sans_jamais_publier_la_valeur():
    secret = "svc-valeur-jamais-publiee"
    infos = PlateformeLinux({"RAILWAY_SERVICE_ID": secret}).infos()
    assert infos["plateforme"] == "linux" and infos["hote"] == "railway" and infos["windows"] is None
    assert secret not in repr(infos)
    assert PlateformeLinux({}).infos()["hote"] == "pc"


def test_emplacements_linux_du_cahier():
    e = EmplacementsLinux()
    assert e.politique == Path("/etc/acp/executant.toml")
    assert e.secrets == Path("/donnees/acp/secrets") and e.sortie == Path("/donnees/acp/sortie")
    assert e.codex_home == Path("/donnees/codex") and e.claude_config == Path("/donnees/claude")
    assert e.depots == Path("/donnees/depots") and e.espaces == Path("/donnees/espaces")
    assert e.carte == Path("/donnees/acp/etat/carte.json")
    assert e.codex_par_defaut == Path("/opt/acp/outils/codex/codex")


def test_emplacements_de_test_sous_la_racine(tmp_path):
    e = EmplacementsLinux.de_test(tmp_path)
    assert e.sous(tmp_path)
    assert not EmplacementsLinux().sous(tmp_path)


def test_identites_et_prefixe_setpriv():
    assert {i.uid for i in IDENTITES.values()} == {10001, 10002, 10003}
    assert all(i.groupes == (10100,) for i in IDENTITES.values())
    argv = prefixe_setpriv(IDENTITES["acp-verif"])
    assert argv == ["/usr/bin/setpriv", "--reuid=10003", "--regid=10003", "--groups=10100", "--inh-caps=-all",
                    "--bounding-set=-all", "--no-new-privs", "--"]
    # Jamais --reset-env : il remplacerait l'environnement calculé (CODEX_HOME, jeton de Claude).
    assert "--reset-env" not in argv and "--init-groups" not in argv


def test_environnement_agent_calcule_sans_heritage(monkeypatch):
    monkeypatch.setenv("ACP_SECRET_DU_SUPERVISEUR", "ne-doit-pas-passer")
    env = environnement_agent(IDENTITES["acp-codex"], tmpdir=Path("/tmp/acp/t_1/codex"), CODEX_HOME="/donnees/codex")
    assert env == {"HOME": "/home/acp-codex", "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                   "LC_ALL": "C.UTF-8", "TMPDIR": "/tmp/acp/t_1/codex", "CODEX_HOME": "/donnees/codex"}


def test_contexte_lanceurs_linux(poste):
    from acp_poste.politique import charger

    poste.ecrire_politique()
    politique = charger(poste.emplacements)
    contexte = Contexte(emplacements=poste.emplacements, coffre=poste.coffre, plateforme="linux",
                        identites={"codex": IDENTITES["acp-codex"], "claude": IDENTITES["acp-claude"]})
    lanceurs = contexte.lanceurs_pour(politique)
    # Les exécutables de la politique de test existent (l'interpréteur du test) : setpriv vers l'UID de l'outil.
    assert lanceurs["codex"][:2] == ["/usr/bin/setpriv", "--reuid=10001"]
    assert lanceurs["codex"][-1] == str(politique.codex.executable)
    assert lanceurs["claude"][1] == "--reuid=10002"
    # Une injection de test l'emporte ; une identité absente (Windows) ne produit aucun lanceur.
    contexte.lanceurs = {"codex": ["faux"]}
    assert contexte.lanceurs_pour(politique)["codex"] == ["faux"]
    assert Contexte(emplacements=poste.emplacements, coffre=poste.coffre).lanceurs_pour(politique) == {}
    assert contexte.environnement_pour("claude")["HOME"] == "/home/acp-claude"


# ------------------------------------------------------------------ coffre en fichiers 0600


@POSIX
def test_coffre_fichiers_ecrit_en_0600_et_relit(tmp_path):
    coffre = CoffreFichiers(tmp_path / "secrets")
    assert coffre.lire("jeton-machine") is None and not coffre.present("jeton-claude")
    coffre.ecrire("jeton-claude", "sk-ant-oat01-factice\n")
    fichier = tmp_path / "secrets" / "claude-oauth"
    assert (fichier.stat().st_mode & 0o777) == 0o600
    assert ((tmp_path / "secrets").stat().st_mode & 0o777) == 0o700
    assert coffre.lire("jeton-claude") == "sk-ant-oat01-factice"
    assert coffre.effacer("jeton-claude") and coffre.lire("jeton-claude") is None
    with pytest.raises(CoffreErreur, match="inconnu"):
        coffre.lire("jeton-railway")


@POSIX
def test_coffre_fichiers_refuse_droits_larges_et_lien(tmp_path):
    coffre = CoffreFichiers(tmp_path / "secrets")
    coffre.ecrire("jeton-machine", "acpm_" + "a" * 43)
    fichier = tmp_path / "secrets" / "jeton-machine"
    os.chmod(fichier, 0o640)
    with pytest.raises(CoffreErreur, match="0600"):
        coffre.lire("jeton-machine")
    fichier.unlink()
    cible = tmp_path / "ailleurs"
    cible.write_text("acpm_" + "b" * 43, encoding="utf-8")
    os.chmod(cible, 0o600)
    fichier.symlink_to(cible)
    with pytest.raises(CoffreErreur, match="lien symbolique"):
        coffre.lire("jeton-machine")
    os.chmod(tmp_path / "secrets", 0o755)
    with pytest.raises(CoffreErreur, match="0700"):
        coffre.ecrire("jeton-github", "github_pat_factice")


@RACINE_LINUX
def test_coffre_fichiers_refuse_un_autre_proprietaire(tmp_path):
    coffre = CoffreFichiers(tmp_path / "secrets")
    coffre.ecrire("jeton-github", "github_pat_factice")
    os.chown(tmp_path / "secrets" / "github-lecture", 10001, 10001)
    with pytest.raises(CoffreErreur, match="autre propriétaire"):
        coffre.lire("jeton-github")


# ------------------------------------------------------------------ arrêt par UID (§ 7.5)


def test_balayage_refuse_un_uid_qui_n_est_pas_dedie():
    with pytest.raises(ValueError, match="UID dédié"):
        ArretUid(0).executer()
    with pytest.raises(ValueError, match="UID dédié"):
        ArretUid(1000).executer()


def test_arret_reste_refuse_si_survivant():
    tues = []
    arret = ArretUid(10003, lister=lambda uid: [4242], tuer=lambda pid, sig: tues.append((pid, sig)), pause_s=0)
    assert arret.executer() is False
    assert len(tues) == 5 and all(sig == 9 for _pid, sig in tues)


def test_un_zombie_ne_compte_pas():
    from acp_poste.plateforme.linux import _uids_du_statut

    vivant = "Name:\tpython\nState:\tS (sleeping)\nUid:\t10003\t10003\t10003\t10003\n"
    assert _uids_du_statut(vivant) == {10003}
    assert _uids_du_statut(vivant.replace("S (sleeping)", "Z (zombie)")) == set()


def test_balayage_conclut_quand_l_uid_est_vide():
    vivants = {501, 502}
    arret = ArretUid(10003, lister=lambda uid: sorted(vivants), tuer=lambda pid, sig: vivants.discard(pid), pause_s=0)
    assert arret.executer() is True and sorted(arret.tues) == [501, 502]


@RACINE_LINUX
def test_processus_de_l_uid_lit_proc():
    processus = subprocess.Popen([*prefixe_setpriv(IDENTITE_TEST), sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        deadline = time.monotonic() + 5
        while processus.pid not in processus_de_l_uid(UID_TEST) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert processus.pid in processus_de_l_uid(UID_TEST)
        assert os.getpid() not in processus_de_l_uid(UID_TEST)
    finally:
        processus.kill()
        processus.wait()


ECHAPPE = r"""
import os, sys, time
pid = os.fork()
if pid == 0:
    os.setsid()
    if os.fork() == 0:
        open(sys.argv[1], "w").write(str(os.getpid()))
        time.sleep(120)
    os._exit(0)
time.sleep(120)
"""


@RACINE_LINUX
async def test_arret_par_uid_rattrape_setsid(tmp_path):
    from acp_poste.local_runner import spawn_fenced_process

    import tempfile

    # tmp_path vit sous /tmp/pytest-of-root (0700) : l'UID de test n'y entre pas.
    dossier = Path(tempfile.mkdtemp(prefix="acp-echappe-", dir="/tmp"))
    os.chmod(dossier, 0o777)
    temoin = dossier / "echappe.pid"
    processus = await spawn_fenced_process(
        [*prefixe_setpriv(IDENTITE_TEST), sys.executable, "-c", ECHAPPE, str(temoin)], cwd=str(dossier),
        env=environnement_agent(IDENTITE_TEST), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while not temoin.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    echappe = int(temoin.read_text())
    # Le petit-fils a quitté le groupe : killpg seul ne l'atteint pas.
    assert os.getpgid(echappe) != processus.pid
    assert await arreter_agent(processus.process, UID_TEST, grace_s=0.5)
    assert processus_de_l_uid(UID_TEST) == []
    # Tué : disparu, ou zombie en attente d'être recueilli (PID 1 du conteneur de test ; tini dans l'image).
    statut = Path(f"/proc/{echappe}/status")
    assert not statut.exists() or "\nState:\tZ" in statut.read_text(encoding="utf-8")


@RACINE_LINUX
def test_dossiers_des_sondes_a_l_uid_de_l_outil(tmp_path, poste):
    contexte = Contexte(emplacements=EmplacementsLinux.de_test(tmp_path), coffre=poste.coffre, plateforme="linux",
                        identites={"codex": IDENTITES["acp-codex"]})
    fabrique = contexte.dossiers_pour("codex")
    assert contexte.dossiers_pour("claude") is None
    with fabrique(prefix="acp-sonde-") as dossier:
        etat = os.stat(dossier)
        assert (etat.st_uid, etat.st_mode & 0o777) == (10001, 0o700)
    assert not Path(dossier).exists()
