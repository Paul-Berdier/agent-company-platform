"""scripts/verifier_releve_r0.py (cahier P6 § 15) : un relevé de sonde R0 n'est publiable que complet, cohérent avec
ses propres mesures et sans identifiant ni secret. Les relevés sont PRODUITS par la vraie sonde
(acp_poste.sonde_plateforme.sonder) avec un exécuteur injecté : aucune commande n'est lancée."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acp_poste.sonde_plateforme import sonder

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("verifier_releve_r0", RACINE / "scripts" / "verifier_releve_r0.py")
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def _executeur(regime: str):
    def executer(argv):
        texte = " ".join(argv)
        if "id -u" in texte or argv[-2:] == ["id", "-u"]:
            return 0, "10003"
        if "unshare" in texte or "bwrap" in texte:
            return (0, "") if regime == "A" else (1, "bwrap: No permissions to create a new namespace")
        if "/proc/1/environ" in texte or "fichier-root" in texte or "kill" in texte:
            return 1, "Permission denied"
        return 0, ""

    return executer


def _releve(regime: str = "B") -> dict:
    releve = sonder(maintenant=datetime(2026, 10, 1, 12, 0, tzinfo=UTC), executer=_executeur(regime), codex=None,
                    claude=None, bwrap="/usr/bin/bwrap")
    # Sous Windows (suite du dépôt), le fichier témoin du point 7 vit sous C:\…\Temp : ramené à la forme Linux de
    # l'exécutant, seule forme qu'une vraie sonde R0 produit.
    for r in releve["releves"]:
        r["commande"] = re.sub(r"\S*fichier-root", "/tmp/acp-sonde-root-x/fichier-root", r["commande"])
    return releve


def test_releve_b_publiable_et_normalise(tmp_path, capsys):
    releve = _releve("B")
    assert releve["verdict"]["regime"] == "B" and releve["verdict"]["uid_separes"] is True
    colle = tmp_path / "journaux.txt"
    colle.write_text("2026-10-01 12:00:01 Starting Container\n" + json.dumps(releve, ensure_ascii=False, indent=2) +
                     "\n2026-10-01 12:00:09 Stopping Container\n", encoding="utf-8")
    sortie = tmp_path / "preuves" / "r0-sonde.json"
    assert script.main([str(colle), "--sortie", str(sortie)]) == 0
    assert "Relevé R0 publiable (2026-10-01T12:00:00Z) : régime B" in capsys.readouterr().out
    publie = sortie.read_text(encoding="utf-8")
    assert json.loads(publie) == releve and publie.endswith("}\n") and "\r" not in publie


def test_releve_tronque_refuse(tmp_path, capsys):
    texte = json.dumps(_releve(), indent=2)
    (tmp_path / "x.txt").write_text(texte[: len(texte) // 2], encoding="utf-8")
    assert script.main([str(tmp_path / "x.txt")]) == 1
    assert "incomplet ou illisible" in capsys.readouterr().err


@pytest.mark.parametrize("retouche, fragment", [
    (lambda r: r["verdict"].update(regime="A"), "Régime « A » incohérent"),
    (lambda r: r["verdict"].update(uid_separes=False), "« uid_separes » incohérent"),
    (lambda r: next(x for x in r["releves"] if x["point"] == "7.environ_pid1").update(code=0),
     "« uid_separes » incohérent"),
    (lambda r: r.update(protocole="autre/1"), "Protocole"),
    (lambda r: r["verdict"].pop("raison"), "Verdict incomplet"),
    (lambda r: r.update(releves=[x for x in r["releves"] if x["point"] != "7.kill_pid1"]), "7.kill_pid1"),
])
def test_releve_retouche_refuse(retouche, fragment):
    releve = copy.deepcopy(_releve("B"))
    retouche(releve)
    with pytest.raises(script.Refus, match=fragment):
        script.verifier(releve)


def test_releve_a_coherent_admis_et_secret_ou_identifiant_refuses():
    releve = _releve("A")
    # Sans Codex dans ce relevé produit, les essais du point 6 manquent : le verdict reste B, et c'est cohérent.
    assert script.verifier(releve)["regime"] == releve["verdict"]["regime"]
    for valeur, fragment in (("cle " + "sk-ant-" + "faux" * 8, "secret"), ("ecrit par proprietaire@example.com",
                                                                          "Identifiant")):
        abime = copy.deepcopy(releve)
        abime["releves"][0]["sortie"] = valeur
        with pytest.raises(script.Refus, match=fragment):
            script.verifier(abime)


# ------------------------------------------------------------------ relecture de P6 : bibliothèque standard seulement


def test_lance_sans_paquet_tiers_comme_sur_le_pc_du_proprietaire(tmp_path):
    """Haute (relecture de P6) : le contrôleur importait le contrat, donc pydantic, absent du Python du propriétaire
    et de tout clone neuf : trace en anglais et code 1 (« relevé refusé »). Lancé ici SANS aucun paquet tiers
    (``-S -I`` : ni site-packages ni environnement), il rend 0 sur un relevé valide."""
    import subprocess
    import sys

    sans_tiers = [sys.executable, "-S", "-I"]
    assert subprocess.run([*sans_tiers, "-c", "import pydantic"], capture_output=True).returncode != 0
    colle = tmp_path / "releve-r0.txt"
    colle.write_text(json.dumps(_releve("B"), ensure_ascii=False, indent=2), encoding="utf-8")
    resultat = subprocess.run([*sans_tiers, str(RACINE / "scripts" / "verifier_releve_r0.py"), str(colle)],
                              capture_output=True)
    sortie, erreur = resultat.stdout.decode("utf-8"), resultat.stderr.decode("utf-8")
    assert resultat.returncode == 0, erreur
    assert "Relevé R0 publiable" in sortie and "Traceback" not in erreur


def test_motifs_du_contrat_introuvables_code_2(tmp_path, capsys, monkeypatch):
    colle = tmp_path / "releve-r0.txt"
    colle.write_text(json.dumps(_releve("B")), encoding="utf-8")
    monkeypatch.setattr(script, "MOTIFS_SECRETS", tmp_path / "absent.py")
    assert script.main([str(colle)]) == 2
    assert "Motifs de secrets du contrat introuvables" in capsys.readouterr().err


@pytest.mark.parametrize("objet", [
    "rien", r"C:\Users\paul\x", r"\\serveur\partage", "/home/x/users/y", "a@b", "acpm_" + "a" * 43, "acpe_x",
    "sk-ant-" + "b" * 30, {"cle@": "v"}, {"a": ["ok", {"b": "D:/x"}]}, ["ok", 3, None, {"c": "github_pat_" + "c" * 31}],
    {"profond": [[[["eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12]]]]},
])
def test_garde_en_parite_avec_le_contrat(objet):
    """La garde copiée (bibliothèque standard) rend EXACTEMENT ce que rend le contrat."""
    from acp_poste_contrat.inventaire import _LECTEUR, _PROFIL, _UNC, identifiant_trouve
    from acp_poste_contrat.machine import secret_trouve
    from acp_poste_contrat.motifs_secrets import motif_trouve

    assert script.identifiant_trouve(objet, motif_trouve) == identifiant_trouve(objet)
    assert script.secret_trouve(objet, motif_trouve) == secret_trouve(objet)
    assert (script._LECTEUR.pattern, script._UNC.pattern, script._PROFIL.pattern) == (
        _LECTEUR.pattern, _UNC.pattern, _PROFIL.pattern)
