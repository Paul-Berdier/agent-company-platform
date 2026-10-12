"""Contrat de coffre borné : aucune commande ni chemin hôte dans le transport."""
import hashlib
from uuid import uuid4

import pytest
from acp_poste_contrat import coffre as c
from acp_poste_contrat.motifs_secrets import motif_trouve


@pytest.mark.parametrize("chemin", ["/secret.md", "../secret.md", "a/../b.md", "C:/x.md", "a\\b.md", ".obsidian/a.md",
    "a/.cache/b.md", "a//b.md", "CON.md", "dir/AUX.txt/a.md", "fichier.md:secret", "a /b.md", "a.txt", "e\u0301.md"])
def test_chemins_hors_coffre_refuses(chemin):
    with pytest.raises(ValueError):
        c.chemin_relatif(chemin)


@pytest.mark.parametrize("action,parametres", [("shell", {"commande": "echo x"}), ("lire", {"chemin": "note.md", "script": "x"}),
    ("ecrire", {"chemin": "note.md", "contenu": "x"}), ("lister", {"limite": True}), ("lister", {"limite": 201}),
    ("creer", {"chemin": "note.md", "contenu": "x\0y"}), ("creer", {"chemin": "note.md", "contenu": "é" * 65537}),
    ("renommer", {"chemin": "a.md", "destination": "A.md", "empreinte_attendue": "0"*64})])
def test_parametres_inconnus_ou_non_bornes(action, parametres):
    with pytest.raises(ValueError):
        c.DemandeOperation(id_operation=str(uuid4()), coffre_id=str(uuid4()), action=action, parametres=parametres)


def test_texte_et_enveloppe_ont_deux_bornes():
    ids = dict(id_operation=str(uuid4()), coffre_id=str(uuid4()), action="creer")
    c.DemandeOperation(**ids, parametres={"chemin":"Équipe/note.md", "contenu":"é" * 65536})
    with pytest.raises(ValueError):
        c.DemandeOperation(**ids, parametres={"chemin":"a.md", "contenu":"\t" * 131072})


def test_lecture_verifie_contenu_hash_taille():
    data = {"chemin":"a.md", "contenu":"Bonjour", "empreinte":hashlib.sha256(b"Bonjour").hexdigest(), "octets":7}
    c.resultat_valide("lire", data)
    for changement in ({"octets":8}, {"empreinte":"0" * 64}, {"chemin":"../a.md"}):
        with pytest.raises(ValueError):
            c.resultat_valide("lire", dict(data, **changement))


def test_resultat_ne_fabrique_pas_de_succes():
    ids = dict(protocole=c.PROTOCOLE, id_operation=str(uuid4()), coffre_id=str(uuid4()))
    for champs in ({"etat":"reussie"}, {"etat":"refusee", "resultat":{}}, {"etat":"indeterminee"},
                   {"etat":"reussie", "resultat":{}, "erreur":{"code":"x", "message":"x"}}):
        with pytest.raises(ValueError):
            c.Resultat(**ids, **champs)
    c.Resultat(**ids, etat="refusee", erreur={"code":"conflit", "message":"Relisez la note."})


def test_renommage_ne_promet_pas_reecriture_et_ecriture_peut_archiver():
    r={"chemin":"a.md", "destination":"b.md", "liens_modifies":False}
    c.resultat_valide("renommer", r)
    with pytest.raises(ValueError):
        c.resultat_valide("renommer", dict(r, liens_modifies=True))
    c.resultat_valide("ecrire", {"chemin":"a.md", "empreinte":"0"*64,"octets":0,"archive_id":str(uuid4())})


def test_jetons_coffre_sont_masquables_par_la_liste_partagee():
    for prefix in ("acpct_", "acpce_"):
        assert motif_trouve(prefix + "A"*43)
