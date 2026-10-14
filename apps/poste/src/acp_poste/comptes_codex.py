"""Connexions officielles Codex et Claude pilotées par un contrôleur unique sur Linux.

Le CLI possède les identifiants. Le serveur propriétaire ne reçoit que le défi
temporaire et un état filtré. Aucune sortie brute ni exception du CLI n’est journalisée.
"""
from __future__ import annotations
import asyncio
import time
from uuid import uuid4
from acp_poste_contrat import comptes as C
from .app_server import Session, MethodeRefusee, ReponseMalFormee, ArretNonConfirme
from .sondes_codex import extraire_compte, lire_version
from .verrou import Verrou, VerrouOccupe
from .protocole import JetonRefuse, PosteRevoque, ProtocoleIncompatible
from .comptes_claude import SessionCompteClaude, lire_etat_claude, VERSION_CLAUDE

VERSION_CODEX = "0.156.1"


class SessionCompte(Session):
    """Capacité distincte de la sonde : aucun token externe ni configuration arbitraire."""
    METHODES = frozenset({"initialize", "account/read", "account/login/start", "account/login/cancel"})

    def _admise(self, methode):
        return methode in self.METHODES

    async def __aenter__(self):
        await super().__aenter__()
        self.terminee = asyncio.get_running_loop().create_future()
        self._notifications["account/login/completed"] = self.terminee
        return self

    async def appeler(self, methode, params=None, *, avec_params=True):
        if methode == "account/login/start" and params != {"type":"chatgptDeviceCode"}:
            raise MethodeRefusee(methode)
        if methode == "account/login/cancel" and (not isinstance(params,dict) or set(params)!={"loginId"} or not isinstance(params["loginId"],str) or len(params["loginId"])>128):
            raise MethodeRefusee(methode)
        if methode == "account/read" and params != {"refreshToken":False}:
            raise MethodeRefusee(methode)
        return await super().appeler(methode,params,avec_params=avec_params)

    async def __aexit__(self,*args):
        try:
            return await super().__aexit__(*args)
        finally:
            if self.terminee.done() and not self.terminee.cancelled():
                self.terminee.exception()  # récupérer aussi l’erreur d’une fermeture sans notification
            # Session ne lève pas pendant une exception existante. Une connexion ne
            # doit pourtant jamais rendre le moteur disponible sans preuve d’arrêt.
            if self.arret_confirme is False:
                raise ArretNonConfirme from None


def defi(resultat):
    if not isinstance(resultat,dict) or resultat.get("type")!="chatgptDeviceCode":
        raise ReponseMalFormee()
    identifiant=resultat.get("loginId")
    if not isinstance(identifiant,str) or not identifiant or len(identifiant)>128:
        raise ReponseMalFormee()
    try:
        C.Observation(operation_id=str(uuid4()),moteur="codex",numero=1,etat="code_disponible",motif="code",
                      defi_id=str(uuid4()),defi_type="codex_device",
                      verification_url=resultat.get("verificationUrl"),code_utilisateur=resultat.get("userCode"))
    except ValueError:
        raise ReponseMalFormee() from None
    return identifiant,resultat["verificationUrl"],resultat["userCode"]


class ControleurComptes:
    def __init__(self, contexte, politique, protocole, jeton, *, libre, apres, session=SessionCompte, version=lire_version, autorise=lambda: True, refus_definitif=lambda exc: None, politique_courante=None, suspendre=lambda: None,
                 session_claude=SessionCompteClaude, etat_claude=lire_etat_claude):
        self.contexte,self.politique,self.protocole,self.jeton=contexte,politique,protocole,jeton
        self.libre,self.apres,self.session,self.version=libre,apres,session,version
        self.autorise, self.refus_definitif = autorise, refus_definitif
        self.politique_courante = politique_courante or (lambda: politique)
        self.instance_id=str(uuid4())
        self.operation_id=None
        self.observation=None
        self.tache=None
        self.annulation=asyncio.Event()
        self.numero=0
        self.vues=set()
        self.echec_arret = False
        self.suspendre = suspendre
        self.session_claude, self.etat_claude = session_claude, etat_claude
        self.moteur = "codex"
        self.defi_id = None
        self.code_transmis = None
        self._session_claude = None

    @property
    def occupe(self):
        return self.echec_arret or (self.tache is not None and not self.tache.done())

    def noter(self,etat,motif,**champs):
        self.numero+=1
        champs.setdefault("code_transmis", self.code_transmis)
        self.observation=C.Observation(operation_id=self.operation_id,moteur=self.moteur,numero=self.numero,etat=etat,motif=motif,**champs).model_dump(mode="json")

    async def tour(self):
        if self.contexte.plateforme!="linux": return
        if not self.autorise():
            self.annulation.set()
            return
        self.politique = self.politique_courante()
        requete={"instance_id":self.instance_id,"libre":bool(self.libre()) and not self.occupe,"observation":self.observation}
        reponse=await asyncio.to_thread(self.protocole.comptes,self.jeton,requete)
        commande=C.Reponse.model_validate(reponse).operation
        if commande is None:
            # Une expiration côté serveur n’est jamais une raison de relancer le CLI.
            if self.occupe: self.annulation.set()
            return
        if commande.id == self.operation_id and commande.moteur != self.moteur:
            self.annulation.set()
            raise ReponseMalFormee("Moteur de connexion incohérent.")
        if commande.action == "fournir_code":
            await self._fournir_claude(commande)
            return
        if commande.action=="annuler":
            self.annulation.set()
        if commande.id in self.vues: return
        if self.occupe: return
        self.vues.add(commande.id)
        self.operation_id=commande.id
        self.moteur=commande.moteur
        self.defi_id=None
        self.code_transmis=None
        self.numero=0
        self.annulation=asyncio.Event()
        self.noter("demarrage","demarrage")
        # Si la réponse initiale de réclamation a été perdue, seulement relire l’état.
        mode=commande.action if commande.action in ("demarrer","reconcilier","annuler") else "reconcilier"
        self.tache=asyncio.create_task(self._traiter(commande,mode))

    def _arret_non_confirme(self):
        if not self.echec_arret:
            self.echec_arret = True
            self.noter("erreur", "indisponible")
            self.suspendre()

    async def _traiter(self,commande,mode):
        if self.moteur == "claude_code":
            return await self._traiter_claude(commande, mode)
        verrou=None
        session=None
        try:
            if mode=="annuler":
                self.noter("annulee","annulee")
                return
            if not self.libre():
                self.noter("erreur","occupe")
                return
            section=self.politique.codex
            if section is None or section.version_testee!=VERSION_CODEX:
                self.noter("erreur","incompatible")
                return
            chemin=self.contexte.emplacements.verrou_codex
            chemin.parent.mkdir(parents=True,exist_ok=True)
            verrou=Verrou(chemin).prendre()
            from .plateforme.linux import environnement_agent
            identite=self.contexte.identites.get("codex")
            argv=self.contexte.lanceurs_pour(self.politique).get("codex")
            if identite is None or not argv:
                self.noter("erreur","indisponible")
                return
            env=environnement_agent(identite,CODEX_HOME=section.home.as_posix())
            if await asyncio.wait_for(self.version(argv,env,str(section.home)),timeout=20)!=VERSION_CODEX:
                self.noter("erreur","incompatible")
                return
            async with self.session([*argv,"-c",'cli_auth_credentials_store="file"',"app-server"],env=env,cwd=section.home) as session:
                await asyncio.wait_for(session.initialiser(),timeout=20)
                if mode=="reconcilier":
                    await self._verifier(session,reprise=True)
                    return
                if self.annulation.is_set():
                    self.noter("annulee","annulee")
                    return
                resultat=await asyncio.wait_for(session.appeler("account/login/start",{"type":"chatgptDeviceCode"}),timeout=30)
                login_id,url,code=defi(resultat)
                self.defi_id = str(uuid4())
                self.noter("code_disponible","code",defi_id=self.defi_id,defi_type="codex_device",
                           verification_url=url,code_utilisateur=code)
                annulation=asyncio.create_task(self.annulation.wait())
                try:
                    delai=max(0,min(900,commande.limite_attente_le-time.time()))
                    done,_=await asyncio.wait([session.terminee,annulation],timeout=delai,return_when=asyncio.FIRST_COMPLETED)
                    if session.terminee in done:
                        notification=session.terminee.result()
                        if notification.get("loginId")!=login_id or type(notification.get("success")) is not bool:
                            raise ReponseMalFormee()
                        if not notification["success"]:
                            self.noter("erreur","refuse")
                            return
                        self.noter("verification","verification")
                        await self._verifier(session)
                    else:
                        await asyncio.wait_for(session.appeler("account/login/cancel",{"loginId":login_id}),timeout=10)
                        self.noter("annulee" if annulation in done else "expiree","annulee" if annulation in done else "expiree")
                finally:
                    annulation.cancel()
                    await asyncio.gather(annulation,return_exceptions=True)
        except ArretNonConfirme:
            self._arret_non_confirme()
        except asyncio.CancelledError:
            self.noter("interrompue","interrompue")
            raise
        except VerrouOccupe:
            self.noter("erreur","occupe")
        except Exception:
            self.noter("erreur","indisponible")
        finally:
            # Deuxième garde : couvre aussi un gestionnaire de contexte qui rend
            # False pendant l’erreur initiale au lieu de lever ArretNonConfirme.
            if session is not None and getattr(session, "arret_confirme", None) is False:
                self._arret_non_confirme()
            if verrou is not None: verrou.rendre()
            if not self.echec_arret:
                self.apres()

    async def _fournir_claude(self, commande):
        retour = commande.retour_code
        if (self.moteur != "claude_code" or commande.id != self.operation_id
                or retour is None or retour.defi_id != self.defi_id or self.annulation.is_set()
                or time.time() >= commande.limite_attente_le):
            return  # Jamais lancer un login à la réception d'un code orphelin.
        if self.code_transmis is not None:
            if self.code_transmis == {"defi_id": retour.defi_id, "soumission_id": retour.soumission_id}:
                return  # ACK déjà présent dans l'observation courante, même si la réponse précédente a été perdue.
            raise ReponseMalFormee("Soumission différente après transmission.")
        session = self._session_claude
        if session is None or self.tache is None or self.tache.done():
            return
        if await session.fournir_code(retour.soumission_id, retour.code):
            self.code_transmis = {"defi_id": retour.defi_id, "soumission_id": retour.soumission_id}
            # Le CLI peut finir pendant drain(). Une observation terminale ne doit pas revenir à verification.
            ancien = self.observation or {}
            if ancien.get("etat") in C.TERMINAUX:
                self.noter(ancien["etat"], ancien["motif"], compte_connecte=ancien.get("compte_connecte"))
            else:
                self.noter("verification", "verification")

    async def _traiter_claude(self, commande, mode):
        verrou, session = None, None
        try:
            if not self.libre():
                self.noter("erreur", "occupe")
                return
            section = getattr(self.politique, "claude", None)
            if section is None or section.version_testee != VERSION_CLAUDE:
                self.noter("erreur", "incompatible")
                return
            chemin = self.contexte.emplacements.verrou_claude
            chemin.parent.mkdir(parents=True, exist_ok=True)
            verrou = Verrou(chemin).prendre()
            from .plateforme.linux import environnement_agent
            identite = self.contexte.identites.get("claude")
            argv = self.contexte.lanceurs_pour(self.politique).get("claude")
            if identite is None or not argv:
                self.noter("erreur", "indisponible")
                return
            env = environnement_agent(identite, CLAUDE_CONFIG_DIR=section.config_dir.as_posix(),
                DISABLE_UPDATES="1", DISABLE_AUTOUPDATER="1", DISABLE_TELEMETRY="1")
            if await asyncio.wait_for(self.version(argv, env, str(section.config_dir)), timeout=20) != VERSION_CLAUDE:
                self.noter("erreur", "incompatible")
                return
            if mode in ("reconcilier", "annuler"):
                compte = await self.etat_claude(argv, env, section.config_dir)
                # Le magasin peut contenir un ancien compte : il ne prouve pas le succès de cette tentative.
                etat = "annulee" if mode == "annuler" or self.annulation.is_set() else "interrompue"
                self.noter(etat, etat, compte_connecte=compte.reconnu)
                return
            issue, motif, sortie = "erreur", "indisponible", None
            async with self.session_claude(argv, env=env, cwd=section.config_dir) as session:
                self._session_claude = session
                annulation = asyncio.create_task(self.annulation.wait())
                try:
                    restant = max(0, min(900, commande.limite_attente_le - time.time()))
                    done, _ = await asyncio.wait([session.defi, annulation], timeout=min(30, restant),
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if annulation in done:
                        issue = motif = "annulee"
                    elif session.defi not in done:
                        if restant <= 30:
                            issue = motif = "expiree"
                    else:
                        url = session.defi.result()
                        self.defi_id = str(uuid4())
                        self.noter("code_disponible", "code", defi_id=self.defi_id,
                                   defi_type="claude_oauth_code", verification_url=url)
                        restant = max(0, min(900, commande.limite_attente_le - time.time()))
                        done, _ = await asyncio.wait([session.terminee, annulation], timeout=restant,
                                                     return_when=asyncio.FIRST_COMPLETED)
                        if annulation in done or self.annulation.is_set():
                            issue = motif = "annulee"
                        elif session.terminee not in done:
                            issue = motif = "expiree"
                        else:
                            sortie = session.terminee.result()
                            issue, motif = "erreur", "refuse"
                finally:
                    annulation.cancel()
                    await asyncio.gather(annulation, return_exceptions=True)
            self._session_claude = None
            # Lecture après arrêt, jamais en parallèle avec le login (rotation du magasin appartenant au CLI).
            compte = await self.etat_claude(argv, env, section.config_dir)
            if self.annulation.is_set():
                issue = motif = "annulee"
            elif (issue not in ("annulee", "expiree") and sortie == 0 and session.code_transmis and compte.reconnu):
                issue = motif = "connecte"
            self.noter(issue, motif, compte_connecte=compte.reconnu)
        except ArretNonConfirme:
            self._arret_non_confirme()
        except asyncio.CancelledError:
            self.noter("interrompue", "interrompue")
            raise
        except VerrouOccupe:
            self.noter("erreur", "occupe")
        except (ReponseMalFormee, ValueError):
            self.noter("erreur", "incompatible")
        except Exception:
            self.noter("erreur", "indisponible")
        finally:
            self._session_claude = None
            if session is not None and getattr(session, "arret_confirme", None) is False:
                self._arret_non_confirme()
            if verrou is not None:
                verrou.rendre()
            if not self.echec_arret:
                self.apres()

    async def _verifier(self,session,*,reprise=False):
        compte,_=extraire_compte(await asyncio.wait_for(session.appeler("account/read",{"refreshToken":False}),timeout=20))
        if compte=="compte_chatgpt":
            self.noter("connecte","connecte",compte_connecte=True)
        else:
            self.noter("interrompue" if reprise else "erreur","interrompue" if reprise else "refuse",compte_connecte=False)

    async def servir(self,fin):
        if self.contexte.plateforme!="linux": return
        try:
            while not fin.is_set():
                try:
                    await self.tour()
                except (JetonRefuse, PosteRevoque, ProtocoleIncompatible) as exc:
                    self.refus_definitif(exc)
                    break
                except Exception:
                    # Réseau/serveur temporairement absent : garder la même opération et le même processus.
                    pass
                try:
                    await asyncio.wait_for(fin.wait(),timeout=3)
                except TimeoutError:
                    pass
        finally:
            client = getattr(self.protocole, "client", None)
            if client is not None:
                client.interrompre()
            if self.tache is not None:
                if not self.tache.done(): self.tache.cancel()
                await asyncio.gather(self.tache,return_exceptions=True)
