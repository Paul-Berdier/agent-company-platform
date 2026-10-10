"""Sonde de plateforme de l'exécutant (cahier P6 § 4.1) et inventaire Linux (§ 7.3).

Le verdict est une fonction pure des mesures (éprouvée partout) ; les relevés sont pris par des commandes injectables
(aucun lancement réel hors Linux) ; la sonde réelle tourne dans le conteneur de test en root (seccomp Docker par
défaut : bubblewrap refusé attendu, régime B — ce n'est PAS une preuve pour Railway, seule la sonde R0 en est une).
"""

from __future__ import annotations

import re

import json
import os
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from acp_poste import sonde_plateforme as sp
from acp_poste.inventaire import construire
from acp_poste.plateforme.linux import EmplacementsLinux
from acp_poste.politique import SectionCodex, analyser_executant
from acp_poste.sondes_codex import CONFIG_TOML_LINUX, ecrire_config_toml, etat_config_toml, sonder_codex
from acp_poste_contrat.inventaire import IsolementLinux, identifiant_trouve, valider_inventaire

RACINE_LINUX = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="exige Linux et root (setpriv, unshare, bubblewrap) : conteneur de test de P6 seulement")
RACINE_DEPOT = Path(__file__).resolve().parents[3]
VERSIONNEE = RACINE_DEPOT / "executant" / "politique" / "executant.toml"


def _mesures(**changements) -> sp.Mesures:
    base = dict(unshare_root=0, unshare_uid=0, bwrap_present=True, bwrap_base=0, bwrap_proc=1, codex_present=True,
                essai_true=0, essai_ecriture_hors=1, essai_reseau=2, essai_auth=1, setpriv_id="10003",
                environ_pid1_refuse=True, fichier_root_refuse=True, kill_pid1_refuse=True)
    base.update(changements)
    return sp.Mesures(**base)


# ------------------------------------------------------------------ verdict (fonction pure)


def test_regime_a_exige_tout():
    v = sp.verdict(_mesures())
    assert v == {"regime": "A", "bwrap": "fonctionne", "proc_neuf": False, "reseau_coupe": True, "uid_separes": True,
                 "raison": v["raison"]}
    assert v["raison"].startswith("Régime A")


@pytest.mark.parametrize(("changement", "bwrap", "motif"), [
    ({"bwrap_base": 1}, "refuse", "bubblewrap refusé"),
    ({"bwrap_present": False, "bwrap_base": None}, "absent", "bubblewrap absent"),
    ({"unshare_uid": 1}, "fonctionne", "unshare -Ur refusé"),
    ({"codex_present": False, "essai_true": None, "essai_ecriture_hors": None, "essai_reseau": None,
      "essai_auth": None}, "fonctionne", "Codex absent"),
    ({"essai_reseau": 0}, "fonctionne", "n'a pas tenu"),
    ({"essai_auth": 0}, "fonctionne", "n'a pas tenu"),
    ({"essai_ecriture_hors": 0}, "fonctionne", "n'a pas tenu"),
    ({"essai_true": 1}, "fonctionne", "n'a pas tenu"),
])
def test_regime_b_et_sa_raison(changement, bwrap, motif):
    v = sp.verdict(_mesures(**changement))
    assert v["regime"] == "B" and v["bwrap"] == bwrap and v["uid_separes"] is True
    assert motif in v["raison"]


@pytest.mark.parametrize("changement", [{"setpriv_id": "0"}, {"setpriv_id": None}, {"environ_pid1_refuse": False},
                                        {"fichier_root_refuse": False}, {"kill_pid1_refuse": False}])
def test_uid_non_separes_aucune_ecriture(changement):
    v = sp.verdict(_mesures(**changement))
    assert v["regime"] == "B" and v["uid_separes"] is False and "non prouvés" in v["raison"]
    bloc = sp.isolement({"verdict": v, "sonde_le": "2026-10-01T10:00:00Z"})
    assert bloc["ecriture_admise"] == {"codex": False, "claude": False}
    IsolementLinux.model_validate(bloc)


def test_isolement_publie_selon_le_regime():
    a = sp.isolement({"verdict": sp.verdict(_mesures()), "sonde_le": "2026-10-01T10:00:00Z"})
    assert a["ecriture_admise"] == {"codex": True, "claude": True} and a["raison"] is None
    b = sp.isolement({"verdict": sp.verdict(_mesures(bwrap_base=1)), "sonde_le": "2026-10-01T10:00:00Z"})
    assert b["ecriture_admise"] == {"codex": False, "claude": True}
    assert "Voie Codex fermée" in b["raison"] and "D79" in b["raison"]
    sans = sp.isolement(None, maintenant=datetime(2026, 10, 1, tzinfo=UTC))
    assert sans["regime"] == "inconnu" and sans["ecriture_admise"] == {"codex": False, "claude": False}
    for bloc in (a, b, sans):
        IsolementLinux.model_validate(bloc)


def test_profil_de_verification_lisible():
    profil = tomllib.loads(sp.profil_codex_toml())
    assert profil["default_permissions"] == "acp_verif"
    fs = profil["permissions"]["acp_verif"]["filesystem"]
    assert fs[":project_roots"] == "write" and fs[":root"] == "read"
    assert all(fs[c] == "deny" for c in ("/donnees/codex", "/donnees/claude", "/donnees/acp", "/etc/acp"))
    assert profil["permissions"]["acp_verif"]["network"] == {"enabled": False}


# ------------------------------------------------------------------ relevés par commandes injectées


def test_mesurer_sous_les_bons_uid_et_sans_lancement_reel(tmp_path):
    lances = []

    def executer(argv):
        lances.append(list(argv))
        if "bwrap" in argv[-1] or any("bwrap" in a for a in argv):
            return 1, "bwrap: setting up uid map: Permission denied"
        if argv[-2:] == ["id", "-u"]:
            return 0, "10003\n"
        if "unshare" in argv:
            return 1, "unshare: unshare failed: Operation not permitted"
        return 1, "Permission denied"

    plateforme, m = sp.mesurer(executer=executer, codex=None, claude=None, bwrap="/usr/bin/bwrap",
                               racine_temporaire=str(tmp_path))
    v = sp.verdict(m)
    assert v["regime"] == "B" and v["bwrap"] == "refuse" and v["uid_separes"] is True
    bwrap = [a for a in lances if "/usr/bin/bwrap" in a]
    assert bwrap and all("--reuid=10001" in a for a in bwrap)
    assert all("--reuid=10003" in a for a in lances if "/proc/1/environ" in a or "kill" in a)
    assert ["unshare", "-Ur", "true"] in lances
    points = [r.point for r in m.releves]
    for attendu in ("1.codex_doctor", "4.unshare_root", "4.unshare_10003", "5.bwrap", "5.bwrap_proc",
                    "6.codex_sandbox", "7.id", "7.environ_pid1", "7.fichier_root", "7.kill_pid1",
                    "9.codex_version", "9.claude_version"):
        assert attendu in points
    assert all(len(r.sortie) <= 200 for r in m.releves)
    assert "architecture" in plateforme and "statut" in plateforme


def test_sortie_filtree_sans_adresse_ni_profil():
    assert "titulaire@example.com" not in sp._filtrer("erreur pour titulaire@example.com dans /home/paul/x")
    assert len(sp._filtrer("x" * 500)) == 200


def test_sortie_filtree_sans_l_avertissement_des_alias_de_codex():
    """L'avertissement de Codex sur son CODEX_HOME sous /tmp ne masque plus la vraie cause d'un refus."""
    brut = ('WARNING: proceeding, even though we could not create PATH aliases: Refusing to create helper binaries '
            'under temporary dir "/tmp" (codex_home: AbsolutePathBuf("/tmp/x"))\nbwrap: Can\'t mount proc on /newroot/proc')
    assert sp._filtrer(brut) == "bwrap: Can't mount proc on /newroot/proc"


# ------------------------------------------------------------------ sonde réelle (conteneur de test, root)


@RACINE_LINUX
def test_sonde_reelle_conteneur_docker_par_defaut(tmp_path):
    resultat = sp.sonder(codex=None, claude=None)
    v = resultat["verdict"]
    # Conteneur Docker au seccomp par défaut : pas d'espace de noms utilisateur, donc bubblewrap refusé et régime B ;
    # setpriv fonctionne (CAP_SETUID et CAP_SETGID du jeu par défaut) : UID séparés.
    assert v["regime"] == "B" and v["uid_separes"] is True
    assert v["bwrap"] in ("refuse", "absent")
    assert identifiant_trouve(resultat) is None
    IsolementLinux.model_validate(sp.isolement(resultat))
    json.dumps(resultat)


# ------------------------------------------------------------------ inventaire Linux (§ 7.3)


def _politique_linux(tmp_path):
    texte = re.sub(r'(?m)^origine = "[^"\n]*"$', 'origine = "https://hermes-acp-test.up.railway.app"', VERSIONNEE.read_text(encoding="utf-8"), count=1)
    return analyser_executant(texte.encode("utf-8"), EmplacementsLinux.de_test(tmp_path))


def _resultat_claude():
    from acp_poste.sondes_claude import ResultatClaude

    releve = {"voie": "poste-claude", "source": "poste", "version_cli": "2.1.283",
              "releve_le": "2026-10-01T10:00:00Z", "modeles": [], "quotas": None, "compteurs": [],
              "origine_liste": "aucune", "etat": "cli_absente", "detail": "Claude Code introuvable.",
              "documentation_lue_le": None, "resolutions_observees": []}
    return ResultatClaude(releve=releve, connexion="jeton_absent",
                          version={"lue": None, "testee": "2.1.283", "conforme": False})


def test_inventaire_linux_valide_et_sans_bac_windows(tmp_path):
    politique = _politique_linux(tmp_path)
    isolement = sp.isolement({"verdict": sp.verdict(_mesures(bwrap_base=1)), "sonde_le": "2026-10-01T10:00:00Z"})
    inventaire = construire(politique, None, _resultat_claude(), valeurs_exactes=[],
                            infos={"plateforme": "linux", "hote": "railway", "noyau": "6.8.0-railway"},
                            isolement=isolement, maintenant=datetime(2026, 10, 1, 10, tzinfo=UTC))
    valide = valider_inventaire(inventaire)
    assert valide.poste.plateforme == "linux" and valide.poste.compte == "uid_dedie"
    assert valide.poste.hote == "railway" and valide.poste.windows is None and valide.poste.noyau == "6.8.0-railway"
    assert valide.bac_a_sable_codex is None and valide.isolement_linux.regime == "B"
    assert valide.politique.conditions == {"codex": date(2026, 10, 1), "claude": date(2026, 10, 1)}
    assert valide.poste.hermes_meme_enveloppe_que_codex is True


def test_inventaire_linux_sans_sonde_inconnu(tmp_path):
    inventaire = construire(_politique_linux(tmp_path), None, _resultat_claude(), valeurs_exactes=[],
                            infos={"plateforme": "linux", "hote": "pc", "noyau": None})
    bloc = valider_inventaire(inventaire).isolement_linux
    assert bloc.regime == "inconnu" and bloc.ecriture_admise == {"codex": False, "claude": False}


# ------------------------------------------------------------------ sonde Codex en mode Linux (faux app-server)


async def test_sonde_codex_linux_stockage_file_sans_readiness(poste):
    home = poste.emplacements.acp_local / "codex-home-linux"
    assert ecrire_config_toml(home, "linux") == "cree"
    assert (home / "config.toml").read_bytes() == CONFIG_TOML_LINUX and etat_config_toml(home, "linux") == "conforme"
    assert etat_config_toml(home) == "modifie"  # le profil Windows n'est pas celui de l'exécutant
    enregistrement = poste.racine / "codex-linux.jsonl"
    poste.scenario_codex = {"config": {"service_tier": "default", "cli_auth_credentials_store": "file",
                                       "model": None},
                            "origines": {}, "enregistrer": str(enregistrement)}
    section = SectionCodex(executable=Path(sys.executable), home=home, version_testee="0.156.1", modeles_permis=(),
                           bac_a_sable="bubblewrap")
    resultat = await sonder_codex(section, poste.emplacements, delai_s=30, prefixe=poste.lanceurs()["codex"],
                                  plateforme="linux")
    assert resultat.releve["etat"] == "ok" and resultat.bac_a_sable is None and resultat.stockage == "file"
    assert not [a for a in resultat.alertes if "Stockage" in a]
    lignes = [json.loads(l) for l in enregistrement.read_text(encoding="utf-8").splitlines()]
    argv = next(l["argv"] for l in lignes if "app-server" in l.get("argv", []))
    methodes = [l.get("method") for l in lignes if "method" in l]
    assert "account/read" in methodes and "windowsSandbox/readiness" not in methodes
    assert 'cli_auth_credentials_store="file"' in argv and 'service_tier="default"' in argv
    assert not any("windows.sandbox" in a for a in argv)


@RACINE_LINUX
def test_commande_sonde_plateforme_json(tmp_path, capsys):
    from acp_poste.cli import main
    from acp_poste.contexte import Contexte
    from acp_poste.plateforme.linux import CoffreFichiers

    emplacements = EmplacementsLinux.de_test(tmp_path)
    contexte = Contexte(emplacements=emplacements, coffre=CoffreFichiers(emplacements.secrets), plateforme="linux")
    assert main(["sonde-plateforme", "--json"], contexte=contexte) == 0
    resultat = json.loads(capsys.readouterr().out)
    assert resultat["protocole"] == "acp-sonde-plateforme/1" and resultat["verdict"]["regime"] in ("A", "B")
    # Aucune politique ni aucun volume exigés (projet jetable acp-sonde) : rien n'a été créé sous la racine.
    assert not emplacements.donnees.exists()
