"""Journal local masqué du poste (cahier P5 § 6.4, décision D64)."""

from __future__ import annotations

import json
from pathlib import Path

from acp_poste.journal import NOM, Journal, lire_fin, masquer

JETON = "acpm_" + "k" * 43
CODE = "acpe_" + "c" * 43


def _lignes(dossier: Path) -> list[dict]:
    return [json.loads(ligne) for ligne in (dossier / NOM).read_text(encoding="utf-8").splitlines()]


def test_masque_valeurs_exactes(tmp_path: Path):
    journal = Journal(tmp_path)
    journal.masquer_valeur("jeton-claude", "jeton-claude-sans-forme-connue")
    journal.ecrire("info", "essai", "valeur jeton-claude-sans-forme-connue dans le message",
                   detail="et jeton-claude-sans-forme-connue ici")
    texte = (tmp_path / NOM).read_text(encoding="utf-8")
    assert "jeton-claude-sans-forme-connue" not in texte
    ligne = _lignes(tmp_path)[0]
    assert ligne["message"] == "valeur «masqué:jeton-claude» dans le message"
    assert ligne["details"]["detail"] == "et «masqué:jeton-claude» ici"
    journal.masquer_valeur("jeton-claude", None)
    assert journal.valeurs_masquees() == []


def test_masque_motifs():
    texte = (f"jeton {JETON} code {CODE} clé sk-ant-api03-{'a' * 30} github ghp_{'b' * 36} "
             "adresse titulaire@example.com profil C:\\Users\\Paul\\AppData et /home/paul/x")
    masque = masquer(texte)
    for secret in (JETON, CODE, "sk-ant-api03", "ghp_", "titulaire@example.com", "Paul", "/home/paul"):
        assert secret not in masque, secret
    assert "«masqué:jeton machine ACP»" in masque and "«masqué:code d'enrôlement ACP»" in masque
    assert "<adresse>" in masque and masque.count("<profil>") == 2


def test_rotation(tmp_path: Path):
    journal = Journal(tmp_path, taille_max_octets=600, fichiers=3)
    for rang in range(40):
        journal.ecrire("info", "ligne", f"ligne numéro {rang:03d} " + "x" * 60)
    noms = sorted(p.name for p in tmp_path.iterdir() if not p.name.endswith(".verrou"))
    assert noms == [NOM, f"{NOM}.1", f"{NOM}.2"]
    assert all(p.stat().st_size <= 600 for p in tmp_path.iterdir() if p.name.startswith(NOM + ".") or p.name == NOM)
    assert "ligne numéro 039" in (tmp_path / NOM).read_text(encoding="utf-8")


def test_aucun_corps_ni_en_tete(tmp_path: Path):
    """Les détails n'admettent que des scalaires et des listes de chaînes courtes : un dictionnaire (corps, en-têtes,
    environnement) est remplacé, jamais écrit ; une chaîne longue est tronquée à 200 caractères."""
    journal = Journal(tmp_path)
    journal.ecrire("info", "essai", "message", entetes={"Authorization": f"Bearer {JETON}"},
                   corps=b'{"jeton": "x"}', long="y" * 500, liste=["a", "b"], nombre=3, drapeau=True, rien=None)
    ligne = _lignes(tmp_path)[0]
    assert ligne["details"]["entetes"] == "«refusé : type non journalisable»"
    assert ligne["details"]["corps"] == "«refusé : type non journalisable»"
    assert len(ligne["details"]["long"]) == 200
    assert ligne["details"]["liste"] == ["a", "b"] and ligne["details"]["nombre"] == 3
    assert JETON not in (tmp_path / NOM).read_text(encoding="utf-8")


def test_utf8(tmp_path: Path):
    journal = Journal(tmp_path)
    journal.ecrire("avertissement", "Accentué é", "Relevé « Liste de secours » : ç, œ, …")
    ligne = _lignes(tmp_path)[0]
    assert ligne["message"] == "Relevé « Liste de secours » : ç, œ, …"
    assert ligne["evenement"] == "accentu___"
    assert ligne["niveau"] == "avertissement" and ligne["quand"].endswith("Z")


def test_niveau_detail_et_limite(tmp_path: Path):
    journal = Journal(tmp_path, niveau="info")
    journal.ecrire("detail", "etape", "invisible au niveau info")
    assert not (tmp_path / NOM).exists()
    assert journal.ecrire_au_plus("reseau", 600, "avertissement", "hermes", "une fois") is True
    assert journal.ecrire_au_plus("reseau", 600, "avertissement", "hermes", "pas deux") is False
    assert [l["message"] for l in _lignes(tmp_path)] == ["une fois"]


def test_lire_fin(tmp_path: Path):
    assert lire_fin(tmp_path, 5) is None
    journal = Journal(tmp_path)
    for rang in range(10):
        journal.ecrire("info", "l", f"{rang}")
    assert [json.loads(l)["message"] for l in lire_fin(tmp_path, 3)] == ["7", "8", "9"]
