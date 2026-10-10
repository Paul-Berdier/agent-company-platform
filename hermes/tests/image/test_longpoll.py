"""Long-poll ``/machine/v1/reclamer`` (étape P5, cahier P5 § 4.5, § 14.3) sur un vrai serveur : retour à l'échéance,
réveil par un ordre écrit DEPUIS UN FIL en moins d'une seconde, la plus récente attente gagne, déconnexion libérée,
aucun fil tenu pendant l'attente, révocation pendant l'attente (401 ``poste_revoque``), présence et acquittements."""

from __future__ import annotations

import json
import socket
import threading
import time
from urllib.parse import urlsplit

from conftest import fixture_machine

from acp_poste_contrat import machine as contrat  # noqa: E402

M = "/api/plugins/acp-poste/machine/v1"


def _poste_actif(pile):
    with pile.noyau.base.connexion() as conn:
        code = pile.noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    reponse = pile.post(f"{M}/enrolement", fixture_machine("enrolement_requete.json"), jeton=code).json()
    with pile.noyau.base.connexion() as conn:
        pile.noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")
    return reponse["machine_id"], reponse["jeton"]


def _reclamer(pile, jeton, attente=25, acquittes=()):
    corps = dict(fixture_machine("reclamer_requete.json"), ordres_acquittes=list(acquittes), attente_max_s=attente)
    return pile.post(f"{M}/reclamer", corps, jeton=jeton)


def _en_fond(fonction):
    resultat = {}

    def cible():
        debut = time.monotonic()
        resultat["reponse"] = fonction()
        resultat["fin"] = time.monotonic()
        resultat["duree"] = resultat["fin"] - debut
    fil = threading.Thread(target=cible, daemon=True)
    fil.start()
    return fil, resultat


def _attendre_l_attente(pile, machine, delai=10.0):
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        if machine in pile.module.attentes_en_cours():
            return
        time.sleep(0.02)
    raise AssertionError("l'attente du poste n'a pas commencé")


def test_retour_a_l_echeance_et_presence(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    debut = time.monotonic()
    reponse = _reclamer(pile_machine, jeton, attente=5)
    duree = time.monotonic() - debut
    assert reponse.status_code == 200 and 4.5 <= duree <= 8.0, duree
    corps = contrat.ReponseReclamer.model_validate(reponse.json())
    assert corps.ordres == [] and corps.carte is None and corps.remplace is False and corps.etat_machine == "actif"
    with pile_machine.noyau.base.connexion() as conn:
        ligne = conn.execute("SELECT source FROM presence WHERE machine_id = ?", (machine,)).fetchone()
        assert ligne[0] == "longpoll"
        assert pile_machine.noyau.presence.etat_poste(conn)["etat"] == "en_ligne"
    assert machine not in pile_machine.module.attentes_en_cours()


def test_reveil_par_ordre(pile_machine):
    """Un ordre écrit par une route du propriétaire (groupe de fils) réveille l'attente en moins d'une seconde : la
    relecture de 2 s ne peut pas masquer un réveil cassé."""
    machine, jeton = _poste_actif(pile_machine)
    fil, resultat = _en_fond(lambda: _reclamer(pile_machine, jeton, attente=25))
    _attendre_l_attente(pile_machine, machine)
    time.sleep(0.3)
    ordonne = time.monotonic()
    identifiant = pile_machine.module.ordonner(machine, "releve", "proprietaire:test")  # CE fil n'est pas la boucle
    fil.join(10)
    delai = resultat["fin"] - ordonne
    print(f"\nréveil par ordre : {delai * 1000:.0f} ms")
    assert delai < 1.0, delai
    corps = resultat["reponse"].json()
    assert [(o["id"], o["genre"]) for o in corps["ordres"]] == [(identifiant, "releve")]
    # Livré, pas encore acquitté : l'ordre revient tant qu'il n'est pas acquitté (au moins une fois).
    assert [o["id"] for o in _reclamer(pile_machine, jeton, attente=5).json()["ordres"]] == [identifiant]
    reponse = _reclamer(pile_machine, jeton, attente=5, acquittes=[identifiant])
    assert reponse.json()["ordres"] == []


def test_remplacement(pile_machine):
    """La plus récente attente gagne : l'ancienne rend « remplace » tout de suite (reconnexion après coupure)."""
    machine, jeton = _poste_actif(pile_machine)
    fil, resultat = _en_fond(lambda: _reclamer(pile_machine, jeton, attente=25))
    _attendre_l_attente(pile_machine, machine)
    fil2, resultat2 = _en_fond(lambda: _reclamer(pile_machine, jeton, attente=5))
    fil.join(10)
    assert resultat["reponse"].json()["remplace"] is True and resultat["duree"] < 5
    fil2.join(15)
    assert resultat2["reponse"].json()["remplace"] is False
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT remplacements_minute FROM machines WHERE id = ?", (machine,)).fetchone()[0] == 1


def test_deconnexion_libere(pile_machine):
    """Le poste coupe la connexion : l'attente est libérée (relecture de 2 s puis is_disconnected), sans attendre
    l'échéance de 25 s."""
    machine, jeton = _poste_actif(pile_machine)
    corps = json.dumps(dict(fixture_machine("reclamer_requete.json"), ordres_acquittes=[], attente_max_s=25)).encode()
    adresse = urlsplit(pile_machine.url)
    brut = socket.create_connection((adresse.hostname, adresse.port), timeout=5)
    brut.sendall(b"POST " + M.encode() + b"/reclamer HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\n"
                 + b"Authorization: Bearer " + jeton.encode() + b"\r\nContent-Length: " + str(len(corps)).encode()
                 + b"\r\n\r\n" + corps)
    _attendre_l_attente(pile_machine, machine)
    coupe = time.monotonic()
    brut.close()
    limite = coupe + 10
    while machine in pile_machine.module.attentes_en_cours() and time.monotonic() < limite:
        time.sleep(0.05)
    libere = time.monotonic() - coupe
    print(f"\nattente libérée {libere:.2f} s après la coupure")
    assert machine not in pile_machine.module.attentes_en_cours() and libere < 5, libere


def test_aucun_fil_tenu(pile_machine):
    """Pendant l'attente, le groupe de fils n'est pas occupé : la boucle attend un événement, pas un fil."""
    machine, jeton = _poste_actif(pile_machine)
    fil, _resultat = _en_fond(lambda: _reclamer(pile_machine, jeton, attente=6))
    _attendre_l_attente(pile_machine, machine)
    releves = []
    for _ in range(20):
        releves.append(pile_machine.get("/test/fils-occupes").json()["occupes"])
        time.sleep(0.1)
    fil.join(15)
    assert releves.count(0) >= 15, releves


def test_revocation_pendant_l_attente(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    fil, resultat = _en_fond(lambda: _reclamer(pile_machine, jeton, attente=25))
    _attendre_l_attente(pile_machine, machine)
    revoque = time.monotonic()
    pile_machine.module.revoquer(machine, "PC perdu", "proprietaire:test")
    fil.join(10)
    reponse = resultat["reponse"]
    assert reponse.status_code == 401 and resultat["fin"] - revoque < 1.0
    detail = contrat.ErreurMachine.model_validate(reponse.json()).detail
    assert detail.code == "poste_revoque" and detail.message.startswith("Poste révoqué par le propriétaire le ")
    assert detail.message.endswith(" : jeton local effacé.")
    # L'appel suivant : la couture ne connaît plus l'empreinte (401 générique, ambigu).
    suivant = _reclamer(pile_machine, jeton, attente=5)
    assert suivant.status_code == 401 and suivant.json() == contrat.CORPS_401_COUTURE


def test_revocation_relue_dans_la_transaction(pile_machine, monkeypatch):
    """Révocation entre la couture et le gestionnaire : l'état relu dans la transaction rend 401 poste_revoque."""
    machine, jeton = _poste_actif(pile_machine)
    jm = pile_machine.module._n("jeton_machine")
    original = jm.FournisseurJetonMachine._verifier

    def verifier_puis_revoquer(self, token):
        principal = original(self, token)
        with pile_machine.noyau.base.connexion() as conn:
            pile_machine.noyau.machines.revoquer(conn, machine, "course", "proprietaire:test")
        return principal
    monkeypatch.setattr(jm.FournisseurJetonMachine, "_verifier", verifier_puis_revoquer)
    reponse = _reclamer(pile_machine, jeton, attente=5)
    assert reponse.status_code == 401 and reponse.json()["detail"]["code"] == "poste_revoque"


def test_politique_invalide_annoncee(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    fil, _r = _en_fond(lambda: pile_machine.post(f"{M}/reclamer", dict(fixture_machine("reclamer_requete.json"),
                                                  ordres_acquittes=[], attente_max_s=5, politique_valide=False),
                                                  jeton=jeton))
    fil.join(15)
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT politique_valide FROM machines WHERE id = ?", (machine,)).fetchone()[0] == 0
        assert pile_machine.noyau.presence.etat_poste(conn)["message"] == (
            "Politique locale invalide : le poste reste joignable mais ne publie plus rien.")


def test_pause_generale_transmise(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    with pile_machine.noyau.base.connexion() as conn:
        pile_machine.noyau.base.poser_reglage(conn, "pause_reclamations", 1, "test")
    ordre = pile_machine.module.ordonner(machine, "pause", "proprietaire:test")
    corps = _reclamer(pile_machine, jeton, attente=5).json()
    assert corps["pause_reclamations"] is True and [o["genre"] for o in corps["ordres"]] == ["pause"]
    assert corps["ordres"][0]["id"] == ordre
