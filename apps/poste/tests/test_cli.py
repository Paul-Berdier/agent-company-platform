"""Commande ``acp-poste`` (cahier P5 § 6.3) : sous-commandes, codes de sortie, refus en français, aucune commande
simulée. Chaque test injecte un contexte sur une racine jetable : jamais les vrais emplacements d'une installation."""

from __future__ import annotations

import json
import os
import sys

import pytest

from acp_poste.cli import main
from acp_poste.journal import Journal
from acp_poste_contrat.inventaire import valider_inventaire


@pytest.mark.parametrize("commande", ["start", "register", "doctor", "claims"])
def test_commandes_de_l_ancienne_api_absentes(commande: str):
    with pytest.raises(SystemExit) as refus:
        main([commande])
    assert refus.value.code == 2


def test_version(capsys):
    with pytest.raises(SystemExit) as fin:
        main(["--version"])
    assert fin.value.code == 0 and capsys.readouterr().out.strip() == "acp-poste 0.11.0"


@pytest.mark.parametrize("argv, attendu", [
    (["connexion"], "acp-poste connexion : commande refusée : arguments obligatoires manquants : cible"),
    (["enrole"], "acp-poste : commande refusée : argument commande : choix invalide : 'enrole' (choix possibles : "
                 "servir, enroler"),
    (["journal", "--lignes", "x"], "argument --lignes : valeur invalide (int attendu) : 'x'"),
    (["releve", "--inconnu"], "acp-poste : commande refusée : arguments non reconnus : --inconnu"),
])
def test_saisie_erronee_refusee_en_francais(capsys, argv, attendu):
    """Relecture de P5 : les erreurs de saisie répondaient en anglais (« error: the following arguments are
    required »). Code 2 comme avant, message et utilisation en français ; argparse est rendu à l'anglais après."""
    import argparse

    with pytest.raises(SystemExit) as refus:
        main(argv)
    erreur = capsys.readouterr().err
    assert refus.value.code == 2 and attendu in erreur and erreur.startswith("utilisation : acp-poste")
    assert "error" not in erreur and "usage" not in erreur and "required" not in erreur
    assert argparse._("usage: ") == "usage: "


def test_aide_en_francais(capsys):
    with pytest.raises(SystemExit) as fin:
        main(["-h"])
    sortie = capsys.readouterr().out
    assert fin.value.code == 0 and sortie.startswith("utilisation : acp-poste")
    assert "arguments positionnels :" in sortie and "afficher cette aide et quitter" in sortie
    assert "show this help" not in sortie and "positional arguments" not in sortie


def test_journal_absent_puis_present(poste, capsys):
    contexte = poste.contexte()
    assert main(["journal"], contexte=contexte) == 0
    assert capsys.readouterr().out.strip() == "Aucun journal : le service n'a encore rien écrit."
    Journal(poste.emplacements.journal).ecrire("info", "essai", "Ligne de test.")
    assert main(["journal", "--lignes", "5"], contexte=contexte) == 0
    assert json.loads(capsys.readouterr().out)["message"] == "Ligne de test."


def test_oublier_jeton(poste, capsys):
    contexte = poste.contexte()
    assert main(["oublier-jeton"], contexte=contexte) == 0
    assert "Aucun jeton machine" in capsys.readouterr().out
    poste.coffre.ecrire("jeton-machine", "acpm_" + "a" * 43)
    poste.emplacements.machine.parent.mkdir(parents=True, exist_ok=True)
    poste.emplacements.machine.write_text("{}", encoding="utf-8")
    assert main(["oublier-jeton"], contexte=contexte) == 0
    assert "effacé" in capsys.readouterr().out
    assert poste.coffre.lire("jeton-machine") is None and not poste.emplacements.machine.exists()


def test_configuration_invalide_refusee_en_francais(poste, capsys):
    poste.ecrire_politique(poste.toml(sections={"hermes": {"origine": "http://127.0.0.1:9119"}}))
    for commande in (["releve"], ["quotas"], ["enroler", "--code-stdin"], ["connexion", "codex"]):
        assert main(commande, contexte=poste.contexte()) == 2
        erreur = capsys.readouterr().err
        assert erreur.startswith("Configuration du poste refusée : poste.toml : [hermes] origine doit être une origine "
                                 "HTTPS")


def test_quotas_sans_accord_rien_n_est_lance(poste, capsys, tmp_path):
    enregistrement = tmp_path / "codex.jsonl"
    poste.scenario_codex = {"enregistrer": str(enregistrement)}
    poste.ecrire_politique(poste.toml(sections={"sondes": {"codex": False, "claude": False}}))
    assert main(["quotas"], contexte=poste.contexte()) == 2
    sortie = capsys.readouterr()
    assert sortie.out == "" and "aucune sonde autorisée par poste.toml" in sortie.err
    assert not enregistrement.exists()


def test_quotas_sources_absentes_sans_invention(poste, capsys):
    """Exécutables absents : chaque voie dit son état, aucune valeur inventée."""
    poste.ecrire_politique(poste.toml(sections={"codex": {"executable": str(poste.racine / "absent" / "codex.exe")},
                                                "claude": {"executable": str(poste.racine / "absent" / "claude.exe")}}))
    contexte = poste.contexte()
    contexte.lanceurs = {}
    assert main(["quotas"], contexte=contexte) == 0
    rapport = json.loads(capsys.readouterr().out)
    assert rapport["poste-codex"]["etat"] == "cli_absente" and rapport["poste-codex"]["compteurs"] == []
    assert rapport["poste-claude"]["etat"] == "cli_absente"


def test_releve_imprime_un_inventaire_au_contrat(poste, capsys):
    poste.ecrire_politique()
    poste.preparer_profil_codex()
    assert main(["releve"], contexte=poste.contexte()) == 0
    inventaire = valider_inventaire(json.loads(capsys.readouterr().out))
    assert {r.voie for r in inventaire.releves} == {"poste-codex", "poste-claude"}
    assert inventaire.connexions.claude == "jeton_absent"


def test_releve_publier_exige_l_enrolement(poste, capsys):
    poste.ecrire_politique()
    poste.preparer_profil_codex()
    assert main(["releve", "--publier"], contexte=poste.contexte()) == 2
    assert "Poste non enrôlé" in capsys.readouterr().err


def test_servir_non_enrole_code_0_une_ligne_par_jour(poste, capsys):
    poste.ecrire_politique()
    contexte = poste.contexte()
    from acp_poste.chemins import commande_poste

    assert main(["servir"], contexte=contexte) == 0
    assert f"Poste non enrôlé : lancez « {commande_poste('enroler')} »" in capsys.readouterr().err
    assert main(["servir"], contexte=contexte) == 0
    lignes = (poste.emplacements.journal / "poste.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum(json.loads(l)["evenement"] == "non_enrole" for l in lignes) == 1


def test_les_commandes_citees_aux_consoles_sont_executables_telles_quelles(poste, capsys):
    """Relecture de P5 : « acp-poste enroler » n'est reconnu par aucune console (dossier hors du PATH), et un chemin
    entre guillemets sans « & » est une erreur d'analyse de PowerShell. Les messages imprimés dans la console du
    compte citent la forme exécutable (décision D68)."""
    from acp_poste import enrolement, protocole, service
    from acp_poste.chemins import commande_poste

    forme = commande_poste("enroler")
    if sys.platform.startswith("linux"):
        # Étape P6 : sur l'exécutant Linux, l'enveloppe /usr/local/bin/acp-poste est sur le PATH de railway ssh.
        assert forme == "acp-poste enroler"
    else:
        assert forme.startswith("& '") and forme.endswith(r"\ACP\poste\acp-poste.cmd' enroler")
    assert f"« {forme} »" in service.NON_ENROLE
    assert f"« {commande_poste('oublier-jeton')} »" in service.JETON_ILLISIBLE
    assert f"« {commande_poste('enroler --remplacer')} »" in enrolement.DEJA_ENROLE.format(empreinte="AAAA-BBBB")
    assert f"« {commande_poste('enroler --remplacer')} »" in protocole.JETON_REFUSE
    if not sys.platform.startswith("linux"):
        for message in (service.NON_ENROLE, service.JETON_ILLISIBLE, protocole.JETON_REFUSE):
            assert "« acp-poste " not in message
    poste.ecrire_politique()
    poste.preparer_profil_codex()
    assert main(["releve", "--publier"], contexte=poste.contexte()) == 2
    assert f"Poste non enrôlé : lancez « {forme} » avant de publier." in capsys.readouterr().err


def test_servir_compte_dedie_different_refuse(poste, capsys):
    poste.ecrire_politique(poste.toml(compte="dedie"))
    assert main(["servir"], contexte=poste.contexte(compte_courant=lambda: "Paul")) == 2
    assert "doit tourner sous « acp-poste »" in capsys.readouterr().err


def test_servir_compte_dedie_refuse_un_interpreteur_modifiable(poste, capsys, monkeypatch):
    """Relecture de P5 (D67) : le service détient les jetons déchiffrés ; si le compte du poste peut écrire dans le
    site-packages de l'interpréteur (un .pth s'y exécute même sous -I), il refuse de démarrer (code 2), sans chemin
    dans le message, avant de lire le coffre."""
    import sysconfig
    from pathlib import Path

    from acp_poste import politique as module

    site = Path(sysconfig.get_paths()["purelib"])
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: (
        "ouvert" if dossier and Path(cible) == site and acces == module.FILE_ADD_FILE else "refuse"))
    poste.coffre.valeurs["jeton-machine"] = "illisible-mais-jamais-lu"
    poste.ecrire_politique(poste.toml(compte="dedie"))
    assert main(["servir"], contexte=poste.contexte(compte_courant=lambda: "acp-poste")) == 2
    erreur = capsys.readouterr().err
    assert "Interpréteur Python ou bibliothèques du poste modifiables par le compte du poste (site-packages : " \
           "FILE_ADD_FILE (dossier))" in erreur and "décision D67" in erreur
    assert str(site) not in erreur and ":\\" not in erreur
    journal = (poste.emplacements.journal / "poste.jsonl").read_text(encoding="utf-8")
    assert "demarrage_refuse" in journal and "jeton_illisible" not in journal


@pytest.mark.skipif(os.name == "nt", reason="sous Windows, les emplacements réels existent (jamais lus ici)")
def test_systeme_non_pris_en_charge_refuse(capsys, monkeypatch):
    # Étape P6 : Windows (poste) et Linux (exécutant) ont leurs emplacements ; tout autre système est refusé, sans
    # emplacement par défaut.
    monkeypatch.setattr(sys, "platform", "darwin")
    assert main(["diagnostic"]) == 2
    assert "non pris en charge" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "posix", reason="coffre en fichiers 0600 : Linux seulement")
def test_contexte_linux_par_defaut_sans_toucher_le_disque(monkeypatch):
    from acp_poste.contexte import Contexte
    from acp_poste.plateforme.linux import CoffreFichiers, EmplacementsLinux

    monkeypatch.setattr(sys, "platform", "linux")
    contexte = Contexte.du_compte()
    assert contexte.plateforme == "linux"
    assert isinstance(contexte.emplacements, EmplacementsLinux) and isinstance(contexte.coffre, CoffreFichiers)
    assert contexte.emplacements.politique.as_posix() == "/etc/acp/executant.toml"
    assert {outil: i.uid for outil, i in contexte.identites.items()} == {"codex": 10001, "claude": 10002}


def test_connexion_claude_masquee(poste, capsys, monkeypatch):
    from acp_poste import connexions

    poste.ecrire_politique()
    invites = []
    monkeypatch.setattr(connexions.getpass, "getpass", lambda invite: invites.append(invite) or "sk-ant-oat01-" + "j" * 30)
    assert main(["connexion", "claude"], contexte=poste.contexte()) == 0
    sortie = capsys.readouterr().out
    assert "Jeton Claude enregistré (DPAPI)." in sortie and "sk-ant" not in sortie
    assert invites and "saisie masquée" in invites[0]
    assert poste.coffre.lire("jeton-claude").startswith("sk-ant-oat01-")
    monkeypatch.setattr(connexions.getpass, "getpass", lambda _i: "avec espace")
    assert main(["connexion", "claude"], contexte=poste.contexte()) == 2


def test_gestes_du_compte_du_poste_refuses_dans_un_autre_compte(poste, capsys, monkeypatch):
    """Mode dédié : enrôlement, connexions et preuve ne se font que dans le compte du poste (sinon jeton, profil et
    coffre atterriraient dans le profil d'un autre compte, où le service ne les trouverait jamais)."""
    from acp_poste import connexions

    monkeypatch.setattr(connexions.getpass, "getpass", lambda _i: pytest.fail("aucune saisie dans le mauvais compte"))
    poste.ecrire_politique(poste.toml(compte="dedie"))
    for commande in (["enroler", "--code-stdin"], ["connexion", "claude"], ["connexion", "codex"],
                     ["connexion", "bac-a-sable"], ["preuve", "model-list"]):
        assert main(commande, contexte=poste.contexte(compte_courant=lambda: "Paul")) == 2
        assert "doit tourner sous « acp-poste »" in capsys.readouterr().err
    assert poste.coffre.valeurs == {}


def test_connexion_bac_a_sable_refusee_hors_console(poste, capsys, tmp_path):
    enregistrement = tmp_path / "codex.jsonl"
    poste.scenario_codex = {"enregistrer": str(enregistrement)}
    poste.ecrire_politique()
    assert main(["connexion", "bac-a-sable"], contexte=poste.contexte()) == 2
    assert "hors d'une console interactive" in capsys.readouterr().err
    assert not enregistrement.exists()


def test_connexion_bac_a_sable_interactive_sans_cwd(poste, capsys, tmp_path):
    """Console interactive : setupStart {mode: elevated} SANS cwd, attente de setupCompleted ; en mode propriétaire,
    le poste dit qu'il ne vérifie pas les droits (jamais un « droits relus » qui n'a pas eu lieu)."""
    from acp_poste.connexions import connexion_bac_a_sable
    from acp_poste.politique import charger

    enregistrement = tmp_path / "codex.jsonl"
    poste.scenario_codex = {"enregistrer": str(enregistrement)}
    poste.ecrire_politique()
    contexte = poste.contexte()
    assert connexion_bac_a_sable(contexte, charger(poste.emplacements), interactif=True, delai_s=30) == 0
    sortie = capsys.readouterr().out
    assert "Installation élevée du bac à sable terminée" in sortie and "ne sont pas vérifiés" in sortie
    demandes = [json.loads(l) for l in enregistrement.read_text(encoding="utf-8").splitlines()]
    assert [d["params"] for d in demandes if d.get("method") == "windowsSandbox/setupStart"] == [{"mode": "elevated"}]


def test_connexion_codex_ecrit_le_profil_puis_lance_la_connexion(poste, capsys, tmp_path):
    enregistrement = tmp_path / "codex.jsonl"
    poste.scenario_codex = {"enregistrer": str(enregistrement)}
    poste.ecrire_politique()
    assert main(["connexion", "codex"], contexte=poste.contexte()) == 0
    assert "config.toml du profil Codex écrit par le poste." in capsys.readouterr().out
    argv = [json.loads(l)["argv"] for l in enregistrement.read_text(encoding="utf-8").splitlines()]
    assert argv == [["-c", 'cli_auth_credentials_store="keyring"', "login", "--device-auth"]]
    home = poste.emplacements.acp_local / "codex-home"
    (home / "config.toml").write_text("model = 'x'\n", encoding="utf-8")
    assert main(["connexion", "codex"], contexte=poste.contexte()) == 2
    assert "modifié hors du poste" in capsys.readouterr().err


def test_sonde_plateforme_refusee_hors_linux(poste, capsys):
    assert main(["sonde-plateforme", "--json"], contexte=poste.contexte()) == 2
    assert "exécutant Linux" in capsys.readouterr().err
