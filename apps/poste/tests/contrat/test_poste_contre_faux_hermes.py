"""Contrat du VRAI poste contre un faux Hermes HTTPS (cahier P5 § 14.2).

Le poste réel (commande ``acp-poste``, service ``servir``) parle en HTTPS, derrière une autorité de test, à un faux
greffon qui applique les modèles du contrat partagé et les règles du protocole. Codex et Claude sont de faux
processus locaux (``faux_codex.py``, ``faux_claude.py``) ; le coffre est en mémoire (jamais une option de
``poste.toml``).
"""

from __future__ import annotations

import asyncio
import io
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from acp_poste import cli
from acp_poste.jeton import Jeton
from acp_poste.journal import NOM
from acp_poste.protocole import Protocole
from acp_poste.service import Repli, servir
from acp_poste_contrat import machine as contrat
from acp_poste_contrat.inventaire import valider_inventaire

JETON_CLAUDE = "sk-ant-oat01-" + "q" * 40


def rapide() -> Repli:
    return Repli(maximum=0.3)


def preparer(poste, hermes, **politique):
    poste.origine = hermes.origine
    poste.options = hermes.options_client()
    poste.ecrire_politique(**politique)
    poste.preparer_profil_codex()
    poste.coffre.ecrire("jeton-claude", JETON_CLAUDE)
    return poste.contexte()


def enroler(poste, hermes, monkeypatch, capsys) -> tuple[str, str]:
    code = hermes.creer_code()
    monkeypatch.setattr("sys.stdin", io.StringIO(code + "\n"))
    assert cli.main(["enroler", "--code-stdin"], contexte=poste.contexte()) == 0
    sortie = capsys.readouterr()
    machine_id, ligne = hermes.machine()
    return machine_id, sortie.out


async def attendre(hermes, predicat, delai_s: float) -> bool:
    return await asyncio.to_thread(hermes.attendre, predicat, delai_s)


async def test_enrolement_puis_attente_puis_inventaire(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, sortie = enroler(poste, hermes, monkeypatch, capsys)
    jeton = poste.coffre.lire("jeton-machine")
    assert contrat.JETON_MACHINE.fullmatch(jeton)
    assert hermes.machines[machine_id]["empreinte"] in sortie and jeton not in sortie
    identite = json.loads(poste.emplacements.machine.read_text(encoding="utf-8"))
    assert identite["machine_id"] == machine_id and identite["empreinte"] == Jeton(jeton).empreinte
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    # À confirmer : ni présence, ni inventaire.
    assert await attendre(hermes, lambda: any(r["chemin"] == contrat.ROUTE_RECLAMER for r in hermes.requetes), 10)
    await asyncio.sleep(1.5)
    assert hermes.inventaires == [] and machine_id not in hermes.presence
    hermes.confirmer(machine_id)
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20), "inventaire après la confirmation"
    assert machine_id in hermes.presence
    inventaire = valider_inventaire(hermes.inventaires[0]["corps"])
    assert [r.voie for r in inventaire.releves] == ["poste-codex", "poste-claude"]
    assert inventaire.connexions.codex == "compte_chatgpt" and inventaire.connexions.claude == "jeton_reconnu"
    assert inventaire.poste.nom == "Poste de test" and inventaire.poste.compte == "proprietaire"
    assert await asyncio.to_thread(hermes.revoquer_pendant_l_attente, machine_id)
    assert await asyncio.wait_for(tache, 10) == 0
    # Le code ne réapparaît jamais après son usage ; le jeton ne sort que dans l'en-tête Authorization.
    for requete in hermes.requetes[1:]:
        assert requete["entetes"]["Authorization"] == f"Bearer {jeton}"
        assert jeton.encode() not in requete["corps"]
        texte = json.dumps({k: v for k, v in requete["entetes"].items() if k != "Authorization"})
        assert jeton not in texte and "acpe_" not in texte and "Cookie" not in requete["entetes"]
    assert all(b"acpe_" not in r["corps"] for r in hermes.requetes)


async def test_requetes_du_poste_ont_la_forme_des_exemples(poste, hermes, monkeypatch, capsys, module_faux_hermes):
    """Fidélité : les corps envoyés par le poste ont exactement les clés des exemples partagés avec le vrai greffon
    (``hermes/tests/outils/fixtures_machine``) et valident par les mêmes modèles."""
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20)
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)
    exemples = {contrat.ROUTE_ENROLEMENT: "enrolement_requete", contrat.ROUTE_RECLAMER: "reclamer_requete",
                contrat.ROUTE_INVENTAIRE: "inventaire_requete"}
    vus = set()
    for requete in hermes.requetes:
        corps = json.loads(requete["corps"])
        attendu = module_faux_hermes.exemple(exemples[requete["chemin"]])
        assert set(corps) == set(attendu), requete["chemin"]
        vus.add(requete["chemin"])
        assert requete["entetes"]["User-Agent"] == "acp-poste/1.0.0 (acp-machine/1)"
        assert requete["entetes"]["X-ACP-Protocole"] == "acp-machine/1"
        assert requete["entetes"]["Content-Type"] == "application/json"
    assert vus == set(exemples)
    reclamer = next(json.loads(r["corps"]) for r in hermes.requetes if r["chemin"] == contrat.ROUTE_RECLAMER)
    assert reclamer["peut_executer"] is False and reclamer["attente_max_s"] == 5


async def test_revocation_pendant_l_attente(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20)
    assert await asyncio.to_thread(hermes.attendre, lambda: hermes.en_attente.get(machine_id, 0) > 0, 10)
    debut = time.monotonic()
    hermes.revoquer(machine_id)  # le poste est dans une attente longue
    assert await asyncio.wait_for(tache, 10) == 0
    duree = time.monotonic() - debut
    assert duree < 3, f"révocation vue en {duree:.2f} s"
    assert poste.coffre.lire("jeton-machine") is None and not poste.emplacements.machine.exists()
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    assert "poste_revoque" in journal


async def test_401_de_la_couture_garde_le_jeton(poste, hermes, monkeypatch, capsys, tmp_path):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    enregistrement = tmp_path / "codex.jsonl"
    poste.scenario_codex = {"enregistrer": str(enregistrement)}
    contexte = poste.contexte()
    hermes.injecter("401_couture")
    jeton = poste.coffre.lire("jeton-machine")
    assert await asyncio.wait_for(servir(contexte, duree_max_s=30, repli=rapide), 15) == 4
    assert poste.coffre.lire("jeton-machine") == jeton, "le 401 ambigu de la couture n'efface jamais le jeton"
    assert not enregistrement.exists(), "aucune sonde après le refus du jeton"
    etat = json.loads(poste.emplacements.etat_service.read_text(encoding="utf-8"))
    assert etat["jeton_refuse_depuis"] is not None
    assert "jeton_refuse" in (poste.emplacements.journal / NOM).read_text(encoding="utf-8")


async def test_remplacement_de_l_attente(poste, hermes, monkeypatch, capsys):
    preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    jeton = Jeton(poste.coffre.lire("jeton-machine"))
    protocole = Protocole(poste.contexte().client(__import__("acp_poste.politique").politique.charger(
        poste.emplacements)))
    premiere = asyncio.create_task(asyncio.to_thread(protocole.reclamer, jeton, acquittes=[], attente_max_s=10,
                                                     politique_valide=True))
    await asyncio.sleep(1.0)
    seconde_protocole = Protocole(poste.contexte().client(__import__("acp_poste.politique").politique.charger(
        poste.emplacements)))
    seconde = asyncio.create_task(asyncio.to_thread(seconde_protocole.reclamer, jeton, acquittes=[],
                                                    attente_max_s=5, politique_valide=True))
    reponse = await asyncio.wait_for(premiere, 5)
    assert reponse.remplace is True and reponse.ordres == []
    assert (await asyncio.wait_for(seconde, 10)).remplace is False


async def test_ordre_releve_moins_de_3_s(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    tache = asyncio.create_task(servir(contexte, duree_max_s=40, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20)
    await asyncio.sleep(0.5)
    debut = time.monotonic()
    ordre = hermes.ordonner(machine_id, "releve")
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 2, 10), "second inventaire après l'ordre"
    duree = time.monotonic() - debut
    assert duree < 3, f"ordre releve → inventaire en {duree:.2f} s"
    assert await attendre(hermes, lambda: all(o["acquitte"] for o in hermes.ordres if o["id"] == ordre), 10)
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)


async def test_reponse_hors_contrat_refusee(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    hermes.injecter("hors_contrat")
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20), "reprise après le refus"
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    assert "Réponse de réclamation refusée" in journal and "champ inconnu refusé" in journal


async def test_aucun_identifiant_n_est_envoye(poste, hermes, monkeypatch, capsys):
    """Le faux Codex rend une adresse (``account/read``), le faux Claude en écrit une sur sa sortie, le coffre porte un
    jeton Claude : rien de cela, ni aucun chemin, n'atteint Hermes."""
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20)
    hermes.revoquer(machine_id)
    await asyncio.wait_for(tache, 10)
    tout = b"\n".join(r["corps"] for r in hermes.requetes).decode("utf-8")
    for interdit in ("titulaire@example.com", "@", JETON_CLAUDE, str(poste.racine), "codex-home", "claude-config",
                     "secret-de-sortie"):
        assert interdit not in tout, interdit


async def test_hermes_indisponible_repli(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    hermes.injecter("503", 3)
    hermes.injecter("coupure", 2)
    tache = asyncio.create_task(servir(contexte, duree_max_s=30, repli=rapide))
    assert await attendre(hermes, lambda: len(hermes.inventaires) == 1, 20), "reprise après 503 et coupures"
    assert await asyncio.to_thread(hermes.revoquer_pendant_l_attente, machine_id)
    assert await asyncio.wait_for(tache, 10) == 0
    journal = [json.loads(l) for l in (poste.emplacements.journal / NOM).read_text(encoding="utf-8").splitlines()]
    indisponibles = [l for l in journal if l["evenement"] == "hermes_indisponible"]
    assert len(indisponibles) == 1, "une ligne de journal par période de 10 min au plus"


async def test_409_protocole_arret(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    hermes.injecter("409_protocole")
    assert await asyncio.wait_for(servir(contexte, duree_max_s=30, repli=rapide), 15) == 2
    assert poste.coffre.lire("jeton-machine") is not None


async def test_ecart_horloge_retient_l_inventaire(poste, hermes, monkeypatch, capsys):
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    tache = asyncio.create_task(servir(contexte, duree_max_s=8, repli=rapide,
                                       horloge=lambda: datetime.now(UTC) + timedelta(minutes=5)))
    assert await asyncio.wait_for(tache, 20) == 0
    assert hermes.inventaires == [] and machine_id in hermes.presence
    journal = (poste.emplacements.journal / NOM).read_text(encoding="utf-8")
    assert "inventaire retenu" in journal.lower()
    etat = json.loads(poste.emplacements.etat_service.read_text(encoding="utf-8"))
    assert etat["ecart_horloge_s"] >= 290


async def test_429_retry_after(poste, hermes, monkeypatch, capsys):
    """Un inventaire trop fréquent (429) est gardé et renvoyé après ``Retry-After``."""
    hermes.intervalle_inventaire_s = 2
    contexte = preparer(poste, hermes)
    machine_id, _ = enroler(poste, hermes, monkeypatch, capsys)
    hermes.confirmer(machine_id)
    from acp_poste.protocole import TropFrequent

    jeton = Jeton(poste.coffre.lire("jeton-machine"))
    protocole = Protocole(contexte.client(__import__("acp_poste.politique").politique.charger(poste.emplacements)))
    corps = __import__("json").loads(json.dumps(hermes_exemple_inventaire()))
    protocole.publier(jeton, corps)
    with pytest.raises(TropFrequent) as exc:
        protocole.publier(jeton, corps)
    assert 1 <= exc.value.retry_after <= 3 and "prochain envoi possible" in exc.value.message
    time.sleep(exc.value.retry_after)
    protocole.publier(jeton, corps)


def hermes_exemple_inventaire():
    from importlib import util
    from pathlib import Path

    spec = util.spec_from_file_location("fh", Path(__file__).with_name("faux_hermes.py"))
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    corps = module.exemple("inventaire_requete")
    maintenant = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    corps["releve_le"] = maintenant
    corps["bac_a_sable_codex"]["lu_le"] = maintenant
    for releve in corps["releves"]:
        releve["releve_le"] = maintenant
        for compteur in releve["compteurs"]:
            compteur["observed_at"] = maintenant
    return corps
