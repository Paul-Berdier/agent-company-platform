"""Protocole ``acp-machine/1`` côté poste (cahier P5 § 4) : appels des trois routes machine, validés par le contrat
partagé ``acp_poste_contrat.machine`` (le poste refuse une réponse hors contrat comme le greffon refuse une requête).

Classement des réponses (§ 4.4 et § 4.5) :

- 401 **explicite** du greffon ``poste_revoque`` → :class:`PosteRevoque` : le service efface le jeton et s'arrête
  (code 0) ;
- 401 **de la couture de Hermes** (``{"error": "unauthenticated", "detail": "Unauthorized"}``, en anglais, avant le
  greffon) et tout autre 401 → :class:`JetonRefuse` : **ambigu** (révocation pendant une absence, fournisseur absent
  ou bogué côté Hermes) ; le jeton est **gardé**, plus aucun échange, arrêt (code 4, décision D65) ;
- 409 ``protocole_incompatible`` → :class:`ProtocoleIncompatible` (code 2) ; 429 → :class:`TropFrequent`
  (``Retry-After``) ; 5xx et réseau → :class:`HermesIndisponible` (repli exponentiel) ; 3xx → refus (jamais suivi) ;
  réponse hors contrat → :class:`HorsContrat`.

Étape P6 (cahier P6 § 5) : ``reclamer`` annonce, pour l'exécutant, ``peut_executer``, ses voies, sa carte en main et
l'espace libre (le corps du poste Windows de P5 ne change pas), et sa réponse peut porter une carte — refusée si le
poste ne l'a pas demandée ; les six routes de l'exécution (:meth:`Protocole.envoyer`) valident la requête par le
contrat AVANT l'envoi (bornes de 8 et 32 Kio) et la réponse après ; 409 ``reclamation_perdue`` et les autres refus
du greffon restent des :class:`Refus` portant leur code.
"""

from __future__ import annotations

import json
from typing import Any

from acp_poste_contrat.inventaire import PROTOCOLE
from acp_poste_contrat import machine as contrat
from acp_poste_contrat.machine import (
    CORPS_401_COUTURE,
    MODELES_P6,
    PREFIXE_ROUTES,
    ROUTE_ENROLEMENT,
    ROUTE_INVENTAIRE,
    ROUTE_RECLAMER,
    TAILLE_MAX_INVENTAIRE,
    TAILLE_MAX_REQUETE,
    ErreurMachine,
    ReponseEnrolement,
    ReponseInventaire,
    ReponseReclamer,
    valider,
)

from . import __version__
from .chemins import commande_poste
from .client_hermes import ClientHermes, ErreurReseau, ReponseHTTP
from .jeton import CodeEnrolement, Jeton

USER_AGENT = f"acp-poste/{__version__} ({PROTOCOLE})"
MARGE_LECTURE_S = 15

JETON_REFUSE = ("Jeton machine refusé par ACP (révoqué, inconnu, ou fournisseur de jeton absent côté Hermes) : plus "
                "aucun échange ; le jeton local est gardé. Vérifiez l'état sur la page Poste ; si le poste y est "
                f"révoqué, lancez « {commande_poste('enroler --remplacer')} ».")
CODE_REFUSE = ("Code d'enrôlement refusé : inconnu, expiré ou déjà utilisé. Générez-en un nouveau depuis la page "
               "Poste.")
HERMES_INDISPONIBLE = "Hermes indisponible (HTTP {statut}) : nouvel essai plus tard."
HERMES_INDISPONIBLE_503 = "Hermes indisponible (base du greffon illisible) : nouvel essai plus tard."


class Refus(Exception):
    """Réponse de Hermes refusée ou refus de Hermes ; ``message`` est toujours en français."""

    def __init__(self, message: str, *, statut: int | None = None, code: str | None = None,
                 retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.statut = statut
        self.code = code
        self.retry_after = retry_after


class PosteRevoque(Refus):
    """401 explicite ``poste_revoque`` : le jeton local doit être effacé."""


class JetonRefuse(Refus):
    """401 de la couture (ou 401 non explicite) : ambigu, le jeton local est gardé (D65)."""


class ProtocoleIncompatible(Refus):
    """409 ``protocole_incompatible`` : le poste doit être mis à jour."""


class TropFrequent(Refus):
    """429 : inventaire gardé, renvoyé après ``Retry-After``."""


class HermesIndisponible(Refus):
    """5xx ou réseau : repli exponentiel."""


class HorsContrat(Refus):
    """Réponse de Hermes hors du contrat partagé : rien n'est fait."""


def _json(reponse: ReponseHTTP) -> Any:
    try:
        return json.loads(reponse.corps.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _retry_after(reponse: ReponseHTTP) -> int | None:
    valeur = reponse.entetes.get("retry-after", "")
    return int(valeur) if valeur.isdigit() and int(valeur) <= 3600 else None


def classer(reponse: ReponseHTTP, attendu: int, *, enrolement: bool = False) -> Any:
    """Corps JSON d'une réponse ``attendu`` ; sinon lève le refus qui correspond (voir l'en-tête du module)."""
    corps = _json(reponse)
    if reponse.statut == attendu:
        if corps is None:
            raise HorsContrat("Réponse de Hermes illisible (JSON attendu) : rien n'a été fait.", statut=reponse.statut)
        return corps
    if 300 <= reponse.statut < 400:
        raise Refus(f"Redirection refusée (HTTP {reponse.statut}) : le poste ne suit jamais une redirection ; vérifiez "
                    "[hermes] origine dans poste.toml.", statut=reponse.statut)
    detail = None
    if isinstance(corps, dict) and corps != CORPS_401_COUTURE:
        try:
            detail = valider(ErreurMachine, corps, quoi="Erreur de Hermes").detail
        except ValueError:
            detail = None
    if reponse.statut == 401:
        if detail is not None and detail.code == "poste_revoque":
            raise PosteRevoque(detail.message, statut=401, code="poste_revoque")
        raise JetonRefuse(CODE_REFUSE if enrolement else JETON_REFUSE, statut=401,
                          code=detail.code if detail else None)
    if reponse.statut >= 500:
        message = HERMES_INDISPONIBLE_503 if reponse.statut == 503 else HERMES_INDISPONIBLE.format(statut=reponse.statut)
        raise HermesIndisponible(message, statut=reponse.statut, retry_after=_retry_after(reponse))
    if reponse.statut == 429:
        attente = _retry_after(reponse) or 60
        raise TropFrequent(detail.message if detail else f"Inventaire trop fréquent : prochain envoi possible dans "
                           f"{attente} s.", statut=429, code="trop_frequent", retry_after=attente)
    if detail is not None and detail.code == "protocole_incompatible":
        raise ProtocoleIncompatible(detail.message, statut=reponse.statut, code=detail.code)
    if detail is not None:
        raise Refus(detail.message, statut=reponse.statut, code=detail.code)
    raise Refus(f"Réponse inattendue de Hermes (HTTP {reponse.statut}) : rien n'a été fait.", statut=reponse.statut)


def _valide(modele, corps: Any, quoi: str):
    try:
        return valider(modele, corps, quoi=quoi)
    except ValueError as exc:
        raise HorsContrat(f"{exc} Rien n'a été fait.") from None


class Protocole:
    """Les trois routes machine et la santé publique de Hermes, sur un :class:`ClientHermes`."""

    def __init__(self, client: ClientHermes) -> None:
        self.client = client

    def _poster(self, route: str, corps: dict[str, Any], porteur: str, *, limite: int,
                delai_lecture_s: float) -> ReponseHTTP:
        donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
        if len(donnees) > limite:
            raise Refus(f"Requête du poste refusée avant l'envoi : corps de plus de {limite // 1024} Kio.")
        entetes = {"Authorization": porteur, "Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": USER_AGENT, "X-ACP-Protocole": PROTOCOLE}
        try:
            return self.client.echanger("POST", route, corps=donnees, entetes=entetes,
                                        delai_lecture_s=delai_lecture_s)
        except ErreurReseau as exc:
            raise HermesIndisponible(str(exc)) from None

    def enroler(self, code: CodeEnrolement, *, nom: str) -> ReponseEnrolement:
        corps = {"protocole": PROTOCOLE, "version_poste": __version__, "nom": nom}
        reponse = self._poster(ROUTE_ENROLEMENT, corps, code.en_tete(), limite=TAILLE_MAX_REQUETE,
                               delai_lecture_s=30)
        return _valide(ReponseEnrolement, classer(reponse, 201, enrolement=True), "Réponse d'enrôlement refusée")

    def reclamer(self, jeton: Jeton, *, acquittes: list[int], attente_max_s: int,
                 politique_valide: bool, execution: dict[str, Any] | None = None) -> ReponseReclamer:
        """``execution`` (exécutant, étape P6) : ``peut_executer``, ``voies_disponibles``, ``carte_en_cours`` et
        ``espace_libre_mio`` ; absent (poste Windows), le corps de P5 est envoyé tel quel."""
        corps = {"protocole": PROTOCOLE, "version_poste": __version__, "peut_executer": False,
                 "ordres_acquittes": list(acquittes), "attente_max_s": attente_max_s,
                 "politique_valide": politique_valide}
        if execution:
            corps.update({cle: execution[cle] for cle in ("peut_executer", "voies_disponibles", "carte_en_cours",
                                                          "espace_libre_mio") if cle in execution})
            try:
                valider(contrat.RequeteReclamer, corps, quoi="Réclamation refusée par le contrat")
            except ValueError as exc:
                raise Refus(f"{exc} Rien n'a été envoyé.") from None
        reponse = self._poster(ROUTE_RECLAMER, corps, jeton.en_tete(), limite=TAILLE_MAX_REQUETE,
                               delai_lecture_s=attente_max_s + MARGE_LECTURE_S)
        resultat = _valide(ReponseReclamer, classer(reponse, 200), "Réponse de réclamation refusée")
        if resultat.carte is not None:
            voies = corps.get("voies_disponibles") or []
            if not corps["peut_executer"] or resultat.carte.voie not in voies:
                raise HorsContrat("Carte servie sans avoir été demandée (voie non annoncée ou exécution non "
                                  "admise) : refusée, rien n'a été fait.")
        return resultat

    def envoyer(self, jeton: Jeton, route: str, corps: dict[str, Any]) -> Any:
        """Une des six routes de l'exécution (P6) : requête validée par le contrat AVANT l'envoi, réponse après."""
        chemin = f"{PREFIXE_ROUTES}/{route}"
        if chemin not in MODELES_P6:
            raise Refus(f"Route machine inconnue : {route}.")
        requete, reponse_modele, borne = MODELES_P6[chemin]
        try:
            valider(getattr(contrat, requete), corps, quoi=f"Envoi « {route} » refusé par le contrat")
        except ValueError as exc:
            raise Refus(f"{exc} Rien n'a été envoyé.") from None
        reponse = self._poster(chemin, corps, jeton.en_tete(), limite=borne, delai_lecture_s=60)
        return _valide(getattr(contrat, reponse_modele), classer(reponse, 200), f"Réponse à « {route} » refusée")

    def publier(self, jeton: Jeton, inventaire: dict[str, Any]) -> ReponseInventaire:
        reponse = self._poster(ROUTE_INVENTAIRE, inventaire, jeton.en_tete(), limite=TAILLE_MAX_INVENTAIRE,
                               delai_lecture_s=60)
        return _valide(ReponseInventaire, classer(reponse, 200), "Réponse d'inventaire refusée")

    def sante(self) -> tuple[bool, str]:
        """``GET /api/health`` sans jeton (chemin public de Hermes) : (joignable, message français)."""
        try:
            reponse = self.client.echanger("GET", "/api/health", entetes={"Accept": "application/json",
                                                                          "User-Agent": USER_AGENT},
                                           delai_lecture_s=15)
        except ErreurReseau as exc:
            return False, str(exc)
        if reponse.statut == 200:
            return True, "Hermes joignable en HTTPS (/api/health)."
        return False, f"Hermes a répondu HTTP {reponse.statut} sur /api/health."
