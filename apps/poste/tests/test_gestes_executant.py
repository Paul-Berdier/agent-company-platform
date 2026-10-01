"""Gestes du propriétaire sur l'exécutant (cahier P6 § 11, § 12.2, § 16) et diagnostic Linux, par ``acp-poste``.

POSIX seulement (coffre en fichiers 0600, droits de ``executant.toml``) ; le refus de ces commandes sur le poste
Windows est éprouvé sur toutes les plateformes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from acp_poste.cli import main
from acp_poste.contexte import Contexte
from acp_poste.depots import Depots
from acp_poste.plateforme.linux import CoffreFichiers, EmplacementsLinux
from acp_poste.politique import DepotDistant

POSIX = pytest.mark.skipif(os.name != "posix", reason="exécutant Linux (coffre 0600, droits POSIX)")
ICI = Path(__file__).resolve().parent
RACINE_DEPOT = ICI.parents[2]
PYTHON = str(Path(sys.executable).resolve())


def _contexte(racine: Path, **options) -> Contexte:
    emplacements = EmplacementsLinux.de_test(racine)
    return Contexte(emplacements=emplacements, coffre=CoffreFichiers(emplacements.secrets), plateforme="linux",
                    infos_plateforme=lambda: {"plateforme": "linux", "hote": "pc", "noyau": "6.1.0",
                                              "windows": None}, **options)


def _politique(contexte: Contexte, *, depot: bool = True) -> None:
    e = contexte.emplacements
    texte = (RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8").replace(
        'origine = "https://<libellé-hermes>.up.railway.app"', 'origine = "https://hermes-acp-test.up.railway.app"')
    texte = texte.replace('home = "/donnees/codex"', f'home = "{e.codex_home}"')
    if depot:
        texte += ('\n[depots.jetable]\nurl = "https://github.com/proprietaire-factice/jetable.git"\n'
                  'verification = ["true"]\n')
    e.politique.parent.mkdir(parents=True, exist_ok=True)
    e.politique.write_text(texte, encoding="utf-8")


# ------------------------------------------------------------------ refus hors de l'exécutant


@pytest.mark.parametrize("argv", [["pause"], ["reprise"], ["cartes"], ["bundle", "jetable", "hermes/projet-x"]])
def test_commandes_de_l_executant_refusees_sur_le_poste_windows(poste, capsys, argv):
    assert main(argv, contexte=poste.contexte()) == 2
    assert "exécutant Linux" in capsys.readouterr().err


def test_connexion_github_sans_objet_sur_windows(poste, capsys):
    poste.ecrire_politique()
    assert main(["connexion", "github", "--stdin"], contexte=poste.contexte()) == 2
    assert "sans objet sur le poste Windows" in capsys.readouterr().err


def test_servir_plateforme_annoncee_contraire(poste, capsys):
    autre = "linux" if sys.platform == "win32" else "windows"
    assert main(["servir", "--plateforme", autre], contexte=poste.contexte()) == 2
    assert "différente de la plateforme réelle" in capsys.readouterr().err


# ------------------------------------------------------------------ jetons déposés sur le volume (D92)


@POSIX
@pytest.mark.parametrize(("cible", "fichier"), [("claude", "claude-oauth"), ("github", "github-lecture")])
def test_connexion_par_stdin_en_0600(tmp_path, capsys, monkeypatch, cible, fichier):
    contexte = _contexte(tmp_path)
    _politique(contexte)
    secret = ("sk-ant-oat01-" if cible == "claude" else "github_pat_") + "z" * 40
    monkeypatch.setattr(sys, "stdin", type("Entree", (), {"readline": staticmethod(lambda: secret + "\n")})())
    assert main(["connexion", cible, "--stdin"], contexte=contexte) == 0
    sortie = capsys.readouterr()
    assert secret not in sortie.out + sortie.err and "Empreinte :" in sortie.out
    chemin = contexte.emplacements.secrets / fichier
    assert (chemin.stat().st_mode & 0o777) == 0o600 and chemin.read_text(encoding="utf-8") == secret


@POSIX
def test_jeton_avec_espace_refuse(tmp_path, capsys, monkeypatch):
    contexte = _contexte(tmp_path)
    _politique(contexte)
    monkeypatch.setattr(sys, "stdin", type("Entree", (), {"readline": staticmethod(lambda: "deux mots\n")})())
    assert main(["connexion", "github", "--stdin"], contexte=contexte) == 2
    assert not (contexte.emplacements.secrets / "github-lecture").exists()


# ------------------------------------------------------------------ Codex par code d'appareil


@POSIX
def test_connexion_codex_exige_la_pause_puis_lance_le_login(tmp_path, capfd):
    contexte = _contexte(tmp_path, lanceurs={"codex": [PYTHON, "-c", "import sys; print('ARGV', sys.argv[1:])"]})
    _politique(contexte)
    assert main(["connexion", "codex"], contexte=contexte) == 2
    assert "acp-poste pause" in capfd.readouterr().err
    assert main(["pause"], contexte=contexte) == 0
    assert main(["connexion", "codex"], contexte=contexte) == 0
    sortie = capfd.readouterr().out
    assert "config.toml du profil Codex écrit." in sortie
    assert "'-c', 'cli_auth_credentials_store=\"file\"', 'login', '--device-auth'" in sortie
    assert (contexte.emplacements.codex_home / "config.toml").read_text(encoding="utf-8").count('"file"') == 1
    assert main(["reprise"], contexte=contexte) == 0 and not contexte.emplacements.pause_locale.exists()


# ------------------------------------------------------------------ bundle, cartes, diagnostic


@POSIX
def test_bundle_d_une_branche_prete(tmp_path, capsys):
    contexte = _contexte(tmp_path)
    _politique(contexte)
    distant = tmp_path / "distant"
    distant.mkdir()
    git = ["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main"]
    subprocess.run([*git, "init", "-q"], cwd=distant, check=True)
    (distant / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], cwd=distant, check=True)
    subprocess.run([*git, "commit", "-qm", "a"], cwd=distant, check=True)
    e = contexte.emplacements
    depots = Depots(racine_depots=e.depots, racine_espaces=e.espaces, racine_bundles=e.bundles,
                    protocoles=("https", "file"), droits=False)
    depot = DepotDistant(alias="jetable", url=str(distant), branche_base="main", acces="public", preparation=(),
                         verification=("true",), verification_max_s=900, reprises_verification=2,
                         verification_sans_bac_a_sable=False, liens_symboliques=False, pilotage_supplementaire=())
    depots.recuperer(depot)
    depots.worktree(depot, "projet-demo", "hermes/projet-demo", "origin/main")
    assert main(["bundle", "jetable", "hermes/projet-demo"], contexte=contexte) == 0
    sortie = capsys.readouterr().out
    assert "SHA-256 : " in sortie and "Tête de hermes/projet-demo : " in sortie and str(tmp_path) not in sortie
    assert main(["bundle", "inconnu", "hermes/projet-demo"], contexte=contexte) == 2


@POSIX
def test_cartes_et_diagnostic_linux(tmp_path, capsys):
    contexte = _contexte(tmp_path)
    _politique(contexte)
    e = contexte.emplacements
    e.etat.mkdir(parents=True, exist_ok=True)
    e.carte.write_text(json.dumps({"tableau": "acp-x", "carte": "t_ab12cd34", "run_id": 3, "role": "implementation",
                                   "voie": "poste-claude", "etape": "agent"}), encoding="utf-8")
    e.sonde_isolement.write_text(json.dumps({"sonde_le": "2026-10-01T10:00:00Z", "verdict": {
        "regime": "B", "bwrap": "refuse", "uid_separes": True, "raison": "Régime B."}}), encoding="utf-8")
    assert main(["cartes"], contexte=contexte) == 0
    cartes = json.loads(capsys.readouterr().out)
    assert cartes["carte_en_main"]["carte"] == "t_ab12cd34" and cartes["file_de_sortie"] == []
    assert main(["diagnostic", "--isolement"], contexte=contexte) == 0
    rapport = json.loads(capsys.readouterr().out)
    bloc = rapport["executant"]
    assert bloc["sonde"]["regime"] == "B" and bloc["carte_en_main"]["etape"] == "agent"
    assert bloc["file_de_sortie"] == {"en_attente": 0, "refusees": 0} and bloc["jeton_github"] == "absent"
    assert bloc["plafonds_du_jour"]["cartes_max"] == 20 and rapport["service"]["tache_planifiee"] is None
    if sys.platform.startswith("linux"):
        assert isinstance(bloc["sockets_a_l_ecoute"], int)
