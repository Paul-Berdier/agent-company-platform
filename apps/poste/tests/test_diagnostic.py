"""Diagnostic du poste (cahier P5 § 6.5) : JSON sans chemin ni secret ; isolement du profil du propriétaire."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from acp_poste.cli import main
from acp_poste.diagnostic import diagnostic
from acp_poste.inventaire import construire, relever
from acp_poste.politique import charger
from acp_poste_contrat.inventaire import identifiant_trouve

JETON = "acpm_" + "d" * 43
JETON_CLAUDE = "sk-ant-oat01-" + "e" * 40


def _jeton_eleve() -> bool:
    """Jeton administrateur élevé (exécuteurs de CI Windows) : ses privilèges contournent les ACL de test (écriture et
    liste constatées malgré un ACE limité ou refusé, run 36279917625) ; le compte dédié du poste est un compte standard."""
    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


ACL_NON_ELEVE = pytest.mark.skipif(
    os.name != "nt" or _jeton_eleve(),
    reason="ACL réelles : exige Windows et un jeton NON élevé (le jeton élevé de la CI contourne les ACL) ; éprouvé sur "
           "le poste de développement")


async def test_sans_chemin_ni_secret(poste, capsys):
    poste.ecrire_politique()
    poste.preparer_profil_codex()
    poste.coffre.ecrire("jeton-machine", JETON)
    poste.coffre.ecrire("jeton-claude", JETON_CLAUDE)
    poste.emplacements.etat.mkdir(parents=True, exist_ok=True)
    poste.emplacements.machine.write_text(json.dumps({"machine_id": "m0123456789a", "empreinte": "ABCD-1234"}),
                                          encoding="utf-8")
    politique = charger(poste.emplacements)
    codex, claude = await relever(politique, emplacements=poste.emplacements, coffre=poste.coffre,
                                  lanceurs=poste.lanceurs())
    poste.emplacements.dernier_inventaire.write_text(json.dumps(construire(
        politique, codex, claude, windows="10.0.19045", valeurs_exactes=[])), encoding="utf-8")
    rapport = await __import__("asyncio").to_thread(diagnostic, poste.contexte(), isolement=True)
    texte = json.dumps(rapport, ensure_ascii=False)
    assert identifiant_trouve(rapport, valeurs_exactes=[JETON, JETON_CLAUDE]) is None
    for interdit in (str(poste.racine), "codex-home", "LocalAppData", JETON, JETON_CLAUDE, "\\\\"):
        assert interdit not in texte, interdit
    assert rapport["politique"]["etat"] == "valide" and rapport["compte"] == {"mode": "proprietaire", "conforme": True}
    assert rapport["jeton"] == {"present": True, "machine_id": "m0123456789a", "empreinte": "ABCD-1234"}
    assert rapport["codex"]["version"] == "0.156.1" and rapport["codex"]["config_toml"] == "conforme"
    assert rapport["codex"]["bac_a_sable"]["ecriture_admise"] is True
    assert rapport["claude"]["jeton"] == "present" and rapport["claude"]["ligne_etat"] == "non_declaree"
    assert rapport["hermes"]["joignable"] is None, "aucun réseau sans --reseau"
    assert rapport["isolement"]["profils"] == 0


def test_politique_invalide_dite_sans_valeur(poste):
    poste.ecrire_politique(poste.toml(sections={"codex": {"executable": "\\\\serveur\\partage\\codex.exe"}}))
    rapport = diagnostic(poste.contexte())
    assert rapport["politique"]["etat"] == "invalide" and "UNC" in rapport["politique"]["refus"]
    assert "serveur" not in json.dumps(rapport)


def test_commande_diagnostic(poste, capsys):
    poste.ecrire_politique()
    assert main(["diagnostic"], contexte=poste.contexte()) == 0
    rapport = json.loads(capsys.readouterr().out)
    assert rapport["version_poste"] == "0.11.0" and rapport["protocole"] == "acp-machine/1"
    assert rapport["service"]["verrou"] == "libre"


@ACL_NON_ELEVE
def test_isolement_liste_refusee(poste, tmp_path):
    """Un dossier dont l'ACL refuse la liste au compte courant vaut « profil non lisible » ; un dossier ouvert vaut
    « lisible ». Rien n'est lu dans ces dossiers."""
    ferme = tmp_path / "profil-ferme"
    ferme.mkdir()
    utilisateur = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["icacls", str(ferme), "/deny", f"{utilisateur}:(RD)"], check=True, capture_output=True)
    try:
        poste.ecrire_politique(poste.toml(sections={"isolement": {"profils_interdits": [str(ferme)]}}))
        rapport = diagnostic(poste.contexte(), isolement=True)
        assert rapport["isolement"]["profil_proprietaire_lisible"] is False and rapport["isolement"]["refuses"] == 1
        ouvert = tmp_path / "profil-ouvert"
        ouvert.mkdir()
        poste.ecrire_politique(poste.toml(sections={"isolement": {"profils_interdits": [str(ouvert)]}}))
        assert diagnostic(poste.contexte(), isolement=True)["isolement"]["profil_proprietaire_lisible"] is True
    finally:
        subprocess.run(["icacls", str(ferme), "/remove:d", utilisateur], capture_output=True)
