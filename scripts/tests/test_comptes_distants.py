"""Contrôles SQLite/HTTP réels ; identité Hermes et compte fournisseur doublés.

Aucune connexion personnelle, aucun CLI et aucun service de production ne sont utilisés.
"""
from contextlib import contextmanager
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from acp_poste_contrat import comptes as C

GREFFON = Path(__file__).resolve().parents[2] / "hermes/plugins/acp-poste"
NOM = "_noyau_comptes_tests"
spec = importlib.util.spec_from_file_location(NOM, GREFFON / "noyau/__init__.py", submodule_search_locations=[str(GREFFON / "noyau")])
paquet = importlib.util.module_from_spec(spec)
sys.modules[NOM] = paquet
spec.loader.exec_module(paquet)
ka = ModuleType(NOM + ".kanban_adapter")
ka.masquer = lambda texte: texte
ka.VOIE_INTEGRATION = "poste-integration"
ka.VOIES_POSTE = ("poste-codex", "poste-claude")
sys.modules[ka.__name__] = ka
base = importlib.import_module(NOM + ".base")
c = importlib.import_module(NOM + ".comptes")
RefusACP = importlib.import_module(NOM + ".textes").RefusACP
MACHINE = "m" + "1" * 11


@pytest.fixture
def banc(tmp_path, monkeypatch):
    chemin = tmp_path / "comptes.db"
    horloge = [1000]
    @contextmanager
    def ouvrir():
        conn = sqlite3.connect(chemin, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()
    with ouvrir() as conn:
        base.migrer(conn)
        conn.execute("INSERT INTO machines (id,nom,empreinte_jeton,etat,protocole,version_poste,cree_le) VALUES (?,?,?,'actif','acp-machine/1','2.0.0',1000)", (MACHINE,"Serveur de test","1"*64))
        conn.execute("INSERT INTO inventaires (machine_id,recu_le,releve_le,empreinte,contenu) VALUES (?,1000,1000,'test',?)", (MACHINE,json.dumps({"poste":{"plateforme":"linux","hote":"railway"}})))
    monkeypatch.setattr(base, "connexion", ouvrir)
    monkeypatch.setattr(base, "maintenant", lambda: horloge[0])
    c._DEFIS.clear()
    instance = str(uuid4())
    with ouvrir() as conn:
        assert c.echanger(conn,MACHINE,C.Echange(instance_id=instance,libre=True))["operation"] is None
    return SimpleNamespace(ouvrir=ouvrir,horloge=horloge,instance=instance,chemin=chemin)


def creer(banc, cle=None):
    with banc.ouvrir() as conn:
        return c.creer(conn,cle or str(uuid4()),"proprietaire:test")


def echange(banc, *, observation=None, instance=None, libre=True):
    with banc.ouvrir() as conn:
        return c.echanger(conn,MACHINE,C.Echange(instance_id=instance or banc.instance,libre=libre,observation=observation))


def voir(banc,id):
    with banc.ouvrir() as conn:
        return c.lire(conn,id)


def observation(id,numero=1,etat="code_disponible",**champs):
    motifs={"code_disponible":"code","demarrage":"demarrage","verification":"verification","connecte":"connecte","annulee":"annulee","interrompue":"interrompue"}
    valeurs={"operation_id":id,"numero":numero,"etat":etat,"motif":motifs[etat]}
    if etat=="code_disponible":
        valeurs.update(verification_url=C.URL_CODEX,code_utilisateur="UNIT-TEST")
    if etat=="connecte":
        valeurs.update(compte_connecte=True)
    valeurs.update(champs)
    return C.Observation(**valeurs)


def test_idempotence_identite_unique_et_aucun_defi_persistant(banc):
    cle=str(uuid4())
    op=creer(banc,cle)
    assert creer(banc,cle)==op
    with pytest.raises(RefusACP,match="déjà en cours"):
        creer(banc)
    assert echange(banc)["operation"]["action"]=="demarrer"
    assert echange(banc)["operation"]["action"]=="attendre"
    obs=observation(op["id"])
    echange(banc,observation=obs)
    vue=voir(banc,op["id"])
    assert vue["code_utilisateur"]=="UNIT-TEST" and vue["verification_url"]==C.URL_CODEX
    with banc.ouvrir() as conn:
        assert c.etat(conn)["comptes"][0]["connexion"]==vue
        assert conn.execute("SELECT count(*) FROM machines").fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM ordres").fetchone()[0]==1
        dump="\n".join(conn.iterdump())
        assert "UNIT-TEST" not in dump and C.URL_CODEX not in dump
    # Redémarrage du dashboard : métadonnées persistantes, défi réémis seulement par le CLI vivant.
    c._DEFIS.clear()
    sans_defi = voir(banc,op["id"])
    assert sans_defi["code_utilisateur"] is None and sans_defi["verification_url"] is None
    assert sans_defi["etat"] == "code_disponible"
    assert "annulez cette demande puis relancez" in sans_defi["message"]
    assert "déjà autorisé" in sans_defi["message"]
    with banc.ouvrir() as conn:
        assert c.etat(conn)["comptes"][0]["connexion"] == sans_defi
        assert "\n".join(conn.iterdump()) == dump  # lecture seule : aucun nouveau login/ordre/état
    assert echange(banc,observation=obs)["operation"]["action"] == "attendre"
    assert voir(banc,op["id"])["code_utilisateur"]=="UNIT-TEST"
    assert voir(banc,op["id"])["message"] == c.MESSAGES["code"]


def test_reprise_executant_reconcilie_sans_login_et_exclut_double_instance(banc):
    op=creer(banc)
    echange(banc)
    nouveau=str(uuid4())
    with pytest.raises(RefusACP,match="autre instance"):
        echange(banc,instance=nouveau)
    banc.horloge[0]+=46
    assert echange(banc,instance=nouveau)["operation"]["action"]=="reconcilier"
    with pytest.raises(RefusACP):
        echange(banc,observation=observation(op["id"]))
    echange(banc,instance=nouveau,observation=observation(op["id"],etat="connecte"))
    assert voir(banc,op["id"])["compte_connecte"] is True
    assert voir(banc,op["id"])["inference_verifiee"] is False


def test_annulation_repetee_survit_reprise_et_reponse_tardive(banc):
    op=creer(banc)
    echange(banc)
    with banc.ouvrir() as conn:
        a=c.annuler(conn,op["id"],"proprietaire:test")
        assert c.annuler(conn,op["id"],"proprietaire:test")==a
    assert echange(banc,observation=observation(op["id"]))["operation"]["action"]=="annuler"
    assert voir(banc,op["id"])["code_utilisateur"] is None
    banc.horloge[0]+=46
    nouveau=str(uuid4())
    assert echange(banc,instance=nouveau)["operation"]["action"]=="annuler"
    echange(banc,instance=nouveau,observation=observation(op["id"],etat="annulee"))
    assert echange(banc,instance=nouveau,observation=observation(op["id"],numero=2,etat="connecte"))["operation"] is None
    assert voir(banc,op["id"])["etat"]=="annulee"


def test_annuler_avant_reclamation_ne_lance_rien_et_expiration_purge_code(banc):
    op=creer(banc)
    with banc.ouvrir() as conn:
        assert c.annuler(conn,op["id"],"proprietaire:test")["etat"]=="annulee"
    assert echange(banc)["operation"] is None
    op=creer(banc)
    echange(banc)
    echange(banc,observation=observation(op["id"]))
    banc.horloge[0]+=901
    assert echange(banc)["operation"] is None
    vue=voir(banc,op["id"])
    assert vue["etat"]=="expiree" and vue["code_utilisateur"] is None


def test_observations_ne_reculent_pas_et_terminal_ne_change_pas(banc):
    op=creer(banc)
    echange(banc)
    echange(banc,observation=observation(op["id"],numero=2))
    with pytest.raises(RefusACP):
        echange(banc,observation=observation(op["id"],numero=2,etat="connecte"))
    with pytest.raises(RefusACP):
        echange(banc,observation=observation(op["id"],numero=3,etat="demarrage"))
    echange(banc,observation=observation(op["id"],numero=1,etat="demarrage"))
    assert voir(banc,op["id"])["etat"]=="code_disponible"
    echange(banc,observation=observation(op["id"],numero=4,etat="connecte"))
    assert creer(banc,str(uuid4()))["etat"]=="en_attente"
    with banc.ouvrir() as conn:
        assert conn.execute("SELECT acquitte_le FROM ordres ORDER BY id LIMIT 1").fetchone()[0]==1000


def test_refuse_pc_revoque_absence_service_et_ne_promet_pas_inference(banc):
    with banc.ouvrir() as conn:
        etat=c.etat(conn)
        assert etat["serveur"]["disponible"] is True
        assert [x["implementation"] for x in etat["comptes"]]==["disponible","non_implemente","non_implemente"]
        assert all(x["inference_verifiee"] is False for x in etat["comptes"])
        conn.execute("UPDATE inventaires SET contenu=?",(json.dumps({"poste":{"plateforme":"windows","hote":"pc"}}),))
        assert c.etat(conn)["serveur"]["disponible"] is False
        with pytest.raises(RefusACP): c.creer(conn,str(uuid4()),"proprietaire:test")
        with pytest.raises(RefusACP): c.echanger(conn,MACHINE,C.Echange(instance_id=banc.instance,libre=True))
        conn.execute("UPDATE machines SET etat='revoque'")
        assert c.etat(conn)["serveur"]["disponible"] is False


@pytest.mark.parametrize("url",["https://evil.invalid/codex/device","http://auth.openai.com/codex/device",C.URL_CODEX+"?token=x","https://evil@auth.openai.com/codex/device",C.URL_CODEX+"#x"])
def test_defi_refuse_url_non_officielle(url):
    with pytest.raises(ValueError): observation(str(uuid4()),verification_url=url)


def test_http_auth_bornes_origine_et_poll_apres_reouverture(banc):
    # La CI Python minimale n’installe pas le serveur ; HTTP aussi obligatoire dans l’image Hermes.
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    spec=importlib.util.spec_from_file_location("_comptes_api_tests",GREFFON/"comptes_api.py")
    api=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    app=FastAPI()
    @app.middleware("http")
    async def identites(request,call_next):
        # Double explicite de l’authentification du dashboard ; jamais utilisé en produit.
        role=request.headers.get("x-test-role")
        if role=="machine": request.state.token_principal=SimpleNamespace(provider="acp-poste-machine",scopes=("machine",),principal="acp-poste:"+MACHINE)
        if role=="enrolement": request.state.token_principal=SimpleNamespace(provider="acp-poste-machine",scopes=("enrolement",),principal="acp-poste:"+MACHINE)
        return await call_next(request)
    app.include_router(api.creer_router(lambda nom:importlib.import_module(NOM+"."+nom), lambda r:"proprietaire:test" if r.headers.get("x-test-role")=="owner" else None, lambda:"https://acp.example"))
    with TestClient(app) as http:
        assert http.get("/v1/comptes").status_code==401
        assert http.post("/machine/v1/comptes",json={}).status_code==401
        assert http.post("/machine/v1/comptes",json={},headers={"x-test-role":"owner"}).status_code==401
        assert http.post("/machine/v1/comptes",json={},headers={"x-test-role":"enrolement"}).status_code==403
        h={"x-test-role":"owner"}
        route="/v1/comptes/codex/connexions"
        assert http.post(route,json={},headers=h|{"origin":"https://evil.invalid"}).status_code==403
        assert http.post(route,content="x",headers=h).status_code==415
        assert http.post(route,json={"x":"x"*4200},headers=h).status_code==413
        cle=str(uuid4())
        r=http.post(route,json={"idempotency_key":cle},headers=h)
        assert r.status_code==202, r.text
        assert r.headers["cache-control"]=="no-store"
        assert http.post(route,json={"idempotency_key":cle},headers=h).json()==r.json()
        assert http.get("/v1/comptes",headers=h).json()["comptes"][0]["connexion"]["id"]==r.json()["id"]
        assert http.get("/v1/comptes/connexions/invalid",headers=h).status_code==400
        assert http.get("/v1/comptes/connexions/"+str(uuid4()),headers=h).status_code==404
        reponse=http.post("/machine/v1/comptes",json={"instance_id":banc.instance,"libre":True},headers={"x-test-role":"machine"})
        assert reponse.status_code==200 and reponse.json()["operation"]["action"]=="demarrer"
        assert http.post("/v1/comptes/connexions/"+r.json()["id"]+"/annuler",json={},headers=h).json()["etat"]=="annulation_demandee"


def publier_inventaire(banc, inv):
    # Vrai réceptionnaire + validation + relevés séparés + SQLite ; seules l'identité
    # kanban et les données fournisseur restent factices dans ce banc sans Hermes.
    reception = importlib.import_module(NOM + ".inventaire")
    with banc.ouvrir() as conn:
        with base.transaction(conn):
            reception.recevoir_dans(conn, MACHINE, inv)
        contenu = json.loads(conn.execute("SELECT contenu FROM inventaires ORDER BY id DESC LIMIT 1").fetchone()[0])
        assert isinstance(contenu["releves"], dict) and "alertes" in contenu


def inventaire_compte():
    return json.loads((GREFFON.parents[1]/"tests/outils/fixtures_machine/inventaire_requete_linux.json").read_text(encoding="utf-8"))


def test_projection_inventaire_recu_et_logout_remplace_connexion_recente(banc):
    op=creer(banc)
    echange(banc)
    echange(banc,observation=observation(op["id"],etat="connecte"))
    inv=inventaire_compte()
    publier_inventaire(banc,inv)
    # Réouverture SQLite et perte des défis éphémères : le relevé persistant suffit.
    c._DEFIS.clear()
    with banc.ouvrir() as conn:
        vue=c.etat(conn)["comptes"][0]
        assert vue["compte_connecte"] is True and vue["version"]=="0.156.1"
        assert len(vue["modeles"])==2 and vue["observation"]["quotas"][0]["windows"][0]["used_percent"]==41
        assert vue["observation"]["etat"]=="a_jour" and vue["observation"]["origine_modeles"]=="compte"
        assert vue["inference_verifiee"] is False
    banc.horloge[0]+=1
    inv["connexions"]["codex"]="non_connecte"
    publier_inventaire(banc,inv)
    with banc.ouvrir() as conn:
        vue=c.etat(conn)["comptes"][0]
        assert vue["compte_connecte"] is False and vue["modeles"]==[]
        assert vue["etat"]=="non_configure" and vue["observation"]["connexion"]=="non_connecte"
        # Le succès historique reste consultable sans supplanter le nouvel inventaire.
        assert vue["connexion"]["compte_connecte"] is True
        banc.horloge[0]+=7201
        vue=c.etat(conn)["comptes"][0]
        assert vue["compte_connecte"] is None and vue["observation"]["etat"]=="perime"


def test_projection_catalogue_embarque_ne_promet_pas_modeles_de_compte(banc):
    inv=inventaire_compte()
    inv["releves"][0]["origine_liste"]="catalogue_embarque"
    publier_inventaire(banc,inv)
    with banc.ouvrir() as conn:
        vue=c.etat(conn)["comptes"][0]
        assert vue["compte_connecte"] is True and vue["modeles"]==[]
        assert vue["observation"]["origine_modeles"]=="catalogue_embarque"
        assert vue["inference_verifiee"] is False


@pytest.mark.parametrize("alterer", ["absent", "autre_machine", "autre_voie"])
def test_projection_refuse_reference_de_releve_incoherente(banc,alterer):
    publier_inventaire(banc,inventaire_compte())
    with banc.ouvrir() as conn:
        if alterer=="absent": conn.execute("DELETE FROM releves WHERE voie='poste-codex'")
        elif alterer=="autre_machine": conn.execute("UPDATE releves SET machine_id=NULL WHERE voie='poste-codex'")
        else: conn.execute("UPDATE releves SET voie='poste-claude' WHERE voie='poste-codex'")
        vue=c.etat(conn)["comptes"][0]
        assert vue["compte_connecte"] is None and vue["modeles"]==[]
        assert vue["observation"]["etat"]=="inconnu"
