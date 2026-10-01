"""Protocole ``acp-machine/1`` entre le poste Windows et le greffon ``acp-poste`` (étape P5, cahier P5 § 4).

Trois routes, toutes ``POST`` et JSON UTF-8, sous ``<origine>/api/plugins/acp-poste/machine/v1/`` :

- ``enrolement`` (porteur : code d'enrôlement ``acpe_…``) : :class:`RequeteEnrolement` → :class:`ReponseEnrolement` ;
- ``reclamer`` (porteur : jeton machine ``acpm_…``), long-poll ≤ 50 s : :class:`RequeteReclamer` →
  :class:`ReponseReclamer` ;
- ``inventaire`` (porteur : jeton machine) : ``InventairePoste`` (module :mod:`inventaire`) → :class:`ReponseInventaire`.

Les DEUX côtés valident par ces modèles (``extra="forbid"``, refus en français) : le greffon refuse une requête
hors contrat (422), le poste refuse une réponse hors contrat. Les erreurs du greffon ont la forme
:class:`ErreurMachine` ; les 401 et 503 produits par la couture d'authentification de Hermes (anglais, corps
:data:`CORPS_401_COUTURE`) ne viennent pas du greffon et restent AMBIGUS (cahier P5 § 4.5).

Jetons : ``acpm_`` ou ``acpe_`` suivi de 43 caractères base64url (256 bits d'aléa). Le greffon ne garde que leur
SHA-256 (:func:`empreinte_jeton`) ; l'empreinte AFFICHÉE (``3F9A-0C1B``, :func:`empreinte_courte`) est tirée des
8 premiers caractères hexadécimaux de ce condensat : le poste la recalcule depuis son jeton, le propriétaire la
compare sur la page Poste avant de confirmer (décision D49).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError, field_validator, model_validator

from .inventaire import _Contrat, _instant, _message, _texte, _VERSION, PROTOCOLE, raison_identifiant

PREFIXE_ROUTES = "/api/plugins/acp-poste/machine/v1"
ROUTE_ENROLEMENT = f"{PREFIXE_ROUTES}/enrolement"
ROUTE_RECLAMER = f"{PREFIXE_ROUTES}/reclamer"
ROUTE_INVENTAIRE = f"{PREFIXE_ROUTES}/inventaire"
ROUTES = (ROUTE_ENROLEMENT, ROUTE_RECLAMER, ROUTE_INVENTAIRE)

JETON_MACHINE = re.compile(r"acpm_[A-Za-z0-9_-]{43}")
CODE_ENROLEMENT = re.compile(r"acpe_[A-Za-z0-9_-]{43}")
MACHINE_ID = re.compile(r"m[0-9a-f]{11}")
EMPREINTE_COURTE = re.compile(r"[0-9A-F]{4}-[0-9A-F]{4}")
_PROTOCOLE = re.compile(r"acp-machine/[0-9]{1,3}")

ATTENTE_MIN_S = 5
ATTENTE_MAX_S = 50
ACQUITTES_MAX = 64
ORDRES_MAX = 32
ALERTES_MAX = 16

# Bornes des corps (cahier P5 § 4.1), vérifiées sur Content-Length ET à la lecture.
TAILLE_MAX_REQUETE = 4 * 1024
TAILLE_MAX_INVENTAIRE = 256 * 1024
TAILLE_MAX_REPONSE = 64 * 1024
# Profondeur d'imbrication admise d'un corps JSON (objets et listes) : un inventaire réel en compte moins de 10 ; au-delà,
# refus 422 plutôt qu'un RecursionError du décodeur ou du balayage (relecture de P5).
PROFONDEUR_MAX_CORPS = 32

# Corps exact du 401 de la couture de Hermes (hermes_cli/dashboard_auth/token_auth.py:96) : AMBIGU (jeton
# révoqué pendant une absence, fournisseur absent ou bogué) ; le poste ne l'efface JAMAIS (décision D65).
CORPS_401_COUTURE = {"error": "unauthenticated", "detail": "Unauthorized"}

GENRES_ORDRE = ("releve", "pause", "reprise")
ETATS_MACHINE = ("a_confirmer", "actif")

# Forme EXÉCUTABLE d'une commande du poste dans la console du compte (``runas /user:acp-poste "powershell
# -NoProfile"``), telle que Hermes et l'inventaire l'affichent : le dossier du poste n'est dans aucun PATH, un chemin
# entre guillemets sans ``&`` est une erreur d'analyse de PowerShell, et la garde « aucun identifiant » refuse une
# lettre de lecteur, d'où ``$env:ProgramFiles`` (relecture de P5, décision D68). Sur le poste, les messages locaux
# donnent le chemin réel (``acp_poste.chemins.commande_poste``).
COMMANDE_POSTE_PUBLIEE = '& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd"'


def commande_publiee(arguments: str) -> str:
    """``& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" <arguments>`` (décision D68)."""
    return f"{COMMANDE_POSTE_PUBLIEE} {arguments}"


def empreinte_jeton(jeton: str) -> str:
    """SHA-256 hexadécimal (64 caractères) d'un jeton ou d'un code : seule forme gardée par le greffon."""
    return hashlib.sha256(jeton.encode("ascii")).hexdigest()


def empreinte_courte(empreinte_hex: str) -> str:
    """« 3F9A-0C1B » : 8 premiers caractères hexadécimaux du condensat, en majuscules, groupés 4-4."""
    tete = empreinte_hex[:8].upper()
    return f"{tete[:4]}-{tete[4:]}"


def empreinte_courte_normalisee(saisie: Any) -> Optional[str]:
    """Empreinte saisie par le propriétaire (casse et tiret indifférents) ramenée à ``XXXX-XXXX``, ou None."""
    if not isinstance(saisie, str):
        return None
    brut = re.sub(r"[\s-]", "", saisie).upper()
    if not re.fullmatch(r"[0-9A-F]{8}", brut):
        return None
    return f"{brut[:4]}-{brut[4:]}"


def majeure(protocole: str) -> Optional[int]:
    """Majeure d'un protocole ``acp-machine/<n>``, ou None s'il n'a pas cette forme."""
    trouve = _PROTOCOLE.fullmatch(protocole or "")
    return int(protocole.rsplit("/", 1)[1]) if trouve else None


def _protocole(valeur: Any) -> str:
    return _texte(valeur, champ="protocole", maximum=20, motif=_PROTOCOLE)


def _booleen(valeur: Any, champ: str) -> bool:
    if type(valeur) is not bool:
        raise ValueError(f"« {champ} » doit être un booléen (true ou false)")
    return valeur


def _entier(valeur: Any, champ: str, minimum: int, maximum: int) -> int:
    if type(valeur) is not int or not minimum <= valeur <= maximum:
        raise ValueError(f"« {champ} » doit être un entier compris entre {minimum} et {maximum}")
    return valeur


# ------------------------------------------------------------------ enrôlement


class RequeteEnrolement(_Contrat):
    protocole: str
    version_poste: str
    nom: str

    @field_validator("protocole", mode="before")
    @classmethod
    def _p(cls, valeur: Any) -> str:
        return _protocole(valeur)

    @field_validator("version_poste", mode="before")
    @classmethod
    def _v(cls, valeur: Any) -> str:
        return _texte(valeur, champ="version_poste", maximum=64, motif=_VERSION)

    @field_validator("nom", mode="before")
    @classmethod
    def _nom(cls, valeur: Any) -> str:
        nom = _texte(valeur, champ="nom", maximum=60, motif=re.compile(r"[^\x00-\x1f\x7f]{1,60}"))
        raison = raison_identifiant(nom)
        if raison:
            # Le nom est recopié dans chaque inventaire, dont la garde « aucun identifiant » le refuserait : le poste
            # s'enrôlerait puis ne publierait jamais rien (relecture de P5). Jamais la valeur dans le message.
            raise ValueError(f"« nom » : {raison} refusé dans le nom du poste, publié dans chaque inventaire ; "
                             "choisissez un nom sans adresse, chemin ni secret ([poste] nom de poste.toml)")
        return nom


class ReponseEnrolement(_Contrat):
    """Le SEUL message qui contienne le jeton machine (201)."""

    machine_id: str
    jeton: str
    empreinte: str
    etat: str
    protocole: str

    @field_validator("machine_id", mode="before")
    @classmethod
    def _id(cls, valeur: Any) -> str:
        return _texte(valeur, champ="machine_id", maximum=12, motif=MACHINE_ID)

    @field_validator("jeton", mode="before")
    @classmethod
    def _jeton(cls, valeur: Any) -> str:
        if not isinstance(valeur, str) or not JETON_MACHINE.fullmatch(valeur):
            raise ValueError("« jeton » : jeton machine au format invalide")  # jamais la valeur dans le message
        return valeur

    @field_validator("empreinte", mode="before")
    @classmethod
    def _empreinte(cls, valeur: Any) -> str:
        return _texte(valeur, champ="empreinte", maximum=9, motif=EMPREINTE_COURTE)

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        if valeur != "a_confirmer":
            raise ValueError("« etat » : un poste enrôlé est « a_confirmer » jusqu'à la confirmation de l'empreinte")
        return valeur

    @field_validator("protocole", mode="before")
    @classmethod
    def _p(cls, valeur: Any) -> str:
        return _protocole(valeur)

    @model_validator(mode="after")
    def _coherence(self) -> "ReponseEnrolement":
        if empreinte_courte(empreinte_jeton(self.jeton)) != self.empreinte:
            raise ValueError("« empreinte » ne correspond pas au jeton reçu")
        return self


# ------------------------------------------------------------------ réclamation (long-poll)


class RequeteReclamer(_Contrat):
    protocole: str
    version_poste: str
    peut_executer: bool
    ordres_acquittes: List[int] = []
    attente_max_s: int = 25
    politique_valide: bool = True

    @field_validator("protocole", mode="before")
    @classmethod
    def _p(cls, valeur: Any) -> str:
        return _protocole(valeur)

    @field_validator("version_poste", mode="before")
    @classmethod
    def _v(cls, valeur: Any) -> str:
        return _texte(valeur, champ="version_poste", maximum=64, motif=_VERSION)

    @field_validator("peut_executer", "politique_valide", mode="before")
    @classmethod
    def _b(cls, valeur: Any, info) -> bool:
        return _booleen(valeur, info.field_name)

    @field_validator("ordres_acquittes", mode="before")
    @classmethod
    def _acquittes(cls, valeur: Any) -> List[int]:
        if not isinstance(valeur, list) or len(valeur) > ACQUITTES_MAX:
            raise ValueError(f"« ordres_acquittes » doit être une liste d'au plus {ACQUITTES_MAX} identifiants")
        return [_entier(v, "ordres_acquittes", 1, 2**62) for v in valeur]

    @field_validator("attente_max_s", mode="before")
    @classmethod
    def _attente(cls, valeur: Any) -> int:
        return _entier(valeur, "attente_max_s", ATTENTE_MIN_S, ATTENTE_MAX_S)


class Ordre(_Contrat):
    id: int
    genre: str
    cree_le: datetime

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valeur: Any) -> int:
        return _entier(valeur, "id", 1, 2**62)

    @field_validator("genre", mode="before")
    @classmethod
    def _genre(cls, valeur: Any) -> str:
        if valeur not in GENRES_ORDRE:
            raise ValueError(f"« genre » : valeurs admises : {', '.join(GENRES_ORDRE)}")
        return valeur

    @field_validator("cree_le", mode="before")
    @classmethod
    def _cree(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="cree_le")


class ReponseReclamer(_Contrat):
    """``carte`` vaut toujours ``null`` en P5 (sans exécution) ; P6 ne la servira qu'à ``peut_executer: true``."""

    maintenant: datetime
    etat_machine: str
    pause_reclamations: bool
    ordres: List[Ordre]
    carte: Optional[Dict[str, Any]] = None
    remplace: bool
    prochaine_attente_s: int

    @field_validator("maintenant", mode="before")
    @classmethod
    def _maintenant(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="maintenant")

    @field_validator("etat_machine", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        if valeur not in ETATS_MACHINE:
            raise ValueError(f"« etat_machine » : valeurs admises : {', '.join(ETATS_MACHINE)}")
        return valeur

    @field_validator("pause_reclamations", "remplace", mode="before")
    @classmethod
    def _b(cls, valeur: Any, info) -> bool:
        return _booleen(valeur, info.field_name)

    @field_validator("ordres", mode="before")
    @classmethod
    def _ordres(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list) or len(valeur) > ORDRES_MAX:
            raise ValueError(f"« ordres » doit être une liste d'au plus {ORDRES_MAX} ordres")
        return valeur

    @field_validator("carte", mode="before")
    @classmethod
    def _carte(cls, valeur: Any) -> None:
        if valeur is not None:
            raise ValueError("« carte » : aucune carte n'est servie à l'étape P5 (sans exécution)")
        return None

    @field_validator("prochaine_attente_s", mode="before")
    @classmethod
    def _prochaine(cls, valeur: Any) -> int:
        return _entier(valeur, "prochaine_attente_s", 0, 3600)


# ------------------------------------------------------------------ inventaire et erreurs


class ReponseInventaire(_Contrat):
    recu_le: datetime
    releves: Dict[str, int]
    alertes: List[str] = []

    @field_validator("recu_le", mode="before")
    @classmethod
    def _recu(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="recu_le")

    @field_validator("releves", mode="before")
    @classmethod
    def _releves(cls, valeur: Any) -> Dict[str, int]:
        if not isinstance(valeur, dict) or not 1 <= len(valeur) <= 2:
            raise ValueError("« releves » : un identifiant de relevé par voie publiée")
        propres = {}
        for voie, identifiant in valeur.items():
            if voie not in ("poste-codex", "poste-claude"):
                raise ValueError("« releves » : voies admises : poste-codex, poste-claude")
            propres[voie] = _entier(identifiant, "releves", 1, 2**62)
        return propres

    @field_validator("alertes", mode="before")
    @classmethod
    def _alertes(cls, valeur: Any) -> List[str]:
        if not isinstance(valeur, list) or len(valeur) > ALERTES_MAX:
            raise ValueError(f"« alertes » doit être une liste d'au plus {ALERTES_MAX} messages")
        return [_texte(v, champ="alertes", maximum=300) for v in valeur]


CODES_ERREUR = ("poste_revoque", "mauvais_fournisseur", "code_enrolement_seulement", "jeton_machine_ici",
                "poste_a_confirmer", "poste_deja_enrole", "protocole_incompatible", "trop_volumineux",
                "json_attendu", "requete_refusee", "trop_frequent", "non_authentifie", "echec")


class DetailErreur(_Contrat):
    code: str
    message: str

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, valeur: Any) -> str:
        if valeur not in CODES_ERREUR:
            raise ValueError(f"« code » : valeurs admises : {', '.join(CODES_ERREUR)}")
        return valeur

    @field_validator("message", mode="before")
    @classmethod
    def _msg(cls, valeur: Any) -> str:
        return _texte(valeur, champ="message", maximum=600)


class ErreurMachine(_Contrat):
    """Erreur d'une route machine produite par le GREFFON : ``{"detail": {"code", "message"}}`` en français."""

    detail: DetailErreur


def valider(modele, donnees: Any, *, quoi: str):
    """``modele`` validé, ou ``ValueError`` au message français (« <quoi> refusé(e) : … »)."""
    try:
        return modele.model_validate(donnees)
    except ValidationError as exc:
        details = "; ".join(_message(e) for e in exc.errors()[:5])
        raise ValueError(f"{quoi} : {details}.") from None
