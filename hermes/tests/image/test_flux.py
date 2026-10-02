"""Flux d'invalidation GET /v1/flux (cahier P7 § 5, § 13.1 ; décision P7-4).

- Empreintes (``noyau/flux.py``) : chaque mutation publie SON sujet et lui seul ; aucune mutation, aucun signal ; la
  présence du poste est évaluée maintenant (le seuil franchi publie ``poste`` sans aucune écriture) ; un tableau ou la
  base illisibles sont publiés UNE fois, marqués ``illisibles`` ; un tableau WAL sans ``-wal`` ni ``-shm`` se lit en
  ``mode=ro`` (le S du § 5.3 tranché ici).
- Diffuseur : révision ``<époque>.<numéro>``, Last-Event-ID, époque changée, sujets fusionnés, réservations abandonnées,
  arrêt du veilleur après le dernier abonné et passe de reprise.
- Route servie par un VRAI serveur uvicorn derrière deux intergiciels HTTP empilés (``pile_machine``) : en-têtes, trame
  d'ouverture, Last-Event-ID, changement en moins de 5 s, battement, fin, 429 au-delà de ``flux_max``, place rendue
  après une déconnexion (avant le premier battement : correction K10), aucun fil tenu pendant un flux. Les six
  intergiciels de Hermes et la vraie porte d'authentification : test_flux_contrat.py.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from conftest import lancer_sans_depot, lancer_sur_depot, poste_confirme, reclamer, releve_factice

SUJETS = ["projets", "questions", "poste", "quotas", "notifications", "pause", "discussions"]
CHEMIN = "/api/plugins/acp-poste/v1/flux"


@pytest.fixture
def flux(noyau):
    from noyau import flux as module

    return module


def changes(flux, avant, apres) -> set:
    return {s for s in flux.SUJETS if avant.valeurs.get(s) != apres.valeurs.get(s)}


class Suivi:
    """Empreintes successives : ``muter(fonction)`` rend les sujets que la mutation a changés."""

    def __init__(self, flux) -> None:
        self.flux = flux
        self.dernier = flux.calculer()

    def muter(self, fonction=None) -> set:
        if fonction is not None:
            fonction()
        apres = self.flux.calculer()
        resultat = changes(self.flux, self.dernier, apres)
        self.dernier = apres
        return resultat


# ============================================================ empreintes


def test_aucune_mutation_aucun_sujet(noyau, conn, flux):
    projet = lancer_sans_depot(noyau, conn)
    machine, _jeton = poste_confirme(noyau, conn)
    noyau.presence.enregistrer(conn, machine, "longpoll")
    suivi = Suivi(flux)
    assert suivi.dernier.illisibles == frozenset() and suivi.dernier.discussions_suivies is True
    assert suivi.muter() == set()
    time.sleep(1.1)  # la présence est évaluée à chaque passe : rien ne bouge tant que le seuil n'est pas franchi
    assert suivi.muter() == set()
    # Le tableau du projet est bien suivi (une ligne par tableau de projet non terminé).
    assert [t for t, _ in suivi.dernier.valeurs["projets"][-1]] == [projet["tableau"]]


def test_chaque_mutation_publie_son_sujet_et_lui_seul(noyau, conn, flux, monkeypatch):
    suivi = Suivi(flux)
    base, ka = noyau.base, noyau.ka

    assert suivi.muter(lambda: base.poser_reglage(conn, "pause_reclamations", 1, "proprietaire:test")) == {"pause"}
    assert suivi.muter(lambda: ka.engage("pause de test")) == {"pause"}
    assert suivi.muter(lambda: ka.disengage()) == {"pause"}
    assert suivi.muter(lambda: noyau.notifications.enfiler(conn, cle="test:1", genre="test",
                                                            texte_notif="Notification de test.")) == {"notifications"}

    def publier_canal():
        with base.transaction(conn):
            base.ecrire_emetteur(conn, "canal", {"canal": "ntfy", "configure": True})
    assert suivi.muter(publier_canal) == {"notifications"}
    assert suivi.muter(lambda: noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex"))) == {"quotas"}
    machine = {}
    assert suivi.muter(lambda: machine.update(id=poste_confirme(noyau, conn)[0])) == {"poste"}
    assert suivi.muter(lambda: noyau.presence.enregistrer(conn, machine["id"], "longpoll")) == {"poste"}
    # Une présence de plus, toujours en ligne : rien à relire.
    assert suivi.muter(lambda: noyau.presence.enregistrer(conn, machine["id"], "longpoll")) == set()
    # Seuil franchi SANS aucune écriture : la présence évaluée maintenant publie « poste ».
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s"))
    assert suivi.muter(lambda: base.fixer_horloge(lambda: time.time() + seuil + 60)) == {"poste"}
    assert suivi.muter(lambda: base.fixer_horloge(None)) == {"poste"}
    assert suivi.muter(lambda: noyau.ordres.creer(conn, machine["id"], "releve", "proprietaire:test")) == {"poste"}
    # Un projet lancé : son tableau naît avec ses événements (projets ET questions relisent les tableaux).
    projet = {}
    assert suivi.muter(lambda: projet.update(lancer_sans_depot(noyau, conn))) == {"projets", "questions"}
    assert suivi.muter(lambda: noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")) == {
        "projets", "questions", "pause"}
    # Discussions : nombre de requêtes ouvertes dans ce processus (lu par l'adaptateur seulement, K9).
    monkeypatch.setattr(ka, "open_request_count", lambda: 0)
    assert suivi.muter() == set()
    monkeypatch.setattr(ka, "open_request_count", lambda: 1)
    assert suivi.muter() == {"discussions"}
    assert suivi.dernier.discussions_suivies is True


def test_question_et_reponse(noyau, conn, flux):
    projet = lancer_sur_depot(noyau, conn, reponses="proprietaire")
    run = reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    suivi = Suivi(flux)
    question = {}
    assert suivi.muter(lambda: question.update(noyau.questions.poser(
        conn, tableau=projet["tableau"], carte=projet["cartes"]["exploration"], run_id=run,
        texte="Quel nom ?"))) == {"projets", "questions", "notifications"}  # escaladée : notifiée au propriétaire
    assert suivi.muter(lambda: noyau.questions.repondre_par_proprietaire(
        conn, question["question"], reponse="« outil ».", auteur="proprietaire:test")) == {"projets", "questions"}


def test_discussions_non_suivies_jamais_publiees(noyau, conn, flux, monkeypatch):
    """Sans le compteur de Hermes (autre version), ``discussions`` vaut ``None`` : jamais publié, et dit."""
    monkeypatch.setattr(noyau.ka, "open_request_count", None)
    suivi = Suivi(flux)
    assert suivi.dernier.discussions_suivies is False and suivi.dernier.valeurs["discussions"] is None
    assert suivi.muter() == set()


def _sans_wal_ni_shm(chemin: Path) -> None:
    """Rien n'est perdu : le journal WAL est d'abord reporté dans la base, puis les deux fichiers sont retirés."""
    import sqlite3

    conn = sqlite3.connect(str(chemin))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    for suffixe in ("-wal", "-shm"):
        Path(f"{chemin}{suffixe}").unlink(missing_ok=True)
        assert not Path(f"{chemin}{suffixe}").exists()


def test_tableau_wal_sans_wal_ni_shm_lu_en_lecture_seule(noyau, conn):
    """S du cahier § 5.3 tranché : ``mode=ro`` sur un tableau WAL dont le ``-shm`` (et le ``-wal``) ont disparu."""
    projet = lancer_sans_depot(noyau, conn)
    chemin = Path(noyau.ka.kanban_db_path(projet["tableau"]))
    with noyau.ka.connexion(projet["tableau"]) as kc:
        attendu = noyau.ka.dernier_evenement(kc)
        assert kc.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert attendu > 0
    _sans_wal_ni_shm(chemin)
    assert noyau.ka.dernier_evenement_lecture_seule(projet["tableau"]) == attendu
    # Hermes écrit toujours dans le tableau après cette lecture (aucun fichier laissé qui tromperait son contrôle).
    with noyau.ka.connexion(projet["tableau"]) as kc:
        noyau.ka.create_task(kc, title="Après la lecture", body="x", assignee="default", created_by="test",
                             board=projet["tableau"])
        assert noyau.ka.dernier_evenement(kc) > attendu
    assert noyau.ka.dernier_evenement_lecture_seule(projet["tableau"]) > attendu
    assert noyau.ka.dernier_evenement_lecture_seule("acp-absent-0000") is None


def test_tableau_illisible_publie_une_fois(noyau, conn, flux):
    projet = lancer_sans_depot(noyau, conn)
    suivi = Suivi(flux)
    chemin = Path(noyau.ka.kanban_db_path(projet["tableau"]))
    _sans_wal_ni_shm(chemin)
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    assert suivi.muter() == {"projets", "questions"}
    assert {"projets", "questions"} <= suivi.dernier.illisibles
    assert suivi.dernier.valeurs["projets"][-1] == ((projet["tableau"], ("illisible", "DatabaseError")),)
    assert suivi.muter() == set()  # stable : publié une fois, pas à chaque tour


def test_base_illisible_publiee_une_fois(noyau, conn, flux, monkeypatch):
    suivi = Suivi(flux)

    def en_panne():
        raise OSError("disque illisible")
    monkeypatch.setattr(flux.base, "connexion", en_panne)
    assert suivi.muter() == set(flux.SUJETS_DE_LA_BASE)
    assert suivi.dernier.illisibles == frozenset(flux.SUJETS_DE_LA_BASE)
    assert suivi.dernier.valeurs["pause"] == ("illisible", "OSError")
    assert suivi.muter() == set()
    assert flux.lire_reglages() == {"flux_intervalle_s": 2, "flux_battement_s": 15, "flux_duree_max_s": 600,
                                    "flux_max": 8}


def test_reglages_bornes(noyau, conn, flux):
    assert flux.reglages(conn) == {"flux_intervalle_s": 2, "flux_battement_s": 15, "flux_duree_max_s": 600,
                                   "flux_max": 8}
    for cle, valeur in (("flux_intervalle_s", 0), ("flux_battement_s", 9999), ("flux_duree_max_s", 1),
                        ("flux_max", "beaucoup")):
        noyau.base.poser_reglage(conn, cle, valeur, "test")
    # Planchers et plafonds : veilleur ≥ 1 s, battement < 5 min, durée < 15 min (bord Railway) ; illisible : défaut.
    assert flux.reglages(conn) == {"flux_intervalle_s": 1, "flux_battement_s": 240, "flux_duree_max_s": 5,
                                   "flux_max": 8}


# ============================================================ diffuseur (une boucle asyncio)


def _releve(flux, valeurs, illisibles=frozenset(), intervalle=1.0):
    return flux.Releve(dict(valeurs), frozenset(illisibles), intervalle, True)


def test_diffuseur_revision_last_event_id_et_epoque(flux):
    async def scenario():
        valeurs = {s: 0 for s in SUJETS}
        # Veilleur à 60 s : seules les passes du test publient (aucune course avec la tâche du veilleur).
        d = flux.Diffuseur(asyncio.get_running_loop(), lambda: _releve(flux, valeurs, intervalle=60))
        try:
            await d.assurer()  # première passe : la référence, rien de publié
            r0 = d.revision
            assert d.sujets_a_l_ouverture(None) == SUJETS
            assert d.sujets_a_l_ouverture(r0) == [] and d.sujets_a_l_ouverture(f" {r0} ") == []
            assert d.sujets_a_l_ouverture(f"{d.epoque}.999") == SUJETS
            a, b = d.abonner(2), d.abonner(2)
            assert a is not None and b is not None and d.abonner(2) is None
            assert await d.passe() == set() and d.revision == r0 and not a.evenement.is_set()
            valeurs["questions"] = 1
            assert await d.passe() == {"questions"} and d.revision == f"{d.epoque}.1"
            valeurs["pause"] = 1
            await d.passe()
            assert a.evenement.is_set()
            assert a.prendre() == (["questions", "pause"], [], f"{d.epoque}.2")  # fusionnés, ordre fixe
            assert a.prendre() is None and not a.evenement.is_set()
            d.desabonner(b)
            assert d.abonner(2) is not None
            # Redémarrage du tableau de bord : nouvelle époque ; l'ancienne révision fait tout relire.
            autre = flux.Diffuseur(asyncio.get_running_loop(), lambda: _releve(flux, valeurs, intervalle=60))
            await autre.assurer()
            assert autre.epoque > d.epoque and autre.sujets_a_l_ouverture(d.revision) == SUJETS
            autre.tache.cancel()
        finally:
            if d.tache is not None:
                d.tache.cancel()
    asyncio.run(scenario())


def test_diffuseur_illisibles_marques_sur_les_sujets_changes(flux):
    async def scenario():
        valeurs, illisibles = {s: 0 for s in SUJETS}, set()
        d = flux.Diffuseur(asyncio.get_running_loop(), lambda: _releve(flux, valeurs, illisibles))
        await d.passe()
        a = d.abonner(8)
        valeurs.update(projets=("illisible", "DatabaseError"), questions=("illisible", "DatabaseError"), quotas=1)
        illisibles.update({"projets", "questions"})
        await d.passe()
        assert a.prendre() == (["projets", "questions", "quotas"], ["projets", "questions"], d.revision)
        await d.passe()  # toujours illisibles, empreinte stable : rien de nouveau
        assert a.prendre() is None
    asyncio.run(scenario())


def test_diffuseur_reservation_abandonnee_et_arret_du_veilleur(flux, monkeypatch):
    monkeypatch.setattr(flux, "ABANDON_RESERVATION_S", 0.05)
    monkeypatch.setattr(flux, "ARRET_VEILLEUR_S", 0.3)

    async def scenario():
        valeurs = {s: 0 for s in SUJETS}
        d = flux.Diffuseur(asyncio.get_running_loop(), lambda: _releve(flux, valeurs, intervalle=0.05))
        await d.assurer()
        jamais_demarre = d.abonner(1)
        assert jamais_demarre is not None and d.abonner(1) is None
        await asyncio.sleep(0.1)
        # Client parti avant la première trame : sa réservation est retirée, la place n'est jamais perdue.
        actif = d.abonner(1)
        assert actif is not None and jamais_demarre not in d.abonnes
        actif.demarre = True
        await asyncio.sleep(0.5)
        assert d.etat()["veilleur"] is True and actif in d.abonnes  # un flux démarré n'est jamais retiré ainsi
        d.desabonner(actif)
        await asyncio.sleep(0.6)
        assert d.tache is None and d.etat()["veilleur"] is False  # arrêté après le dernier abonné
        # Pendant l'arrêt, un sujet change : la reprise fait d'abord une passe, la révision avance.
        avant = d.revision
        valeurs["poste"] = 1
        await d.assurer()
        assert d.revision != avant and d.sujets_a_l_ouverture(avant) == SUJETS
        d.tache.cancel()
    asyncio.run(scenario())


def test_trames_au_format_sse(flux):
    assert flux.trame_ouverture("17.3", SUJETS, ["projets"], False) == (
        'retry: 3000\n\nid: 17.3\nevent: etat\ndata: {"revision":"17.3","sujets":["projets","questions","poste",'
        '"quotas","notifications","pause","discussions"],"discussions_suivies":false,"illisibles":["projets"]}\n\n'
    ).encode()
    assert flux.trame_ouverture("17.3", [], [], True) == (
        'retry: 3000\n\nid: 17.3\nevent: etat\ndata: {"revision":"17.3","sujets":[],"discussions_suivies":true}\n\n'
    ).encode()
    assert flux.trame_changement("17.4", ["pause", "questions"], []) == (
        'id: 17.4\nevent: changement\ndata: {"sujets":["questions","pause"]}\n\n').encode()
    assert flux.trame_fin() == b'event: fin\ndata: {"raison":"duree_max"}\n\n'
    assert flux.TRAME_BATTEMENT == b": battement\n\n"


def test_trames_exemples_partagees_avec_le_desktop(flux):
    """Les trames exemples publiées pour le desktop P8 (hermes/tests/outils/fixtures_flux) sont exactement celles que
    produit le greffon."""
    dossier = Path("/opt/acp-tests/outils/fixtures_flux")
    assert (dossier / "ouverture.txt").read_bytes() == flux.trame_ouverture(
        "1727791200.41", SUJETS, [], True)
    assert (dossier / "reprise.txt").read_bytes() == flux.trame_ouverture("1727791200.41", [], [], True)
    assert (dossier / "changement.txt").read_bytes() == flux.trame_changement(
        "1727791200.42", ["questions", "projets"], [])
    assert (dossier / "illisible.txt").read_bytes() == flux.trame_changement(
        "1727791200.43", ["projets", "questions"], ["projets", "questions"])
    assert (dossier / "battement.txt").read_bytes() == flux.TRAME_BATTEMENT
    assert (dossier / "fin.txt").read_bytes() == flux.trame_fin()


# ============================================================ route, servie par un vrai serveur uvicorn


class LecteurFlux:
    """Flux lu dans un fil (le test garde la main) ; trames découpées sur la ligne vide, horodatées à l'arrivée."""

    def __init__(self, url: str, entetes: Optional[Dict[str, str]] = None) -> None:
        import httpx

        self.client = httpx.Client(timeout=httpx.Timeout(30.0, read=None))
        self.reponse = self.client.send(self.client.build_request("GET", url, headers=entetes or {}), stream=True)
        self.statut = self.reponse.status_code
        self.entetes = self.reponse.headers
        self.trames: "queue.Queue[Any]" = queue.Queue()
        self.fil = threading.Thread(target=self._lire, daemon=True)
        if self.statut == 200:
            self.fil.start()

    def _lire(self) -> None:
        tampon = b""
        try:
            for morceau in self.reponse.iter_raw():
                tampon += morceau
                while b"\n\n" in tampon:
                    brut, tampon = tampon.split(b"\n\n", 1)
                    self.trames.put((time.monotonic(), _analyser(brut.decode("utf-8"))))
        except Exception:  # noqa: BLE001 — flux fermé par le test
            pass
        self.trames.put((time.monotonic(), None))

    def trame(self, delai: float = 10.0):
        """(instant d'arrivée, trame) ; trame ``None`` : flux terminé."""
        return self.trames.get(timeout=delai)

    def jusqu_a(self, evenement: str, delai: float = 10.0):
        limite = time.monotonic() + delai
        vues = []
        while True:
            quand, trame = self.trame(max(0.01, limite - time.monotonic()))
            vues.append(trame)
            if trame is None or trame.get("event") == evenement:
                return quand, trame, vues

    def fermer(self) -> None:
        """Déconnexion RÉELLE : ``shutdown`` du socket d'abord. Un simple ``close`` depuis ce fil, pendant que le fil
        lecteur est bloqué en lecture sur le même socket, ne ferme pas la connexion (le noyau garde le socket tant
        que la lecture tient sa référence) : le serveur ne verrait la déconnexion qu'à son prochain envoi."""
        import socket

        try:
            flux_reseau = self.reponse.extensions.get("network_stream")
            sock = flux_reseau.get_extra_info("socket") if flux_reseau is not None else None
            if sock is not None:
                sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.reponse.close()
        finally:
            self.client.close()


def _analyser(brut: str) -> Dict[str, Any]:
    trame: Dict[str, Any] = {}
    for ligne in brut.split("\n"):
        if ligne.startswith(":"):
            trame.setdefault("commentaires", []).append(ligne[1:].strip())
            continue
        champ, _, valeur = ligne.partition(":")
        trame[champ] = valeur[1:] if valeur.startswith(" ") else valeur
    if "data" in trame:
        trame["donnees"] = json.loads(trame["data"])
    return trame


def _ouvrir(pile, entetes=None) -> LecteurFlux:
    lecteur = LecteurFlux(pile.url + CHEMIN, entetes)
    assert lecteur.statut == 200, lecteur.reponse.read()
    return lecteur


def test_route_entetes_ouverture_et_last_event_id(pile_machine):
    lecteur = _ouvrir(pile_machine)
    try:
        assert lecteur.entetes["content-type"] == "text/event-stream; charset=utf-8"
        assert lecteur.entetes["cache-control"] == "no-store" and lecteur.entetes["x-accel-buffering"] == "no"
        assert lecteur.trame()[1] == {"retry": "3000"}
        etat = lecteur.trame()[1]
        assert etat["event"] == "etat" and etat["id"] == etat["donnees"]["revision"]
        assert etat["donnees"] == {"revision": etat["id"], "sujets": SUJETS, "discussions_suivies": True}
        revision = etat["id"]
    finally:
        lecteur.fermer()
    for dernier, attendu in ((revision, []), (f"{revision}9", SUJETS), ("1.0", SUJETS)):
        lecteur = _ouvrir(pile_machine, {"Last-Event-ID": dernier})
        try:
            lecteur.trame()
            assert lecteur.trame()[1]["donnees"]["sujets"] == attendu, dernier
        finally:
            lecteur.fermer()


def test_route_changement_en_moins_de_5_s_et_aucun_fil_tenu(pile_machine):
    noyau = pile_machine.noyau
    lecteur = _ouvrir(pile_machine)
    try:
        _, etat, _ = lecteur.jusqu_a("etat")
        assert pile_machine.get("/test/fils-occupes").json() == {"occupes": 0}  # attente sur la boucle, pas en fil
        with noyau.base.connexion() as conn:
            debut = time.monotonic()
            noyau.base.poser_reglage(conn, "pause_reclamations", 1, "proprietaire:test")
        quand, trame, vues = lecteur.jusqu_a("changement", delai=15)
        assert trame is not None and trame["donnees"] == {"sujets": ["pause"]}, vues
        assert quand - debut < 5.0, quand - debut
        epoque, numero = trame["id"].split(".")
        assert epoque == etat["id"].split(".")[0] and int(numero) > int(etat["id"].split(".")[1])
    finally:
        lecteur.fermer()


def test_route_battement_et_fin(pile_machine):
    noyau = pile_machine.noyau
    with noyau.base.connexion() as conn:
        noyau.base.poser_reglage(conn, "flux_battement_s", 1, "test")
        noyau.base.poser_reglage(conn, "flux_duree_max_s", 5, "test")
    lecteur = _ouvrir(pile_machine)
    try:
        debut = time.monotonic()
        quand, fin, vues = lecteur.jusqu_a("fin", delai=15)
        assert fin is not None and fin["donnees"] == {"raison": "duree_max"} and "id" not in fin
        assert 4.5 <= quand - debut <= 9.0, quand - debut
        battements = [t for t in vues if t and t.get("commentaires") == ["battement"]]
        assert len(battements) >= 3, vues
        assert lecteur.trame(10)[1] is None  # le serveur ferme le flux après « fin »
    finally:
        lecteur.fermer()


def _place_rendue(pile, delai: float) -> float:
    """Secondes avant qu'un nouveau flux soit accepté (le précédent fermé côté client)."""
    debut = time.monotonic()
    while time.monotonic() - debut < delai:
        lecteur = LecteurFlux(pile.url + CHEMIN)
        try:
            if lecteur.statut == 200:
                return time.monotonic() - debut
        finally:
            lecteur.fermer()
        time.sleep(0.25)
    raise AssertionError(f"place non rendue en {delai} s")


def test_route_429_au_dela_de_flux_max_et_place_rendue(pile_machine):
    noyau = pile_machine.noyau
    with noyau.base.connexion() as conn:
        noyau.base.poser_reglage(conn, "flux_max", 2, "test")
    premier, second = _ouvrir(pile_machine), _ouvrir(pile_machine)
    try:
        premier.jusqu_a("etat")
        second.jusqu_a("etat")
        refus = LecteurFlux(pile_machine.url + CHEMIN)
        try:
            assert refus.statut == 429 and refus.entetes["retry-after"] == "30"
            assert json.loads(refus.reponse.read()) == {"detail": {
                "code": "trop_de_flux", "message": "Trop de pages ouvertes en temps réel : fermez-en une ou attendez."}}
        finally:
            refus.fermer()
        # Déconnexion AVANT le premier battement (15 s) : la place revient bien avant (K10), jamais perdue.
        premier.fermer()
        delai = _place_rendue(pile_machine, 20)
        print(f"place rendue {delai:.2f} s après la déconnexion")
        assert delai < 5, delai  # au plus un tour de flux (2 s), bien avant le battement de 15 s
    finally:
        premier.fermer()
        second.fermer()
