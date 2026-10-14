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
from uuid import NAMESPACE_URL, uuid4, uuid5

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
    c._CODES.clear()
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
    valeurs={"operation_id":id,"moteur":"codex","numero":numero,"etat":etat,"motif":motifs[etat]}
    if etat=="code_disponible":
        valeurs.update(verification_url=C.URL_CODEX,code_utilisateur="UNIT-TEST",defi_id=str(uuid5(NAMESPACE_URL,id)),defi_type="codex_device")
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
        assert [x["implementation"] for x in etat["comptes"]]==["disponible","disponible","non_implemente"]
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


# Fournisseur et identité doublés ; SQLite, routes et contrat restent réels.
URL_CLAUDE_FACTICE = C.URL_CLAUDE + "?state=ETAT-FACTICE&code_challenge=DEFI-FACTICE"
CODE_FACTICE = "RETOUR-TEST-SANS-VALEUR#ETAT-FACTICE"


def claude(banc):
    with banc.ouvrir() as conn:
        op = c.creer(conn, str(uuid4()), "proprietaire:test", "claude_code")
    commande = echange(banc)["operation"]
    assert C.Commande.model_validate(commande).moteur == "claude_code"
    defi = str(uuid4())
    obs = C.Observation(operation_id=op["id"], moteur="claude_code", numero=1,
                        etat="code_disponible", motif="code", defi_id=defi, defi_type="claude_oauth_code",
                        verification_url=URL_CLAUDE_FACTICE)
    echange(banc, observation=obs)
    return op, defi, obs


def soumettre(banc, op, defi, soumission=None, code=CODE_FACTICE):
    soumission = soumission or str(uuid4())
    with banc.ouvrir() as conn:
        return c.soumettre_code(conn, op["id"], defi, soumission, code, "proprietaire:test")


def test_claude_remise_ack_repetitions_et_aucun_secret_persistant(banc):
    op, defi, obs = claude(banc)
    soumission = str(uuid4())
    avant = voir(banc, op["id"])
    assert avant["defi_id"] == defi and avant["defi_type"] == "claude_oauth_code"
    assert avant["code_utilisateur"] is None and avant["reception_code"] is None
    vue = soumettre(banc, op, defi, soumission)
    assert vue["reception_code"] == {"defi_id": defi, "soumission_id": soumission, "etat": "en_attente"}
    assert CODE_FACTICE not in json.dumps(vue)
    assert soumettre(banc, op, defi, soumission) == vue
    # Une réponse HTTP perdue ne réécrit ni ne remplace le code en mémoire.
    with pytest.raises(RefusACP, match="ne peut pas changer"):
        soumettre(banc, op, defi, soumission, "AUTRE-CODE")
    commande = echange(banc, observation=obs)["operation"]
    assert commande == echange(banc, observation=obs)["operation"]
    assert commande["action"] == "fournir_code"
    assert commande["retour_code"] == {"defi_id": defi, "soumission_id": soumission, "code": CODE_FACTICE}
    assert C.Reponse(protocole=C.PROTOCOLE, operation=commande)
    assert voir(banc, op["id"])["reception_code"]["etat"] == "en_attente"
    with banc.ouvrir() as conn:
        dump = "\n".join(conn.iterdump())
        assert CODE_FACTICE not in dump and URL_CLAUDE_FACTICE not in dump and "DEFI-FACTICE" not in dump
        assert c.etat(conn)["comptes"][1]["connexion"]["reception_code"] == vue["reception_code"]
    ack = C.Observation(operation_id=op["id"], moteur="claude_code", numero=2,
                        etat="verification", motif="verification",
                        code_transmis=C.AccuseCode(defi_id=defi, soumission_id=soumission))
    assert echange(banc, observation=ack)["operation"]["action"] == "attendre"
    assert echange(banc, observation=ack)["operation"]["retour_code"] is None
    assert not c._CODES and not c._DEFIS
    assert voir(banc, op["id"])["reception_code"]["etat"] == "transmis"
    assert soumettre(banc, op, defi, soumission)["reception_code"]["etat"] == "transmis"
    fin = ack.model_copy(update={"numero": 3, "etat": "connecte", "motif": "connecte", "compte_connecte": True})
    assert echange(banc, observation=fin)["operation"] is None
    assert echange(banc, observation=fin)["operation"] is None
    assert voir(banc, op["id"])["compte_connecte"] is True


def test_claude_restart_hermes_perd_code_sans_rearmer_envoi(banc):
    op, defi, obs = claude(banc)
    soumission = str(uuid4())
    soumettre(banc, op, defi, soumission)
    c._CODES.clear()
    c._DEFIS.clear()
    assert voir(banc, op["id"])["reception_code"]["etat"] == "perdu"
    assert soumettre(banc, op, defi, soumission)["reception_code"]["etat"] == "perdu"
    with pytest.raises(RefusACP, match="déjà été soumis"):
        soumettre(banc, op, defi)
    # Réémission du défi par le CLI toujours vivant : le code de retour perdu
    # n’est pas reconstitué, même avec le même numéro d’observation.
    assert echange(banc, observation=obs)["operation"]["action"] == "attendre"
    assert voir(banc, op["id"])["reception_code"]["etat"] == "perdu"
    ack = C.Observation(operation_id=op["id"], moteur="claude_code", numero=2,
                        etat="verification", motif="verification",
                        code_transmis={"defi_id": defi, "soumission_id": soumission})
    echange(banc, observation=ack)
    assert voir(banc, op["id"])["reception_code"]["etat"] == "transmis"


@pytest.mark.parametrize("fin", ["annulation", "expiration", "instance_libre", "instance_occupee"])
def test_claude_purge_ram_sur_interruption(banc, fin):
    op, defi, _ = claude(banc)
    soumission = str(uuid4())
    soumettre(banc, op, defi, soumission)
    if fin == "annulation":
        with banc.ouvrir() as conn:
            c.annuler(conn, op["id"], "proprietaire:test")
    elif fin == "expiration":
        banc.horloge[0] += 901
        voir(banc, op["id"])
    else:
        banc.horloge[0] += 46
        reponse = echange(banc, instance=str(uuid4()), libre=fin == "instance_libre")
        assert reponse["operation"] is None if fin == "instance_occupee" else reponse["operation"]["action"] == "reconcilier"
    assert not c._CODES and not c._DEFIS
    assert voir(banc, op["id"])["reception_code"]["etat"] == "perdu"
    assert soumettre(banc, op, defi, soumission)["reception_code"]["etat"] == "perdu"


def test_claude_refuse_double_soumission_defi_etranger_et_ack_etranger(banc):
    op, defi, _ = claude(banc)
    with pytest.raises(RefusACP):
        soumettre(banc, op, str(uuid4()))
    soumission = str(uuid4())
    soumettre(banc, op, defi, soumission)
    with pytest.raises(RefusACP):
        soumettre(banc, op, defi)
    ack = C.Observation(operation_id=op["id"], moteur="claude_code", numero=2,
                        etat="verification", motif="verification",
                        code_transmis={"defi_id": defi, "soumission_id": str(uuid4())})
    with pytest.raises(RefusACP):
        echange(banc, observation=ack)
    assert voir(banc, op["id"])["reception_code"]["etat"] == "en_attente"
    with banc.ouvrir() as conn:
        assert c.lire(conn, op["id"], defi, str(uuid4()))["reception_code"]["etat"] == "non_recue"
        with pytest.raises(ValueError):
            c.lire(conn, op["id"], defi, None)


def test_operations_tous_moteurs_partagent_verrou_et_cle(banc):
    cle = str(uuid4())
    with banc.ouvrir() as conn:
        op = c.creer(conn, cle, "proprietaire:test", "claude_code")
        assert c.creer(conn, cle, "proprietaire:test", "claude_code") == op
        with pytest.raises(RefusACP, match="autre moteur"):
            c.creer(conn, cle, "proprietaire:test", "codex")
        with pytest.raises(RefusACP, match="déjà en cours"):
            c.creer(conn, str(uuid4()), "proprietaire:test", "codex")
    echange(banc)
    with pytest.raises(RefusACP):
        echange(banc, observation=observation(op["id"], etat="demarrage"))


def test_annulation_claude_conserve_ancien_compte_confirme(banc):
    op, _, _ = claude(banc)
    with banc.ouvrir() as conn:
        c.annuler(conn, op["id"], "proprietaire:test")
    echange(banc, observation=C.Observation(operation_id=op["id"], moteur="claude_code", numero=2,
                                           etat="annulee", motif="annulee", compte_connecte=True))
    assert voir(banc, op["id"])["compte_connecte"] is True
    with banc.ouvrir() as conn:
        vue = c.etat(conn)["comptes"][1]
        assert vue["etat"] == "connecte" and vue["connexion"]["etat"] == "annulee"
        assert vue["modeles"] == [] and vue["inference_verifiee"] is False


def test_ram_liee_a_la_base_meme_avec_memes_ids(banc, tmp_path):
    op, defi, _ = claude(banc)
    soumission = str(uuid4())
    soumettre(banc, op, defi, soumission)
    autre = sqlite3.connect(tmp_path / "copie.db", isolation_level=None)
    autre.row_factory = sqlite3.Row
    try:
        with banc.ouvrir() as conn:
            conn.backup(autre)
        vue = c.lire(autre, op["id"])
        assert vue["verification_url"] is None and vue["reception_code"]["etat"] == "perdu"
        assert c.echanger(autre, MACHINE, C.Echange(instance_id=banc.instance, libre=True))["operation"]["action"] == "attendre"
    finally:
        autre.close()
    assert voir(banc, op["id"])["reception_code"]["etat"] == "en_attente"


def test_migration_anciennes_operations_codex_sans_perte(banc):
    op = creer(banc)
    with banc.ouvrir() as conn:
        champs = [r[1] for r in conn.execute("PRAGMA table_info(comptes_operations)") if r[1] not in
                  {"moteur", "defi_id", "defi_type", "soumission_id", "code_transmis"}]
        ancien = dict(conn.execute("SELECT " + ",".join(champs) + " FROM comptes_operations").fetchone())
        for champ in ("moteur", "defi_id", "defi_type", "soumission_id", "code_transmis"):
            conn.execute("ALTER TABLE comptes_operations DROP COLUMN " + champ)
        c.initialiser(conn)
        nouveau = dict(conn.execute("SELECT * FROM comptes_operations").fetchone())
        assert {k: nouveau[k] for k in champs} == ancien
        assert nouveau["moteur"] == "codex" and nouveau["code_transmis"] == 0
        assert c.lire(conn, op["id"])["etat"] == "en_attente"


def test_projection_claude_alias_documentes_distincts(banc):
    inv = inventaire_compte()
    inv["connexions"]["claude"] = "compte_claude"
    publier_inventaire(banc, inv)
    with banc.ouvrir() as conn:
        vue = c.etat(conn)["comptes"][1]
        assert vue["compte_connecte"] is True and vue["version"] == "2.1.283"
        assert vue["modeles"] == [] and len(vue["alias_documentes"]) == 3
        assert vue["observation"]["origine_modeles"] == "alias_documentes"
        assert vue["inference_verifiee"] is False
    banc.horloge[0] += 1
    inv["connexions"]["claude"] = "jeton_absent"
    publier_inventaire(banc, inv)
    with banc.ouvrir() as conn:
        assert c.etat(conn)["comptes"][1]["compte_connecte"] is False


@pytest.fixture
def http_comptes(banc):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    spec = importlib.util.spec_from_file_location("_comptes_api_claude_tests", GREFFON / "comptes_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    app = FastAPI()
    @app.middleware("http")
    async def identites(request, call_next):
        if request.headers.get("x-test-role") == "machine":
            request.state.token_principal = SimpleNamespace(provider="acp-poste-machine", scopes=("machine",), principal="acp-poste:" + MACHINE)
        return await call_next(request)
    app.include_router(api.creer_router(lambda nom: importlib.import_module(NOM + "." + nom),
                       lambda r: "proprietaire:test" if r.headers.get("x-test-role") == "owner" else None,
                       lambda: "https://acp.example"))
    with TestClient(app) as http:
        yield http


def test_http_claude_scopes_origine_bornes_no_store_et_reception(banc, http_comptes):
    http = http_comptes
    h = {"x-test-role": "owner"}
    route = "/v1/comptes/claude/connexions"
    cle = str(uuid4())
    assert http.post(route, json={"idempotency_key": cle}).status_code == 401
    assert http.post(route, json={"idempotency_key": cle}, headers={"x-test-role": "machine"}).status_code == 401
    assert http.post(route, json={"idempotency_key": cle}, headers=h | {"origin": "https://evil.invalid"}).status_code == 403
    r = http.post(route, json={"idempotency_key": cle}, headers=h)
    assert r.status_code == 202 and r.headers["cache-control"] == "no-store"
    op = r.json()
    assert op["moteur"] == "claude_code"
    assert http.post(route, json={"idempotency_key": cle}, headers=h).json() == op
    assert http.post("/v1/comptes/codex/connexions", json={"idempotency_key": cle}, headers=h).status_code == 409
    base_url = "/v1/comptes/connexions/" + op["id"]
    corps = {"defi_id": str(uuid4()), "soumission_id": str(uuid4()), "code": CODE_FACTICE}
    assert http.post(base_url + "/code", json=corps).status_code == 401
    assert http.post(base_url + "/code", json=corps, headers=h | {"origin": "https://evil.invalid"}).status_code == 403
    assert http.post(base_url + "/code", json=corps, headers=h).status_code == 409
    assert http.post(base_url + "/code", json=corps | {"code": "x" * 4096}, headers=h).status_code == 413
    invalide = http.post(base_url + "/code", json=corps | {"code": "SECRET-PRIVE\nAUTRE"}, headers=h)
    assert invalide.status_code == 400 and "SECRET-PRIVE" not in invalide.text
    assert invalide.headers["cache-control"] == "no-store"
    echange(banc)
    obs = C.Observation(operation_id=op["id"], moteur="claude_code", numero=1, etat="code_disponible", motif="code",
                        defi_id=corps["defi_id"], defi_type="claude_oauth_code", verification_url=URL_CLAUDE_FACTICE)
    echange(banc, observation=obs)
    r = http.post(base_url + "/code", json=corps, headers=h)
    assert r.status_code == 202 and r.headers["cache-control"] == "no-store"
    assert CODE_FACTICE not in r.text
    reception = r.json()["reception_code"]
    assert reception["etat"] == "en_attente"
    assert http.get(base_url, headers=h).json()["reception_code"] == reception
    assert http.get("/v1/comptes", headers=h).json()["comptes"][1]["connexion"]["reception_code"] == reception
    ids = {k: corps[k] for k in ("defi_id", "soumission_id")}
    assert http.get(base_url, params=ids, headers=h).json()["reception_code"] == reception
    assert http.get(base_url, params={"defi_id": ids["defi_id"]}, headers=h).status_code == 400
    assert http.get(base_url, params=ids | {"code": "SECRET"}, headers=h).status_code == 400
    assert http.get(base_url, params=list(ids.items()) + [("defi_id", ids["defi_id"])], headers=h).status_code == 400
    c._CODES.clear()
    r = http.get(base_url, params=ids, headers=h)
    assert r.json()["reception_code"]["etat"] == "perdu" and r.headers["cache-control"] == "no-store"
    assert http.post(base_url + "/code", json=corps, headers=h).json()["reception_code"]["etat"] == "perdu"


def test_http_canal_machine_accepte_url_longue_mais_reste_borne(banc, http_comptes):
    op = creer(banc)
    with banc.ouvrir() as conn:
        c.annuler(conn, op["id"], "proprietaire:test")
        op = c.creer(conn, str(uuid4()), "proprietaire:test", "claude_code")
    echange(banc)
    obs = C.Observation(operation_id=op["id"], moteur="claude_code", numero=1, etat="code_disponible", motif="code",
                        defi_id=str(uuid4()), defi_type="claude_oauth_code", verification_url=C.URL_CLAUDE + "?state=" + "x" * 5000)
    route = "/machine/v1/comptes"
    h = {"x-test-role": "machine"}
    corps = {"instance_id": banc.instance, "libre": True, "observation": obs.model_dump()}
    r = http_comptes.post(route, json=corps, headers=h)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert voir(banc, op["id"])["verification_url"] == obs.verification_url
    assert http_comptes.post(route, json={"secret": "x" * 16384}, headers=h).status_code == 413


@pytest.mark.parametrize("etat,numero", [("demarrage", 2), ("verification", 1)])
def test_observation_refusee_avec_ack_valide_ne_detruit_pas_code(banc, etat, numero):
    op, defi, _ = claude(banc)
    soumission = str(uuid4())
    soumettre(banc, op, defi, soumission)
    obs = C.Observation(operation_id=op["id"], moteur="claude_code", numero=numero, etat=etat, motif=etat,
                        code_transmis={"defi_id": defi, "soumission_id": soumission})
    with pytest.raises(RefusACP):
        echange(banc, observation=obs)
    assert voir(banc, op["id"])["reception_code"]["etat"] == "en_attente"
    commande = echange(banc)["operation"]
    assert commande["action"] == "fournir_code" and commande["retour_code"]["code"] == CODE_FACTICE
    with banc.ouvrir() as conn:
        assert conn.execute("SELECT code_transmis FROM comptes_operations WHERE id=?", (op["id"],)).fetchone()[0] == 0


def test_succes_tardif_ne_supprime_pas_annulation_proprietaire(banc):
    op, _, _ = claude(banc)
    succes = C.Observation(operation_id=op["id"], moteur="claude_code", numero=2,
                           etat="connecte", motif="connecte", compte_connecte=True)
    with banc.ouvrir() as conn:
        c.annuler(conn, op["id"], "proprietaire:test")
    assert echange(banc, observation=succes)["operation"] is None
    vue = voir(banc, op["id"])
    assert vue["etat"] == "annulee" and vue["compte_connecte"] is True
    assert echange(banc, observation=succes)["operation"] is None
    assert voir(banc, op["id"]) == vue
