"""Contrôleur de compte avec double explicite d’app-server, sans lancer aucune CLI.

Ces tests éprouvent les courses et limites du produit, pas une authentification personnelle.
Le contrat du vrai binaire épinglé est généré séparément dans l’image Linux.
"""
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from acp_poste import comptes_codex as m
from acp_poste.app_server import MethodeRefusee, ReponseMalFormee, Session
from acp_poste.plateforme.linux import IDENTITES
from acp_poste_contrat import comptes as C


class SessionDouble:
    instances=[]
    connecter=True
    terminer=True
    lecture={"account":{"type":"chatgpt","email":"ne-doit-pas-sortir@example.invalid","planType":"pro"}}
    def __init__(self,argv,**options):
        self.argv,self.options,self.appels=argv,options,[]
        self.fermee=False
        self.instances.append(self)
    async def __aenter__(self):
        self.terminee=asyncio.get_running_loop().create_future()
        return self
    async def __aexit__(self,*args):
        self.fermee=True
    async def initialiser(self):
        self.appels.append(("initialize",{}))
    async def appeler(self,methode,params):
        self.appels.append((methode,params))
        if methode=="account/login/start":
            if self.terminer:
                # Notification avant que l’appelant ne commence son attente.
                self.terminee.set_result({"loginId":"identifiant-natif-prive","success":self.connecter,"error":"sortie-privee-ne-pas-publier"})
            return {"type":"chatgptDeviceCode","loginId":"identifiant-natif-prive","verificationUrl":C.URL_CODEX,"userCode":"UNIT-TEST"}
        if methode=="account/read": return self.lecture
        if methode=="account/login/cancel": return {"status":"canceled"}
        raise AssertionError(methode)


@pytest.fixture
def ctl(tmp_path,monkeypatch):
    SessionDouble.instances=[]
    monkeypatch.setattr(SessionDouble,"connecter",True)
    monkeypatch.setattr(SessionDouble,"terminer",True)
    monkeypatch.setattr(SessionDouble,"lecture",{"account":{"type":"chatgpt","email":"ne-doit-pas-sortir@example.invalid","planType":"pro"}})
    contexte=SimpleNamespace(plateforme="linux", emplacements=SimpleNamespace(verrou_codex=tmp_path/"codex.lock"),
        identites={"codex":IDENTITES["acp-codex"]},lanceurs_pour=lambda p:{"codex":["double-aucun-executable"]})
    politique=SimpleNamespace(codex=SimpleNamespace(home=tmp_path,version_testee=m.VERSION_CODEX))
    async def version(*args): return m.VERSION_CODEX
    class ProtocoleDouble:
        def __init__(self): self.appels=[]; self.reponses=[]
        def comptes(self,jeton,corps):
            self.appels.append(corps)
            if not self.reponses: return {"protocole":C.PROTOCOLE,"operation":None}
            valeur=self.reponses.pop(0)
            if isinstance(valeur,Exception): raise valeur
            return valeur
    protocole=ProtocoleDouble()
    apres=[]
    c=m.ControleurComptes(contexte,politique,protocole,None,libre=lambda:True,apres=lambda:apres.append(True),session=SessionDouble,version=version)
    c.apres_observes=apres
    return c


def commande(id=None,action="demarrer",delai=60):
    return {"protocole":C.PROTOCOLE,"operation":{"id":id or str(uuid4()),"action":action,"limite_attente_le":int(time.time())+delai}}


async def lancer(ctl,**options):
    reponse=commande(**options)
    ctl.protocole.reponses.append(reponse)
    await ctl.tour()
    return reponse["operation"]


async def attendre_code(ctl):
    async def attendre():
        while not ctl.observation or ctl.observation["etat"]!="code_disponible": await asyncio.sleep(0)
    await asyncio.wait_for(attendre(),1)


async def test_login_officiel_code_precoce_compte_confirme_sans_inference_ni_secret(ctl,capsys):
    await lancer(ctl)
    await ctl.tache
    assert ctl.observation["etat"]=="connecte" and ctl.observation["compte_connecte"] is True
    s=SessionDouble.instances[0]
    assert s.appels==[("initialize",{}),("account/login/start",{"type":"chatgptDeviceCode"}),("account/read",{"refreshToken":False})]
    assert s.options["env"]["CODEX_HOME"]==ctl.politique.codex.home.as_posix()
    assert s.fermee and ctl.apres_observes==[True]
    assert ctl.observation["code_utilisateur"] is None
    for prive in ("identifiant-natif-prive","ne-doit-pas-sortir@example.invalid","sortie-privee-ne-pas-publier"):
        assert prive not in str(ctl.observation) and prive not in str(capsys.readouterr())


@pytest.mark.parametrize("action",["reconcilier","attendre"])
async def test_reponse_perdue_ou_redemarrage_lit_sans_relancer_login(ctl,action):
    op=await lancer(ctl,action=action)
    await ctl.tache
    assert [a[0] for a in SessionDouble.instances[0].appels]==["initialize","account/read"]
    assert ctl.observation["etat"]=="connecte"
    ctl.protocole.reponses.append(commande(id=op["id"],action="attendre"))
    await ctl.tour()
    assert len(SessionDouble.instances)==1


async def test_reconciliation_sans_compte_demande_une_nouvelle_connexion(ctl,monkeypatch):
    monkeypatch.setattr(SessionDouble,"lecture",{"account":None})
    await lancer(ctl,action="reconcilier")
    await ctl.tache
    assert ctl.observation["etat"]=="interrompue" and ctl.observation["compte_connecte"] is False
    assert all(a[0]!="account/login/start" for a in SessionDouble.instances[0].appels)


async def test_coupure_reseau_garde_processus_et_annulation_explicite(ctl,monkeypatch):
    monkeypatch.setattr(SessionDouble,"terminer",False)
    op=await lancer(ctl)
    await attendre_code(ctl)
    ctl.protocole.reponses.append(OSError("panne factice"))
    with pytest.raises(OSError): await ctl.tour()
    assert ctl.occupe and not SessionDouble.instances[0].fermee
    ctl.protocole.reponses.append(commande(id=op["id"],action="attendre"))
    await ctl.tour()
    assert len(SessionDouble.instances)==1 and ctl.occupe
    ctl.protocole.reponses.append(commande(id=op["id"],action="annuler"))
    await ctl.tour()
    await ctl.tache
    assert ctl.observation["etat"]=="annulee"
    assert SessionDouble.instances[0].appels[-1]==("account/login/cancel",{"loginId":"identifiant-natif-prive"})


async def test_expiration_annule_le_login_officiel(ctl,monkeypatch):
    monkeypatch.setattr(SessionDouble,"terminer",False)
    await lancer(ctl,delai=-1)
    await ctl.tache
    assert ctl.observation["etat"]=="expiree" and SessionDouble.instances[0].fermee
    assert SessionDouble.instances[0].appels[-1][0]=="account/login/cancel"


@pytest.mark.parametrize("lecture",[{"account":{"type":"apiKey"}},{"account":None},{"account":{"type":"future-provider"}}])
async def test_compte_autre_que_chatgpt_n_est_pas_confirme(ctl,monkeypatch,lecture):
    monkeypatch.setattr(SessionDouble,"lecture",lecture)
    await lancer(ctl)
    await ctl.tache
    assert ctl.observation["etat"]=="erreur" and ctl.observation["compte_connecte"] is False


async def test_windows_ne_demande_rien_et_version_incompatible_ne_lance_rien(ctl):
    ctl.contexte.plateforme="windows"
    await ctl.tour()
    assert ctl.protocole.appels==[]
    ctl.contexte.plateforme="linux"
    ctl.politique.codex.version_testee="0.0.0"
    await lancer(ctl)
    await ctl.tache
    assert ctl.observation["motif"]=="incompatible" and SessionDouble.instances==[]


async def test_annulation_d_operation_reprise_ne_lance_pas_cli(ctl):
    await lancer(ctl,action="annuler")
    await ctl.tache
    assert ctl.observation["etat"]=="annulee" and SessionDouble.instances==[]


@pytest.mark.parametrize("methode,params",[("account/login/start",{"type":"apiKey","apiKey":"jamais-envoye"}), ("account/login/start",{"type":"chatgptAuthTokens"}), ("account/read",{"refreshToken":True}), ("account/login/cancel",{"loginId":"x","token":"x"}), ("account/logout",{}),("account/rateLimitResetCredit/consume",{}),("config/value/write",{}),("thread/start",{})])
async def test_liste_blanche_refuse_avant_envoi(methode,params):
    session=m.SessionCompte([],env={},cwd=".")
    with pytest.raises(MethodeRefusee): await session.appeler(methode,params)
    assert session.methodes_envoyees==[]


@pytest.mark.parametrize("delta",[{"verificationUrl":"https://evil.invalid"},{"userCode":"secret\nligne"},{"loginId":None},{"type":"chatgpt"}])
def test_reponse_login_mal_formee_est_refusee(delta):
    with pytest.raises(ReponseMalFormee):
        m.defi({"type":"chatgptDeviceCode","loginId":"natif","verificationUrl":C.URL_CODEX,"userCode":"UNIT-TEST"}|delta)


async def test_notification_non_attendue_ignoree_et_jeton_refresh_refuse():
    import json
    session=m.SessionCompte([],env={},cwd=".")
    sortie=asyncio.StreamReader()
    messages=[{"method":"account/updated","params":{"email":"prive"}},
        {"id":88,"method":"account/chatgptAuthTokens/refresh","params":{}},
        {"method":"account/login/completed","params":{"loginId":"natif","success":True,"error":None}}]
    sortie.feed_data(("\n".join(json.dumps(x) for x in messages)+"\n").encode())
    sortie.feed_eof()
    session._processus=SimpleNamespace(stdout=sortie)
    future=asyncio.get_running_loop().create_future()
    session._notifications["account/login/completed"]=future
    envoyes=[]
    async def envoyer(obj): envoyes.append(obj)
    session._envoyer=envoyer
    await session._lire()
    assert future.result()["success"] is True
    assert envoyes==[{"id":88,"error":{"code":-32601,"message":"non pris en charge par le poste"}}]
    assert set(session._notifications)=={"account/login/completed"}


async def test_politique_invalide_suspend_echanges_et_annule_login(ctl,monkeypatch):
    monkeypatch.setattr(SessionDouble,"terminer",False)
    await lancer(ctl)
    await attendre_code(ctl)
    nombre=len(ctl.protocole.appels)
    ctl.autorise=lambda:False
    await ctl.tour()
    await ctl.tache
    assert len(ctl.protocole.appels)==nombre and ctl.observation["etat"]=="annulee"


async def test_jeton_machine_refuse_arrete_boucle_et_processus(ctl,monkeypatch):
    from acp_poste.protocole import JetonRefuse
    monkeypatch.setattr(SessionDouble,"terminer",False)
    await lancer(ctl)
    await attendre_code(ctl)
    refus=[]
    ctl.refus_definitif=lambda exc:refus.append(exc)
    ctl.protocole.reponses.append(JetonRefuse("Jeton refusé"))
    await ctl.servir(asyncio.Event())
    assert len(refus)==1 and ctl.tache.done() and SessionDouble.instances[0].fermee
    assert ctl.observation["etat"]=="interrompue"


@pytest.mark.parametrize("erreur",[None,ValueError("double"),TimeoutError(),asyncio.CancelledError()])
async def test_session_compte_fermeture_fatale_meme_pendant_erreur(monkeypatch,erreur):
    from acp_poste import app_server
    async def arreter(*args,**kwargs): return False
    monkeypatch.setattr(app_server,"arreter",arreter)
    session=m.SessionCompte([],env={},cwd=".")
    session.terminee=asyncio.get_running_loop().create_future()
    session._processus=object()  # aucun processus réel : seul le verdict d’arrêt est doublé
    with pytest.raises(app_server.ArretNonConfirme):
        await session.__aexit__(type(erreur) if erreur is not None else None,erreur,None)
    assert session.arret_confirme is False


@pytest.mark.parametrize("cas",["normal","rpc","timeout","annulation"])
async def test_controleur_suspend_service_apres_arret_non_confirme(ctl,monkeypatch,cas):
    from acp_poste.service_executant import ServiceExecutant, SUSPENDU
    class MauvaiseFermeture(SessionDouble):
        async def initialiser(self):
            if cas=="rpc": raise ValueError("sortie privée")
            if cas=="timeout": raise TimeoutError()
            await super().initialiser()
        async def __aexit__(self,*args):
            self.arret_confirme=False
            await super().__aexit__(*args)
            if cas=="normal": raise m.ArretNonConfirme()
    ctl.session=MauvaiseFermeture
    service=SimpleNamespace(suspendu=None,comptes=ctl,journal=SimpleNamespace(ecrire=lambda *a,**k:None),_pause_locale=lambda:False)
    ctl.suspendre=lambda:ServiceExecutant._suspendre_compte(service)
    if cas=="annulation": monkeypatch.setattr(SessionDouble,"terminer",False)
    await lancer(ctl)
    if cas=="annulation":
        await attendre_code(ctl)
        ctl.tache.cancel()
    await asyncio.gather(ctl.tache,return_exceptions=True)
    assert ctl.echec_arret and ctl.occupe and ctl.tache.done()
    assert service.suspendu==SUSPENDU
    assert ServiceExecutant._releves_permis(service) is False
    assert ctl.observation["etat"]=="erreur" and ctl.apres_observes==[]
    avant=len(SessionDouble.instances)
    ctl.protocole.reponses.append(commande())
    await ctl.tour()
    assert len(SessionDouble.instances)==avant
    assert ctl.protocole.appels[-1]["libre"] is False


def test_carte_long_poll_restituee_durablement_sans_moteur(tmp_path):
    from acp_poste.service_executant import ServiceExecutant
    from acp_poste.sortie import FileSortie
    from acp_poste.protocole import HermesIndisponible
    from acp_poste_contrat.machine import RequeteReprendre, ReponseReprise
    file=FileSortie(tmp_path/"sortie")
    service=SimpleNamespace(comptes=SimpleNamespace(occupe=True),sortie=file,journal=SimpleNamespace(ecrire=lambda *a,**k:None))
    carte=SimpleNamespace(tableau="acp-compte-test",carte="t_0001",run_id=1)
    ServiceExecutant._carte_recue(service,carte)
    attente=file.en_attente()
    assert len(attente)==1
    route,corps=file.lire(attente[0])
    RequeteReprendre.model_validate(corps)
    assert route=="reprendre" and corps["motif"]=="compte_occupe"
    def panne(route,corps): raise HermesIndisponible("Panne simulée")
    _,refus=file.rejouer(panne)
    assert refus is not None and len(file.en_attente())==1
    # Nouveau superviseur, même fichier et identifiant ; aucune carte n’a été lancée.
    apres=FileSortie(tmp_path/"sortie")
    envoyes=[]
    def envoi(route,body):
        envoyes.append((route,body))
        return ReponseReprise(etat="rendue")
    resultats,refus=apres.rejouer(envoi)
    assert refus is None and len(resultats)==1 and envoyes==[(route,corps)]
    assert apres.en_attente()==[]
