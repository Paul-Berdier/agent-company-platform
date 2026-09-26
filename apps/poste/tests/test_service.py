"""Boucle « servir » (cahier P5 § 6.1) : ce qui ne demande pas de Hermes (instance unique, repli, boucle unique,
sondes exclusives). Le parcours complet contre un faux Hermes est dans ``contrat/``."""

from __future__ import annotations

import asyncio
import json

import pytest

from acp_poste import cli
from acp_poste.service import AUTRE_INSTANCE, Repli, servir
from acp_poste.verrou import Verrou


async def test_seconde_instance_refusee(poste, capsys):
    poste.ecrire_politique()
    tenu = Verrou(poste.emplacements.verrou_instance).prendre()
    try:
        assert await servir(poste.contexte()) == 3
    finally:
        tenu.rendre()
    assert capsys.readouterr().err.strip() == AUTRE_INSTANCE


def test_repli_exponentiel():
    repli = Repli(aleatoire=lambda: 0.5)
    assert [repli.suivant() for _ in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]
    bas, haut = Repli(aleatoire=lambda: 0.0), Repli(aleatoire=lambda: 1.0)
    assert bas.suivant() == pytest.approx(0.8) and haut.suivant() == pytest.approx(1.2)
    repli.reinitialiser()
    assert repli.suivant() == 1


def test_une_seule_boucle_asyncio(poste, monkeypatch):
    """``acp-poste servir`` lance UNE boucle (``asyncio.run`` une fois) et n'en crée aucune autre ensuite."""
    poste.ecrire_politique()
    poste.coffre.ecrire("jeton-machine", "acpm_" + "a" * 43)
    appels = []
    vrai_run = asyncio.run

    def compter(coro, *a, **k):
        appels.append(1)
        if len(appels) > 1:
            raise AssertionError("seconde boucle asyncio")
        return vrai_run(coro, *a, **k)

    monkeypatch.setattr(asyncio, "run", compter)
    monkeypatch.setattr(asyncio, "new_event_loop", lambda: pytest.fail("aucune boucle créée après le démarrage"))
    from acp_poste import service

    origine = service.servir

    async def borne(contexte, **options):
        return await origine(contexte, duree_max_s=3, repli=lambda: Repli(maximum=0.2))

    monkeypatch.setattr(service, "servir", borne)
    assert cli.main(["servir"], contexte=poste.contexte()) == 0
    assert appels == [1]


async def test_politique_invalide_au_demarrage_code_2(poste, capsys):
    poste.ecrire_politique("version = 1\n")
    assert await servir(poste.contexte()) == 2
    assert "[hermes]" in capsys.readouterr().err
    lignes = [json.loads(l) for l in (poste.emplacements.journal / "poste.jsonl").read_text("utf-8").splitlines()]
    assert lignes[-1]["evenement"] == "politique_refusee"


async def test_coffre_avec_jeton_illisible_code_2(poste, capsys):
    poste.ecrire_politique()
    poste.coffre.ecrire("jeton-machine", "pas-un-jeton")
    assert await servir(poste.contexte()) == 2
    assert "oublier-jeton" in capsys.readouterr().err
