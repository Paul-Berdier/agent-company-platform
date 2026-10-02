"""Boucle « servir » du poste (cahier P5 § 6.1), lancée par la tâche planifiée ``\\ACP\\Poste ACP``.

Démarrage, chaque refus en français :

1. verrou d'instance (sinon « Une autre instance du poste tourne déjà dans ce compte : arrêt. », code 3) ;
2. ``poste.toml`` valide (sinon code 2) ; compte courant = ``compte_attendu`` en mode ``dedie`` (2) ; ``poste.toml`` et
   les binaires des CLI non modifiables par ce compte (2) ;
3. jeton machine au coffre (absent : « Poste non enrôlé… », code 0, une ligne de journal par jour au plus).

Puis **une seule boucle asyncio** pour toute la vie du processus (jamais un ``asyncio.run`` par relevé : sous
Windows, chaque boucle ouvre brièvement un écouteur ``127.0.0.1`` pour son auto-réveil) et deux tâches :

- **attente** : ``reclamer`` en continu (25 s), qui vaut battement de présence ; ordres ``releve`` → relevé,
  ``pause``/``reprise`` → journal ; erreurs réseau et 5xx : repli 1, 2, 4… 60 s, gigue ±20 %, une ligne de journal
  par 10 min au plus ; 401 ``poste_revoque`` : jeton effacé, arrêt (0) ; 401 de la couture : jeton **gardé**, plus
  aucun échange, arrêt (4) ; 409 protocole : arrêt (2) ;
- **relevés** : au démarrage, puis toutes les ``[sondes] intervalle_s``, sur ordre ``releve`` et quand un binaire de
  CLI change ; sondes Codex et Claude en parallèle sous le verrou des sondes, inventaire construit, balayé, publié ;
  429 : inventaire gardé et renvoyé après ``Retry-After`` ; écart d'horloge de plus de 2 min : inventaire retenu.

``poste.toml`` est relu à chaque cycle : devenu invalide (ou modifiable par le compte du poste), il est annoncé
(``politique_valide: false``) et plus rien n'est publié.

Étape P6 : l'exécutant Linux réutilise cette boucle par :class:`acp_poste.service_executant.ServiceExecutant`, qui
remplace les points d'accroche (:meth:`Service._annonce_execution`, :meth:`Service._carte_recue`,
:meth:`Service._avant_reclamer`, :meth:`Service._sondes`, :meth:`Service._inventaire`) ; le poste Windows garde
exactement le comportement de P5 (aucune carte, corps de ``reclamer`` inchangé).
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import UTC, datetime
from typing import Any, Callable

from acp_poste_contrat.machine import ACQUITTES_MAX, ATTENTE_MIN_S

from .chemins import commande_poste
from .coffre import CoffreErreur, ecrire_atomiquement
from .contexte import Contexte
from .inventaire import InventaireRetenu, construire, relever
from .jeton import Jeton, JetonInvalide
from .journal import Journal
from .politique import Politique, PolitiqueRefusee, charger, verifier_compte, verifier_droits, verifier_interpreteur
from .protocole import (
    HermesIndisponible,
    HorsContrat,
    JetonRefuse,
    PosteRevoque,
    Protocole,
    ProtocoleIncompatible,
    Refus,
    TropFrequent,
)
from .verrou import Verrou, VerrouOccupe

CODE_NORMAL = 0
CODE_ERREUR = 1
CODE_CONFIGURATION = 2
CODE_INSTANCE = 3
CODE_JETON_REFUSE = 4

AUTRE_INSTANCE = "Une autre instance du poste tourne déjà dans ce compte : arrêt."
NON_ENROLE = (f"Poste non enrôlé : lancez « {commande_poste('enroler')} » dans la console PowerShell du compte du "
              "poste.")
JETON_ILLISIBLE = (f"Jeton machine du coffre au format invalide : lancez « {commande_poste('oublier-jeton')} » puis "
                   "réenrôlez le poste.")
ECART_HORLOGE_MAX_S = 120
REPLI_MAX_S = 60.0
REVEIL_S = 30.0
ORDRE_EN_COURS_S = 5.0
PUBLICATIONS_MAX = 5
PERIODE_JOURNAL_S = 600.0


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Repli:
    """Repli exponentiel borné (1, 2, 4… 60 s), gigue de ±20 %."""

    def __init__(self, aleatoire: Callable[[], float] = random.random, maximum: float = REPLI_MAX_S) -> None:
        self.aleatoire = aleatoire
        self.maximum = maximum
        self.essais = 0

    def suivant(self) -> float:
        base = min(self.maximum, 2.0 ** self.essais)
        self.essais += 1
        return base * (0.8 + 0.4 * self.aleatoire())

    def reinitialiser(self) -> None:
        self.essais = 0


def _signature(chemin) -> tuple | None:
    try:
        etat = chemin.stat()
        return (etat.st_size, etat.st_mtime_ns)
    except (OSError, AttributeError):
        return None


class Service:
    def __init__(self, contexte: Contexte, politique: Politique, jeton: Jeton, journal: Journal, *,
                 horloge: Callable[[], datetime] = lambda: datetime.now(UTC),
                 repli: Callable[[], Repli] = Repli) -> None:
        self.contexte = contexte
        self.politique = politique
        self.politique_valide = True
        self.jeton = jeton
        self.journal = journal
        self.horloge = horloge
        self.fabrique_repli = repli
        self.protocole = Protocole(contexte.client(politique))
        self.acquittes: list[int] = []
        self.ordres_vus: set[int] = set()
        self.releves_a_servir: list[int] = []
        self.demande = asyncio.Event()
        self.fin = asyncio.Event()
        self.arret: int | None = None
        self.etat_machine: str | None = None
        self.ecart_horloge_s: float | None = None
        self.signatures: dict[str, tuple | None] = {}
        self.etat: dict[str, Any] = {"etat_machine": None, "dernier_echange": None, "joignable": None,
                                     "jeton_refuse_depuis": None, "ecart_horloge_s": None, "dernier_inventaire": None,
                                     "politique_valide": True}
        self.publications = 0
        self.releves = 0
        # Propriétaire attendu de la politique de l'exécutant Linux (root ; les tests sans root passent le leur).
        self.proprietaire = 0

    # ------------------------------------------------------------------ état et arrêt
    def _ecrire_etat(self, **maj: Any) -> None:
        self.etat.update(maj)
        try:
            ecrire_atomiquement(self.contexte.emplacements.etat_service,
                                json.dumps(self.etat, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass

    def _arreter(self, code: int, niveau: str, evenement: str, message: str, **details: Any) -> None:
        if self.arret is None:
            self.arret = code
            self.journal.ecrire(niveau, evenement, message, **details)
            print(message, file=sys.stderr)
        self.fin.set()
        self.protocole.client.interrompre()

    def _revoque(self, exc: PosteRevoque) -> None:
        try:
            self.contexte.coffre.effacer("jeton-machine")
        except CoffreErreur:
            pass
        try:
            self.contexte.emplacements.machine.unlink()
        except OSError:
            pass
        self._ecrire_etat(etat_machine="revoque")
        self._arreter(CODE_NORMAL, "info", "poste_revoque", exc.message)

    def _jeton_refuse(self, exc: JetonRefuse) -> None:
        self._ecrire_etat(jeton_refuse_depuis=_iso(self.horloge()))
        self._arreter(CODE_JETON_REFUSE, "erreur", "jeton_refuse", exc.message, statut=exc.statut)

    def _refus_definitif(self, exc: Refus) -> bool:
        """Traite les refus qui arrêtent le poste ; ``True`` si le service doit s'arrêter."""
        if isinstance(exc, PosteRevoque):
            self._revoque(exc)
        elif isinstance(exc, JetonRefuse):
            self._jeton_refuse(exc)
        elif isinstance(exc, ProtocoleIncompatible):
            self._arreter(CODE_CONFIGURATION, "erreur", "protocole_incompatible", exc.message)
        else:
            return False
        return True

    async def _dormir(self, secondes: float) -> None:
        if secondes <= 0:
            return
        try:
            await asyncio.wait_for(self.fin.wait(), timeout=secondes)
        except TimeoutError:
            pass

    # ------------------------------------------------------------------ politique
    def _relire_politique(self) -> None:
        try:
            nouvelle = charger(self.contexte.emplacements, chemin=self.politique.chemin)
            verifier_droits(nouvelle, proprietaire=self.proprietaire)
        except PolitiqueRefusee as exc:
            if self.politique_valide:
                self.journal.ecrire("erreur", "politique_invalide", f"{exc} Plus rien n'est publié.")
            self.politique_valide = False
            return
        if not self.politique_valide:
            self.journal.ecrire("info", "politique_valide", "poste.toml de nouveau valide : publication reprise.")
            self.demande.set()
        if nouvelle.hermes.origine != self.politique.hermes.origine:
            self.protocole = Protocole(self.contexte.client(nouvelle))
        self.politique = nouvelle
        self.politique_valide = True

    def _cli_changee(self) -> bool:
        changee = False
        for nom, section in (("codex", self.politique.codex), ("claude", self.politique.claude)):
            if section is None:
                continue
            signature = _signature(section.executable)
            if nom in self.signatures and self.signatures[nom] != signature:
                changee = True
        return changee

    def _noter_signatures(self) -> None:
        for nom, section in (("codex", self.politique.codex), ("claude", self.politique.claude)):
            if section is not None:
                self.signatures[nom] = _signature(section.executable)

    # ------------------------------------------------------------------ points d'accroche (exécutant, étape P6)
    def _annonce_execution(self) -> dict[str, Any] | None:
        """Champs d'exécution de ``reclamer`` ; ``None`` : corps de P5 (poste Windows, aucune carte)."""
        return None

    def _carte_recue(self, carte: Any) -> None:
        """Carte servie par Hermes (jamais pour le poste Windows : le protocole la refuse avant)."""

    async def _avant_reclamer(self) -> bool:
        """``False`` : pas de réclamation à ce tour (file de sortie non vidée…)."""
        return True

    def _releves_permis(self) -> bool:
        return True

    async def _sondes(self) -> tuple[Any, Any]:
        return await relever(self.politique, emplacements=self.contexte.emplacements, coffre=self.contexte.coffre,
                             lanceurs=self.contexte.lanceurs, environnement=self.contexte.environnement)

    def _inventaire(self, codex: Any, claude: Any) -> dict[str, Any]:
        return construire(self.politique, codex, claude, windows=self.contexte.version_windows(),
                          valeurs_exactes=self.journal.valeurs_masquees())

    # ------------------------------------------------------------------ attente (long-poll)
    async def _attendre(self) -> None:
        repli = self.fabrique_repli()
        # Première attente courte (5 s, le minimum du contrat) : l'état du poste (confirmé ou non) est connu vite
        # après le démarrage, et le premier relevé part sans attendre une échéance entière.
        attente = ATTENTE_MIN_S
        while self.arret is None:
            await asyncio.to_thread(self._relire_politique)
            self._ecrire_etat(politique_valide=self.politique_valide)
            if not await self._avant_reclamer():
                if self.arret is not None:
                    return
                await self._dormir(repli.suivant())
                continue
            lot = self.acquittes[:ACQUITTES_MAX]
            try:
                reponse = await asyncio.to_thread(
                    self.protocole.reclamer, self.jeton, acquittes=lot,
                    attente_max_s=attente, politique_valide=self.politique_valide,
                    execution=self._annonce_execution())
            except Refus as exc:
                if self.arret is not None or self._refus_definitif(exc):
                    return
                if isinstance(exc, (HermesIndisponible, HorsContrat)):
                    delai = repli.suivant()
                    self._ecrire_etat(joignable=False)
                    self.journal.ecrire_au_plus("reclamer", PERIODE_JOURNAL_S, "avertissement", "hermes_indisponible",
                                                f"{exc.message} Nouvel essai dans {delai:.0f} s.")
                    await self._dormir(delai)
                else:
                    self.journal.ecrire_au_plus("reclamer_refus", PERIODE_JOURNAL_S, "erreur", "reclamer_refuse",
                                                exc.message, statut=exc.statut, code=exc.code)
                    await self._dormir(REPLI_MAX_S)
                continue
            repli.reinitialiser()
            attente = self.politique.hermes.attente_max_s
            del self.acquittes[:len(lot)]
            maintenant = self.horloge()
            ecart = (maintenant - reponse.maintenant).total_seconds()
            self.ecart_horloge_s = ecart
            if abs(ecart) > ECART_HORLOGE_MAX_S:
                self.journal.ecrire_au_plus("horloge", PERIODE_JOURNAL_S, "avertissement", "horloge",
                                            f"Horloge du poste décalée de {ecart:+.0f} s par rapport à Hermes : "
                                            "inventaire retenu tant que l'écart dépasse 2 min.")
            precedent, self.etat_machine = self.etat_machine, reponse.etat_machine
            if precedent != reponse.etat_machine:
                if reponse.etat_machine == "actif":
                    self.journal.ecrire("info", "en_ligne", "Poste confirmé et en ligne : présence et ordres reçus.")
                    self.demande.set()
                else:
                    self.journal.ecrire("info", "a_confirmer", "Poste en attente de confirmation de son empreinte "
                                        "sur la page Poste.")
            if reponse.remplace:
                self.journal.ecrire_au_plus("remplace", PERIODE_JOURNAL_S, "avertissement", "attente_remplacee",
                                            "Attente remplacée par une autre connexion de ce poste (deux processus "
                                            "avec le même jeton ?).")
            nouveaux = 0
            for ordre in reponse.ordres:
                if ordre.id in self.ordres_vus:
                    continue
                self.ordres_vus.add(ordre.id)
                nouveaux += 1
                self.journal.ecrire("info", "ordre", f"Ordre « {ordre.genre} » reçu.", ordre=ordre.id)
                if ordre.genre == "releve":
                    self.releves_a_servir.append(ordre.id)
                    self.demande.set()
                else:
                    self.acquittes.append(ordre.id)
            self._ecrire_etat(dernier_echange=_iso(maintenant), etat_machine=reponse.etat_machine,
                              ecart_horloge_s=round(ecart), joignable=True, pause=reponse.pause_reclamations)
            if reponse.carte is not None:
                self._carte_recue(reponse.carte)
            if reponse.ordres and nouveaux == 0:
                await self._dormir(ORDRE_EN_COURS_S)
            elif reponse.prochaine_attente_s:
                await self._dormir(min(float(reponse.prochaine_attente_s), REPLI_MAX_S))

    # ------------------------------------------------------------------ relevés
    async def _relever(self) -> None:
        boucle = asyncio.get_running_loop()
        prochain = boucle.time()
        while self.arret is None:
            attente = max(0.0, prochain - boucle.time())
            if attente > 0 and not self.demande.is_set():
                try:
                    await asyncio.wait_for(self.demande.wait(), timeout=min(attente, REVEIL_S))
                except TimeoutError:
                    pass
            if self.arret is not None:
                return
            demande = self.demande.is_set()
            self.demande.clear()
            if not demande and boucle.time() < prochain and not self._cli_changee():
                continue
            if self.etat_machine != "actif":
                # Poste à confirmer (ou pas encore joint) : rien n'est publié ; la confirmation relance un relevé.
                prochain = boucle.time() + REVEIL_S
                continue
            if not self._releves_permis():
                prochain = boucle.time() + 60
                continue
            servis = list(self.releves_a_servir)
            if not self.politique_valide:
                self.journal.ecrire_au_plus("politique_releve", PERIODE_JOURNAL_S, "avertissement", "releve_suspendu",
                                            "Politique locale invalide : aucun relevé publié.")
                self._servir(servis)
                prochain = boucle.time() + self.politique.sondes.intervalle_s
                continue
            try:
                verrou = Verrou(self.contexte.emplacements.verrou_sondes).prendre()
            except VerrouOccupe:
                self.journal.ecrire("info", "sondes_occupees", "Une sonde est en cours dans une console : relevé "
                                    "reporté d'une minute.")
                prochain = boucle.time() + 60
                continue
            try:
                codex, claude = await self._sondes()
            finally:
                verrou.rendre()
            self._noter_signatures()
            self.releves += 1
            for nom, resultat in (("codex", codex), ("claude", claude)):
                if resultat is not None:
                    details = {k: v for k, v in resultat.mesures.items() if isinstance(v, (int, float))}
                    details.update(modeles=len(resultat.releve["modeles"]), origine=resultat.releve["origine_liste"],
                                   connexion=resultat.connexion, version=resultat.version.get("lue"))
                    self.journal.ecrire("info", f"sonde_{nom}", f"Sonde {nom} : relevé {resultat.releve['etat']}.",
                                        **details)
            try:
                inventaire = self._inventaire(codex, claude)
            except InventaireRetenu as exc:
                self.journal.ecrire("erreur", "inventaire_retenu", str(exc))
                self._servir(servis)
                prochain = boucle.time() + self.politique.sondes.intervalle_s
                continue
            try:
                ecrire_atomiquement(self.contexte.emplacements.dernier_inventaire,
                                    json.dumps(inventaire, ensure_ascii=False).encode("utf-8"))
            except OSError:
                pass
            if await self._publier(inventaire):
                self._servir(servis)
                prochain = boucle.time() + self.politique.sondes.intervalle_s
            else:
                prochain = boucle.time() + REPLI_MAX_S

    def _servir(self, servis: list[int]) -> None:
        for identifiant in servis:
            if identifiant in self.releves_a_servir:
                self.releves_a_servir.remove(identifiant)
            self.acquittes.append(identifiant)

    async def _publier(self, inventaire: dict[str, Any]) -> bool:
        """Publie l'inventaire (quelques essais) ; ``True`` s'il est reçu ou refusé pour de bon (inutile de
        recommencer tel quel), ``False`` s'il faut réessayer plus tard."""
        repli = self.fabrique_repli()
        for _essai in range(PUBLICATIONS_MAX):
            if self.arret is not None:
                return False
            if self.ecart_horloge_s is not None and abs(self.ecart_horloge_s) > ECART_HORLOGE_MAX_S:
                self.journal.ecrire_au_plus("horloge_inventaire", PERIODE_JOURNAL_S, "avertissement",
                                            "inventaire_retenu", "Horloge du poste décalée de plus de 2 min : "
                                            "inventaire retenu.")
                return False
            try:
                reponse = await asyncio.to_thread(self.protocole.publier, self.jeton, inventaire)
            except TropFrequent as exc:
                await self._dormir(float(exc.retry_after or 60))
                continue
            except Refus as exc:
                if self._refus_definitif(exc):
                    return False
                if isinstance(exc, (HermesIndisponible, HorsContrat)):
                    self.journal.ecrire_au_plus("publier", PERIODE_JOURNAL_S, "avertissement", "publication_reportee",
                                                exc.message)
                    await self._dormir(repli.suivant())
                    continue
                self.journal.ecrire("erreur", "inventaire_refuse", exc.message, statut=exc.statut, code=exc.code)
                return True
            self.publications += 1
            self._ecrire_etat(dernier_inventaire=_iso(reponse.recu_le))
            self.journal.ecrire("info", "inventaire_publie", "Inventaire publié.",
                                releves=[f"{voie}:{identifiant}" for voie, identifiant in reponse.releves.items()],
                                alertes=len(reponse.alertes))
            return True
        return False

    # ------------------------------------------------------------------ vie du service
    async def _garde(self, travail, nom: str) -> None:
        """Une tâche qui tombe arrête le service (code 1) au lieu de mourir en silence."""
        try:
            await travail
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - jamais une trace (chemins) dans le journal : le type seul
            self._arreter(CODE_ERREUR, "erreur", "erreur_imprevue",
                          f"Erreur imprévue dans la tâche « {nom} » du service ({type(exc).__name__}) : arrêt ; la "
                          "tâche planifiée relancera le poste.")

    async def executer(self, duree_max_s: float | None = None) -> int:
        self.journal.ecrire("info", "demarrage", "Service du poste démarré.",
                            empreinte_politique=self.politique.empreinte, jeton=self.jeton.empreinte)
        taches = [asyncio.create_task(self._garde(self._attendre(), "attente")),
                  asyncio.create_task(self._garde(self._relever(), "relevés"))]
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
        self.journal.ecrire("info", "arret", "Service du poste arrêté.", code=self.arret)
        return self.arret


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


async def servir(contexte: Contexte, *, duree_max_s: float | None = None,
                 repli: Callable[[], Repli] = Repli,
                 horloge: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    """``duree_max_s``, ``repli`` et ``horloge`` servent aux tests (arrêt borné, repli accéléré, horloge décalée) ; la
    tâche planifiée n'en passe aucun. L'exécutant Linux a sa propre boucle (:mod:`acp_poste.service_executant`)."""
    if contexte.plateforme == "linux":
        from .service_executant import servir_executant

        return await servir_executant(contexte, duree_max_s=duree_max_s, repli=repli, horloge=horloge)
    verrou = Verrou(contexte.emplacements.verrou_instance)
    try:
        verrou.prendre()
    except VerrouOccupe:
        print(AUTRE_INSTANCE, file=sys.stderr)
        return CODE_INSTANCE
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
            verifier_compte(politique, contexte.compte_courant())
            verifier_droits(politique)
            # Au démarrage seulement : l'interpréteur ne change pas en cours de route (relecture de P5, D67).
            verifier_interpreteur(politique)
        except PolitiqueRefusee as exc:
            journal.ecrire("erreur", "demarrage_refuse", str(exc))
            print(str(exc), file=sys.stderr)
            return CODE_CONFIGURATION
        try:
            brut = contexte.coffre.lire("jeton-machine")
            journal.masquer_valeur("jeton-claude", contexte.coffre.lire("jeton-claude"))
        except CoffreErreur as exc:
            journal.ecrire("erreur", "coffre", str(exc))
            print(str(exc), file=sys.stderr)
            return CODE_CONFIGURATION
        if brut is None:
            _non_enrole_une_fois_par_jour(contexte, journal)
            print(NON_ENROLE, file=sys.stderr)
            return CODE_NORMAL
        try:
            jeton = Jeton(brut)
        except JetonInvalide:
            journal.ecrire("erreur", "jeton_illisible", JETON_ILLISIBLE)
            print(JETON_ILLISIBLE, file=sys.stderr)
            return CODE_CONFIGURATION
        journal.masquer_valeur("jeton-machine", brut)
        return await Service(contexte, politique, jeton, journal, repli=repli, horloge=horloge).executer(
            duree_max_s)
    finally:
        verrou.rendre()
