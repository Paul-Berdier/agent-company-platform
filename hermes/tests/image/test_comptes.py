"""Couture machine Hermes réelle ; compte et inventaire factices, aucune auth fournisseur."""
from uuid import uuid4
import pytest
from acp_poste_contrat import comptes as C
from conftest import inventaire_linux, poste_confirme

P = "/api/plugins/acp-poste"


@pytest.fixture
def pile_comptes(pile_machine):
    # Le fixture commun monte les dix routes, comme le registre produit.
    return pile_machine


def test_couture_auth_et_cycle_comptes_reels(pile_comptes,noyau,conn):
    import httpx
    p=pile_comptes
    route=P+"/v1/comptes/codex/connexions"
    assert httpx.get(p.url+P+"/v1/comptes",headers={"x-test-sans-session":"1"}).status_code==401
    assert p.post(C.ROUTE_MACHINE,{}).status_code==401
    assert p.post(route,{},entetes={"Origin":"https://intrus.test"}).status_code==403
    code=noyau.machines.creer_code(conn,"proprietaire:test")["code"]
    assert p.post(C.ROUTE_MACHINE,{"instance_id":str(uuid4()),"libre":True},jeton=code).status_code==403
    machine,jeton=poste_confirme(noyau,conn,nom="Serveur Linux factice")
    assert p.post(P+"/machine/v1/inventaire",inventaire_linux(),jeton=jeton).status_code==200
    corps={"instance_id":str(uuid4()),"libre":True}
    assert p.post(C.ROUTE_MACHINE,corps,jeton=jeton).status_code==200
    # La route d'inventaire a réellement séparé les relevés et ajouté les alertes.
    compte=p.get(P+"/v1/comptes").json()["comptes"][0]
    assert compte["compte_connecte"] is True and compte["version"]=="0.156.1"
    assert compte["observation"]["etat"]=="a_jour" and compte["observation"]["origine_modeles"]=="compte"
    assert len(compte["modeles"])==2 and compte["observation"]["quotas"]
    # Le relevé demandé autorise une nouvelle publication sans attendre la cadence.
    noyau.ordres.creer(conn,machine,"releve","proprietaire:test")
    deconnecte=inventaire_linux()
    deconnecte["connexions"]["codex"]="non_connecte"
    assert p.post(P+"/machine/v1/inventaire",deconnecte,jeton=jeton).status_code==200
    compte=p.get(P+"/v1/comptes").json()["comptes"][0]
    assert compte["compte_connecte"] is False and compte["etat"]=="non_configure"
    assert compte["observation"]["connexion"]=="non_connecte" and compte["modeles"]==[]
    assert p.post(route,{"idempotency_key":str(uuid4())},jeton=jeton,entetes={"x-test-sans-session":"1"}).status_code==401
    cle=str(uuid4())
    r=p.post(route,{"idempotency_key":cle})
    assert r.status_code==202 and r.headers["cache-control"]=="no-store"
    op=r.json()
    assert p.post(route,{"idempotency_key":cle}).json()==op
    assert p.post(C.ROUTE_MACHINE,corps,jeton=jeton).json()["operation"]["action"]=="demarrer"
    obs={"operation_id":op["id"],"moteur":"codex","defi_id":str(uuid4()),"defi_type":"codex_device","numero":1,"etat":"code_disponible","motif":"code","verification_url":C.URL_CODEX,"code_utilisateur":"UNIT-TEST"}
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":obs},jeton=jeton).status_code==200
    vue=p.get(P+"/v1/comptes").json()["comptes"][0]
    assert vue["connexion"]["code_utilisateur"]=="UNIT-TEST" and vue["inference_verifiee"] is False
    assert "UNIT-TEST" not in "\n".join(conn.iterdump())
    assert p.post(P+"/v1/comptes/connexions/"+op["id"]+"/annuler",{}).json()["etat"]=="annulation_demandee"
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":obs},jeton=jeton).json()["operation"]["action"]=="annuler"


def test_bornes_erreurs_sans_reflet_et_machine_windows_refusee(pile_comptes,noyau,conn):
    from conftest import inventaire_factice
    p=pile_comptes
    _,jeton=poste_confirme(noyau,conn)
    assert p.post(P+"/machine/v1/inventaire",inventaire_factice(),jeton=jeton).status_code==200
    route=P+"/v1/comptes/codex/connexions"
    assert p.post(route,{"x":"x"*5000}).status_code==413
    assert p.post(C.ROUTE_MACHINE,{"instance_id":str(uuid4()),"libre":True},jeton=jeton).status_code==409
    r=p.post(route,{"idempotency_key":"sentinelle-privee"})
    assert r.status_code==400 and "sentinelle-privee" not in r.text
    assert p.post(route,{"idempotency_key":str(uuid4())}).status_code==409


def test_couture_claude_remise_code_ack_et_compte_ancien_sur_annulation(pile_comptes,noyau,conn):
    # Routes/auth/SQLite Hermes réels ; seul le dialogue fournisseur est simulé.
    p=pile_comptes
    _,jeton=poste_confirme(noyau,conn,nom="Serveur Claude factice")
    assert p.post(P+"/machine/v1/inventaire",inventaire_linux(),jeton=jeton).status_code==200
    corps={"instance_id":str(uuid4()),"libre":True}
    assert p.post(C.ROUTE_MACHINE,corps,jeton=jeton).status_code==200
    route=P+"/v1/comptes/claude/connexions"
    cle=str(uuid4())
    assert p.post(route,{"idempotency_key":cle},jeton=jeton,entetes={"x-test-sans-session":"1"}).status_code==401
    assert p.post(route,{"idempotency_key":cle},entetes={"Origin":"https://intrus.test"}).status_code==403
    r=p.post(route,{"idempotency_key":cle})
    assert r.status_code==202 and r.headers["cache-control"]=="no-store"
    op=r.json()
    assert op["moteur"]=="claude_code"
    assert p.post(route,{"idempotency_key":cle}).json()==op
    assert p.post(P+"/v1/comptes/codex/connexions",{"idempotency_key":cle}).status_code==409
    commande=p.post(C.ROUTE_MACHINE,corps,jeton=jeton).json()["operation"]
    assert commande["moteur"]=="claude_code" and commande["action"]=="demarrer"
    defi,soumission=str(uuid4()),str(uuid4())
    url=C.URL_CLAUDE+"?state=ETAT-FACTICE&code_challenge=DEFI-FACTICE"
    obs={"operation_id":op["id"],"moteur":"claude_code","numero":1,"etat":"code_disponible","motif":"code",
         "defi_id":defi,"defi_type":"claude_oauth_code","verification_url":url}
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":obs},jeton=jeton).status_code==200
    connexion=P+"/v1/comptes/connexions/"+op["id"]
    retour={"defi_id":defi,"soumission_id":soumission,"code":"RETOUR-FACTICE#ETAT-FACTICE"}
    assert p.post(connexion+"/code",retour,entetes={"Origin":"https://intrus.test"}).status_code==403
    r=p.post(connexion+"/code",retour)
    assert r.status_code==202 and r.headers["cache-control"]=="no-store"
    assert r.json()["reception_code"]["etat"]=="en_attente" and retour["code"] not in r.text
    assert p.post(connexion+"/code",retour).json()==r.json()
    assert p.get(connexion).json()["reception_code"]==r.json()["reception_code"]
    assert p.get(connexion+"?defi_id="+defi+"&soumission_id="+soumission).json()["reception_code"]==r.json()["reception_code"]
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":obs},jeton=jeton).json()["operation"]["retour_code"]==retour
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":obs},jeton=jeton).json()["operation"]["action"]=="fournir_code"
    ack={"operation_id":op["id"],"moteur":"claude_code","numero":2,"etat":"verification","motif":"verification",
         "code_transmis":{"defi_id":defi,"soumission_id":soumission}}
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":ack},jeton=jeton).json()["operation"]["action"]=="attendre"
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":ack},jeton=jeton).json()["operation"]["retour_code"] is None
    assert p.get(connexion).json()["reception_code"]["etat"]=="transmis"
    dump="\n".join(conn.iterdump())
    assert retour["code"] not in dump and url not in dump and "DEFI-FACTICE" not in dump
    assert p.post(connexion+"/annuler",{}).json()["etat"]=="annulation_demandee"
    fin=ack|{"numero":3,"etat":"annulee","motif":"annulee","compte_connecte":True}
    assert p.post(C.ROUTE_MACHINE,corps|{"observation":fin},jeton=jeton).json()["operation"] is None
    vue=p.get(connexion).json()
    assert vue["etat"]=="annulee" and vue["compte_connecte"] is True
    assert vue["verification_url"] is None and vue["reception_code"]["etat"]=="transmis"
