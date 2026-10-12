"""File coffre réelle SQLite et façade HTTP : reprise, autorisation, bornes, aucun accès aux notes."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from acp_poste_contrat import coffre as C

RACINE = Path(__file__).resolve().parents[2]
NOYAU = RACINE / "hermes/plugins/acp-poste/noyau"
NOM = "_noyau_coffre_tests"
spec = importlib.util.spec_from_file_location(NOM, NOYAU / "__init__.py", submodule_search_locations=[str(NOYAU)])
paquet = importlib.util.module_from_spec(spec)
sys.modules[NOM] = paquet
spec.loader.exec_module(paquet)
ka = ModuleType(NOM + ".kanban_adapter")
ka.masquer = lambda texte: texte
sys.modules[ka.__name__] = ka
base = importlib.import_module(NOM + ".base")
c = importlib.import_module(NOM + ".coffres")
RefusACP = importlib.import_module(NOM + ".textes").RefusACP
# Seul l'adaptateur Hermes est doublé ici ; la file, SQLite, les modèles et les routes sont réels.
aa = ModuleType(NOM + ".auth_adapter")
aa.DashboardAuthProvider = object
aa.ProviderError = type("ProviderError", (Exception,), {})
@dataclass
class Principal:
    principal: str
    provider: str
    scopes: tuple

aa.TokenPrincipal = Principal
aa.register_token_route = lambda route: None
sys.modules[aa.__name__] = aa
j = importlib.import_module(NOM + ".jeton_coffre")
api_spec = importlib.util.spec_from_file_location("_api_coffre_tests", NOYAU.parent / "coffre_api.py")
api = importlib.util.module_from_spec(api_spec)
api_spec.loader.exec_module(api)


@pytest.fixture
def bdd(tmp_path, monkeypatch):
    chemin = tmp_path / "coffre.db"
    horloge = [1000]
    @contextmanager
    def ouvrir():
        conn = sqlite3.connect(chemin, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()
    with ouvrir() as conn:
        base.migrer(conn)
    monkeypatch.setattr(base, "connexion", ouvrir)
    monkeypatch.setattr(base, "chemin_base", lambda: chemin)
    monkeypatch.setattr(base, "maintenant", lambda: horloge[0])
    return SimpleNamespace(ouvrir=ouvrir, horloge=horloge, chemin=chemin)


def _generation(conn, identifiant):
    row=conn.execute("SELECT empreinte_jeton FROM coffres_identites WHERE id=?",(identifiant,)).fetchone()
    return row[0] if row else "0"*64


def reclamer(conn, identifiant, demande):
    return c.reclamer(conn, identifiant, demande, _generation(conn,identifiant))


def resultat(conn, identifiant, demande):
    return c.resultat(conn, identifiant, demande, _generation(conn,identifiant))


def preparer(conn, *, confirmer=True, capacites=C.ACTIONS):
    code = c.creer_code(conn, "proprietaire:test")["code"]
    r = c.enroler(conn, c.empreinte(code), C.Enrolement(protocole=C.PROTOCOLE, version_bridge="1.2.0",
                                                      coffre_id=str(uuid4()), alias="acp"))
    if confirmer:
        c.confirmer(conn, r["coffre_id"], r["empreinte"], "proprietaire:test")
    demande = C.RequeteReclamer(protocole=C.PROTOCOLE, coffre_id=r["coffre_id"], capacites=list(capacites))
    reclamer(conn, r["coffre_id"], demande)
    return r, demande


def nouvelle(id, action="lire", parametres=None):
    return C.DemandeOperation(id_operation=str(uuid4()), coffre_id=id, action=action,
                             parametres=parametres if parametres is not None else {"chemin":"note.md"})


def rendu(d, *, conflit=False):
    r={"protocole":C.PROTOCOLE, "coffre_id":d.coffre_id, "id_operation":d.id_operation, "etat":"refusee" if conflit else "reussie"}
    if conflit:
        r["erreur"]={"code":"conflit", "message":"La note a changé ; relisez-la."}
    else:
        r["resultat"]={"chemin":"note.md","contenu":"Bonjour","empreinte":c.empreinte("Bonjour"),"octets":7}
    return C.Resultat(**r)


def test_enrolement_hash_seul_unique_expire_confirme_separe_des_machines(bdd):
    with bdd.ouvrir() as conn:
        assert c.etat(conn)["etat"] == "non_configure"
        code = c.creer_code(conn, "proprietaire:test")["code"]
        provider = j.FournisseurCoffre()
        assert provider.verify_token(token=code).scopes == ("coffre_enrolement",)
        d = C.Enrolement(protocole=C.PROTOCOLE,version_bridge="1.2.0",coffre_id=str(uuid4()),alias="acp")
        r=c.enroler(conn,c.empreinte(code),d)
        assert provider.verify_token(token=code) is None
        assert provider.verify_token(token=r["jeton"]).principal == "coffre:"+d.coffre_id+":"+c.empreinte(r["jeton"])
        with pytest.raises(RefusACP,match="déjà utilisé"):
            c.enroler(conn,c.empreinte(code),d)
        with pytest.raises(RefusACP,match="diffère"):
            c.confirmer(conn,d.coffre_id,"FFFF-FFFF","proprietaire:test")
        assert c.etat(conn)["etat"] == "a_confirmer"
        assert c.confirmer(conn,d.coffre_id,r["empreinte"],"proprietaire:test")["etat"] == "hors_ligne"
        assert conn.execute("SELECT count(*) FROM machines").fetchone()[0] == 0
        dump="\n".join(conn.iterdump())
        assert code not in dump and r["jeton"] not in dump
        with pytest.raises(RefusACP):
            c.creer_code(conn,"proprietaire:test")
        c.revoquer(conn,d.coffre_id,"Test","proprietaire:test")
        # Reconnu uniquement pour rendre une révocation explicite ; aucune route ne sert une identité révoquée.
        assert provider.verify_token(token=r["jeton"])
        with pytest.raises(RefusACP, match="révoqué"):
            reclamer(conn,d.coffre_id,C.RequeteReclamer(protocole=C.PROTOCOLE,coffre_id=d.coffre_id,capacites=[]))
        code2=c.creer_code(conn,"proprietaire:test")["code"]
        bdd.horloge[0]+=601
        assert provider.verify_token(token=code2) is None


def test_reprise_enveloppe_identique_et_resultat_idempotent(bdd):
    with bdd.ouvrir() as conn:
        r, poll=preparer(conn)
        d=nouvelle(r["coffre_id"])
        debut=c.creer_operation(conn,d,"proprietaire:test")
        assert c.creer_operation(conn,d,"proprietaire:test")==debut
        with pytest.raises(RefusACP,match="autre demande"):
            c.creer_operation(conn,d.model_copy(update={"parametres":{"chemin":"autre.md"}}),"proprietaire:test")
        livraison=reclamer(conn,r["coffre_id"],poll)["operation"]
        bdd.horloge[0]+=20
        assert reclamer(conn,r["coffre_id"],poll)["operation"]==livraison
        reponse=rendu(d)
        assert resultat(conn,r["coffre_id"],reponse)["deja"] is False
        assert resultat(conn,r["coffre_id"],reponse)["deja"] is True
        with pytest.raises(RefusACP,match="résultat différent"):
            resultat(conn,r["coffre_id"],rendu(d,conflit=True))
        assert c.operation(conn,d.id_operation)["resultat"]["contenu"]=="Bonjour"
        assert reclamer(conn,r["coffre_id"],poll)["operation"] is None
        assert conn.execute("SELECT parametres FROM coffres_operations").fetchone()[0] is None


def test_expiration_livree_indeterminee_resultat_tardif_et_purge(bdd):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn)
        livree,attente=nouvelle(r["coffre_id"]),nouvelle(r["coffre_id"])
        for d in (livree,attente): c.creer_operation(conn,d,"proprietaire:test")
        reclamer(conn,r["coffre_id"],poll)
        bdd.horloge[0]+=601
        assert c.operation(conn,livree.id_operation)["etat"]=="indeterminee"
        assert c.operation(conn,attente.id_operation)["etat"]=="expiree"
        assert reclamer(conn,r["coffre_id"],poll)["operation"] is None
        resultat(conn,r["coffre_id"],rendu(livree))
        assert c.operation(conn,livree.id_operation)["etat"]=="reussie"
        bdd.horloge[0]+=3601
        p=c.operation(conn,livree.id_operation)
        assert p["etat"]=="expiree" and p["resultat"] is None
        bdd.horloge[0]+=86401
        with pytest.raises(RefusACP,match="Aucune opération"):
            resultat(conn,r["coffre_id"],rendu(livree))


def test_conflit_reel_preserve_erreur_et_presence_perime(bdd):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn)
        d=nouvelle(r["coffre_id"],"ecrire",{"chemin":"note.md","contenu":"Version locale","empreinte_attendue":"0"*64})
        c.creer_operation(conn,d,"proprietaire:test")
        reclamer(conn,r["coffre_id"],poll)
        resultat(conn,r["coffre_id"],rendu(d,conflit=True))
        p=c.operation(conn,d.id_operation)
        assert p["etat"]=="refusee" and p["erreur"]["code"]=="conflit" and p["resultat"] is None
        assert c.etat(conn)["etat"]=="pret"
        bdd.horloge[0]+=76
        assert c.etat(conn)["etat"]=="hors_ligne"


def test_capacites_file_bornee_et_revocation(bdd):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn,capacites=["lire"])
        with pytest.raises(RefusACP,match="capacité"):
            c.creer_operation(conn,nouvelle(r["coffre_id"],"graphe",{}),"proprietaire:test")
        ids=[]
        for _ in range(32):
            d=nouvelle(r["coffre_id"]); ids.append(d.id_operation); c.creer_operation(conn,d,"proprietaire:test")
        with pytest.raises(RefusACP,match="32 opérations"):
            c.creer_operation(conn,nouvelle(r["coffre_id"]),"proprietaire:test")
        reclamer(conn,r["coffre_id"],poll)
        c.revoquer(conn,r["coffre_id"],"Révoqué par propriétaire","proprietaire:test")
        assert c.operation(conn,ids[0])["etat"]=="indeterminee"
        assert c.operation(conn,ids[1])["etat"]=="refusee"


def test_resultat_non_livre_et_autre_identite_refuses(bdd):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn); d=nouvelle(r["coffre_id"]); c.creer_operation(conn,d,"proprietaire:test")
        with pytest.raises(RefusACP,match="Aucune opération"):
            resultat(conn,r["coffre_id"],rendu(d))
        with pytest.raises(RefusACP,match="pas celui"):
            resultat(conn,str(uuid4()),rendu(d))
        with pytest.raises(RefusACP,match="pas celui"):
            reclamer(conn,str(uuid4()),poll)


@pytest.mark.parametrize("secret", ["acpct_"+"Z"*43,"acpce_"+"Y"*43,"sk-ant-"+"X"*30])
def test_secrets_non_persists_dans_notes_et_resultats(bdd,secret):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn)
        with pytest.raises(RefusACP,match="secret"):
            c.creer_operation(conn,nouvelle(r["coffre_id"],"creer",{"chemin":"a.md","contenu":secret}),"proprietaire:test")
        d=nouvelle(r["coffre_id"]); c.creer_operation(conn,d,"proprietaire:test"); reclamer(conn,r["coffre_id"],poll)
        reponse=rendu(d).model_copy(update={"resultat":{"chemin":"note.md","contenu":secret,"empreinte":c.empreinte(secret),"octets":len(secret)}})
        assert resultat(conn,r["coffre_id"],reponse)["deja"] is False
        assert resultat(conn,r["coffre_id"],reponse)["deja"] is True
        projection=c.operation(conn,d.id_operation)
        assert projection["etat"]=="refusee" and projection["erreur"]["code"]=="secret" and projection["resultat"] is None
        assert reclamer(conn,r["coffre_id"],poll)["operation"] is None
        assert secret not in "\n".join(conn.iterdump())


@pytest.fixture
def http(bdd):
    app=FastAPI()
    provider=j.FournisseurCoffre()
    @app.middleware("http")
    async def identites(request:Request,suivant):
        # Double de la couture Hermes, jamais une identité présumée dans la route testée.
        auth=request.headers.get("authorization","")
        if auth.startswith("Bearer "):
            token=auth[7:]
            request.state.token_principal = Principal("acp-poste:test","acp-poste-machine",("machine",)) if token=="machine-test" else provider.verify_token(token=token)
        return await suivant(request)
    app.include_router(api.creer_router(lambda nom:importlib.import_module(NOM+"."+nom),
        lambda req:"proprietaire:test" if req.headers.get("x-session")=="owner" else None,
        lambda:"https://hermes.test"))
    with TestClient(app) as client: yield client


def test_http_auth_scopes_owner_origine_et_cycle_reel(http):
    owner={"x-session":"owner"}
    assert http.get("/v1/coffre").status_code==401
    assert http.post("/v1/coffre/enrolement",headers=dict(owner,origin="https://intrus.test"),json={}).status_code==403
    code=http.post("/v1/coffre/enrolement",headers=owner,json={}).json()["code"]
    body={"protocole":C.PROTOCOLE,"coffre_id":str(uuid4()),"alias":"acp","version_bridge":"1.2.0"}
    for token,status in ((None,401),("machine-test",403)):
        headers=owner if token is None else {"authorization":"Bearer "+token}
        assert http.post("/coffre/v1/enrolement",headers=headers,json=body).status_code==status
    r=http.post("/coffre/v1/enrolement",headers={"authorization":"Bearer "+code},json=body)
    assert r.status_code==201 and r.headers["cache-control"]=="no-store"
    r=r.json(); token={"authorization":"Bearer "+r["jeton"]}
    assert http.post("/coffre/v1/enrolement",headers=token,json=body).status_code==403
    poll={"protocole":C.PROTOCOLE,"coffre_id":r["coffre_id"],"capacites":list(C.ACTIONS)}
    assert http.post("/coffre/v1/reclamer",headers=token,json=poll).json()["etat"]=="a_confirmer"
    assert http.post("/v1/coffre/confirmer",headers=owner,json={"coffre_id":r["coffre_id"],"empreinte":r["empreinte"]}).status_code==200
    d=nouvelle(r["coffre_id"])
    assert http.post("/v1/coffre/operations",headers=token,json=d.model_dump()).status_code==401
    assert http.post("/v1/coffre/operations",headers=owner,json=d.model_dump()).status_code==202
    assert http.post("/coffre/v1/reclamer",headers=token,json=poll).json()["operation"]["id_operation"]==d.id_operation
    assert http.post("/coffre/v1/resultat",headers=token,json=rendu(d).model_dump()).json()["deja"] is False
    assert http.get("/v1/coffre/operations/"+d.id_operation,headers=owner).json()["etat"]=="reussie"
    assert http.post("/v1/coffre/revoquer",headers=owner,json={"coffre_id":r["coffre_id"],"motif":"Test"}).status_code==200
    refused=http.post("/coffre/v1/reclamer",headers=token,json=poll)
    assert refused.status_code==401 and refused.json()["detail"]["code"]=="coffre_revoque"


def test_http_bornes_et_validation_ne_refletent_pas_le_contenu(http,bdd):
    owner={"x-session":"owner"}
    assert http.post("/v1/coffre/enrolement",headers=owner,json={"x":"a"*65536}).status_code==413
    with bdd.ouvrir() as conn:r,_=preparer(conn)
    d=nouvelle(r["coffre_id"],"creer",{"chemin":"a.md","contenu":"a"*131072})
    assert http.post("/v1/coffre/operations",headers=owner,json=d.model_dump()).status_code==202
    assert http.post("/v1/coffre/operations",headers=owner,json={"x":"a"*C.TAILLE_MAX_CORPS}).status_code==413
    invalid=d.model_dump(); invalid["action"]="exec_secret_sentinel"
    response=http.post("/v1/coffre/operations",headers=owner,json=invalid)
    assert response.status_code==400 and "exec_secret_sentinel" not in response.text
    assert http.get("/v1/coffre/operations/pas-un-uuid",headers=owner).status_code==400


@pytest.mark.parametrize("deja_confirme", [False, True])
def test_reassociation_par_code_neuf_conserve_coffre_et_invalide_ancien_token(bdd,deja_confirme):
    with bdd.ouvrir() as conn:
        r,_=preparer(conn,confirmer=deja_confirme)
        if deja_confirme:
            c.revoquer(conn,r["coffre_id"],"Nouvelle association","proprietaire:test")
        code=c.creer_code(conn,"proprietaire:test")["code"]
        nouveau=c.enroler(conn,c.empreinte(code),C.Enrolement(protocole=C.PROTOCOLE,version_bridge="1.2.0",
            coffre_id=r["coffre_id"],alias="acp"))
        assert nouveau["coffre_id"]==r["coffre_id"] and nouveau["jeton"]!=r["jeton"]
        assert j.FournisseurCoffre().verify_token(token=r["jeton"]) is None
        assert j.FournisseurCoffre().verify_token(token=nouveau["jeton"])
        assert c.etat(conn)["etat"]=="a_confirmer"
        assert conn.execute("SELECT count(*) FROM coffres_identites").fetchone()[0]==1
        c.confirmer(conn,nouveau["coffre_id"],nouveau["empreinte"],"proprietaire:test")
        assert c.etat(conn)["etat"]=="hors_ligne"


def test_requete_authentifiee_avant_rotation_ne_reprend_pas_les_droits(bdd):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn)
        ancienne_generation=c.empreinte(r["jeton"])
        ancien_principal=j.FournisseurCoffre().verify_token(token=r["jeton"])
        d=nouvelle(r["coffre_id"]); c.creer_operation(conn,d,"proprietaire:test")
        c.reclamer(conn,r["coffre_id"],poll,ancienne_generation)
        c.revoquer(conn,r["coffre_id"],"Rotation","proprietaire:test")
        code=c.creer_code(conn,"proprietaire:test")["code"]
        nouveau=c.enroler(conn,c.empreinte(code),C.Enrolement(protocole=C.PROTOCOLE,version_bridge="1.2.0",
            coffre_id=r["coffre_id"],alias="acp"))
        c.confirmer(conn,r["coffre_id"],nouveau["empreinte"],"proprietaire:test")
        nouveau_hash=c.empreinte(nouveau["jeton"])
        c.reclamer(conn,r["coffre_id"],poll,nouveau_hash)
        suivante=nouvelle(r["coffre_id"]); c.creer_operation(conn,suivante,"proprietaire:test")
        # Requête déjà passée par verify_token avant rotation : son principal garde l'ancienne génération.
        assert ancien_principal.principal.endswith(":"+ancienne_generation)
        with pytest.raises(RefusACP,match="remplacée"):
            c.reclamer(conn,r["coffre_id"],poll,ancienne_generation)
        with pytest.raises(RefusACP,match="remplacée"):
            c.resultat(conn,r["coffre_id"],rendu(d),ancienne_generation)
        assert c.operation(conn,suivante.id_operation)["etat"]=="en_attente"
        assert c.reclamer(conn,r["coffre_id"],poll,nouveau_hash)["operation"]["id_operation"]==suivante.id_operation


def test_long_poll_ne_livre_rien_apres_rotation_pendant_attente(http,bdd,monkeypatch):
    with bdd.ouvrir() as conn:
        r,poll=preparer(conn)
    origine=c.reclamer
    appels=[]
    suivante=[]
    def rotation_apres_premier_tick(conn,identifiant,demande,generation):
        appels.append(generation)
        response=origine(conn,identifiant,demande,generation)
        if len(appels)==1:
            assert response["operation"] is None
            c.revoquer(conn,identifiant,"Rotation pendant attente","proprietaire:test")
            code=c.creer_code(conn,"proprietaire:test")["code"]
            nouveau=c.enroler(conn,c.empreinte(code),C.Enrolement(protocole=C.PROTOCOLE,
                version_bridge="1.2.0",coffre_id=identifiant,alias="acp"))
            c.confirmer(conn,identifiant,nouveau["empreinte"],"proprietaire:test")
            origine(conn,identifiant,demande,c.empreinte(nouveau["jeton"]))
            d=nouvelle(identifiant); suivante.append(d.id_operation)
            c.creer_operation(conn,d,"proprietaire:test")
        return response
    monkeypatch.setattr(c,"reclamer",rotation_apres_premier_tick)
    response=http.post("/coffre/v1/reclamer",headers={"authorization":"Bearer "+r["jeton"]},
                       json=poll.model_copy(update={"attente_max_s":2}).model_dump())
    assert response.status_code==401 and response.json()["detail"]["code"]=="coffre_revoque"
    assert appels==[c.empreinte(r["jeton"])]*2
    with bdd.ouvrir() as conn:
        assert c.operation(conn,suivante[0])["etat"]=="en_attente"
