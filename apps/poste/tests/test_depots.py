"""Dépôts de l'exécutant (cahier P6 § 6.2, § 6.6, § 6.7, § 12.2) contre un dépôt « distant » local.

Le protocole ``file`` n'est admis que par injection de test (``protocoles``) : en production, seul ``https`` l'est
(éprouvé). Les droits (propriétaires root, ``acp-travail``) ne sont posés qu'en root : conteneur de test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from acp_poste.depots import Depots, ErreurDepot, analyser_raw, mode_gitlink, mode_lien, options_git
from acp_poste.politique import DepotDistant

POSIX = pytest.mark.skipif(os.name != "posix", reason="liens symboliques, modes et fsmonitor POSIX : Linux seulement")
RACINE_LINUX = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="exige Linux et root (chown root:acp-travail) : conteneur de test de P6 seulement")
ICI = Path(__file__).resolve().parent
ASKPASS = ICI.parents[2] / "executant" / "bin" / "acp-askpass"


def _git(cwd: Path, *argv: str) -> str:
    resultat = subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                               "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *argv], cwd=cwd,
                              capture_output=True, text=True, check=True)
    return resultat.stdout.strip()


@pytest.fixture
def distant(tmp_path) -> Path:
    depot = tmp_path / "distant"
    depot.mkdir()
    _git(depot, "init", "-q")
    (depot / "README.md").write_text("Dépôt jetable\n", encoding="utf-8")
    (depot / "src").mkdir()
    (depot / "src" / "app.py").write_text("print('bonjour')\n", encoding="utf-8")
    (depot / "CLAUDE.md").write_text("Consignes du dépôt\n", encoding="utf-8")
    _git(depot, "add", "-A")
    _git(depot, "commit", "-q", "-m", "initial")
    return depot


@pytest.fixture
def depots(tmp_path) -> Depots:
    return Depots(racine_depots=tmp_path / "donnees" / "depots", racine_espaces=tmp_path / "donnees" / "espaces",
                  racine_bundles=tmp_path / "donnees" / "acp" / "bundles", protocoles=("https", "file"),
                  droits=False)


def _depot(distant: Path, **changements) -> DepotDistant:
    valeurs = dict(alias="jetable", url=str(distant), branche_base="main", acces="public", preparation=(),
                   verification=("true",), verification_max_s=900, reprises_verification=2,
                   verification_sans_bac_a_sable=False, liens_symboliques=False, pilotage_supplementaire=())
    valeurs.update(changements)
    return DepotDistant(**valeurs)


# ------------------------------------------------------------------ options et analyse


def test_options_imposees():
    options = options_git()
    for attendu in ("core.hooksPath=/dev/null", "core.fsmonitor=false", "protocol.allow=never",
                    "protocol.https.allow=always", "submodule.recurse=false", "core.symlinks=false",
                    "credential.helper="):
        assert attendu in options
    assert "protocol.file.allow=always" not in options


def test_analyser_raw_renommages_liens_et_gitlinks():
    brut = (b":100644 100644 aaa bbb M\0src/app.py\0"
            b":100644 100644 aaa bbb R092\0ancien.md\0.claude/nouveau.md\0"
            b":000000 120000 000 ccc A\0lien\0"
            b":000000 160000 000 ddd A\0sous-module\0"
            b":100644 000000 aaa 000 D\0AGENTS.md\0")
    changements = analyser_raw(brut)
    assert [c.statut for c in changements] == ["M", "R", "A", "A", "D"]
    assert changements[1].chemins == ("ancien.md", ".claude/nouveau.md")
    assert mode_lien(changements[2]) and mode_gitlink(changements[3]) and not mode_lien(changements[4])


# ------------------------------------------------------------------ récupération (§ 6.2)


def test_clone_nu_puis_fetch(distant, depots):
    depot = _depot(distant)
    nu = depots.recuperer(depot)
    assert (nu / "HEAD").is_file() and nu == depots.nu("jetable")
    premiere = depots.sha(nu, "refs/remotes/origin/main")
    assert premiere == _git(distant, "rev-parse", "HEAD")
    (distant / "README.md").write_text("Modifié\n", encoding="utf-8")
    _git(distant, "commit", "-qam", "seconde")
    depots.recuperer(depot)
    assert depots.sha(nu, "refs/remotes/origin/main") == _git(distant, "rev-parse", "HEAD") != premiere


def test_clone_d_une_autre_url_jamais_recupere(distant, depots, tmp_path):
    """Étape P7 (relecture de la partie E) : la visibilité est mesurée sur l'URL de la politique ; un alias réaffecté
    à une autre URL ne récupère jamais le clone nu de l'ancienne (échec fermé, message sans URL)."""
    depots.recuperer(_depot(distant))
    autre = tmp_path / "autre"
    autre.mkdir()
    _git(autre, "init", "-q")
    (autre / "x.txt").write_text("x\n", encoding="utf-8")
    _git(autre, "add", "-A")
    _git(autre, "commit", "-q", "-m", "autre")
    with pytest.raises(ErreurDepot, match="vient d'une autre URL que la politique") as exc:
        depots.recuperer(_depot(autre))
    assert str(autre) not in str(exc.value) and str(distant) not in str(exc.value)
    depots.recuperer(_depot(distant))  # la même URL reste récupérée


def test_seul_https_en_production(distant, tmp_path):
    production = Depots(racine_depots=tmp_path / "d", racine_espaces=tmp_path / "e", racine_bundles=tmp_path / "b",
                        droits=False)
    with pytest.raises(ErreurDepot, match="clone en échec"):
        production.recuperer(_depot(distant))


def test_jeton_de_lecture_par_askpass_seulement(distant, depots, monkeypatch):
    depot = _depot(distant, acces="jeton_lecture")
    with pytest.raises(ErreurDepot, match="connexion github"):
        depots.recuperer(depot)
    vus = []
    reel = subprocess.run

    def espion(argv, **options):
        vus.append((list(argv), dict(options.get("env") or {})))
        return reel(argv, **options)

    depots.jeton_lecture = lambda: "github_pat_" + "x" * 30
    monkeypatch.setattr(subprocess, "run", espion)
    depots.recuperer(depot)
    for argv, env in vus:
        assert not any("github_pat_" in a for a in argv)
        if "clone" in argv or "fetch" in argv:
            assert env["ACP_JETON_LECTURE"].startswith("github_pat_") and env["GIT_ASKPASS"].endswith("acp-askpass")
        assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_GLOBAL"] == os.devnull


@POSIX
def test_askpass_rend_le_jeton_et_rien_d_autre():
    env = {"ACP_JETON_LECTURE": "github_pat_factice", "PATH": "/usr/bin:/bin"}
    def demander(invite: str, **sup):
        return subprocess.run(["sh", str(ASKPASS), invite], capture_output=True, text=True, env={**env, **sup})
    assert demander("Username for 'https://github.com': ").stdout == "x-access-token\n"
    assert demander("Password for 'https://x-access-token@github.com': ").stdout == "github_pat_factice\n"
    assert demander("Autre chose").returncode == 1
    assert demander("Password: ", ACP_JETON_LECTURE="").returncode == 1


# ------------------------------------------------------------------ worktree, commit, diff (§ 6.6)


def test_worktree_commit_et_reprise(distant, depots):
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    assert (chemin / "src" / "app.py").is_file()
    base = depots.sha(depots.nu("jetable"), "refs/remotes/origin/main")
    assert depots.committer("jetable", "t_abcd", "implementation(t_abcd): rien") is None
    (chemin / "src" / "app.py").write_text("print('bonjour')\nprint('ajout')\n", encoding="utf-8")
    (chemin / "src" / "nouveau.py").write_text("X = 1\n", encoding="utf-8")
    tete = depots.committer("jetable", "t_abcd", "implementation(t_abcd): ajout")
    assert tete and tete == depots.tete("jetable", "t_abcd") and depots.branche_existe("jetable", "hermes/t_abcd")
    message = _git(chemin, "log", "-1", "--format=%an <%ae>%n%B")
    assert message.startswith("ACP exécutant <executant@acp.invalid>") and "Co-Authored-By" not in message
    assert depots.diffstat("jetable", "t_abcd", base, tete) == {"fichiers": 2, "ajouts": 2, "retraits": 0}
    # Reprise : le worktree existant est gardé tel quel.
    (chemin / "brouillon.txt").write_text("en cours\n", encoding="utf-8")
    assert depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main") == chemin
    assert (chemin / "brouillon.txt").exists()
    # Carte suivante partant de la branche de la carte parente.
    enfant = depots.worktree(depot, "t_ef01", "hermes/t_ef01", "hermes/t_abcd")
    assert (enfant / "src" / "nouveau.py").is_file()
    with pytest.raises(ErreurDepot, match="absente"):
        depots.worktree(depot, "t_ef02", "hermes/t_ef02", "hermes/t_inconnue")
    with pytest.raises(ErreurDepot, match="refusée"):
        depots.worktree(depot, "t_ef03", "main", "origin/main")


def test_changements_et_lignes_ajoutees(distant, depots):
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    base = depots.sha(depots.nu("jetable"), "refs/remotes/origin/main")
    (chemin / ".claude").mkdir()
    shutil.move(str(chemin / "CLAUDE.md"), str(chemin / ".claude" / "CLAUDE.md"))
    (chemin / "README.md").unlink()
    (chemin / "src" / "app.py").write_text("print('bonjour')\nCLE = 'valeur ajoutée'\n", encoding="utf-8")
    depots.indexer("jetable", "t_abcd")
    changements = {c.chemins: c.statut for c in depots.changements("jetable", "t_abcd", base)}
    assert changements[("CLAUDE.md", ".claude/CLAUDE.md")] == "R"
    assert changements[("README.md",)] == "D" and changements[("src/app.py",)] == "M"
    lignes = depots.lignes_ajoutees("jetable", "t_abcd", base)
    assert "CLE = 'valeur ajoutée'" in lignes and "print('bonjour')" not in lignes


@POSIX
def test_lien_ajoute_et_lien_du_depot_neutralise(distant, depots):
    os.symlink("README.md", distant / "lien-du-depot")
    _git(distant, "add", "-A")
    _git(distant, "commit", "-qm", "lien")
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    # core.symlinks=false : le lien du dépôt est un fichier texte, aucun outil ne peut le suivre.
    assert not (chemin / "lien-du-depot").is_symlink()
    assert (chemin / "lien-du-depot").read_text(encoding="utf-8") == "README.md"
    base = depots.sha(depots.nu("jetable"), "refs/remotes/origin/main")
    os.symlink("/etc/passwd", chemin / "lien-ajoute")
    depots.indexer("jetable", "t_abcd")
    ajoute = [c for c in depots.changements("jetable", "t_abcd", base) if c.chemins == ("lien-ajoute",)]
    assert ajoute and mode_lien(ajoute[0])


@POSIX
def test_fichier_git_reecrit_par_un_agent_sans_effet(distant, depots, tmp_path):
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    temoin = tmp_path / "temoin-fsmonitor"
    script = tmp_path / "mechant.sh"
    script.write_text(f"#!/bin/sh\ntouch {temoin}\n", encoding="utf-8")
    script.chmod(0o755)
    # L'agent remplace le fichier .git par un dépôt à lui, avec un fsmonitor et un crochet.
    (chemin / ".git").unlink()
    _git(chemin, "init", "-q")
    _git(chemin, "config", "core.fsmonitor", str(script))
    (chemin / ".git" / "hooks" / "pre-commit").write_text(f"#!/bin/sh\ntouch {temoin}\n", encoding="utf-8")
    (chemin / ".git" / "hooks" / "pre-commit").chmod(0o755)
    (chemin / "src" / "app.py").write_text("print('modifié')\n", encoding="utf-8")
    tete = depots.committer("jetable", "t_abcd", "implementation(t_abcd): essai")
    assert tete is not None and not temoin.exists()
    # Le commit est bien dans le clone nu, sur hermes/t_abcd, et ne contient rien du faux .git.
    assert depots.sha(depots.nu("jetable"), "refs/heads/hermes/t_abcd") == tete
    fichiers = subprocess.run(["git", f"--git-dir={depots.nu('jetable')}", "ls-tree", "-r", "--name-only", tete],
                              capture_output=True, text=True, check=True).stdout.split()
    assert not any(f.startswith(".git/") for f in fichiers)


def test_crochets_du_clone_jamais_lances(distant, depots, tmp_path):
    depot = _depot(distant)
    nu = depots.recuperer(depot)
    temoin = tmp_path / "temoin-crochet"
    crochet = nu / "hooks" / "pre-commit"
    crochet.write_text(f"#!/bin/sh\ntouch '{temoin.as_posix()}'\n", encoding="utf-8")
    crochet.chmod(0o755)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    (chemin / "nouveau.txt").write_text("x\n", encoding="utf-8")
    assert depots.committer("jetable", "t_abcd", "implementation(t_abcd): crochet") is not None
    assert not temoin.exists()


def test_quarantaine(distant, depots):
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    (chemin / "x.txt").write_text("x\n", encoding="utf-8")
    depots.committer("jetable", "t_abcd", "implementation(t_abcd): x")
    assert depots.quarantaine("jetable", "t_abcd", "hermes/t_abcd") == "quarantaine/t_abcd"
    assert not depots.branche_existe("jetable", "hermes/t_abcd")
    assert depots.branche_existe("jetable", "quarantaine/t_abcd")


def test_worktree_en_quarantaine_jamais_repris(distant, depots):
    """Étape P7 (K25) : le worktree d'une carte mise en quarantaine est posé sur ``quarantaine/<carte>`` ; à la carte
    suivante, il n'est PAS repris : retiré, puis recréé depuis le départ sur une branche neuve, sans le commit fautif."""
    depot = _depot(distant)
    depots.recuperer(depot)
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    (chemin / "fuite.txt").write_text("secret\n", encoding="utf-8")
    fautif = depots.committer("jetable", "t_abcd", "implementation(t_abcd): fuite")
    depots.quarantaine("jetable", "t_abcd", "hermes/t_abcd")
    assert depots.branche_du_worktree("jetable", "t_abcd") == "quarantaine/t_abcd"
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    assert depots.branche_du_worktree("jetable", "t_abcd") == "hermes/t_abcd"
    assert not (chemin / "fuite.txt").exists()
    nu = depots.nu("jetable")
    assert depots.tete("jetable", "t_abcd") == depots.sha(nu, "refs/remotes/origin/main")
    assert depots.sha(nu, "refs/heads/quarantaine/t_abcd") == fautif
    # Un worktree posé sur SA branche est gardé tel quel (reprise ordinaire).
    (chemin / "en_cours.txt").write_text("x\n", encoding="utf-8")
    assert depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main") == chemin
    assert (chemin / "en_cours.txt").exists()


# ------------------------------------------------------------------ intégration et bundle (§ 6.7, § 12.2)


def _carte(depots, depot, carte, fichier, contenu, depart="origin/main"):
    chemin = depots.worktree(depot, carte, f"hermes/{carte}", depart)
    (chemin / fichier).write_text(contenu, encoding="utf-8")
    return depots.committer(depot.alias, carte, f"implementation({carte}): {fichier}")


def test_integration_fusionne_puis_bundle(distant, depots, tmp_path):
    depot = _depot(distant)
    depots.recuperer(depot)
    _carte(depots, depot, "t_aaaa", "a.txt", "a\n")
    _carte(depots, depot, "t_bbbb", "b.txt", "b\n")
    depots.worktree(depot, "projet-demo", "hermes/projet-demo", "origin/main")
    assert depots.fusionner("jetable", "projet-demo", ["hermes/t_aaaa", "hermes/t_bbbb", "hermes/t_aaaa"]) == []
    projet = depots.espace("jetable", "projet-demo")
    assert (projet / "a.txt").is_file() and (projet / "b.txt").is_file()
    fichier, empreinte, tete = depots.bundle("jetable", "hermes/projet-demo")
    assert fichier.name == f"jetable-projet-demo-{tete[:12]}.bundle" and len(empreinte) == 64
    if os.name == "posix":
        assert (fichier.stat().st_mode & 0o777) == 0o600
    clone = tmp_path / "pc"
    # Le PC du propriétaire n'a pas le /etc/gitconfig de l'exécutant (protocol.allow=never, https seul) : dans l'image
    # d'essais, ce git-là le lirait et refuserait le bundle local ; le transport « file » est donc rouvert ici seulement.
    subprocess.run(["git", "-c", "protocol.file.allow=always", "clone", "-q", str(fichier), str(clone), "-b",
                    "hermes/projet-demo"], check=True, capture_output=True)
    assert _git(clone, "rev-parse", "HEAD") == tete
    with pytest.raises(ErreurDepot, match="refusée"):
        depots.bundle("jetable", "main")


def test_integration_conflit_annulee(distant, depots):
    depot = _depot(distant)
    depots.recuperer(depot)
    _carte(depots, depot, "t_aaaa", "README.md", "version a\n")
    _carte(depots, depot, "t_bbbb", "README.md", "version b\n")
    depots.worktree(depot, "projet-demo", "hermes/projet-demo", "origin/main")
    assert depots.fusionner("jetable", "projet-demo", ["hermes/t_aaaa", "hermes/t_bbbb"]) == ["README.md"]
    projet = depots.espace("jetable", "projet-demo")
    assert (projet / "README.md").read_text(encoding="utf-8") == "version a\n"
    assert depots.sha(depots.gitdir_du_worktree("jetable", "projet-demo"), "MERGE_HEAD") is None


# ------------------------------------------------------------------ droits (root)


@RACINE_LINUX
def test_droits_du_tour_et_du_clone(distant):
    import tempfile

    # tmp_path vit sous /tmp/pytest-of-root (0700) : les UID d'agents n'y entrent pas ; racine traversable ici.
    racine = Path(tempfile.mkdtemp(prefix="acp-droits-", dir="/tmp"))
    os.chmod(racine, 0o755)
    depots = Depots(racine_depots=racine / "donnees" / "depots", racine_espaces=racine / "donnees" / "espaces",
                    racine_bundles=racine / "donnees" / "acp" / "bundles", protocoles=("https", "file"),
                    droits=True)
    depot = _depot(distant)
    nu = depots.recuperer(depot)
    os.chmod(racine / "donnees", 0o755)
    assert (os.stat(nu).st_uid, os.stat(nu).st_mode & 0o777) == (0, 0o755)
    assert all(not (os.lstat(os.path.join(r, n)).st_mode & 0o022) for r, ds, fs in os.walk(nu) for n in ds + fs
               if not os.path.islink(os.path.join(r, n)))
    chemin = depots.worktree(depot, "t_abcd", "hermes/t_abcd", "origin/main")
    assert (os.stat(chemin.parent).st_gid, os.stat(chemin.parent).st_mode & 0o777) == (10100, 0o751)
    depots.ouvrir_tour(chemin)
    etat = os.stat(chemin)
    assert (etat.st_uid, etat.st_gid, etat.st_mode & 0o7777) == (0, 10100, 0o2770)
    fichier = os.stat(chemin / "src" / "app.py")
    assert fichier.st_gid == 10100 and fichier.st_mode & 0o060 == 0o060
    # Sous l'UID de vérification (groupe acp-travail), écriture admise pendant le tour…
    ecrire = ["/usr/bin/setpriv", "--reuid=10003", "--regid=10003", "--groups=10100", "--", "/bin/sh", "-c",
              f"echo test >> {chemin}/src/app.py"]
    assert subprocess.run(ecrire, capture_output=True).returncode == 0
    depots.fermer_tour(chemin)
    # … refusée hors du tour (test_worktree_d_une_autre_carte_inaccessible, § 3.3).
    assert subprocess.run(ecrire, capture_output=True).returncode != 0
    lire = ["/usr/bin/setpriv", "--reuid=10003", "--regid=10003", "--groups=10100", "--", "cat",
            f"{chemin}/README.md"]
    assert subprocess.run(lire, capture_output=True).returncode != 0


# ------------------------------------------------------------------ purge du disque (relecture de P6)


def _vieillir(depots: Depots, alias: str, nom: str, jours: float) -> None:
    import time

    instant = time.time() - jours * 86400
    for chemin in (depots.espace(alias, nom), depots.gitdir_du_worktree(alias, nom) / "index",
                   depots.gitdir_du_worktree(alias, nom) / "HEAD"):
        if chemin.exists():
            os.utime(chemin, (instant, instant))


def test_purge_des_worktrees_et_bundles_anciens_branches_gardees(depots, distant):
    """``[disque] purge_apres_jours`` était lu et jamais appliqué : les worktrees et les bundles s'accumulaient sur le
    volume de 5 Go. Purge : worktrees sans activité depuis N jours (branches GARDÉES), bundles plus anciens ; jamais
    une carte gardée (en main)."""
    import time

    depot = _depot(distant)
    depots.recuperer(depot)
    for nom in ("t_aaaa0001", "t_bbbb0001", "t_cccc0001"):
        chemin = depots.worktree(depot, nom, f"hermes/{nom}", "origin/main")
        (chemin / f"{nom}.txt").write_text("travail\n", encoding="utf-8")
        depots.committer("jetable", nom, f"implementation({nom}): travail")
    _vieillir(depots, "jetable", "t_aaaa0001", 8)
    _vieillir(depots, "jetable", "t_cccc0001", 30)
    fichier, _empreinte, _tete = depots.bundle("jetable", "hermes/t_aaaa0001")
    recent, _e, _t = depots.bundle("jetable", "hermes/t_bbbb0001")
    os.utime(fichier, (time.time() - 9 * 86400,) * 2)
    retires = depots.purger(age_s=7 * 86400, garder={"t_cccc0001"})
    assert retires == {"worktrees": 1, "bundles": 1}
    assert not depots.espace("jetable", "t_aaaa0001").exists()
    assert depots.espace("jetable", "t_bbbb0001").exists() and depots.espace("jetable", "t_cccc0001").exists()
    assert not fichier.exists() and recent.exists()
    # La branche reste : une reprise recrée le worktree depuis elle, travail committé compris.
    assert depots.branche_existe("jetable", "hermes/t_aaaa0001")
    repris = depots.worktree(depot, "t_aaaa0001", "hermes/t_aaaa0001", "origin/main")
    assert (repris / "t_aaaa0001.txt").read_text(encoding="utf-8") == "travail\n"
    assert depots.purger(age_s=7 * 86400, garder={"t_cccc0001"}) == {"worktrees": 0, "bundles": 0}


@POSIX
def test_purge_ne_suit_aucun_lien(depots, distant, tmp_path):
    depot = _depot(distant)
    depots.recuperer(depot)
    depots.worktree(depot, "t_dddd0001", "hermes/t_dddd0001", "origin/main")
    cible = tmp_path / "cible"
    cible.mkdir()
    (cible / "precieux.txt").write_text("x", encoding="utf-8")
    (depots.racine_espaces / "jetable" / "t_eeee0001").symlink_to(cible, target_is_directory=True)
    (depots.racine_espaces / "autre").symlink_to(cible, target_is_directory=True)
    os.utime(cible, (0, 0))
    assert depots.purger(age_s=1, maintenant=4_000_000_000)["worktrees"] == 1  # le vrai seulement
    assert (cible / "precieux.txt").exists()
