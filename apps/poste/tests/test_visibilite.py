"""Visibilité MESURÉE d'un dépôt (cahier P7 § 11.2, § 13.5, décision P7-11) contre un FAUX serveur git HTTPS local.

Aucun appel réseau hors de la boucle locale : le faux serveur (``faux_depot_https.py``, fixture ``faux_depot`` du
``conftest.py``) imite GitHub (401 sans identifiant pour un dépôt privé, 404 « Repository not found. » hors de la
portée du jeton…), derrière l'autorité jetable du faux Hermes. Le git de la machine de test est celui qui parle : sur la CI de l'exécutant, l'image d'essais
porte git 2.47.3, la version épinglée dans ``executant/Dockerfile`` (``executant.yml``) ; les motifs reconnus sont
donc relevés sur cette version (:func:`test_messages_de_git_releves`).

Règles prouvées : accepté → ``public`` ; motif d'authentification reconnu (code 128) → ``prive`` ; tout le reste →
``inconnue`` ; ``lecture`` avec le jeton → ``ok`` | ``refusee`` | ``inconnue`` ; un serveur ne peut pas forger un
refus ; le jeton n'apparaît jamais dans l'argv, la raison ni la requête anonyme.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acp_poste import depots as module_depots
from acp_poste.depots import MOTIFS_REFUS_GIT, Depots, SortieLsRemote, Visibilite, classer_ls_remote
from acp_poste.politique import DepotDistant

ICI = Path(__file__).resolve().parent
ASKPASS = ICI.parents[2] / "executant" / "bin" / "acp-askpass"
INSTANT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _module_faux():
    spec = importlib.util.spec_from_file_location("faux_depot_https", ICI / "faux_depot_https.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAUX = _module_faux()


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *argv], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _depots(tmp_path, jeton: str | None = FAUX.JETON) -> Depots:
    return Depots(racine_depots=tmp_path / "d", racine_espaces=tmp_path / "e", racine_bundles=tmp_path / "b",
                  jeton_lecture=lambda: jeton, askpass=ASKPASS.as_posix(), droits=False)


def _depot(url: str, acces: str = "jeton_lecture") -> DepotDistant:
    return DepotDistant(alias="mesure", url=url, branche_base="main", acces=acces, preparation=(),
                        verification=("true",), verification_max_s=900, reprises_verification=2,
                        verification_sans_bac_a_sable=False, liens_symboliques=False, pilotage_supplementaire=())


def _mesurer(tmp_path, faux_depot, nom: str, *, acces: str = "jeton_lecture", jeton: str | None = FAUX.JETON,
             delai_s: float = 30.0) -> Visibilite:
    return _depots(tmp_path, jeton).visibilite(_depot(faux_depot.url(nom), acces), delai_s=delai_s,
                                               horloge=lambda: INSTANT)


# ------------------------------------------------------------------ classement (sans réseau)


def test_classement_des_sorties_de_git():
    assert classer_ls_remote(0, b"") == SortieLsRemote(code=0, refus=False)
    for ligne in (b"fatal: could not read Username for 'https://github.com': terminal prompts disabled\n",
                  b"error: unable to read askpass response from '/bin/false'\r\n"
                  b"fatal: could not read Username for 'https://github.com': terminal prompts disabled\r\n",
                  b"remote: Invalid username or token.\nfatal: Authentication failed for 'https://github.com/a/b/'\n",
                  b"remote: Repository not found.\nfatal: repository 'https://github.com/a/b.git/' not found\n"):
        assert classer_ls_remote(128, ligne).refus is True, ligne
    # Code 128 sans motif reconnu, motif hors de son code, ou motif composé par le SERVEUR (« remote: ») : jamais un refus.
    assert classer_ls_remote(128, b"fatal: unable to access 'https://github.com/a/b/': Failed to connect\n").refus \
        is False
    assert classer_ls_remote(1, b"fatal: Authentication failed for 'https://github.com/a/b/'\n").refus is False
    assert classer_ls_remote(128, b"remote: fatal: Authentication failed for 'x'\n").refus is False
    assert classer_ls_remote(128, b"remote: x\rfatal: repository 'x' not found\n").refus is False
    assert classer_ls_remote(None, b"").refus is False


def test_codex_admis_seulement_prive_et_ok():
    admis = {(v, l) for v in ("public", "prive", "inconnue") for l in ("ok", "refusee", "inconnue")
             if Visibilite(v, l, INSTANT, "").codex_admis}
    assert admis == {("prive", "ok")}
    assert Visibilite("prive", "ok", INSTANT, "").contrat() == {"visibilite": "prive", "lecture": "ok",
                                                               "verifie_le": "2026-10-02T12:00:00Z"}


# ------------------------------------------------------------------ contre le faux serveur HTTPS


def test_public(tmp_path, faux_depot, avec_autorite):
    mesure = _mesurer(tmp_path, faux_depot, "public")
    assert (mesure.visibilite, mesure.lecture) == ("public", "ok") and not mesure.codex_admis
    assert mesure.raison.startswith("accès anonyme accepté (dépôt public)")
    declare_public = _mesurer(tmp_path, faux_depot, "public", acces="public", jeton=None)
    assert (declare_public.visibilite, declare_public.lecture) == ("public", "ok")


def test_prive_lu_avec_le_jeton(tmp_path, faux_depot, avec_autorite):
    avant = len(faux_depot.vues("prive"))
    mesure = _mesurer(tmp_path, faux_depot, "prive")
    assert (mesure.visibilite, mesure.lecture) == ("prive", "ok") and mesure.codex_admis
    assert mesure.raison == ("accès anonyme refusé (authentification demandée) ; lecture avec le jeton acceptée.")
    vues = faux_depot.vues("prive")[avant:]
    # La première requête est ANONYME (aucun identifiant envoyé), puis la lecture porte « x-access-token » et le jeton.
    assert vues[0]["utilisateur"] is None
    assert any(v["utilisateur"] == "x-access-token" and v["jeton_attendu"] for v in vues[1:])


def test_prive_jeton_refuse(tmp_path, faux_depot, avec_autorite):
    mesure = _mesurer(tmp_path, faux_depot, "prive", jeton="github_pat_" + "z" * 40)
    assert (mesure.visibilite, mesure.lecture) == ("prive", "refusee") and not mesure.codex_admis


def test_prive_hors_de_portee_du_jeton(tmp_path, faux_depot, avec_autorite):
    mesure = _mesurer(tmp_path, faux_depot, "hors-portee")
    assert (mesure.visibilite, mesure.lecture) == ("prive", "refusee") and not mesure.codex_admis


def test_introuvable_sans_identifiant(tmp_path, faux_depot, avec_autorite):
    mesure = _mesurer(tmp_path, faux_depot, "introuvable")
    assert (mesure.visibilite, mesure.lecture) == ("prive", "refusee") and not mesure.codex_admis


def test_jeton_absent(tmp_path, faux_depot, avec_autorite):
    mesure = _mesurer(tmp_path, faux_depot, "prive", jeton=None)
    assert (mesure.visibilite, mesure.lecture) == ("prive", "inconnue") and not mesure.codex_admis
    assert "jeton de lecture absent" in mesure.raison


def test_declare_public_mais_prive(tmp_path, faux_depot, avec_autorite):
    """La politique dit « public », GitHub refuse l'accès anonyme : la mesure le dit (l'exécutant refuse le dépôt)."""
    mesure = _mesurer(tmp_path, faux_depot, "prive", acces="public")
    assert (mesure.visibilite, mesure.lecture) == ("prive", "refusee")


@pytest.mark.parametrize("nom", ["panne", "interdit", "faux-refus"])
def test_reponses_non_reconnues_inconnues(tmp_path, faux_depot, avec_autorite, nom):
    mesure = _mesurer(tmp_path, faux_depot, nom)
    assert (mesure.visibilite, mesure.lecture) == ("inconnue", "inconnue") and not mesure.codex_admis
    assert "réponse de git non reconnue (code 128)" in mesure.raison


def test_delai_depasse(tmp_path, faux_depot, avec_autorite):
    debut = time.monotonic()
    mesure = _mesurer(tmp_path, faux_depot, "lent", delai_s=1.0)
    assert time.monotonic() - debut < 15
    assert (mesure.visibilite, mesure.lecture) == ("inconnue", "inconnue")
    assert "délai de 1 s dépassé" in mesure.raison


def test_serveur_injoignable(tmp_path, avec_autorite):
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        port = libre.getsockname()[1]
    mesure = _depots(tmp_path).visibilite(_depot(f"https://127.0.0.1:{port}/proprietaire/x.git"), delai_s=20.0)
    assert (mesure.visibilite, mesure.lecture) == ("inconnue", "inconnue")


def test_certificat_inconnu(tmp_path, faux_depot):
    """Sans l'autorité de test, le certificat du faux serveur est refusé : jamais « public » ni « prive »."""
    mesure = _mesurer(tmp_path, faux_depot, "public")
    assert (mesure.visibilite, mesure.lecture) == ("inconnue", "inconnue")


def test_git_absent(tmp_path, faux_depot, avec_autorite, monkeypatch):
    monkeypatch.setattr(module_depots, "GIT", str(tmp_path / "git-absent"))
    mesure = _mesurer(tmp_path, faux_depot, "public")
    assert (mesure.visibilite, mesure.lecture) == ("inconnue", "inconnue")
    assert "git impossible à lancer" in mesure.raison


def test_configuration_du_dossier_courant_jamais_lue(tmp_path, faux_depot, avec_autorite, monkeypatch):
    """Lancé depuis un dépôt dont la configuration détourne l'URL (« insteadOf » vers le dépôt public), la mesure du
    dépôt privé reste « prive » : git ne lit que la configuration imposée, jamais celle du dossier courant."""
    piege = tmp_path / "piege"
    piege.mkdir()
    _git(piege, "init", "-q")
    _git(piege, "config", f"url.{faux_depot.url('public')}.insteadOf", faux_depot.url("prive"))
    monkeypatch.chdir(piege)
    assert _git(piege, "ls-remote", "--get-url", faux_depot.url("prive")) == faux_depot.url("public")
    mesure = _mesurer(tmp_path, faux_depot, "prive")
    assert (mesure.visibilite, mesure.lecture) == ("prive", "ok")


def test_jeton_jamais_dans_l_argv_ni_la_raison(tmp_path, faux_depot, avec_autorite, monkeypatch):
    vus = []
    reel = subprocess.Popen

    def espion(argv, **options):
        vus.append((list(argv), dict(options.get("env") or {})))
        return reel(argv, **options)

    monkeypatch.setattr(subprocess, "Popen", espion)
    for nom in ("prive", "hors-portee", "panne"):
        mesure = _mesurer(tmp_path, faux_depot, nom)
        assert FAUX.JETON not in mesure.raison and faux_depot.url(nom) not in mesure.raison
    assert len(vus) == 6
    for argv, env in vus:
        assert not any(FAUX.JETON in a for a in argv)
        assert argv[-4:-1] == ["ls-remote", "--heads", "--"] and argv[-1].startswith("https://127.0.0.1:")
        assert "credential.helper=" in argv and env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_CONFIG_GLOBAL"] == os.devnull and env["HOME"] == "/nonexistent"
    anonymes = [env for argv, env in vus[0::2]]
    avec_jeton = [env for argv, env in vus[1::2]]
    assert all("ACP_JETON_LECTURE" not in env and env["GIT_ASKPASS"] == "/bin/false" for env in anonymes)
    assert all(env["ACP_JETON_LECTURE"] == FAUX.JETON and env["GIT_ASKPASS"].endswith("acp-askpass")
               for env in avec_jeton)


def test_messages_de_git_releves(tmp_path, faux_depot, avec_autorite, capsys):
    """Motifs exacts relevés sur le git de la machine (2.47.3 dans l'image d'essais de l'exécutant) : chaque refus du
    faux serveur produit le message de git attendu, et un seul motif le reconnaît."""
    depots = _depots(tmp_path)
    version = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip()
    cas = {
        ("prive", None): 0,          # 401 sans identifiant → invite refusée
        ("prive", "mauvais"): 1,     # 401 après des identifiants → authentification refusée
        ("hors-portee", "bon"): 2,   # 404 → dépôt introuvable
        ("introuvable", None): 2,
    }
    for (nom, jeton), attendu in cas.items():
        env = {}
        if jeton is not None:
            env = {"GIT_ASKPASS": ASKPASS.as_posix(),
                   "ACP_JETON_LECTURE": FAUX.JETON if jeton == "bon" else "github_pat_" + "m" * 40}
        argv = ["git", *module_depots.options_git(depots.protocoles), "ls-remote", "--heads", "--",
                faux_depot.url(nom)]
        resultat = subprocess.run(argv, cwd=tmp_path, env=depots._env(env), capture_output=True, timeout=30)
        texte = resultat.stderr.decode("utf-8", "replace").replace("\r\n", "\n")
        reconnus = [i for i, motif in enumerate(MOTIFS_REFUS_GIT) if motif.search(texte)]
        with capsys.disabled():
            print(f"\n[{version}] {nom} ({jeton or 'anonyme'}) → code {resultat.returncode} : "
                  + " | ".join(l for l in texte.splitlines() if l.startswith("fatal:")))
        assert resultat.returncode == 128 and reconnus == [attendu], texte
