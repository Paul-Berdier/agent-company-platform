"""scripts/preuve_accord_requis.py (cahier P7 § 11.3) : le tableau « geste → preuve → verdict » du premier projet sur un
dépôt réel, éprouvé sur des FIXTURES (jamais sur un vrai dépôt) : un relevé conforme, puis chaque écart (référence
poussée, étiquette, palier payant, tâche planifiée, dépôt ajouté, réseau ouvert, revue décidée par un autre que le
propriétaire), chaque preuve manquante (« non prouvé », jamais un succès supposé) et les refus d'utilisation. Aucune
référence ni nom réel du dépôt dans la sortie.

L'inventaire part de l'exemple PARTAGÉ du contrat (``hermes/tests/outils/fixtures_machine/inventaire_requete_linux.json``),
l'export du projet suit la forme réelle de ``GET /v1/projets/<id>`` (``apps/interface/tests/fixtures-projets.ts``), la
tâche du bilan celle du contrat de P7 (``hermes/tests/contrat/test_bilan_contrat.py``)."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("preuve_accord_requis", RACINE / "scripts" / "preuve_accord_requis.py")
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)

NOM_REEL = "proprietaire-reel/outil-interne"


def _sha(texte: str) -> str:
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()


LS_AVANT = (f"From https://github.com/{NOM_REEL}.git\n"
            f"{_sha('main')}\tHEAD\n{_sha('main')}\trefs/heads/main\n{_sha('v1')}\trefs/tags/v1.0.0\n")
INVENTAIRE = json.loads((RACINE / "hermes" / "tests" / "outils" / "fixtures_machine" / "inventaire_requete_linux.json")
                        .read_text(encoding="utf-8"))
INVENTAIRE["depots"] = [{"alias": "outil", "visibilite": "prive", "lecture": "ok", "verifie_le": "2026-10-02T09:00:00Z"}]
for _releve in INVENTAIRE["releves"]:
    _releve["depots"] = copy.deepcopy(INVENTAIRE["depots"])
PROJET = {"projet": {
    "id": "p_367e23fd51b7", "titre": "Outil", "tableau": "acp-outil-3dd5", "etat": "termine", "depot": "outil",
    "cartes": [
        {"carte": "t_7aa28f61", "role": "exploration", "voie": "poste-claude", "statut": "done", "palier": "default"},
        {"carte": "t_342c81eb", "role": "planification", "voie": "hermes", "statut": "done", "palier": "default"},
        {"carte": "t_5e6f7a8b", "role": "implementation", "voie": "poste-claude", "statut": "done",
         "palier": "default"},
        {"carte": "t_9a8b7c6d", "role": "integration", "voie": "poste-integration", "statut": "done", "palier": None},
    ],
    "journal": [
        {"quand": 1790423100, "acteur": "poste:m3b7783ebfe4", "action": "carte_terminee", "cible": "t_9a8b7c6d",
         "detail": None},
        {"quand": 1790423090, "acteur": "proprietaire:proprietaire-test", "action": "revue_acceptee",
         "cible": "t_5e6f7a8b", "detail": None},
        {"quand": 1790423080, "acteur": "poste:m3b7783ebfe4", "action": "carte_en_revue", "cible": "t_5e6f7a8b",
         "detail": "{\"chemins\": [\"AGENTS.md\"]}"},
        {"quand": 1790423039, "acteur": "proprietaire:proprietaire-test", "action": "lancement",
         "cible": "acp-outil-3dd5", "detail": "{\"origine\": \"tableau_de_bord\", \"depot\": \"outil\"}"},
    ],
}}
BILAN = {"id": "c0ffee12", "name": "Bilan ACP", "schedule": "0 8 * * *", "prompt": "", "no_agent": True,
         "script": "acp-bilan.py", "deliver": "local", "next_run_at": "2026-10-03T08:00:00+02:00"}


class Pieces:
    """Les six pièces d'un relevé conforme, écrites dans ``tmp_path`` ; chaque test en altère une."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier
        self.contenus = {"avant": LS_AVANT, "apres": LS_AVANT, "projet": copy.deepcopy(PROJET),
                         "cron": {"jobs": [dict(BILAN)]}, "inventaire-avant": copy.deepcopy(INVENTAIRE),
                         "inventaire-apres": {"inventaire": {"contenu": copy.deepcopy(INVENTAIRE)}}}

    def argv(self, *extra: str) -> list[str]:
        argv = ["--alias", "outil", "--nom-depot", NOM_REEL]
        for nom, contenu in self.contenus.items():
            chemin = self.dossier / f"{nom}.{'txt' if isinstance(contenu, str) else 'json'}"
            chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu, ensure_ascii=False),
                              encoding="utf-8")
            argv += [f"--{nom}", str(chemin)]
        return argv + list(extra)


@pytest.fixture
def pieces(tmp_path) -> Pieces:
    return Pieces(tmp_path)


def _lancer(pieces: Pieces, capsys, *extra: str) -> tuple[int, str, str]:
    code = script.main(pieces.argv(*extra))
    sortie = capsys.readouterr()
    return code, sortie.out, sortie.err


def _verdict(sortie: str, geste: str) -> str:
    ligne = next(l for l in sortie.splitlines() if l.startswith(f"| {geste} |"))
    return ligne.rsplit("|", 2)[-2].strip()


GESTES = ("push, PR, fusion, étiquette, publication", "dépense", "suppression (côté dépôt distant)",
          "nouveau dépôt, réseau, compte", "tâche planifiée", "fichiers de pilotage")


def test_releve_conforme_tout_vert_sans_reference_ni_nom_reel(pieces, capsys, tmp_path):
    code, sortie, erreur = _lancer(pieces, capsys, "--sortie", str(tmp_path / "preuves" / "accord-requis-outil.md"))
    assert code == 0, (sortie, erreur)
    assert [_verdict(sortie, g) for g in GESTES] == ["conforme"] * 6
    assert "ls-remote avant 3 référence(s), après 3" in sortie and "identiques" in sortie
    assert "1 passage(s) en revue, 1 décision(s) au journal, toutes du propriétaire" in sortie
    assert "1 tâche(s), dont 1 bilan quotidien" in sortie
    # Aucune référence (ni SHA, ni nom de branche ou d'étiquette) ; le nom réel du dépôt n'apparaît jamais.
    for interdit in (_sha("main"), _sha("v1"), "refs/heads/main", "v1.0.0", NOM_REEL, "proprietaire-reel"):
        assert interdit not in sortie
    assert "Pièces hors outil" in sortie and "Contents: Read-only" in sortie
    ecrit = (tmp_path / "preuves" / "accord-requis-outil.md").read_bytes()
    assert b"\r" not in ecrit and ecrit.decode("utf-8") in sortie


@pytest.mark.parametrize("apres, constat", [
    (LS_AVANT + f"{_sha('pousse')}\trefs/heads/hermes/projet-outil\n", "1 ajoutée(s), 0 retirée(s), 0 déplacée(s)"),
    (LS_AVANT + f"{_sha('v2')}\trefs/tags/v2.0.0\n", "1 ajoutée(s)"),
    (LS_AVANT.replace(f"{_sha('main')}\trefs/heads/main", f"{_sha('fusion')}\trefs/heads/main"),
     "0 ajoutée(s), 0 retirée(s), 1 déplacée(s)"),
    (LS_AVANT.replace(f"{_sha('v1')}\trefs/tags/v1.0.0\n", ""), "0 ajoutée(s), 1 retirée(s)"),
])
def test_references_distantes_changees(pieces, capsys, apres, constat):
    pieces.contenus["apres"] = apres
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1
    assert _verdict(sortie, GESTES[0]) == "NON CONFORME" and constat in sortie
    assert _verdict(sortie, GESTES[2]) == "NON CONFORME"


def test_palier_payant(pieces, capsys):
    pieces.contenus["projet"]["projet"]["cartes"][2]["palier"] = "priority"
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and _verdict(sortie, "dépense") == "NON CONFORME" and "1 carte(s) à un autre palier" in sortie
    pieces.contenus["projet"]["projet"]["cartes"][2]["palier"] = "default"
    pieces.contenus["inventaire-apres"]["inventaire"]["contenu"]["politique"]["paliers_admis"] = ["default", "priority"]
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and _verdict(sortie, "dépense") == "NON CONFORME"


@pytest.mark.parametrize("tache", [
    {"id": "a1", "name": "Veille", "schedule": "0 * * * *", "prompt": "Résume les nouveautés.", "no_agent": False},
    dict(BILAN, monitor_script="surveiller.py"),
    dict(BILAN, no_agent=False),
    dict(BILAN, script="autre.py"),
])
def test_tache_planifiee_autre_que_le_bilan(pieces, capsys, tache):
    pieces.contenus["cron"] = [dict(BILAN), tache] if tache.get("id") != BILAN["id"] else [tache]
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and _verdict(sortie, "tâche planifiée") == "NON CONFORME"


def test_aucune_tache_est_conforme(pieces, capsys):
    pieces.contenus["cron"] = []
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 0 and "0 tâche(s), dont 0 bilan quotidien" in sortie


def test_depot_ajoute_reseau_ouvert_politique_changee(pieces, capsys):
    contenu = pieces.contenus["inventaire-apres"]["inventaire"]["contenu"]
    contenu["depots"].append({"alias": "autre"})
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and _verdict(sortie, "nouveau dépôt, réseau, compte") == "NON CONFORME"
    contenu["depots"].pop()
    contenu["politique"]["reseau_executants"] = True
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and "réseau des agents non fermé" in sortie
    contenu["politique"]["reseau_executants"] = False
    contenu["poste"]["politique_empreinte"] = "9f9f9f9f9f9f"
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and "politique de l'exécutant changée pendant le projet" in sortie


def test_revue_decidee_par_un_autre_que_le_proprietaire(pieces, capsys):
    pieces.contenus["projet"]["projet"]["journal"][1]["acteur"] = "acp-poste:emetteur"
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and _verdict(sortie, "fichiers de pilotage") == "NON CONFORME"


def _ligne(quand: int, acteur: str, action: str, cible: str = "t_5e6f7a8b") -> dict:
    return {"quand": quand, "acteur": acteur, "action": action, "cible": cible, "detail": None}


@pytest.mark.parametrize("ajout, verdict", [
    # Refus du propriétaire, carte corrigée qui REPASSE en revue, seconde décision par un autre acteur.
    ([_ligne(1790423095, "proprietaire:proprietaire-test", "revue_refusee"),
      _ligne(1790423096, "poste:m3b7783ebfe4", "carte_en_revue"),
      _ligne(1790423097, "acp-poste:emetteur", "revue_acceptee")], "NON CONFORME"),
    # Même parcours, seconde revue encore sans décision : jamais « conforme ».
    ([_ligne(1790423095, "proprietaire:proprietaire-test", "revue_refusee"),
      _ligne(1790423096, "poste:m3b7783ebfe4", "carte_en_revue")], "non prouvé"),
    # Seconde revue décidée par le propriétaire : conforme.
    ([_ligne(1790423095, "proprietaire:proprietaire-test", "revue_refusee"),
      _ligne(1790423096, "poste:m3b7783ebfe4", "carte_en_revue"),
      _ligne(1790423097, "proprietaire:proprietaire-test", "revue_acceptee")], "conforme"),
])
def test_revues_successives_rejouees_dans_l_ordre(pieces, capsys, ajout, verdict):
    journal = pieces.contenus["projet"]["projet"]["journal"]
    # L'export est du plus récent au plus ancien : les nouvelles lignes vont en tête.
    pieces.contenus["projet"]["projet"]["journal"] = list(reversed(ajout)) + journal
    _code, sortie, _ = _lancer(pieces, capsys)
    assert _verdict(sortie, "fichiers de pilotage") == verdict


def test_journal_peut_etre_tronque_jamais_conforme(pieces, capsys):
    """L'export ne rend que les 100 dernières lignes : un journal plein peut avoir perdu une revue ancienne."""
    pieces.contenus["projet"]["projet"]["journal"] = [
        _ligne(1790424000 - i, "poste:m3b7783ebfe4", "carte_servie", f"t_{i:08x}") for i in range(100)]
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 3 and _verdict(sortie, "fichiers de pilotage") == "non prouvé" and "peut-être tronqué" in sortie


def test_comptes_connectes_changes_ou_absents(pieces, capsys):
    contenu = pieces.contenus["inventaire-apres"]["inventaire"]["contenu"]
    contenu["connexions"] = dict(contenu["connexions"], codex="cle_api")
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 1 and "comptes connectés changés pendant le projet" in sortie
    del contenu["connexions"]
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 3 and "connexions absentes de l'inventaire" in sortie


def test_alias_absent_de_l_inventaire_sans_plantage(pieces, capsys):
    pieces.contenus["inventaire-apres"]["inventaire"]["contenu"]["depots"].append({"alias": None})
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 0 and _verdict(sortie, "nouveau dépôt, réseau, compte") == "conforme"


def test_preuves_manquantes_jamais_un_succes(pieces, capsys):
    """Revue sans décision, relevé ls-remote vide : « non prouvé », code 3 (aucun écart, preuve incomplète)."""
    del pieces.contenus["projet"]["projet"]["journal"][1]
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 3 and _verdict(sortie, "fichiers de pilotage") == "non prouvé" and "en attente" in sortie
    pieces = Pieces(pieces.dossier)
    pieces.contenus["apres"] = "From https://github.com/x/y.git\n"
    code, sortie, _ = _lancer(pieces, capsys)
    assert code == 3 and _verdict(sortie, GESTES[0]) == "non prouvé" and _verdict(sortie, GESTES[2]) == "non prouvé"


@pytest.mark.parametrize("alterer, message", [
    (lambda p: p.contenus.update(projet="pas du json"), "n'est pas un JSON valide"),
    (lambda p: p.contenus.update(projet={"projet": {"id": "p"}}), "« cartes » absent"),
    (lambda p: p.contenus.update(cron={"jobs": "x"}), "liste de tâches attendue"),
    (lambda p: p.contenus.update({"inventaire-avant": {"poste": {}}}), "Inventaire illisible"),
    (lambda p: p.contenus["projet"]["projet"].update(depot="autre"), "un autre dépôt que « outil »"),
])
def test_pieces_invalides_code_2(pieces, capsys, alterer, message):
    alterer(pieces)
    if pieces.contenus["projet"] == "pas du json":
        argv = pieces.argv()
        (pieces.dossier / "projet.txt").write_text("pas du json", encoding="utf-8")
        argv[argv.index("--projet") + 1] = str(pieces.dossier / "projet.txt")
        code = script.main(argv)
        erreur = capsys.readouterr().err
    else:
        code, _sortie, erreur = _lancer(pieces, capsys)
    assert code == 2 and message in erreur


def test_alias_refuse(pieces, capsys):
    argv = pieces.argv()
    argv[argv.index("--alias") + 1] = "Outil Interne"
    assert script.main(argv) == 2 and "Alias refusé" in capsys.readouterr().err


def test_sortie_controlee_avant_impression():
    """Défense en profondeur : une sortie qui porterait un secret, une adresse ou le nom réel est refusée."""
    jeton = "github_pat_" + "Z" * 40
    with pytest.raises(script.Utilisation, match="secret"):
        script.controler_sortie(f"| x | {jeton} | conforme |", None, "outil")
    with pytest.raises(script.Utilisation, match="adresse"):
        script.controler_sortie("| x | git@github.com | conforme |", None, "outil")
    with pytest.raises(script.Utilisation, match="nom réel"):
        script.controler_sortie(f"| x | {NOM_REEL} | conforme |", NOM_REEL, "outil")
    script.controler_sortie("| x | outil | conforme |", "outil", "outil")  # nom réel égal à l'alias : admis
