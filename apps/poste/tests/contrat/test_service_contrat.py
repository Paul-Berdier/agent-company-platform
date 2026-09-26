"""Boucle « servir » contre le faux Hermes (cahier P5 § 6.1, § 14.1) : relevé au démarrage puis à l'intervalle,
politique devenue invalide, sondes exclusives entre le service et une commande de console."""

from __future__ import annotations

import asyncio
import io
import json

from acp_poste import cli
from acp_poste.journal import NOM
from acp_poste.service import Repli, servir
from acp_poste.verrou import Verrou


def rapide() -> Repli:
    return Repli(maximum=0.3)


def pret(poste, hermes, monkeypatch, capsys, **politique):
    poste.origine = hermes.origine
    poste.options = hermes.options_client()
    poste.ecrire_politique(**politique)
    poste.preparer_profil_codex()
    monkeypatch.setattr("sys.stdin", io.StringIO(hermes.creer_code() + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=poste.contexte()) == 0
    capsys.readouterr()
    machine_id, _ = hermes.machine()
    hermes.confirmer(machine_id)
    return machine_id


async def attendre(hermes, predicat, delai_s):
    return await asyncio.to_thread(hermes.attendre, predicat, delai_s)


async def test_releve_au_demarrage_puis_intervalle(poste, hermes, monkeypatch, capsys):
    hermes.intervalle_inventaire_s = 0
    machine_id = pret(poste, hermes, monkeypatch, capsys)
    from acp_poste import service

    monkeypatch.setattr(service, "REVEIL_S", 0.5)
    contexte = poste.contexte()
    politique_courte = poste.toml(sections={"sondes": {"intervalle_s": 600}})
    poste.ecrire_politique(politique_courte)
    tache = asyncio.create_task(servir(contexte, duree_max_s=40, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 15), "relevé au démarrage"
    # Intervalle : on avance l'échéance en réduisant l'intervalle lu à chaque cycle (600 s est le minimum admis) ;
    # la boucle se réveille au plus tard toutes les 0,5 s ici.
    monkeypatch.setattr(service.Service, "_cli_changee", lambda self: True)
    assert await attendre(hermes, lambda: len(hermes.inventaires) >= 2, 15), "nouveau relevé quand une CLI change"
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)


async def test_politique_devenue_invalide_ne_publie_plus(poste, hermes, monkeypatch, capsys):
    hermes.intervalle_inventaire_s = 0
    machine_id = pret(poste, hermes, monkeypatch, capsys)
    tache = asyncio.create_task(servir(poste.contexte(), duree_max_s=40, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 15)
    poste.ecrire_politique("version = 1\n[hermes]\norigine = 'http://127.0.0.1'\n")
    assert await attendre(hermes, lambda: hermes.machines[machine_id].get("politique_valide") is False, 15), \
        "politique invalide annoncée"
    hermes.ordonner(machine_id, "releve")
    await asyncio.sleep(3)
    assert len(hermes.inventaires) == 1, "plus rien n'est publié"
    assert await attendre(hermes, lambda: all(o["acquitte"] for o in hermes.ordres), 10), \
        "l'ordre non servable est acquitté (jamais relivré sans fin)"
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    assert "politique_invalide" in journal and "releve_suspendu" in journal


async def test_sondes_exclusives(poste, hermes, monkeypatch, capsys, tmp_path):
    """Une commande de console tient le verrou des sondes : le service reporte son relevé (et le journalise) ; la
    commande de console, elle, refuse pendant qu'une sonde du service tourne."""
    machine_id = pret(poste, hermes, monkeypatch, capsys)
    console = Verrou(poste.emplacements.verrou_sondes).prendre()
    tache = asyncio.create_task(servir(poste.contexte(), duree_max_s=40, repli=rapide))
    await asyncio.sleep(7)
    assert hermes.inventaires == [], "aucun relevé du service pendant la sonde de la console"
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    assert "sondes_occupees" in journal
    assert cli.main(["releve"], contexte=poste.contexte()) == 2
    assert "Une sonde est en cours dans le service" in capsys.readouterr().err
    console.rendre()
    hermes.ordonner(machine_id, "releve")
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 15)
    assert await asyncio.to_thread(hermes.revoquer_pendant_l_attente, machine_id)
    assert await asyncio.wait_for(tache, 10) == 0
    etat = json.loads(poste.emplacements.etat_service.read_text(encoding="utf-8"))
    assert etat["etat_machine"] == "revoque"
