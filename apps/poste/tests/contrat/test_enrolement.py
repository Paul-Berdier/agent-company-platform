"""Enrôlement du poste (cahier P5 § 5.1, décisions D48 et D49) contre le faux Hermes."""

from __future__ import annotations

import io
import json

from acp_poste import cli
from acp_poste.enrolement import enroler
from acp_poste.jeton import Jeton
from acp_poste.journal import NOM
from acp_poste.politique import charger


def preparer(poste, hermes):
    poste.origine = hermes.origine
    poste.options = hermes.options_client()
    poste.ecrire_politique()
    return poste.contexte()


def test_code_lu_masque_jamais_journalise(poste, hermes, capsys):
    contexte = preparer(poste, hermes)
    code = hermes.creer_code()
    invites = []
    politique = charger(poste.emplacements)
    assert enroler(contexte, politique, contexte.journal(politique), code_stdin=False, remplacer=False,
                   lire_code=lambda invite: invites.append(invite) or code) == 0
    assert invites == ["Code d'enrôlement (collé, saisie masquée) : "]
    sortie = capsys.readouterr()
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    jeton = poste.coffre.lire("jeton-machine")
    for texte in (sortie.out, sortie.err, journal):
        assert code not in texte and jeton not in texte and "acpe_" not in texte and "acpm_" not in texte


def test_jeton_range_au_coffre(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 0
    machine_id, ligne = hermes.machine()
    jeton = poste.coffre.lire("jeton-machine")
    assert ligne["empreinte_jeton"] == __import__("hashlib").sha256(jeton.encode()).hexdigest()
    identite = json.loads(poste.emplacements.machine.read_text(encoding="utf-8"))
    assert identite == {"machine_id": machine_id, "empreinte": Jeton(jeton).empreinte,
                        "enrole_le": identite["enrole_le"]}
    assert "jeton" not in json.dumps(identite).lower().replace("empreinte", "")


def test_empreinte_affichee(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 0
    _, ligne = hermes.machine()
    sortie = capsys.readouterr().out
    assert f"Empreinte : {ligne['empreinte']}" in sortie and "Confirmer" in sortie


def test_deja_enrole_refuse_sans_remplacer(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 0
    premier = poste.coffre.lire("jeton-machine")
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 2
    assert "Poste déjà enrôlé" in capsys.readouterr().err and poste.coffre.lire("jeton-machine") == premier
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin", "--remplacer"], contexte=contexte) == 0
    assert poste.coffre.lire("jeton-machine") != premier


def test_401_message_code_expire(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    code = hermes.creer_code(validite_s=-1)
    monkeypatch.setattr("sys.stdin", io.StringIO(code + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 2
    assert capsys.readouterr().err.strip() == ("Code d'enrôlement refusé : inconnu, expiré ou déjà utilisé. Générez-en "
                                               "un nouveau depuis la page Poste.")
    assert poste.coffre.lire("jeton-machine") is None
    utilise = hermes.creer_code()
    monkeypatch.setattr("sys.stdin", io.StringIO(utilise + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 0
    poste.coffre.effacer("jeton-machine")
    monkeypatch.setattr("sys.stdin", io.StringIO(utilise + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 2, "code à usage unique"


def test_code_au_format_invalide(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    monkeypatch.setattr("sys.stdin", io.StringIO("acpe_trop-court\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 2
    erreur = capsys.readouterr().err
    assert "format invalide" in erreur and "trop-court" not in erreur
    assert hermes.requetes == [], "rien n'est envoyé pour un code mal formé"


def test_poste_deja_enrole_cote_hermes(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=contexte) == 0
    hermes.confirmer(hermes.machine()[0])
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin", "--remplacer"], contexte=contexte) == 2
    assert "Un poste est déjà enrôlé" in capsys.readouterr().err
