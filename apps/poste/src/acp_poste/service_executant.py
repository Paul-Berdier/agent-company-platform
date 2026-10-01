"""Boucle « servir » de l'exécutant Linux (cahier P6 § 6.1, § 6.4, § 7.4 ``service.py``, § 7.6).

Lancée par ``acp-entree-executant`` sous ``tini`` (``acp-poste servir --plateforme linux``), en root. Au démarrage :
verrou d'instance (code 3), ``executant.toml`` valide et non modifiable par un agent, interpréteur non modifiable
(code 2), ``config.toml`` du profil Codex (stockage ``file``), **sonde de plateforme rejouée** (le régime peut changer
après une migration Railway). Puis, sur la même boucle asyncio :

- **attente d'enrôlement sans sortie** (§ 7.6, correction n° 10) : sans jeton, aucune requête vers Hermes, une ligne
  de journal par jour, relecture du jeton toutes les 10 s ; une sortie mettrait le déploiement en « Completed » et
  rendrait ``railway ssh`` impossible ;
- **tâche A** : file de sortie rejouée dans l'ordre AVANT toute réclamation, puis ``reclamer`` (25 s) avec
  ``peut_executer`` (§ 6.1 : politique valide, sonde faite et UID séparés, une voie au moins, espace libre, plafonds
  du jour, aucune pause locale ni suspension), ``voies_disponibles``, ``carte_en_cours`` et ``espace_libre_mio`` ;
- **tâche B** : relevés (sondes Codex et Claude sous l'UID de chaque outil, jamais pendant une carte ni en pause),
  inventaire Linux (isolement mesuré, quotas Claude du dernier ``rate_limit_event``) ;
- **tâche C** : une carte à la fois (:mod:`acp_poste.execution`).

401 ``poste_revoque`` : jeton effacé, retour à l'attente d'enrôlement, **sans sortie** (aucune notification « hors
ligne » ne suit, la révocation supprime la présence). 401 ambigu de la couture : jeton gardé, plus aucun échange,
nouvel essai toutes les 15 min dans le processus. SIGTERM (redéploiement, migration) : plus aucune réclamation, arrêt
de l'agent (SIGTERM, puis SIGKILL de l'UID après 20 s), commit « wip », ``arret(sigterm)`` par la file de sortie,
sortie 0 en moins de 90 s. Processus d'agent impossibles à arrêter : exécution suspendue jusqu'au redémarrage.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from datetime import UTC, datetime
from typing import Any, Callable

from .coffre import CoffreErreur, ecrire_atomiquement
from .contexte import Contexte
from .depots import Depots, espace_libre_mio
from .execution import AgentSurvivant, Execution, IssueCarte, LanceurAgents
from .garde_quota import Budget, QuotasClaude
from .inventaire import construire, relever
from .jeton import Jeton, JetonInvalide
from .journal import Journal
from .politique import Politique, PolitiqueRefusee, charger, verifier_droits, verifier_interpreteur
from .protocole import JetonRefuse, PosteRevoque, ProtocoleIncompatible, Refus
from .service import (
    CODE_CONFIGURATION,
    CODE_ERREUR,
    CODE_INSTANCE,
    CODE_NORMAL,
    AUTRE_INSTANCE,
    Repli,
    Service,
)
from .sonde_plateforme import isolement as bloc_isolement
from .sonde_plateforme import sonder
from .sortie import FileSortie
from .verrou import Verrou, VerrouOccupe

NON_ENROLE = ("Exécutant non enrôlé : créez un code sur la page Poste, puis lancez « acp-poste enroler » dans une "
              "session railway ssh. En attente, sans sortie (aucune requête vers Hermes).")
JETON_ILLISIBLE = ("Jeton machine de l'exécutant au format invalide : lancez « acp-poste oublier-jeton » puis "
                   "réenrôlez l'exécutant.")
JETON_REFUSE_ATTENTE_S = 15 * 60
RELECTURE_JETON_S = 10.0
ARRET_CARTE_MAX_S = 80.0
SUSPENDU = "Processus de l'agent impossibles à arrêter : exécution suspendue jusqu'au redémarrage de l'exécutant."
PAS_ROOT = ("Le superviseur de l'exécutant tourne en root (tini, acp-entree-executant) : il change d'UID pour chaque "
            "agent ; refus de démarrer.")


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ServiceExecutant(Service):
    """La boucle du poste (tâches A et B), plus l'exécution des cartes (tâche C) et leurs annonces."""

    def __init__(self, contexte: Contexte, politique: Politique, jeton: Jeton, journal: Journal, *,
                 isolement: dict[str, Any], arret_global: asyncio.Event,
                 fabrique_depots: Callable[[Politique], Depots] | None = None,
                 executables: dict[str, list[str]] | None = None, lanceur: LanceurAgents | None = None,
                 intervalle_battement_s: float | None = None, protocole: Any = None, proprietaire: int = 0,
                 **options: Any) -> None:
        super().__init__(contexte, politique, jeton, journal, **options)
        self.proprietaire = proprietaire
        if protocole is not None:
            self.protocole = protocole
        e = contexte.emplacements
        self.isolement = isolement
        self.arret_global = arret_global
        self.sortie = FileSortie(e.sortie, e.sortie_refusees)
        self.quotas_claude = QuotasClaude(e.quotas_claude)
        self.budget = Budget(e.compteurs, politique.politique.cartes_par_jour,
                             politique.politique.heures_agent_par_jour)
        self.lanceur = lanceur or LanceurAgents(
            identites={i.nom: i for i in contexte.identites.values()} | self._verif(contexte),
            droits=hasattr(os, "geteuid") and os.geteuid() == 0 and bool(contexte.identites))
        depots = (fabrique_depots or self._depots)(politique)
        options_execution: dict[str, Any] = {}
        if intervalle_battement_s is not None:
            options_execution["intervalle_battement_s"] = intervalle_battement_s
        self.execution = Execution(
            politique=politique, emplacements=e, depots=depots, coffre=contexte.coffre, journal=journal,
            sortie=self.sortie, envoyer=self._envoyer, lanceur=self.lanceur, isolement=isolement,
            quotas_claude=self.quotas_claude, budget=self.budget, executables=dict(executables or {}),
            compteurs_codex=lambda: self.compteurs_codex, **options_execution)
        self.compteurs_codex: list[dict[str, Any]] | None = None
        self.resultats_sondes: dict[str, Any] = {}
        self.tache_carte: asyncio.Task | None = None
        self.carte_courante: Any = None
        self.arret_carte = asyncio.Event()
        self.revoque = False
        self.jeton_refuse = False
        self.suspendu: str | None = None
        self.demarrage_fait = False
        self.annonce: dict[str, Any] = {}

    @staticmethod
    def _verif(contexte: Contexte) -> dict[str, Any]:
        if not contexte.identites:
            return {}
        from .plateforme.linux import IDENTITES

        return {"acp-verif": IDENTITES["acp-verif"]}

    def _depots(self, politique: Politique) -> Depots:
        e = self.contexte.emplacements
        coffre = self.contexte.coffre
        auteur = (politique.git.auteur_nom, politique.git.auteur_courriel) if politique.git else None

        def jeton_lecture() -> str | None:
            try:
                return coffre.lire("jeton-github")
            except CoffreErreur:
                return None

        depots = Depots(racine_depots=e.depots, racine_espaces=e.espaces, racine_bundles=e.bundles,
                        jeton_lecture=jeton_lecture)
        if auteur:
            depots.auteur = auteur
        return depots

    def _envoyer(self, route: str, corps: dict[str, Any]) -> Any:
        return self.protocole.envoyer(self.jeton, route, corps)

    # ------------------------------------------------------------------ refus définitifs (Linux : jamais de sortie)
    def _refus_definitif(self, exc: Refus) -> bool:
        if isinstance(exc, PosteRevoque):
            try:
                self.contexte.coffre.effacer("jeton-machine")
            except CoffreErreur:
                pass
            try:
                self.contexte.emplacements.machine.unlink()
            except OSError:
                pass
            self.revoque = True
            self._ecrire_etat(etat_machine="revoque")
            self.journal.ecrire("info", "poste_revoque", f"{exc.message} Retour à l'attente d'enrôlement, sans sortie.")
            self._stopper()
            return True
        if isinstance(exc, JetonRefuse):
            self.jeton_refuse = True
            self._ecrire_etat(jeton_refuse_depuis=_iso(self.horloge()))
            self.journal.ecrire("erreur", "jeton_refuse", f"{exc.message} Nouvel essai dans 15 min, sans sortie.",
                                statut=exc.statut)
            self._stopper()
            return True
        if isinstance(exc, ProtocoleIncompatible):
            self._arreter(CODE_CONFIGURATION, "erreur", "protocole_incompatible", exc.message)
            return True
        return False

    def _stopper(self) -> None:
        if self.arret is None:
            self.arret = CODE_NORMAL
        self.fin.set()
        self.protocole.client.interrompre()

    # ------------------------------------------------------------------ peut_executer (§ 6.1)
    def _pause_locale(self) -> bool:
        return self.contexte.emplacements.pause_locale.exists()

    def _voies_sondees(self) -> dict[str, str | None]:
        """Conditions des sondes (§ 6.1, point 3) : Codex connecté par compte ChatGPT, stockage ``file``, version
        épinglée ; Claude : jeton reconnu par ``auth status``, version épinglée. Sans sonde : fermé."""
        fermetures: dict[str, str | None] = {}
        codex = self.resultats_sondes.get("codex")
        if codex is None:
            fermetures["poste-codex"] = "Sonde Codex pas encore faite."
        elif codex.connexion != "compte_chatgpt":
            fermetures["poste-codex"] = "Codex non connecté par un compte ChatGPT sur l'exécutant."
        elif codex.stockage != "file":
            fermetures["poste-codex"] = "Stockage des identifiants Codex autre que « file »."
        elif not codex.version.get("conforme"):
            fermetures["poste-codex"] = "Version de Codex différente de la version épinglée."
        else:
            fermetures["poste-codex"] = None
        claude = self.resultats_sondes.get("claude")
        if claude is None:
            fermetures["poste-claude"] = "Sonde Claude pas encore faite."
        elif claude.connexion != "jeton_reconnu":
            fermetures["poste-claude"] = "Jeton Claude absent ou non reconnu (claude auth status)."
        elif not claude.version.get("conforme"):
            fermetures["poste-claude"] = "Version de Claude Code différente de la version épinglée."
        else:
            fermetures["poste-claude"] = None
        return fermetures

    def calculer_annonce(self) -> dict[str, Any]:
        """``peut_executer``, voies, carte en main, espace libre, et la raison quand l'exécution est refusée."""
        e = self.contexte.emplacements
        libre = espace_libre_mio(e.donnees) if e.donnees.exists() else None
        en_main = self.execution.carte_en_main()
        carte_en_cours = ({"tableau": en_main["tableau"], "carte": en_main["carte"], "run_id": en_main["run_id"]}
                          if en_main and {"tableau", "carte", "run_id"} <= set(en_main) else None)
        if self.tache_carte is not None and not self.tache_carte.done() and self.carte_courante is not None:
            # Carte en main, même avant que son état soit écrit (ou pendant l'envoi d'un refus) : aucune autre.
            c = self.carte_courante
            carte_en_cours = {"tableau": c.tableau, "carte": c.carte, "run_id": c.run_id}
        raison = None
        voies: list[str] = []
        if self.suspendu:
            raison = self.suspendu
        elif self.arret_global.is_set():
            raison = "Arrêt de l'exécutant en cours."
        elif not self.politique_valide:
            raison = "Politique de l'exécutant invalide."
        elif self.isolement.get("uid_separes") is not True:
            raison = self.isolement.get("raison") or "Sonde de plateforme non faite."
        elif self._pause_locale():
            raison = "Pause locale (acp-poste pause)."
        elif libre is not None and self.politique.disque and libre < self.politique.disque.seuil_libre_mio:
            raison = f"Espace libre du volume sous le seuil ({libre} Mio < {self.politique.disque.seuil_libre_mio})."
        else:
            ouvert, raison_budget = self.budget.ouvert(self.horloge())
            if not ouvert and carte_en_cours is None:
                raison = raison_budget
            else:
                sondees = self._voies_sondees()
                for voie, fermeture in self.execution.voies_ouvertes().items():
                    if fermeture is None and sondees.get(voie) is None:
                        voies.append(voie)
                if not voies:
                    raison = "Aucune voie ouverte (régime, conditions, quotas ou sondes)."
        peut = raison is None and bool(voies)
        self.annonce = {"peut_executer": peut, "voies_disponibles": voies if peut else [],
                        "carte_en_cours": carte_en_cours, "espace_libre_mio": libre}
        self._ecrire_etat(execution={"peut_executer": peut, "raison": raison, "voies": voies if peut else [],
                                     "carte_en_cours": carte_en_cours, "regime": self.isolement.get("regime")})
        return self.annonce

    # ------------------------------------------------------------------ points d'accroche
    def _annonce_execution(self) -> dict[str, Any] | None:
        return self.calculer_annonce()

    def _carte_recue(self, carte: Any) -> None:
        if self.tache_carte is not None and not self.tache_carte.done():
            self.journal.ecrire("erreur", "carte_en_trop", "Carte servie alors qu'une carte est en main : ignorée "
                                "(elle reviendra à l'échéance de sa réclamation).", carte=carte.carte)
            return
        self.journal.ecrire("info", "carte_recue", f"Carte {carte.role} reçue ({carte.voie}).", carte=carte.carte,
                            reprise=carte.reprise)
        self.arret_carte = asyncio.Event()
        self.carte_courante = carte
        self.tache_carte = asyncio.create_task(self._carte(carte))

    async def _carte(self, carte: Any) -> None:
        try:
            issue = await self.execution.executer(carte, self.arret_carte)
        except AgentSurvivant:
            self.suspendu = SUSPENDU
            self.journal.ecrire("erreur", "execution_suspendue", SUSPENDU, carte=carte.carte)
            return
        except Exception as exc:  # noqa: BLE001 — la carte reste réclamée jusqu'à son TTL ; jamais une trace au journal
            self.journal.ecrire("erreur", "carte_en_erreur", f"Erreur imprévue pendant la carte "
                                f"({type(exc).__name__}) : la réclamation expirera d'elle-même.", carte=carte.carte)
            return
        self._apres_issue(issue)
        self.carte_courante = None
        self.demande.set()

    def _apres_issue(self, issue: IssueCarte) -> None:
        reponse = issue.reponse
        if issue.route in ("reprendre", "arret") and reponse is not None and getattr(reponse, "etat", None) == \
                "deja_libre":
            self.execution.oublier_carte()

    async def _avant_reclamer(self) -> bool:
        if self.arret_global.is_set():
            return False
        resultats, refus = await asyncio.to_thread(self.sortie.rejouer, self._envoyer)
        for resultat in resultats:
            if resultat.route in ("reprendre", "arret") and getattr(resultat.reponse, "etat", None) == "deja_libre":
                en_main = self.execution.carte_en_main()
                if en_main and en_main.get("carte") == resultat.corps.get("carte"):
                    self.execution.oublier_carte()
        if refus is not None:
            if self._refus_definitif(refus):
                return False
            self.journal.ecrire_au_plus("sortie", 600, "avertissement", "file_de_sortie",
                                        f"File de sortie non vidée : {refus.message}")
            return False
        if not self.demarrage_fait:
            self.demarrage_fait = True
            await self._reprendre_au_demarrage()
        return True

    async def _reprendre_au_demarrage(self) -> None:
        """Carte en main au démarrage (§ 6.4) : rendue proprement (``arret``/``reprendre`` déjà envoyé) → rien ;
        sinon arrêt brutal (OOM, redémarrage du conteneur) → ``reprendre(redemarrage)``, ou ``bloquer(memoire)`` au
        deuxième sur la même carte."""
        en_main = self.execution.carte_en_main()
        if not en_main or en_main.get("etape") in ("arretee", "rendue"):
            return
        base = {"tableau": en_main["tableau"], "carte": en_main["carte"], "run_id": en_main["run_id"]}
        oom = int(self.execution.session(en_main["carte"]).get("oom", 0))
        if en_main.get("etape") in ("agent", "verification", "preparation_dependances"):
            # Arrêt brutal pendant que l'agent ou la vérification tournait : compté comme un arrêt mémoire (§ 6.4).
            # Pendant la préparation git ou l'envoi d'une issue, la reprise suffit.
            oom += 1
            self.execution._noter_session(en_main["carte"], oom=oom)
        from .sortie import nouvel_id_envoi

        if oom >= 2:
            corps = dict(base, id_envoi=nouvel_id_envoi(), genre="memoire",
                         raison="Mémoire insuffisante (limite 4 Gio) : deux arrêts brutaux sur cette carte.")
            issue = await asyncio.to_thread(self.execution.emettre, "bloquer", corps)
            if issue.envoyee:
                self.execution.oublier_carte()
            return
        corps = dict(base, id_envoi=nouvel_id_envoi(), motif="redemarrage")
        self.execution._ecrire_json(self.contexte.emplacements.carte, dict(en_main, etape="rendue"))
        issue = await asyncio.to_thread(self.execution.emettre, "reprendre", corps)
        self._apres_issue(issue)

    def _releves_permis(self) -> bool:
        if self._pause_locale():
            return False
        return self.tache_carte is None or self.tache_carte.done()

    async def _sondes(self) -> tuple[Any, Any]:
        verrous = []
        try:
            for chemin in (self.contexte.emplacements.verrou_codex, self.contexte.emplacements.verrou_claude):
                chemin.parent.mkdir(parents=True, exist_ok=True)
                verrous.append(Verrou(chemin).prendre())
        except VerrouOccupe:
            for verrou in verrous:
                verrou.rendre()
            return None, None
        try:
            codex, claude = await relever(self.politique, emplacements=self.contexte.emplacements,
                                          coffre=self.contexte.coffre,
                                          compteur_claude=self.quotas_claude.releve,
                                          **self.contexte.parametres_releve(self.politique))
        finally:
            for verrou in verrous:
                verrou.rendre()
        self.resultats_sondes = {"codex": codex, "claude": claude}
        if codex is not None:
            self.compteurs_codex = codex.releve.get("compteurs")
        return codex, claude

    def _inventaire(self, codex: Any, claude: Any) -> dict[str, Any]:
        return construire(self.politique, codex, claude, valeurs_exactes=self.journal.valeurs_masquees(),
                          infos=self.contexte.infos(), isolement=self.isolement)

    # ------------------------------------------------------------------ vie du service
    async def _surveiller(self) -> None:
        """Arrêt global (SIGTERM) ou pause locale pendant une carte : la carte s'arrête proprement."""
        while self.arret is None:
            if self.tache_carte is not None and not self.tache_carte.done():
                if self.arret_global.is_set():
                    self.execution.motif_arret = "sigterm"
                    self.arret_carte.set()
                elif self._pause_locale():
                    self.execution.motif_arret = "pause_locale"
                    self.arret_carte.set()
            if self.arret_global.is_set():
                if self.tache_carte is not None and not self.tache_carte.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(self.tache_carte), timeout=ARRET_CARTE_MAX_S)
                    except (TimeoutError, asyncio.CancelledError):
                        pass
                self._stopper()
                return
            await self._dormir(0.5)

    async def executer(self, duree_max_s: float | None = None) -> int:
        self.journal.ecrire("info", "demarrage", "Service de l'exécutant démarré.",
                            empreinte_politique=self.politique.empreinte, jeton=self.jeton.empreinte,
                            regime=self.isolement.get("regime"))
        taches = [asyncio.create_task(self._garde(self._attendre(), "attente")),
                  asyncio.create_task(self._garde(self._relever(), "relevés")),
                  asyncio.create_task(self._garde(self._surveiller(), "surveillance"))]
        try:
            try:
                await asyncio.wait_for(self.fin.wait(), timeout=duree_max_s)
            except TimeoutError:
                pass
        finally:
            if self.arret is None:
                self.arret = CODE_NORMAL
            self.fin.set()
            self.protocole.client.interrompre()
            for tache in taches:
                tache.cancel()
            await asyncio.gather(*taches, return_exceptions=True)
            if self.tache_carte is not None and not self.tache_carte.done():
                self.execution.motif_arret = "sigterm"
                self.arret_carte.set()
                try:
                    await asyncio.wait_for(asyncio.shield(self.tache_carte), timeout=ARRET_CARTE_MAX_S)
                except (TimeoutError, asyncio.CancelledError):
                    pass
        self.journal.ecrire("info", "arret", "Service de l'exécutant arrêté.", code=self.arret)
        return self.arret


# ============================================================ démarrage


def _non_enrole_une_fois_par_jour(contexte: Contexte, journal: Journal) -> None:
    marque = contexte.emplacements.etat / "non-enrole.jour"
    jour = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        if marque.read_text(encoding="ascii").strip() == jour:
            return
    except OSError:
        pass
    journal.ecrire("info", "non_enrole", NON_ENROLE)
    try:
        ecrire_atomiquement(marque, jour.encode("ascii"))
    except OSError:
        pass


async def _dormir(arret: asyncio.Event, secondes: float) -> None:
    try:
        await asyncio.wait_for(arret.wait(), timeout=secondes)
    except TimeoutError:
        pass


async def attendre_enrolement(contexte: Contexte, journal: Journal, arret: asyncio.Event, *,
                              relecture_s: float = RELECTURE_JETON_S) -> str | None:
    """Jeton machine dès qu'``acp-poste enroler`` l'a écrit ; ``None`` si l'arrêt est demandé avant. Aucune requête
    vers Hermes pendant l'attente ; une ligne de journal par jour."""
    while not arret.is_set():
        try:
            brut = contexte.coffre.lire("jeton-machine")
        except CoffreErreur as exc:
            journal.ecrire_au_plus("coffre", 3600, "erreur", "coffre", str(exc))
            brut = None
        if brut:
            return brut
        _non_enrole_une_fois_par_jour(contexte, journal)
        await _dormir(arret, relecture_s)
    return None


def preparer_volume(contexte: Contexte, politique: Politique, journal: Journal) -> None:
    """``config.toml`` du profil Codex (stockage ``file``), écrit s'il manque, jamais par-dessus une version modifiée."""
    from .sondes_codex import ecrire_config_toml

    if politique.codex is None:
        return
    try:
        etat = ecrire_config_toml(politique.codex.home, "linux")
    except (ValueError, OSError) as exc:
        journal.ecrire("erreur", "profil_codex", str(exc)[:300])
        return
    identite = contexte.identites.get("codex")
    if etat == "cree" and identite is not None and hasattr(os, "chown"):
        for chemin in (politique.codex.home, politique.codex.home / "config.toml"):
            os.chown(chemin, identite.uid, identite.gid)
        os.chmod(politique.codex.home, 0o700)


def faire_sonde(contexte: Contexte, politique: Politique, journal: Journal) -> dict[str, Any]:
    """Sonde de plateforme au démarrage (rangée dans ``etat/isolement.json``) → bloc ``isolement_linux``."""
    resultat = sonder(codex=str(politique.codex.executable) if politique.codex else None,
                      claude=str(politique.claude.executable) if politique.claude else None,
                      racine_temporaire=None)
    try:
        ecrire_atomiquement(contexte.emplacements.sonde_isolement,
                            json.dumps(resultat, ensure_ascii=False).encode("utf-8"))
    except OSError:
        pass
    verdict = resultat["verdict"]
    journal.ecrire("info", "sonde_plateforme", f"Sonde de plateforme : régime {verdict['regime']}. "
                   f"{verdict['raison']}", bwrap=verdict["bwrap"], uid_separes=verdict["uid_separes"])
    sans = politique.codex.sans_bac_a_sable if politique.codex else "refuse"
    return bloc_isolement(resultat, sans_bac_a_sable=sans)


async def servir_executant(contexte: Contexte, *, duree_max_s: float | None = None,
                           repli: Callable[[], Repli] = Repli,
                           horloge: Callable[[], datetime] = lambda: datetime.now(UTC),
                           sonde: Callable[[Contexte, Politique, Journal], dict[str, Any]] | None = None,
                           controles_systeme: bool = True, proprietaire: int = 0,
                           signaux: bool = True, arret: asyncio.Event | None = None,
                           relecture_jeton_s: float = RELECTURE_JETON_S,
                           attente_jeton_refuse_s: float = JETON_REFUSE_ATTENTE_S, **options: Any) -> int:
    """Boucle de l'exécutant. Les tests passent ``sonde`` (aucun lancement réel), ``controles_systeme=False`` et
    ``proprietaire`` (pas de root), ``signaux=False`` et leur propre ``arret``, des délais courts, et les options de
    :class:`ServiceExecutant` (faux protocole, faux agents, dépôts locaux)."""
    contexte.emplacements.verrous.mkdir(parents=True, exist_ok=True)
    verrou = Verrou(contexte.emplacements.verrou_instance)
    try:
        verrou.prendre()
    except VerrouOccupe:
        print(AUTRE_INSTANCE, file=sys.stderr)
        return CODE_INSTANCE
    arret = arret or asyncio.Event()
    boucle = asyncio.get_running_loop()
    if signaux and hasattr(signal, "SIGTERM"):
        try:
            boucle.add_signal_handler(signal.SIGTERM, arret.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        journal = contexte.journal()
        try:
            politique = charger(contexte.emplacements)
        except PolitiqueRefusee as exc:
            journal.ecrire("erreur", "politique_refusee", str(exc))
            print(str(exc), file=sys.stderr)
            return CODE_CONFIGURATION
        journal = contexte.journal(politique)
        try:
            if controles_systeme:
                if not (hasattr(os, "geteuid") and os.geteuid() == 0):
                    raise PolitiqueRefusee(PAS_ROOT)
                verifier_interpreteur(politique)
            verifier_droits(politique, proprietaire=proprietaire)
        except PolitiqueRefusee as exc:
            journal.ecrire("erreur", "demarrage_refuse", str(exc))
            print(str(exc), file=sys.stderr)
            return CODE_CONFIGURATION
        preparer_volume(contexte, politique, journal)
        isolement = await asyncio.to_thread(sonde or faire_sonde, contexte, politique, journal)
        try:
            journal.masquer_valeur("jeton-claude", contexte.coffre.lire("jeton-claude"))
            journal.masquer_valeur("jeton-github", contexte.coffre.lire("jeton-github"))
        except CoffreErreur as exc:
            journal.ecrire("erreur", "coffre", str(exc))
        while not arret.is_set():
            brut = await attendre_enrolement(contexte, journal, arret, relecture_s=relecture_jeton_s)
            if brut is None:
                break
            try:
                jeton = Jeton(brut)
            except JetonInvalide:
                journal.ecrire("erreur", "jeton_illisible", JETON_ILLISIBLE)
                print(JETON_ILLISIBLE, file=sys.stderr)
                # Jamais de sortie (railway ssh resterait possible) : le propriétaire oublie le jeton et réenrôle.
                await _dormir(arret, attente_jeton_refuse_s)
                continue
            journal.masquer_valeur("jeton-machine", brut)
            service = ServiceExecutant(contexte, politique, jeton, journal, isolement=isolement, arret_global=arret,
                                       repli=repli, horloge=horloge, proprietaire=proprietaire, **options)
            code = await service.executer(duree_max_s)
            if arret.is_set():
                break
            if service.revoque:
                continue
            if service.jeton_refuse:
                await _dormir(arret, attente_jeton_refuse_s)
                continue
            if duree_max_s is not None:
                return code
            if code != CODE_NORMAL:
                return code
        return CODE_NORMAL
    except Exception as exc:  # noqa: BLE001 — jamais une trace (chemins) : le type seul
        print(f"Erreur imprévue du superviseur ({type(exc).__name__}) : arrêt.", file=sys.stderr)
        return CODE_ERREUR
    finally:
        verrou.rendre()
