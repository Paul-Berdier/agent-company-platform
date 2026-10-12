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
