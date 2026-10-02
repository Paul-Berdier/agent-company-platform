"""Flux d'invalidation du tableau de bord (étape P7, cahier P7 § 5 ; décision P7-4).

Le flux ``GET /v1/flux`` SIGNALE qu'un sujet a changé ; la page relit alors la route REST du sujet. Aucune donnée
métier ne passe par le flux : pas de second format à tenir, aucune divergence possible entre flux et routes, et un
client qui rate un signal retombe sur l'état exact à la relecture suivante.

Sujets (:data:`SUJETS`) et ce que leur empreinte relit, en lecture seule :

- ``projets`` : projets (nombre, dernière mise à jour), demandes (créées, observées, réclamées, relancées), lignes du
  journal rattachées à un projet, tours, et le dernier événement de chaque tableau de projet non terminé ;
- ``questions`` : questions (nombre, dernière mise à jour, livraison à l'exécutant) et les mêmes derniers événements
  de tableaux (triage, blocage, revue en viennent) ;
- ``poste`` : postes (état, conditions annoncées à la réclamation, carte en main, disque, politique), présence ÉVALUÉE
  MAINTENANT (en ligne ou hors ligne au seuil ``seuil_hors_ligne_s``, redéploiement annoncé), inventaires reçus, ordres
  en attente ;
- ``quotas`` : relevés (reçus, acceptés), attentes de quota, table de routage, surcharges et politique (la page
  Routage lit les mêmes relevés que la page Quotas) ;
- ``notifications`` : canal publié par la passerelle, notifications par état ;
- ``pause`` : arrêt d'urgence de Hermes, réglage ``pause_reclamations``, projets en pause ;
- ``discussions`` : nombre de requêtes du serveur au client ouvertes dans CE processus (``ka.requetes_ouvertes``) ;
  inconnu (``None``) : ``discussions_suivies: false``, le sujet n'est alors jamais publié et le client relit la
  section lui-même.

Veilleur : UNE tâche asyncio par boucle du tableau de bord (:class:`Diffuseur`), démarrée au premier abonné, arrêtée
:data:`ARRET_VEILLEUR_S` secondes après le dernier. Toutes les ``flux_intervalle_s`` secondes (plancher 1), DANS UN FIL
(jamais sur la boucle, où tourne le ping des WebSocket de l'agent), elle calcule les empreintes et publie les sujets
dont l'empreinte a changé. Un sujet illisible (base ou tableau) prend une empreinte « illisible » STABLE : il est publié
une fois, marqué ``illisibles``, jamais une fausse stabilité ni une publication à chaque tour.

Révision : ``<époque>.<numéro>``. L'époque est l'heure de création du diffuseur (démarrage du tableau de bord) ; le
numéro croît à chaque publication. Un client qui revient avec ``Last-Event-ID`` égal à la révision courante n'a rien
manqué (première trame vide) ; toute autre valeur, ou aucune, lui fait tout relire.

État en mémoire, propre au processus du tableau de bord (les abonnés et la dernière empreinte) : il ne porte aucune
correction (tout est en base) ; une seconde copie de ce module dans un autre processus serait sans effet sur celui-ci.
Aucun import de Hermes ici : les lectures de Hermes passent par :mod:`kanban_adapter`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from . import base
from . import kanban_adapter as ka

_log = logging.getLogger(__name__)

SUJETS: Tuple[str, ...] = ("projets", "questions", "poste", "quotas", "notifications", "pause", "discussions")
VERSION = 1
CHEMIN = "/api/plugins/acp-poste/v1/flux"
# Délai de reconnexion conseillé au client (champ ``retry`` de la première trame), en millisecondes.
RETRY_MS = 3000
# Arrêt du veilleur après le départ du dernier abonné.
ARRET_VEILLEUR_S = 60.0
# Un abonné réservé par la route mais dont le flux n'a jamais commencé (client parti avant la première trame) est
# retiré après ce délai : sa place n'est jamais perdue.
ABANDON_RESERVATION_S = 15.0
# Réglages du flux : (clé, plancher, plafond). Battement sous les 5 min sans octet du bord Railway, durée sous ses
# 15 min (rw:33402).
BORNES = {
    "flux_intervalle_s": (1, 60),
    "flux_battement_s": (1, 240),
    "flux_duree_max_s": (5, 840),
    "flux_max": (1, 64),
}
ETATS_SUIVIS = ("creation", "actif", "en_pause")
ILLISIBLE = "illisible"
# Sujets dont l'empreinte vient de la base du greffon (``discussions`` vient du processus).
SUJETS_DE_LA_BASE = tuple(s for s in SUJETS if s != "discussions")


# ------------------------------------------------------------------ réglages


def borner(cle: str, valeur: Any) -> int:
    plancher, plafond = BORNES[cle]
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        nombre = int(base.REGLAGES_PAR_DEFAUT[cle])
    return max(plancher, min(plafond, nombre))


def reglages(conn) -> Dict[str, int]:
    """Les quatre réglages du flux, bornés."""
    return {cle: borner(cle, base.reglage(conn, cle)) for cle in BORNES}


def lire_reglages() -> Dict[str, int]:
    """Réglages lus dans la base (à appeler dans un fil) ; base illisible : les valeurs par défaut, bornées."""
    try:
        with base.connexion() as conn:
            return reglages(conn)
    except Exception:  # noqa: BLE001 — le flux reste servi ; ses sujets diront « illisible »
        return {cle: borner(cle, base.REGLAGES_PAR_DEFAUT[cle]) for cle in BORNES}


# ------------------------------------------------------------------ empreintes (lecture seule, dans un fil)


def _illisible(exc: BaseException) -> Tuple[str, str]:
    # Le TYPE seulement : un message variable (chemin, horodatage) ferait publier le sujet à chaque tour.
    return (ILLISIBLE, type(exc).__name__)


def _ligne(conn, sql: str, parametres: Iterable[Any] = ()) -> Tuple[Any, ...]:
    ligne = conn.execute(sql, tuple(parametres)).fetchone()
    return tuple(ligne) if ligne is not None else ()


def _lignes(conn, sql: str, parametres: Iterable[Any] = ()) -> Tuple[Tuple[Any, ...], ...]:
    return tuple(tuple(l) for l in conn.execute(sql, tuple(parametres)).fetchall())


def derniers_evenements(conn) -> Tuple[Tuple[Tuple[str, Any], ...], bool]:
    """Dernier événement de chaque tableau de projet non terminé, lu en lecture seule, et si l'un d'eux est illisible.
    Un tableau encore absent d'un projet en création vaut ``absent`` (sa création changera l'empreinte) ; absent pour
    un projet déjà créé, il est illisible."""
    valeurs: List[Tuple[str, Any]] = []
    illisible = False
    for tableau, etat in _lignes(conn, "SELECT tableau, etat FROM projets WHERE etat IN ('creation', 'actif', "
                                       "'en_pause') ORDER BY tableau"):
        try:
            dernier = ka.dernier_evenement_lecture_seule(str(tableau))
        except Exception as exc:  # noqa: BLE001
            valeurs.append((str(tableau), _illisible(exc)))
            illisible = True
            continue
        if dernier is None:
            valeurs.append((str(tableau), "absent"))
            illisible = illisible or etat != "creation"
        else:
            valeurs.append((str(tableau), dernier))
    return tuple(valeurs), illisible


# Les dates sont à la seconde : deux écritures dans la même seconde ne changeraient pas un MAX. Chaque empreinte
# porte donc aussi des comptes par état et des identifiants croissants (journal, ordres, notifications).


def _projets(conn, tableaux) -> Any:
    return (_lignes(conn, "SELECT etat, COUNT(*), MAX(maj_le) FROM projets GROUP BY etat ORDER BY etat"),
            _ligne(conn, "SELECT COUNT(*), MAX(cree_le), MAX(observe_le), COUNT(observe_le), MAX(reclamee_le), "
                         "MAX(relancee_le), COUNT(relancee_le) FROM demandes"),
            _ligne(conn, "SELECT MAX(id) FROM journal WHERE projet_id IS NOT NULL"),
            _ligne(conn, "SELECT COUNT(*), MAX(cree_le) FROM tours"),
            tableaux)


def _questions(conn, tableaux) -> Any:
    return (_lignes(conn, "SELECT etat, COUNT(*), MAX(maj_le), COUNT(livree_le) FROM questions GROUP BY etat "
                          "ORDER BY etat"), tableaux)


def _poste(conn, _tableaux) -> Any:
    maintenant = base.maintenant()
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s") or 180)
    grace = int(base.reglage(conn, "grace_arret_propre_s") or 600)
    presences = tuple(
        (machine, maintenant - int(vue) <= seuil, hors_ligne_depuis, arret,
         arret is not None and maintenant - int(arret) <= grace)
        for machine, vue, hors_ligne_depuis, arret in _lignes(
            conn, "SELECT machine_id, derniere_vue, hors_ligne_depuis, arret_propre_le FROM presence "
                  "ORDER BY machine_id"))
    return (_lignes(conn, "SELECT id, etat, peut_executer, carte_en_cours, voies_disponibles, espace_libre_mio, "
                          "politique_valide, confirme_le, revoque_le, plateforme, hote FROM machines ORDER BY id"),
            presences,
            _ligne(conn, "SELECT COUNT(*), MAX(recu_le) FROM inventaires"),
            _ligne(conn, "SELECT COUNT(*), MAX(id), SUM(CASE WHEN livre_le IS NULL THEN 0 ELSE 1 END) FROM ordres "
                         "WHERE acquitte_le IS NULL AND abandonne_le IS NULL"))


def _quotas(conn, _tableaux) -> Any:
    return (_ligne(conn, "SELECT COUNT(*), MAX(id), MAX(recu_le), MAX(accepte_le), COUNT(accepte_le) FROM releves"),
            _lignes(conn, "SELECT tableau, carte, motif, reprise_le FROM attentes ORDER BY tableau, carte"),
            _lignes(conn, "SELECT classe, entrees, valide_le, valide_par, source FROM routage ORDER BY classe"),
            _ligne(conn, "SELECT COUNT(*), MAX(id), SUM(active) FROM surcharges"),
            _lignes(conn, "SELECT cle, valeur FROM reglages WHERE cle IN ('efforts_interdits', 'paliers_admis', "
                          "'relecture_repli_meme_voie') ORDER BY cle"))


def _notifications(conn, _tableaux) -> Any:
    return (json.dumps(base.lire_emetteur(conn, "canal"), sort_keys=True, ensure_ascii=False),
            _lignes(conn, "SELECT etat, COUNT(*), MAX(id) FROM notifications GROUP BY etat ORDER BY etat"))


def _pause(conn, _tableaux) -> Any:
    arret = ka.get_state()
    return (json.dumps(arret, sort_keys=True, ensure_ascii=False, default=str),
            bool(base.reglage(conn, "pause_reclamations")),
            _lignes(conn, "SELECT id FROM projets WHERE etat = 'en_pause' ORDER BY id"))


LECTEURS: Dict[str, Callable[[Any, Any], Any]] = {
    "projets": _projets, "questions": _questions, "poste": _poste, "quotas": _quotas,
    "notifications": _notifications, "pause": _pause,
}


class Releve:
    """Une lecture de toutes les empreintes : valeurs par sujet, sujets illisibles, intervalle du veilleur."""

    def __init__(self, valeurs: Dict[str, Any], illisibles: FrozenSet[str], intervalle: int,
                 discussions_suivies: bool) -> None:
        self.valeurs = valeurs
        self.illisibles = illisibles
        self.intervalle = intervalle
        self.discussions_suivies = discussions_suivies


def calculer() -> Releve:
    """Empreinte de chaque sujet (à appeler DANS UN FIL). Jamais d'exception : un sujet illisible le dit."""
    valeurs: Dict[str, Any] = {}
    illisibles: Set[str] = set()
    intervalle = borner("flux_intervalle_s", base.REGLAGES_PAR_DEFAUT["flux_intervalle_s"])
    try:
        with base.connexion() as conn:
            intervalle = borner("flux_intervalle_s", base.reglage(conn, "flux_intervalle_s"))
            try:
                tableaux, tableau_illisible = derniers_evenements(conn)
            except Exception as exc:  # noqa: BLE001
                tableaux, tableau_illisible = _illisible(exc), True
            if tableau_illisible:
                illisibles.update(("projets", "questions"))
            for sujet, lecteur in LECTEURS.items():
                try:
                    valeurs[sujet] = lecteur(conn, tableaux)
                except Exception as exc:  # noqa: BLE001
                    valeurs[sujet] = _illisible(exc)
                    illisibles.add(sujet)
    except Exception as exc:  # noqa: BLE001 — base du greffon illisible : tous ses sujets le disent
        for sujet in SUJETS_DE_LA_BASE:
            valeurs[sujet] = _illisible(exc)
            illisibles.add(sujet)
    ouvertes = ka.requetes_ouvertes()
    valeurs["discussions"] = ouvertes
    return Releve(valeurs, frozenset(illisibles), intervalle, ouvertes is not None)


# ------------------------------------------------------------------ trames (format SSE, octets UTF-8)


def _champ_donnees(donnees: Dict[str, Any]) -> str:
    # JSON sur UNE ligne (aucun retour à la ligne dans un champ data) ; ordre fixe des sujets.
    return json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))


def _ordonner(sujets: Iterable[str]) -> List[str]:
    vus = set(sujets)
    return [s for s in SUJETS if s in vus]


def trame_ouverture(revision: str, sujets: Iterable[str], illisibles: Iterable[str],
                    discussions_suivies: bool) -> bytes:
    donnees: Dict[str, Any] = {"revision": revision, "sujets": _ordonner(sujets),
                               "discussions_suivies": bool(discussions_suivies)}
    illisibles = _ordonner(illisibles)
    if illisibles:
        donnees["illisibles"] = illisibles
    return f"retry: {RETRY_MS}\n\nid: {revision}\nevent: etat\ndata: {_champ_donnees(donnees)}\n\n".encode("utf-8")


def trame_changement(revision: str, sujets: Iterable[str], illisibles: Iterable[str]) -> bytes:
    donnees: Dict[str, Any] = {"sujets": _ordonner(sujets)}
    illisibles = _ordonner(illisibles)
    if illisibles:
        donnees["illisibles"] = illisibles
    return f"id: {revision}\nevent: changement\ndata: {_champ_donnees(donnees)}\n\n".encode("utf-8")


TRAME_BATTEMENT = b": battement\n\n"


def trame_fin(raison: str = "duree_max") -> bytes:
    return f"event: fin\ndata: {_champ_donnees({'raison': raison})}\n\n".encode("utf-8")


# ------------------------------------------------------------------ abonnés et veilleur (boucle du tableau de bord)


class Abonne:
    """Un flux ouvert : sujets à signaler (fusionnés tant que le flux ne les a pas écrits), réveil, révision."""

    def __init__(self, maintenant: float) -> None:
        self.evenement = asyncio.Event()
        self.sujets: Set[str] = set()
        self.illisibles: Set[str] = set()
        self.revision: Optional[str] = None
        self.reserve_le = maintenant
        self.demarre = False

    def signaler(self, sujets: Set[str], illisibles: Set[str], revision: str) -> None:
        self.sujets |= sujets
        self.illisibles = (self.illisibles - sujets) | (illisibles & sujets)
        self.revision = revision
        self.evenement.set()

    def prendre(self) -> Optional[Tuple[List[str], List[str], str]]:
        """Sujets signalés depuis la dernière trame (et la révision), ou ``None`` ; remet l'abonné en attente."""
        self.evenement.clear()
        if not self.sujets or self.revision is None:
            return None
        sujets, illisibles, revision = _ordonner(self.sujets), _ordonner(self.illisibles), self.revision
        self.sujets, self.illisibles = set(), set()
        return sujets, illisibles, revision


_derniere_epoque = 0


def _nouvelle_epoque() -> int:
    global _derniere_epoque
    _derniere_epoque = max(int(time.time()), _derniere_epoque + 1)
    return _derniere_epoque


class Diffuseur:
    """Abonnés et veilleur d'UNE boucle d'événements (celle du tableau de bord). Toutes ses méthodes s'appellent
    depuis cette boucle : aucun verrou de fil n'est nécessaire, seules les lectures de la base partent dans un fil."""

    def __init__(self, boucle: asyncio.AbstractEventLoop,
                 calcul: Callable[[], Releve] = calculer) -> None:
        self.boucle = boucle
        self.epoque = _nouvelle_epoque()
        self.numero = 0
        self.abonnes: Set[Abonne] = set()
        self.empreintes: Optional[Dict[str, Any]] = None
        self.illisibles: FrozenSet[str] = frozenset()
        self.discussions_suivies = False
        self.intervalle = borner("flux_intervalle_s", base.REGLAGES_PAR_DEFAUT["flux_intervalle_s"])
        self.tache: Optional[asyncio.Task] = None
        # Aucun abonné à la création : le veilleur s'arrête 60 s après s'il n'en vient aucun.
        self.dernier_depart: Optional[float] = boucle.time()
        self.passes = 0
        self._calcul = calcul
        self._verrou = asyncio.Lock()

    @property
    def revision(self) -> str:
        return f"{self.epoque}.{self.numero}"

    async def passe(self) -> Set[str]:
        """Une lecture des empreintes ; publie les sujets changés à tous les abonnés et rend leur ensemble."""
        async with self._verrou:
            releve = await asyncio.to_thread(self._calcul)
            self.passes += 1
            self.intervalle = releve.intervalle
            self.discussions_suivies = releve.discussions_suivies
            avant = self.empreintes
            self.empreintes = releve.valeurs
            self.illisibles = releve.illisibles
            if avant is None:
                return set()
            changes = {s for s in SUJETS if releve.valeurs.get(s) != avant.get(s)}
            if changes:
                self.numero += 1
                for abonne in list(self.abonnes):
                    abonne.signaler(changes, set(releve.illisibles), self.revision)
            return changes

    async def assurer(self) -> None:
        """Veilleur en marche ; s'il était arrêté, une passe D'ABORD (ce qui a changé pendant l'arrêt est publié et
        fait avancer la révision) avant que l'appelant n'inscrive son abonné."""
        if self.tache is not None and not self.tache.done():
            return
        await self.passe()
        if self.tache is None or self.tache.done():
            self.tache = self.boucle.create_task(self._veiller(), name="acp-poste-flux-veilleur")

    async def _veiller(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.intervalle)
                self._retirer_reservations_abandonnees()
                if not self.abonnes and self.dernier_depart is not None and \
                        self.boucle.time() - self.dernier_depart >= ARRET_VEILLEUR_S:
                    return
                try:
                    await self.passe()
                except Exception as exc:  # noqa: BLE001 — une passe ratée n'arrête pas le veilleur
                    _log.warning("acp-poste : passe du flux en échec (%s).", type(exc).__name__)
        finally:
            if asyncio.current_task() is self.tache:
                self.tache = None

    def abonner(self, maximum: int) -> Optional[Abonne]:
        """Inscrit un abonné, ou ``None`` si ``maximum`` flux sont déjà ouverts (ou réservés)."""
        self._retirer_reservations_abandonnees()
        if len(self.abonnes) >= maximum:
            return None
        abonne = Abonne(self.boucle.time())
        self.abonnes.add(abonne)
        self.dernier_depart = None
        return abonne

    def desabonner(self, abonne: Abonne) -> None:
        if abonne in self.abonnes:
            self.abonnes.discard(abonne)
            if not self.abonnes:
                self.dernier_depart = self.boucle.time()

    def _retirer_reservations_abandonnees(self) -> None:
        limite = self.boucle.time() - ABANDON_RESERVATION_S
        for abonne in [a for a in self.abonnes if not a.demarre and a.reserve_le < limite]:
            self.desabonner(abonne)

    def sujets_a_l_ouverture(self, dernier_id: Optional[str]) -> List[str]:
        """Première trame : rien si le client revient avec la révision courante, sinon tout."""
        if dernier_id is not None and dernier_id.strip() == self.revision:
            return []
        return list(SUJETS)

    def etat(self) -> Dict[str, Any]:
        """État lisible (tests, diagnostic) : jamais une donnée métier."""
        return {"revision": self.revision, "abonnes": len(self.abonnes),
                "veilleur": self.tache is not None and not self.tache.done(), "passes": self.passes,
                "illisibles": _ordonner(self.illisibles), "discussions_suivies": self.discussions_suivies}


_diffuseur: Optional[Diffuseur] = None


def diffuseur() -> Diffuseur:
    """Le diffuseur de la boucle courante (créé au premier appel ; recréé si la boucle a changé : tests)."""
    global _diffuseur
    boucle = asyncio.get_running_loop()
    if _diffuseur is None or _diffuseur.boucle is not boucle or boucle.is_closed():
        _diffuseur = Diffuseur(boucle)
    return _diffuseur


def oublier() -> None:
    """Oublie le diffuseur courant (tests : une boucle par serveur de test)."""
    global _diffuseur
    _diffuseur = None
