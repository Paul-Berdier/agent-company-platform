"""Jeton machine et code d'enrôlement (cahier P5 § 5.4) : formes, empreinte ``XXXX-XXXX``, ``repr`` masqué.
L'absence du jeton dans l'argv et l'environnement des CLI est prouvée par ``test_sondes_claude.py``
(``test_jamais_dans_argv_ni_env_enfant``)."""

from __future__ import annotations

import hashlib
import json
import pickle

import pytest

from acp_poste.jeton import CodeEnrolement, Jeton, JetonInvalide

JETON = "acpm_" + "Zq3" * 14 + "x"


def test_forme_acpm():
    assert Jeton(JETON).valeur_secrete() == JETON
    for mauvais in ("acpm_court", "acpe_" + "A" * 43, "acpm_" + "A" * 42 + "!", "", None, "Bearer " + JETON):
        with pytest.raises(JetonInvalide) as exc:
            Jeton(mauvais)
        assert str(exc.value) == "Jeton machine au format invalide."
    assert CodeEnrolement("acpe_" + "B" * 43).en_tete() == "Bearer acpe_" + "B" * 43
    with pytest.raises(JetonInvalide, match="Code d'enrôlement au format invalide"):
        CodeEnrolement(JETON)


def test_empreinte_8_hex():
    attendu = hashlib.sha256(JETON.encode("ascii")).hexdigest()[:8].upper()
    assert Jeton(JETON).empreinte == f"{attendu[:4]}-{attendu[4:]}"


def test_repr_masque():
    jeton = Jeton(JETON)
    for texte in (repr(jeton), str(jeton), f"{jeton}", "%s" % (jeton,), json.dumps({"j": str(jeton)}, ensure_ascii=False)):
        assert JETON not in texte and "«masqué»" in texte and jeton.empreinte in texte
    with pytest.raises(TypeError, match="sérialisation refusée"):
        pickle.dumps(jeton)
