"""Coffres jetables ; aucune note personnelle ni application Obsidian ouverte."""
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest

from acp_poste.obsidian import CoffreNotes, RefusNotes, chemin_note, creer_coffre, NOTE_MAX

@pytest.fixture
def coffre(tmp_path):
    root = tmp_path / "Coffre ACP"
    return CoffreNotes(root, creer_coffre(root))


def demande(c, action, **params):
    return {"id_operation": str(uuid4()), "coffre_id": c.coffre_id, "action": action,
            "parametres": params, "expire_le": int(time.time()) + 600}


def execute(c, action, **params):
    return c.executer(demande(c, action, **params))


def test_coffre_neuf_refuse_existant_et_mauvais_id(coffre):
    with pytest.raises(FileExistsError):
        creer_coffre(coffre.racine)
    with pytest.raises(RefusNotes):
        CoffreNotes(coffre.racine, str(uuid4()))
    result = execute(coffre, "lister")
    assert result["etat"] == "reussie", result
    assert [n["chemin"] for n in result["resultat"]["notes"]] == ["Accueil.md", "Journal.md", "Projets.md"]


@pytest.mark.parametrize("path", ["../hors.md", "/hors.md", "C:/hors.md", "C:hors.md", r"\\serveur\hors.md",
                                    "a/../hors.md", "a//b.md", "a\\b.md", ".obsidian/data.md", ".git/x.md",
                                    "NUL.md", "con.txt.md", "COM¹.md", "x.md:secret", "a./b.md", "x.txt"])
def test_chemins_refuses(path):
    with pytest.raises(RefusNotes):
        chemin_note(path)


def test_crud_conflit_archive_et_rejeu(coffre):
    op = demande(coffre, "creer", chemin="Dossier/épreuve.md", contenu="Ancien\n")
    created = coffre.executer(op)
    assert created["etat"] == "reussie", created
    assert coffre.executer(op) == created
    different = dict(op, parametres={"chemin": "Dossier/autre.md", "contenu": "Surprise"})
    assert coffre.executer(different)["erreur"]["code"] == "conflit"
    old = execute(coffre, "lire", chemin="Dossier/épreuve.md")["resultat"]
    conflict = execute(coffre, "ecrire", chemin=old["chemin"], contenu="Perdu", empreinte_attendue="0" * 64)
    assert conflict["erreur"]["code"] == "conflit"
    assert (coffre.racine / old["chemin"]).read_text(encoding="utf-8") == "Ancien\n"
    saved = execute(coffre, "ecrire", chemin=old["chemin"], contenu="Nouveau\n", empreinte_attendue=old["empreinte"])
    assert saved["etat"] == "reussie", saved
    archive = coffre.racine / ".acp" / "archives" / (saved["resultat"]["archive_id"] + ".md")
    assert archive.read_text(encoding="utf-8") == "Ancien\n"
    archived = execute(coffre, "archiver", chemin=old["chemin"], empreinte_attendue=saved["resultat"]["empreinte"])
    assert archived["etat"] == "reussie", archived
    assert not (coffre.racine / old["chemin"]).exists()
    assert (coffre.racine / ".acp" / "archives" / (archived["resultat"]["archive_id"] + ".md")).read_text(encoding="utf-8") == "Nouveau\n"


def test_renommer_sans_ecraser_ni_promettre_reecriture(coffre):
    read = execute(coffre, "lire", chemin="Journal.md")["resultat"]
    collision = execute(coffre, "renommer", chemin="Journal.md", destination="Projets.md", empreinte_attendue=read["empreinte"])
    assert collision["etat"] != "reussie"
    moved = execute(coffre, "renommer", chemin="Journal.md", destination="Sous/Journal.md", empreinte_attendue=read["empreinte"])
    assert moved["etat"] == "reussie", moved
    assert moved["resultat"]["liens_modifies"] is False
    assert not (coffre.racine / "Journal.md").exists()
    assert (coffre.racine / "Sous" / "Journal.md").exists()


def test_liens_recherche_et_bornes(coffre):
    assert execute(coffre, "creer", chemin="Essai.md", contenu="[[Projets]]\n[Journal](Journal.md)\n[[Absent]]\n`[[Ignore]]`\nTexte unique\n")["etat"] == "reussie"
    graph = execute(coffre, "graphe")["resultat"]
    assert {"source": "Essai.md", "cible": "Projets.md"} in graph["liens"]
    assert {"source": "Essai.md", "cible": "Journal.md"} in graph["liens"]
    assert {"source": "Essai.md", "cible": "Absent"} in graph["non_resolus"]
    assert not any(x["cible"] == "Ignore" for x in graph["non_resolus"])
    back = execute(coffre, "backlinks", chemin="Projets.md")["resultat"]
    assert any(x["source"] == "Essai.md" for x in back["liens"])
    search = execute(coffre, "rechercher", texte="UNIQUE")["resultat"]
    assert search["resultats"] == [{"chemin": "Essai.md", "ligne": 5, "extrait": "Texte unique"}]
    assert execute(coffre, "lister", limite=1)["resultat"]["tronque"] is True
    assert execute(coffre, "creer", chemin="Gros.md", contenu="é" * NOTE_MAX)["erreur"]["code"] == "trop_volumineux"
    assert not (coffre.racine / "Gros.md").exists()


def test_hardlink_refuse_sans_toucher_original(coffre, tmp_path):
    outside = tmp_path / "hors.md"
    outside.write_text("ne pas toucher", encoding="utf-8")
    os.link(outside, coffre.racine / "Lie.md")
    result = execute(coffre, "ecrire", chemin="Lie.md", contenu="danger", empreinte_attendue=hashlib.sha256(outside.read_bytes()).hexdigest())
    assert result["etat"] != "reussie"
    assert outside.read_text(encoding="utf-8") == "ne pas toucher"
    assert execute(coffre, "lister")["etat"] != "reussie"


def test_symlink_refuse(coffre, tmp_path):
    outside = tmp_path / "ailleurs"
    outside.mkdir()
    (outside / "secret.md").write_text("ne pas lire", encoding="utf-8")
    try:
        (coffre.racine / "Lien").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Création de symlink indisponible pour ce compte de test")
    assert execute(coffre, "lire", chemin="Lien/secret.md")["etat"] != "reussie"
    assert execute(coffre, "creer", chemin="Lien/nouveau.md", contenu="non")["etat"] != "reussie"
    assert not (outside / "nouveau.md").exists()


def test_expiration_et_ancien_traitement_ne_rejouent_pas(coffre):
    op = demande(coffre, "creer", chemin="Expire.md", contenu="non")
    op["expire_le"] = int(time.time()) - 1
    assert coffre.executer(op)["erreur"]["code"] == "expiree"
    assert not (coffre.racine / "Expire.md").exists()
    op = demande(coffre, "creer", chemin="Interrompu.md", contenu="non")
    digest = hashlib.sha256(json.dumps(op, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    (coffre.racine / ".acp" / "operations" / (op["id_operation"] + ".json")).write_text(json.dumps({"demande": digest}))
    assert coffre.executer(op)["etat"] == "indeterminee"
    assert not (coffre.racine / "Interrompu.md").exists()


@pytest.mark.skipif(os.name != "nt", reason="preuve de partage obligatoire Windows")
def test_handle_note_interdit_modification_concurrente(coffre):
    from acp_poste.obsidian_fichiers import fichier_epingle
    path = coffre.racine / "Journal.md"
    with fichier_epingle(path, ecriture=True):
        with pytest.raises(OSError):
            path.write_text("changement concurrent", encoding="utf-8")
        with pytest.raises(OSError):
            path.unlink()


@pytest.mark.skipif(os.name != "nt", reason="preuve de partage obligatoire Windows")
def test_dossier_epingle_interdit_remplacement(coffre):
    from acp_poste.obsidian_fichiers import dossier_epingle
    with dossier_epingle(coffre.racine):
        with pytest.raises(OSError):
            coffre.racine.rename(coffre.racine.with_name("remplace"))


@pytest.mark.skipif(os.name != "nt", reason="jonction Windows")
def test_jonction_refusee_sans_privilege_symlink(coffre, tmp_path):
    import subprocess
    outside = tmp_path / "ailleurs"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("conservé", encoding="utf-8")
    junction = coffre.racine / "Jonction"
    result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    try:
        assert execute(coffre, "lire", chemin="Jonction/secret.md")["etat"] != "reussie"
        assert execute(coffre, "creer", chemin="Jonction/nouveau.md", contenu="non")["etat"] != "reussie"
        assert execute(coffre, "lister")["etat"] != "reussie"
        assert secret.read_text(encoding="utf-8") == "conservé"
        assert not (outside / "nouveau.md").exists()
    finally:
        junction.rmdir()  # Retire seulement la jonction créée ici, jamais sa cible.


def test_erreur_apres_mutation_est_indeterminee(coffre, monkeypatch):
    original = coffre._action
    def panne(action, params, identifiant):
        result = original(action, params, identifiant)
        raise OSError("panne après effet")
    monkeypatch.setattr(coffre, "_action", panne)
    op = demande(coffre, "creer", chemin="Effectue.md", contenu="conservé")
    result = coffre.executer(op)
    assert result["etat"] == "indeterminee"
    assert (coffre.racine / "Effectue.md").read_text(encoding="utf-8") == "conservé"
    monkeypatch.setattr(coffre, "_action", original)
    assert coffre.executer(op) == result



def test_resultat_prouve_rejoue_meme_apres_echeance(coffre, monkeypatch):
    op = demande(coffre, "creer", chemin="Preuve.md", contenu="une seule fois")
    result = coffre.executer(op)
    assert result["etat"] == "reussie"
    monkeypatch.setattr("acp_poste.obsidian.time.time", lambda: op["expire_le"] + 10)
    assert coffre.executer(op) == result


def test_preuve_corrompue_ne_promet_pas_absence_effet(coffre):
    op = demande(coffre, "creer", chemin="Preuve.md", contenu="une seule fois")
    assert coffre.executer(op)["etat"] == "reussie"
    path = coffre.racine / ".acp" / "operations" / (op["id_operation"] + ".json")
    path.write_bytes(b'{"demande":')
    assert coffre.executer(op)["etat"] == "indeterminee"
    assert (coffre.racine / "Preuve.md").read_text(encoding="utf-8") == "une seule fois"



@pytest.mark.skipif(os.name != "nt", reason="course hardlink Windows")
def test_hardlink_ajoute_apres_cas_ne_recoit_pas_nouvelle_version(coffre, tmp_path, monkeypatch):
    from acp_poste import obsidian
    note = execute(coffre, "lire", chemin="Journal.md")["resultat"]
    outside = tmp_path / "copie-liee.md"
    initial = (coffre.racine / "Journal.md").read_bytes()
    original = obsidian.renommer_handle
    added = False
    def ajouter_lien(stream, source, destination, parent):
        nonlocal added
        if source.name == "Journal.md" and not added:
            os.link(source, outside)
            added = True
        return original(stream, source, destination, parent)
    monkeypatch.setattr(obsidian, "renommer_handle", ajouter_lien)
    result = execute(coffre, "ecrire", chemin="Journal.md", contenu="Nouvelle version", empreinte_attendue=note["empreinte"])
    assert result["etat"] == "reussie", result
    assert added
    assert outside.read_bytes() == initial
    assert (coffre.racine / "Journal.md").read_text(encoding="utf-8") == "Nouvelle version"



def test_motif_secret_lu_pas_duplique_dans_preuves(coffre):
    secret = "sk-" + "X" * 32
    (coffre.racine / "Prive.md").write_text(secret, encoding="utf-8")
    result = execute(coffre, "lire", chemin="Prive.md")
    assert result["etat"] == "refusee"
    assert result["erreur"]["code"] == "secret"
    assert secret not in json.dumps(result)
    assert all(secret not in p.read_text(encoding="utf-8") for p in (coffre.racine / ".acp" / "operations").glob("*.json"))
    refused = execute(coffre, "creer", chemin="Nouvelle.md", contenu=secret)
    assert refused["erreur"]["code"] == "secret"
    assert not (coffre.racine / "Nouvelle.md").exists()


def test_note_locale_trop_grosse_et_lien_long_restent_au_contrat(coffre):
    from acp_poste_contrat.coffre import resultat_valide
    (coffre.racine / "Gros.md").write_text("a" * (NOTE_MAX + 1), encoding="utf-8")
    assert execute(coffre, "lister")["erreur"]["code"] == "trop_volumineux"
    (coffre.racine / "Gros.md").unlink()
    execute(coffre, "creer", chemin="Liens.md", contenu="[[" + "a" * 700 + "]]")
    result = execute(coffre, "graphe")
    assert result["etat"] == "reussie"
    assert result["resultat"]["tronque"] is True
    resultat_valide("graphe", result["resultat"])



def test_liens_relatifs_normalises_dans_coffre(coffre):
    assert execute(coffre, "creer", chemin="Sous/Note.md", contenu="[Accueil](../Accueil.md)\n[Hors](../../hors.md)")["etat"] == "reussie"
    graph = execute(coffre, "graphe")["resultat"]
    assert {"source": "Sous/Note.md", "cible": "Accueil.md"} in graph["liens"]
    assert {"source": "Sous/Note.md", "cible": "../../hors.md"} in graph["non_resolus"]
    assert {"source": "Sous/Note.md", "cible": "Accueil.md"} in execute(coffre, "backlinks", chemin="Accueil.md")["resultat"]["liens"]



def test_lien_markdown_relatif_prime_sur_homonyme_racine(coffre):
    execute(coffre, "creer", chemin="Note.md", contenu="Racine")
    execute(coffre, "creer", chemin="dossier/Note.md", contenu="Dossier")
    execute(coffre, "creer", chemin="dossier/Source.md", contenu="[Note](Note.md)")
    graph = execute(coffre, "graphe")["resultat"]
    assert {"source": "dossier/Source.md", "cible": "dossier/Note.md"} in graph["liens"]
    assert not any(x["source"] == "dossier/Source.md" for x in graph["non_resolus"])
