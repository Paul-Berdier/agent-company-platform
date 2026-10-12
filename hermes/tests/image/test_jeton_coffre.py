"""Coffre indépendant : conformité au vrai Hermes épinglé et étanchéité des routes à jeton."""
from uuid import uuid4

import pytest
from acp_poste_contrat import coffre as C
from conftest import poste_confirme


@pytest.fixture
def pile_coffre(pile_machine):
    import meta
    from hermes_cli.dashboard_auth.registry import register_global_provider
    from hermes_cli.dashboard_auth.token_auth import register_token_route
    fournisseur = meta.sous_module_noyau("jeton_coffre").FournisseurCoffre()
    register_global_provider(fournisseur)
    pile_machine._fournisseurs.append(fournisseur)
    for route in C.ROUTES:
        register_token_route(route)
    return pile_machine


def test_protocole_auth_coffre_reel(noyau):
    from noyau.jeton_coffre import FournisseurCoffre
    from hermes_cli.dashboard_auth.base import DashboardAuthProvider, assert_protocol_compliance
    assert_protocol_compliance(FournisseurCoffre)
    fournisseur=FournisseurCoffre()
    assert isinstance(fournisseur,DashboardAuthProvider)
    assert (fournisseur.name,fournisseur.supports_token,fournisseur.supports_session,fournisseur.supports_password)==(
        "acp-coffre",True,False,False)
    assert fournisseur.verify_session(access_token="x") is None
    assert fournisseur.revoke_session(refresh_token="x") is None
    for methode,arguments in (("start_login",{"redirect_uri":"x"}), ("refresh_session",{"refresh_token":"x"}),
        ("complete_login",{"code":"c","state":"s","code_verifier":"v","redirect_uri":"x"})):
        with pytest.raises(NotImplementedError):
            getattr(fournisseur,methode)(**arguments)


def test_couture_reelle_exige_identite_dediee_et_ne_remplace_pas_executant(pile_coffre,noyau,conn):
    p=pile_coffre
    machine,jeton_machine=poste_confirme(noyau,conn)
    code=p.post("/api/plugins/acp-poste/v1/coffre/enrolement",{}).json()["code"]
    body={"protocole":C.PROTOCOLE,"version_bridge":"1.2.0","coffre_id":str(uuid4()),"alias":"acp"}
    assert p.post(C.ROUTE_ENROLEMENT,body).status_code==401
    assert p.post(C.ROUTE_ENROLEMENT,body,jeton=jeton_machine).status_code==403
    r=p.post(C.ROUTE_ENROLEMENT,body,jeton=code)
    assert r.status_code==201,r.text
    r=r.json()
    assert p.post(C.ROUTE_ENROLEMENT,body,jeton=code).status_code==401
    assert p.post("/api/plugins/acp-poste/machine/v1/reclamer",{},jeton=r["jeton"]).status_code==403
    assert p.post("/api/plugins/acp-poste/v1/coffre/enrolement",{},jeton=r["jeton"],
                  entetes={"x-test-sans-session":"1"}).status_code==401
    assert p.post("/api/plugins/acp-poste/v1/coffre/confirmer",{
        "coffre_id":r["coffre_id"],"empreinte":r["empreinte"]}).status_code==200
    poll={"protocole":C.PROTOCOLE,"coffre_id":r["coffre_id"],"capacites":list(C.ACTIONS),"attente_max_s":0}
    assert p.post(C.ROUTE_RECLAMER,poll,jeton=r["jeton"]).json()["etat"]=="actif"
    assert conn.execute("SELECT etat FROM machines WHERE id=?",(machine,)).fetchone()[0]=="actif"
    d={"id_operation":str(uuid4()),"coffre_id":r["coffre_id"],"action":"lister","parametres":{}}
    assert p.post("/api/plugins/acp-poste/v1/coffre/operations",d).status_code==202
    delivered=p.post(C.ROUTE_RECLAMER,poll,jeton=r["jeton"]).json()["operation"]
    assert delivered["id_operation"]==d["id_operation"]
    result={"protocole":C.PROTOCOLE,"coffre_id":r["coffre_id"],"id_operation":d["id_operation"],
            "etat":"reussie","resultat":{"notes":[],"tronque":False},"erreur":None}
    assert p.post(C.ROUTE_RESULTAT,result,jeton=r["jeton"]).json()["deja"] is False
    assert p.post(C.ROUTE_RESULTAT,result,jeton=r["jeton"]).json()["deja"] is True
    assert p.post("/api/plugins/acp-poste/v1/coffre/revoquer",{
        "coffre_id":r["coffre_id"],"motif":"Fin du test"}).status_code==200
    refused=p.post(C.ROUTE_RECLAMER,poll,jeton=r["jeton"])
    assert refused.status_code==401 and refused.json()["detail"]["code"]=="coffre_revoque"
    assert conn.execute("SELECT etat FROM machines WHERE id=?",(machine,)).fetchone()[0]=="actif"


def _coffre_actif(pile):
    prefixe = "/api/plugins/acp-poste"
    code = pile.post(prefixe + "/v1/coffre/enrolement", {}).json()["code"]
    body = {"protocole": C.PROTOCOLE, "coffre_id": str(uuid4()), "alias": "acp", "version_bridge": "1.2.0"}
    response = pile.post(C.ROUTE_ENROLEMENT, body, jeton=code)
    assert response.status_code == 201, response.text
    r = response.json()
    assert pile.post(prefixe + "/v1/coffre/confirmer", {
        "coffre_id": r["coffre_id"], "empreinte": r["empreinte"]}).status_code == 200
    poll = {"protocole": C.PROTOCOLE, "coffre_id": r["coffre_id"], "capacites": list(C.ACTIONS), "attente_max_s": 0}
    assert pile.post(C.ROUTE_RECLAMER, poll, jeton=r["jeton"]).json()["etat"] == "actif"
    return r, poll


def test_http_auth_scopes_owner_origine_et_cycle_reel(pile_coffre):
    """Assertions HTTP déplacées de la suite host : vraie couture du Hermes épinglé, sans skip."""
    import hashlib
    import httpx

    p = pile_coffre
    prefixe = "/api/plugins/acp-poste"
    assert httpx.get(p.url + prefixe + "/v1/coffre", headers={"x-test-sans-session": "1"}).status_code == 401
    assert p.post(prefixe + "/v1/coffre/enrolement", {}, entetes={"Origin": "https://intrus.test"}).status_code == 403
    code = p.post(prefixe + "/v1/coffre/enrolement", {}).json()["code"]
    body = {"protocole": C.PROTOCOLE, "coffre_id": str(uuid4()), "alias": "acp", "version_bridge": "1.2.0"}
    assert p.post(C.ROUTE_ENROLEMENT, body).status_code == 401
    response = p.post(C.ROUTE_ENROLEMENT, body, jeton=code)
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    r = response.json()
    assert p.post(C.ROUTE_ENROLEMENT, body, jeton=r["jeton"]).status_code == 403
    poll = {"protocole": C.PROTOCOLE, "coffre_id": r["coffre_id"], "capacites": list(C.ACTIONS), "attente_max_s": 0}
    assert p.post(C.ROUTE_RECLAMER, poll, jeton=r["jeton"]).json()["etat"] == "a_confirmer"
    assert p.post(prefixe + "/v1/coffre/confirmer", {"coffre_id": r["coffre_id"], "empreinte": r["empreinte"]}).status_code == 200
    demande = {"id_operation": str(uuid4()), "coffre_id": r["coffre_id"], "action": "lire", "parametres": {"chemin": "note.md"}}
    assert p.post(prefixe + "/v1/coffre/operations", demande, jeton=r["jeton"], entetes={"x-test-sans-session": "1"}).status_code == 401
    assert p.post(prefixe + "/v1/coffre/operations", demande).status_code == 202
    assert p.post(C.ROUTE_RECLAMER, poll, jeton=r["jeton"]).json()["operation"]["id_operation"] == demande["id_operation"]
    result = {"protocole": C.PROTOCOLE, "coffre_id": r["coffre_id"], "id_operation": demande["id_operation"],
              "etat": "reussie", "resultat": {"chemin": "note.md", "contenu": "Bonjour", "octets": 7,
                                               "empreinte": hashlib.sha256(b"Bonjour").hexdigest()}, "erreur": None}
    assert p.post(C.ROUTE_RESULTAT, result, jeton=r["jeton"]).json()["deja"] is False
    assert p.get(prefixe + "/v1/coffre/operations/" + demande["id_operation"]).json()["etat"] == "reussie"
    assert p.post(prefixe + "/v1/coffre/revoquer", {"coffre_id": r["coffre_id"], "motif": "Test"}).status_code == 200
    refused = p.post(C.ROUTE_RECLAMER, poll, jeton=r["jeton"])
    assert refused.status_code == 401 and refused.json()["detail"]["code"] == "coffre_revoque"


def test_http_bornes_et_validation_ne_refletent_pas_le_contenu(pile_coffre):
    p = pile_coffre
    prefixe = "/api/plugins/acp-poste"
    assert p.post(prefixe + "/v1/coffre/enrolement", {"x": "a" * 65536}).status_code == 413
    r, _ = _coffre_actif(p)
    demande = {"id_operation": str(uuid4()), "coffre_id": r["coffre_id"], "action": "creer",
               "parametres": {"chemin": "a.md", "contenu": "a" * 131072}}
    assert p.post(prefixe + "/v1/coffre/operations", demande).status_code == 202
    assert p.post(prefixe + "/v1/coffre/operations", {"x": "a" * C.TAILLE_MAX_CORPS}).status_code == 413
    invalid = dict(demande, action="exec_secret_sentinel")
    response = p.post(prefixe + "/v1/coffre/operations", invalid)
    assert response.status_code == 400 and "exec_secret_sentinel" not in response.text
    assert p.get(prefixe + "/v1/coffre/operations/pas-un-uuid").status_code == 400


def test_long_poll_ne_livre_rien_apres_rotation_pendant_attente(pile_coffre, monkeypatch):
    import meta

    p = pile_coffre
    r, poll = _coffre_actif(p)
    c = meta.sous_module_noyau("coffres")
    base = meta.sous_module_noyau("base")
    origine, appels, suivante = c.reclamer, [], []

    def rotation_apres_premier_tick(conn, identifiant, demande, generation):
        appels.append(generation)
        response = origine(conn, identifiant, demande, generation)
        if len(appels) == 1:
            assert response["operation"] is None
            c.revoquer(conn, identifiant, "Rotation pendant attente", "proprietaire:test")
            code = c.creer_code(conn, "proprietaire:test")["code"]
            nouveau = c.enroler(conn, c.empreinte(code), C.Enrolement(protocole=C.PROTOCOLE,
                version_bridge="1.2.0", coffre_id=identifiant, alias="acp"))
            c.confirmer(conn, identifiant, nouveau["empreinte"], "proprietaire:test")
            origine(conn, identifiant, demande, c.empreinte(nouveau["jeton"]))
            d = C.DemandeOperation(id_operation=str(uuid4()), coffre_id=identifiant,
                                  action="lire", parametres={"chemin": "note.md"})
            suivante.append(d.id_operation)
            c.creer_operation(conn, d, "proprietaire:test")
        return response

    monkeypatch.setattr(c, "reclamer", rotation_apres_premier_tick)
    response = p.post(C.ROUTE_RECLAMER, dict(poll, attente_max_s=2), jeton=r["jeton"])
    assert response.status_code == 401 and response.json()["detail"]["code"] == "coffre_revoque"
    assert appels == [c.empreinte(r["jeton"])] * 2
    with base.connexion() as conn:
        assert c.operation(conn, suivante[0])["etat"] == "en_attente"
