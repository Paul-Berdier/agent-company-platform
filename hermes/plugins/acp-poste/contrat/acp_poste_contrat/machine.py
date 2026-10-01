"""Protocole ``acp-machine/1`` entre le poste (Windows, P5) ou l'exécutant Railway (Linux, P6) et le greffon
``acp-poste`` (cahier P5 § 4, cahier P6 § 5).

Neuf routes, toutes ``POST`` et JSON UTF-8, sous ``<origine>/api/plugins/acp-poste/machine/v1/`` :

- ``enrolement`` (porteur : code d'enrôlement ``acpe_…``) : :class:`RequeteEnrolement` → :class:`ReponseEnrolement` ;
- ``reclamer`` (porteur : jeton machine ``acpm_…``), long-poll ≤ 50 s : :class:`RequeteReclamer` →
  :class:`ReponseReclamer` ; depuis P6, ``carte`` porte une :class:`DemandeCarte` quand le poste a annoncé
  ``peut_executer: true`` et une voie disponible ;
- ``inventaire`` (porteur : jeton machine) : ``InventairePoste`` (module :mod:`inventaire`) → :class:`ReponseInventaire` ;
- étape P6 (porteur : jeton machine), chacune avec un ``id_envoi`` (UUID v4) qui la rend idempotente :
  ``battement`` (:class:`RequeteBattement` → :class:`ReponseBattement`), ``terminer`` (:class:`RequeteTerminer` →
  :class:`ReponseTerminer`), ``question`` (:class:`RequeteQuestion` → :class:`ReponseQuestion`), ``bloquer``
  (:class:`RequeteBloquer` → :class:`ReponseBloquer`), ``reprendre`` (:class:`RequeteReprendre`) et ``arret``
  (:class:`RequeteArret`) → :class:`ReponseReprise`.

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
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError, field_validator, model_validator

from .inventaire import (_Contrat, _EFFORT, _ID_MODELE, _instant, _message, _PALIER, _texte, _VERSION, ALIAS_DEPOT,
                         PROTOCOLE, raison_identifiant)
from .motifs_secrets import motif_trouve

PREFIXE_ROUTES = "/api/plugins/acp-poste/machine/v1"
ROUTE_ENROLEMENT = f"{PREFIXE_ROUTES}/enrolement"
ROUTE_RECLAMER = f"{PREFIXE_ROUTES}/reclamer"
ROUTE_INVENTAIRE = f"{PREFIXE_ROUTES}/inventaire"
# Étape P6 (cahier P6 § 5.1) : six chemins exacts de plus, réservés par P5 § 4.8.
ROUTE_BATTEMENT = f"{PREFIXE_ROUTES}/battement"
ROUTE_TERMINER = f"{PREFIXE_ROUTES}/terminer"
ROUTE_QUESTION = f"{PREFIXE_ROUTES}/question"
ROUTE_BLOQUER = f"{PREFIXE_ROUTES}/bloquer"
ROUTE_REPRENDRE = f"{PREFIXE_ROUTES}/reprendre"
ROUTE_ARRET = f"{PREFIXE_ROUTES}/arret"
ROUTES_P5 = (ROUTE_ENROLEMENT, ROUTE_RECLAMER, ROUTE_INVENTAIRE)
ROUTES_P6 = (ROUTE_BATTEMENT, ROUTE_TERMINER, ROUTE_QUESTION, ROUTE_BLOQUER, ROUTE_REPRENDRE, ROUTE_ARRET)
ROUTES = ROUTES_P5 + ROUTES_P6

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
# Étape P6 (cahier P6 § 5.1) : 8 Kio pour battement, bloquer, reprendre et arret ; 32 Kio pour terminer ET question
# (texte et contexte de 4 000 caractères chacun, jusqu'à 4 octets par caractère en UTF-8) ; une carte servie par
# reclamer tient dans la réponse de 64 Kio (consigne et résumés des parents tronqués par le greffon, et dit).
TAILLE_MAX_EVENEMENT = 8 * 1024
TAILLE_MAX_ISSUE = 32 * 1024
TAILLE_MAX_CARTE = 60 * 1024
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


# ------------------------------------------------------------------ carte servie par reclamer (étape P6, § 5.2)

TABLEAU = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
CARTE = re.compile(r"t_[0-9a-f]{4,32}")
PROJET = re.compile(r"p_[0-9a-f]{12}")
QUESTION = re.compile(r"q_[0-9a-f]{12}")
ID_ENVOI = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
SHA40 = re.compile(r"[0-9a-f]{40}")
BRANCHE_CARTE = re.compile(r"hermes/t_[0-9a-f]{4,32}")
BRANCHE_PROJET = re.compile(r"hermes/projet-[a-z0-9][a-z0-9-]{0,62}")
_BRANCHE_GIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")

VOIES_EXECUTION = ("poste-codex", "poste-claude", "poste-integration")
ROLES_CARTE = ("exploration", "implementation", "relecture", "correction", "integration")
TTL_RECLAMATION_S = 2700
PARENTS_MAX = 12
RESUME_PARENT_MAX = 2000
REPONSES_MAX = 8
BRANCHES_INTEGRATION_MAX = 64
CONSIGNE_MAX = 16_000


def _identifiant(valeur: Any, champ: str, motif: re.Pattern, maximum: int = 80) -> str:
    return _texte(valeur, champ=champ, maximum=maximum, motif=motif)


def _identifiant_facultatif(valeur: Any, champ: str, motif: re.Pattern, maximum: int = 128) -> Optional[str]:
    return None if valeur is None else _texte(valeur, champ=champ, maximum=maximum, motif=motif)


def branche_git_valide(nom: str) -> bool:
    """Forme d'un nom de branche que ``git check-ref-format --branch`` accepte (sous-ensemble prudent)."""
    if not _BRANCHE_GIT.fullmatch(nom) or ".." in nom or "//" in nom or "@{" in nom:
        return False
    return not (nom.endswith("/") or nom.endswith(".") or nom.endswith(".lock")
                or any(partie.startswith(".") for partie in nom.split("/")))


def _choix(valeur: Any, champ: str, admis: tuple) -> str:
    if not isinstance(valeur, str) or valeur not in admis:
        raise ValueError(f"« {champ} » : valeurs admises : {', '.join(admis)}")
    return valeur


def taille_json(objet: Any) -> int:
    """Octets du JSON UTF-8 (sans échappement ASCII, comme les réponses du greffon) d'un objet décodé."""
    return len(json.dumps(objet, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class CarteEnCours(_Contrat):
    """Carte que l'exécutant a en main (concurrence 1) : le greffon ne lui en sert aucune autre."""

    tableau: str
    carte: str
    run_id: int

    @field_validator("tableau", mode="before")
    @classmethod
    def _tableau(cls, valeur: Any) -> str:
        return _identifiant(valeur, "tableau", TABLEAU, 64)

    @field_validator("carte", mode="before")
    @classmethod
    def _carte(cls, valeur: Any) -> str:
        return _identifiant(valeur, "carte", CARTE, 34)

    @field_validator("run_id", mode="before")
    @classmethod
    def _run(cls, valeur: Any) -> int:
        return _entier(valeur, "run_id", 1, 2**62)


class ParentCarte(_Contrat):
    """Carte parente FINIE dont le résumé est transmis (tronqué à 2 000 caractères, et dit)."""

    carte: str
    role: str
    resume: Optional[str] = None
    tronque: bool = False
    branche: Optional[str] = None

    @field_validator("carte", mode="before")
    @classmethod
    def _carte(cls, valeur: Any) -> str:
        return _identifiant(valeur, "carte", CARTE, 34)

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, valeur: Any) -> str:
        return _choix(valeur, "role", ("exploration", "planification", "implementation", "relecture", "correction",
                                       "hermes", "synthese", "repondre", "triage", "integration"))

    @field_validator("resume", mode="before")
    @classmethod
    def _resume(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="resume", maximum=RESUME_PARENT_MAX)

    @field_validator("tronque", mode="before")
    @classmethod
    def _tronque(cls, valeur: Any) -> bool:
        return _booleen(valeur, "tronque")

    @field_validator("branche", mode="before")
    @classmethod
    def _branche(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "branche", BRANCHE_CARTE, 48)


class ReponseQuestionLivree(_Contrat):
    """Réponse à livrer à la carte servie : réponse à SA question (``question``) ou motif du refus d'une revue des
    fichiers de pilotage par le propriétaire (``refus_revue``, cahier P6 § 5.4)."""

    genre: str
    question: Optional[str] = None
    texte: str
    repondu_par: str
    le: datetime

    @field_validator("genre", mode="before")
    @classmethod
    def _genre(cls, valeur: Any) -> str:
        return _choix(valeur, "genre", ("question", "refus_revue"))

    @field_validator("question", mode="before")
    @classmethod
    def _question(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "question", QUESTION, 14)

    @field_validator("texte", mode="before")
    @classmethod
    def _texte_reponse(cls, valeur: Any) -> str:
        return _texte(valeur, champ="texte", maximum=4000)

    @field_validator("repondu_par", mode="before")
    @classmethod
    def _par(cls, valeur: Any) -> str:
        return _choix(valeur, "repondu_par", ("hermes", "proprietaire"))

    @field_validator("le", mode="before")
    @classmethod
    def _le(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="le")

    @model_validator(mode="after")
    def _coherence(self) -> "ReponseQuestionLivree":
        if (self.genre == "question") != (self.question is not None):
            raise ValueError("« question » : exigée pour une réponse à une question, absente pour un refus de revue")
        if self.genre == "refus_revue" and self.repondu_par != "proprietaire":
            raise ValueError("« repondu_par » : seul le propriétaire refuse une revue")
        return self


class DemandeCarte(_Contrat):
    """Carte servie à l'exécutant par ``reclamer`` (cahier P6 § 5.2). La DEMANDE enregistrée par le greffon fait foi :
    voie, modèle, effort et palier sont ceux que le routage a résolus (l'exécutant les recontrôle contre sa
    politique) ; ``branche_base`` est ``None`` (la politique de l'exécutant la porte, jamais Hermes, D75).

    - ``integration`` : voie ``poste-integration``, sans modèle, effort ni palier ; ``branches_a_integrer`` non vide.
    - ``relecture`` : ``carte_relue`` désigne la carte relue (sa branche locale est ``hermes/<carte_relue>``).
    - Taille : la carte entière tient dans :data:`TAILLE_MAX_CARTE` octets (réponse de 64 Kio)."""

    tableau: str
    carte: str
    run_id: int
    projet_id: str
    role: str
    voie: str
    modele: Optional[str] = None
    effort: Optional[str] = None
    palier: Optional[str] = None
    depot_alias: str
    branche_base: Optional[str] = None
    branche: str
    branche_depart: Optional[str] = None
    consigne: str
    consigne_tronquee: bool = False
    parents: List[ParentCarte] = []
    carte_relue: Optional[str] = None
    correction_n: int = 0
    branches_a_integrer: List[str] = []
    duree_max_s: int
    ttl_s: int = TTL_RECLAMATION_S
    reponses: List[ReponseQuestionLivree] = []
    reprise: bool = False

    @field_validator("tableau", mode="before")
    @classmethod
    def _tableau(cls, valeur: Any) -> str:
        return _identifiant(valeur, "tableau", TABLEAU, 64)

    @field_validator("carte", "carte_relue", mode="before")
    @classmethod
    def _cartes(cls, valeur: Any, info) -> Optional[str]:
        if valeur is None and info.field_name == "carte_relue":
            return None
        return _identifiant(valeur, info.field_name, CARTE, 34)

    @field_validator("run_id", mode="before")
    @classmethod
    def _run(cls, valeur: Any) -> int:
        return _entier(valeur, "run_id", 1, 2**62)

    @field_validator("projet_id", mode="before")
    @classmethod
    def _projet(cls, valeur: Any) -> str:
        return _identifiant(valeur, "projet_id", PROJET, 14)

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, valeur: Any) -> str:
        return _choix(valeur, "role", ROLES_CARTE)

    @field_validator("voie", mode="before")
    @classmethod
    def _voie(cls, valeur: Any) -> str:
        return _choix(valeur, "voie", VOIES_EXECUTION)

    @field_validator("modele", mode="before")
    @classmethod
    def _modele(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "modele", _ID_MODELE)

    @field_validator("effort", mode="before")
    @classmethod
    def _effort(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "effort", _EFFORT, 20)

    @field_validator("palier", mode="before")
    @classmethod
    def _palier(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "palier", _PALIER, 32)

    @field_validator("depot_alias", mode="before")
    @classmethod
    def _depot(cls, valeur: Any) -> str:
        return _identifiant(valeur, "depot_alias", ALIAS_DEPOT, 32)

    @field_validator("branche_base", mode="before")
    @classmethod
    def _base(cls, valeur: Any) -> Optional[str]:
        if valeur is None:
            return None
        if not isinstance(valeur, str) or not branche_git_valide(valeur):
            raise ValueError("« branche_base » : nom de branche git invalide")
        return valeur

    @field_validator("branche", mode="before")
    @classmethod
    def _branche(cls, valeur: Any) -> str:
        texte = _texte(valeur, champ="branche", maximum=80)
        if not (BRANCHE_CARTE.fullmatch(texte) or BRANCHE_PROJET.fullmatch(texte)):
            raise ValueError("« branche » : hermes/<carte> ou hermes/projet-<slug> attendu")
        return texte

    @field_validator("branche_depart", mode="before")
    @classmethod
    def _depart(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "branche_depart", BRANCHE_CARTE, 48)

    @field_validator("consigne", mode="before")
    @classmethod
    def _consigne(cls, valeur: Any) -> str:
        return _texte(valeur, champ="consigne", maximum=CONSIGNE_MAX)

    @field_validator("consigne_tronquee", "reprise", mode="before")
    @classmethod
    def _bools(cls, valeur: Any, info) -> bool:
        return _booleen(valeur, info.field_name)

    @field_validator("parents", mode="before")
    @classmethod
    def _parents(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list) or len(valeur) > PARENTS_MAX:
            raise ValueError(f"« parents » doit être une liste d'au plus {PARENTS_MAX} cartes")
        return valeur

    @field_validator("correction_n", mode="before")
    @classmethod
    def _correction(cls, valeur: Any) -> int:
        return _entier(valeur, "correction_n", 0, 99)

    @field_validator("branches_a_integrer", mode="before")
    @classmethod
    def _branches(cls, valeur: Any) -> List[str]:
        if not isinstance(valeur, list) or len(valeur) > BRANCHES_INTEGRATION_MAX:
            raise ValueError(f"« branches_a_integrer » : au plus {BRANCHES_INTEGRATION_MAX} branches")
        propres = [_identifiant(v, "branches_a_integrer", BRANCHE_CARTE, 48) for v in valeur]
        if len(set(propres)) != len(propres):
            raise ValueError("« branches_a_integrer » contient un doublon")
        return propres

    @field_validator("duree_max_s", mode="before")
    @classmethod
    def _duree(cls, valeur: Any) -> int:
        return _entier(valeur, "duree_max_s", 60, 86_400)

    @field_validator("ttl_s", mode="before")
    @classmethod
    def _ttl(cls, valeur: Any) -> int:
        return _entier(valeur, "ttl_s", 60, 86_400)

    @field_validator("reponses", mode="before")
    @classmethod
    def _reponses(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list) or len(valeur) > REPONSES_MAX:
            raise ValueError(f"« reponses » doit être une liste d'au plus {REPONSES_MAX} réponses")
        return valeur

    @model_validator(mode="after")
    def _coherence(self) -> "DemandeCarte":
        integration = self.role == "integration"
        if integration != (self.voie == "poste-integration"):
            raise ValueError("« voie » : poste-integration porte les cartes d'intégration, et elles seules")
        if integration:
            if self.modele is not None or self.effort is not None or self.palier is not None:
                raise ValueError("une carte d'intégration n'a ni modèle, ni effort, ni palier")
            if not self.branches_a_integrer:
                raise ValueError("« branches_a_integrer » : une carte d'intégration fusionne au moins une branche")
            if not BRANCHE_PROJET.fullmatch(self.branche):
                raise ValueError("« branche » : une intégration écrit hermes/projet-<slug>")
        else:
            if self.modele is None:
                raise ValueError(f"« modele » : une carte {self.role} porte le modèle résolu par le routage")
            if self.branches_a_integrer:
                raise ValueError("« branches_a_integrer » : réservé aux cartes d'intégration")
            if self.branche != f"hermes/{self.carte}":
                raise ValueError("« branche » : la branche d'une carte est hermes/<carte>")
        if (self.role == "relecture") != (self.carte_relue is not None):
            raise ValueError("« carte_relue » : exigée pour une relecture, et pour elle seule")
        if self.role != "correction" and self.correction_n:
            raise ValueError("« correction_n » : réservé aux cartes de correction")
        taille = taille_json(self.model_dump(mode="json"))
        if taille > TAILLE_MAX_CARTE:
            raise ValueError(f"carte de {taille} octets : au plus {TAILLE_MAX_CARTE} (consigne et résumés à tronquer)")
        return self


# ------------------------------------------------------------------ réclamation (long-poll)


class RequeteReclamer(_Contrat):
    """Étape P6 (compatible, valeurs par défaut) : ``voies_disponibles`` (vide ⇒ aucune carte ; exige
    ``peut_executer``), ``carte_en_cours`` (concurrence 1) et ``espace_libre_mio`` (diagnostic)."""

    protocole: str
    version_poste: str
    peut_executer: bool
    ordres_acquittes: List[int] = []
    attente_max_s: int = 25
    politique_valide: bool = True
    voies_disponibles: List[str] = []
    carte_en_cours: Optional[CarteEnCours] = None
    espace_libre_mio: Optional[int] = None

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

    @field_validator("voies_disponibles", mode="before")
    @classmethod
    def _voies(cls, valeur: Any) -> List[str]:
        if not isinstance(valeur, list) or len(valeur) > len(VOIES_EXECUTION):
            raise ValueError(f"« voies_disponibles » : au plus {len(VOIES_EXECUTION)} voies")
        propres = [_choix(v, "voies_disponibles", VOIES_EXECUTION) for v in valeur]
        if len(set(propres)) != len(propres):
            raise ValueError("« voies_disponibles » contient un doublon")
        return propres

    @field_validator("espace_libre_mio", mode="before")
    @classmethod
    def _espace(cls, valeur: Any) -> Optional[int]:
        return None if valeur is None else _entier(valeur, "espace_libre_mio", 0, 10**8)

    @model_validator(mode="after")
    def _coherence(self) -> "RequeteReclamer":
        if self.voies_disponibles and not self.peut_executer:
            raise ValueError("« voies_disponibles » : un poste qui ne peut pas exécuter n'annonce aucune voie")
        return self


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
    """``carte`` : une :class:`DemandeCarte` (étape P6), servie seulement à un poste qui a annoncé
    ``peut_executer: true`` et la voie de la carte ; le poste refuse une carte s'il ne l'a pas demandée."""

    maintenant: datetime
    etat_machine: str
    pause_reclamations: bool
    ordres: List[Ordre]
    carte: Optional[DemandeCarte] = None
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
                "json_attendu", "requete_refusee", "trop_frequent", "non_authentifie", "echec",
                # Étape P6 (cahier P6 § 5.10).
                "reclamation_perdue", "projet_en_pause", "carte_inconnue", "carte_non_emise", "secret_detecte",
                "issue_invalide")


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


# ------------------------------------------------------------------ routes de l'exécution (étape P6, § 5.3 à § 5.8)

GENRES_BLOCAGE = ("capacite", "quota", "secret", "memoire", "disque", "duree", "politique")
MOTIFS_REPRENDRE = ("redemarrage", "reclamation_perdue")
MOTIFS_ARRET = ("sigterm", "pause_locale", "annulee")
REGIMES = ("A", "B", "inconnu")
ETATS_VERIFICATION = ("reussie", "echouee", "non_executee")
CHEMINS_PILOTAGE_MAX = 50
NOTE_MAX = 500
RESUME_MAX = 4000


def secret_trouve(objet: Any) -> Optional[str]:
    """Nom du premier motif de secret trouvé dans une chaîne (ou une clé) d'un corps JSON décodé, ou ``None``.
    Parcours ITÉRATIF (aucune RecursionError) ; la valeur n'est jamais rendue, seulement le nom du motif."""
    pile: list = [objet]
    while pile:
        courant = pile.pop()
        if isinstance(courant, str):
            nom = motif_trouve(courant)
            if nom:
                return nom
        elif isinstance(courant, Mapping):
            for cle, valeur in courant.items():
                pile.append(valeur)
                if isinstance(cle, str):
                    pile.append(cle)
        elif isinstance(courant, (list, tuple)):
            pile.extend(courant)
    return None


class _RequeteCarte(_Contrat):
    """Champs communs des six routes de l'exécution : envoi idempotent (``id_envoi``, UUID v4) et preuve de
    propriété (tableau, carte et run courant, vérifiés par le greffon contre ``claim_lock`` et ``current_run_id``)."""

    id_envoi: str
    tableau: str
    carte: str
    run_id: int

    @field_validator("id_envoi", mode="before")
    @classmethod
    def _id_envoi(cls, valeur: Any) -> str:
        return _identifiant(valeur, "id_envoi", ID_ENVOI, 36)

    @field_validator("tableau", mode="before")
    @classmethod
    def _tableau(cls, valeur: Any) -> str:
        return _identifiant(valeur, "tableau", TABLEAU, 64)

    @field_validator("carte", mode="before")
    @classmethod
    def _carte(cls, valeur: Any) -> str:
        return _identifiant(valeur, "carte", CARTE, 34)

    @field_validator("run_id", mode="before")
    @classmethod
    def _run(cls, valeur: Any) -> int:
        return _entier(valeur, "run_id", 1, 2**62)


class RequeteBattement(_RequeteCarte):
    """Toutes les 60 s ; ``note`` est composée par l'exécutant (étape, compte des tests), jamais une sortie brute."""

    note: str

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, valeur: Any) -> str:
        return _texte(valeur, champ="note", maximum=NOTE_MAX)


class ReponseBattement(_Contrat):
    """``valide: false`` : réclamation perdue (arrêter, committer, ``reprendre``) ; ``annuler: true`` : projet en pause
    ou carte archivée (arrêter, committer, ``arret``)."""

    valide: bool
    pause: bool
    annuler: bool

    @field_validator("valide", "pause", "annuler", mode="before")
    @classmethod
    def _b(cls, valeur: Any, info) -> bool:
        return _booleen(valeur, info.field_name)


def _entier_facultatif(valeur: Any, champ: str, minimum: int, maximum: int) -> Optional[int]:
    return None if valeur is None else _entier(valeur, champ, minimum, maximum)


class Jetons(_Contrat):
    entree: Optional[int] = None
    sortie: Optional[int] = None
    cache: Optional[int] = None

    @field_validator("entree", "sortie", "cache", mode="before")
    @classmethod
    def _n(cls, valeur: Any, info) -> Optional[int]:
        return _entier_facultatif(valeur, info.field_name, 0, 10**12)


class Diffstat(_Contrat):
    fichiers: int
    ajouts: int
    retraits: int

    @field_validator("fichiers", "ajouts", "retraits", mode="before")
    @classmethod
    def _n(cls, valeur: Any, info) -> int:
        return _entier(valeur, info.field_name, 0, 10**8)


class Verification(_Contrat):
    """Vérification de la politique du dépôt ; ``non_executee`` dit pourquoi (régime B sans
    ``verification_sans_bac_a_sable``, relecture, exploration…). Aucun succès simulé."""

    etat: str
    code: Optional[int] = None
    duree_s: Optional[int] = None
    tentatives: int = 0
    raison: Optional[str] = None

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        return _choix(valeur, "etat", ETATS_VERIFICATION)

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, valeur: Any) -> Optional[int]:
        return _entier_facultatif(valeur, "code", -255, 255)

    @field_validator("duree_s", mode="before")
    @classmethod
    def _duree(cls, valeur: Any) -> Optional[int]:
        return _entier_facultatif(valeur, "duree_s", 0, 86_400)

    @field_validator("tentatives", mode="before")
    @classmethod
    def _tentatives(cls, valeur: Any) -> int:
        return _entier(valeur, "tentatives", 0, 20)

    @field_validator("raison", mode="before")
    @classmethod
    def _raison(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="raison", maximum=300)

    @model_validator(mode="after")
    def _coherence(self) -> "Verification":
        if self.etat == "reussie" and self.code != 0:
            raise ValueError("« verification » : réussie exige le code 0")
        if self.etat == "echouee" and (self.code == 0 or (self.code is None and self.raison is None)):
            raise ValueError("« verification » : un échec porte un code non nul ou sa raison")
        if self.etat == "non_executee" and (self.raison is None or self.code is not None):
            raise ValueError("« verification » : non exécutée dit pourquoi, sans code")
        return self


class Pilotage(_Contrat):
    """Fichiers de pilotage des agents touchés par le diff (cahier P6 § 6.6) : un seul chemin ⇒ revue."""

    touche: bool = False
    chemins: List[str] = []

    @field_validator("touche", mode="before")
    @classmethod
    def _touche(cls, valeur: Any) -> bool:
        return _booleen(valeur, "touche")

    @field_validator("chemins", mode="before")
    @classmethod
    def _chemins(cls, valeur: Any) -> List[str]:
        if not isinstance(valeur, list) or len(valeur) > CHEMINS_PILOTAGE_MAX:
            raise ValueError(f"« chemins » : au plus {CHEMINS_PILOTAGE_MAX} chemins")
        return [_texte(v, champ="chemins", maximum=300) for v in valeur]

    @model_validator(mode="after")
    def _coherence(self) -> "Pilotage":
        if self.touche != bool(self.chemins):
            raise ValueError("« pilotage » : « touche » vaut vrai exactement quand des chemins sont cités")
        return self


class MetadonneesExecution(_Contrat):
    """Ce que l'exécutant a observé (cahier P6 § 5.4) ; rangé sur le run par ``complete_task`` (jamais de clé
    ``artifacts`` ni ``published_pr`` : champs fermés)."""

    modele_demande: Optional[str] = None
    modele_servi: Optional[str] = None
    effort: Optional[str] = None
    palier_demande: Optional[str] = None
    palier_servi: Optional[str] = None
    jetons: Optional[Jetons] = None
    branche: str
    base: Optional[str] = None
    tete: Optional[str] = None
    diffstat: Optional[Diffstat] = None
    verification: Optional[Verification] = None
    pilotage: Pilotage = Pilotage()
    regime: str = "inconnu"
    session_locale: bool = False

    @field_validator("modele_demande", "modele_servi", mode="before")
    @classmethod
    def _modeles(cls, valeur: Any, info) -> Optional[str]:
        return _identifiant_facultatif(valeur, info.field_name, _ID_MODELE)

    @field_validator("effort", mode="before")
    @classmethod
    def _effort(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "effort", _EFFORT, 20)

    @field_validator("palier_demande", "palier_servi", mode="before")
    @classmethod
    def _paliers(cls, valeur: Any, info) -> Optional[str]:
        return _identifiant_facultatif(valeur, info.field_name, _PALIER, 32)

    @field_validator("branche", mode="before")
    @classmethod
    def _branche(cls, valeur: Any) -> str:
        texte = _texte(valeur, champ="branche", maximum=80)
        if not (BRANCHE_CARTE.fullmatch(texte) or BRANCHE_PROJET.fullmatch(texte)):
            raise ValueError("« branche » : hermes/<carte> ou hermes/projet-<slug> attendu")
        return texte

    @field_validator("base", "tete", mode="before")
    @classmethod
    def _sha(cls, valeur: Any, info) -> Optional[str]:
        return _identifiant_facultatif(valeur, info.field_name, SHA40, 40)

    @field_validator("regime", mode="before")
    @classmethod
    def _regime(cls, valeur: Any) -> str:
        return _choix(valeur, "regime", REGIMES)

    @field_validator("session_locale", mode="before")
    @classmethod
    def _session(cls, valeur: Any) -> bool:
        return _booleen(valeur, "session_locale")


class RequeteTerminer(_RequeteCarte):
    """Issue normale d'une carte. ``verdict`` (``accepte`` ou ``corrections``) pour une relecture seulement ;
    ``corrections`` porte alors la consigne de correction. Un résumé vide est refusé (``complete_task`` lèverait
    ``EmptyCompletionError`` depuis ``running``)."""

    issue: str
    resume: str
    verdict: Optional[str] = None
    corrections: Optional[str] = None
    metadonnees: MetadonneesExecution

    @field_validator("issue", mode="before")
    @classmethod
    def _issue(cls, valeur: Any) -> str:
        return _choix(valeur, "issue", ("termine",))

    @field_validator("resume", mode="before")
    @classmethod
    def _resume(cls, valeur: Any) -> str:
        return _texte(valeur, champ="resume", maximum=RESUME_MAX)

    @field_validator("verdict", mode="before")
    @classmethod
    def _verdict(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _choix(valeur, "verdict", ("accepte", "corrections"))

    @field_validator("corrections", mode="before")
    @classmethod
    def _corrections(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="corrections", maximum=RESUME_MAX)

    @model_validator(mode="after")
    def _coherence(self) -> "RequeteTerminer":
        if (self.verdict == "corrections") != (self.corrections is not None):
            raise ValueError("« corrections » : exigée avec le verdict « corrections », et avec lui seul")
        branche = self.metadonnees.branche
        if BRANCHE_CARTE.fullmatch(branche) and branche != f"hermes/{self.carte}":
            raise ValueError("« metadonnees.branche » : la branche d'une carte est hermes/<carte>")
        return self


class ReponseTerminer(_Contrat):
    etat: str
    deja_recu: bool = False

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        return _choix(valeur, "etat", ("done", "review", "correction_creee"))

    @field_validator("deja_recu", mode="before")
    @classmethod
    def _deja(cls, valeur: Any) -> bool:
        return _booleen(valeur, "deja_recu")


class RequeteQuestion(_RequeteCarte):
    """Question posée par la carte (le travail en cours est committé avant l'envoi)."""

    texte: str
    contexte: Optional[str] = None

    @field_validator("texte", mode="before")
    @classmethod
    def _texte_question(cls, valeur: Any) -> str:
        return _texte(valeur, champ="texte", maximum=4000)

    @field_validator("contexte", mode="before")
    @classmethod
    def _contexte(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="contexte", maximum=4000)


class ReponseQuestion(_Contrat):
    question: str
    etat: str
    carte_repondre: Optional[str] = None
    deja_recu: bool = False

    @field_validator("question", mode="before")
    @classmethod
    def _question(cls, valeur: Any) -> str:
        return _identifiant(valeur, "question", QUESTION, 14)

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        return _choix(valeur, "etat", ("ouverte", "escaladee", "repondue", "annulee"))

    @field_validator("carte_repondre", mode="before")
    @classmethod
    def _repondre(cls, valeur: Any) -> Optional[str]:
        return _identifiant_facultatif(valeur, "carte_repondre", CARTE, 34)

    @field_validator("deja_recu", mode="before")
    @classmethod
    def _deja(cls, valeur: Any) -> bool:
        return _booleen(valeur, "deja_recu")


class RequeteBloquer(_RequeteCarte):
    """Blocage décidé par l'exécutant ; ``raison`` est une phrase française qu'il compose (≤ 500), ``reprise_le``
    (genre ``quota`` seulement) l'heure de remise à zéro annoncée par la CLI."""

    genre: str
    raison: str
    reprise_le: Optional[datetime] = None

    @field_validator("genre", mode="before")
    @classmethod
    def _genre(cls, valeur: Any) -> str:
        return _choix(valeur, "genre", GENRES_BLOCAGE)

    @field_validator("raison", mode="before")
    @classmethod
    def _raison(cls, valeur: Any) -> str:
        return _texte(valeur, champ="raison", maximum=500)

    @field_validator("reprise_le", mode="before")
    @classmethod
    def _reprise(cls, valeur: Any) -> Optional[datetime]:
        return None if valeur is None else _instant(valeur, champ="reprise_le")

    @model_validator(mode="after")
    def _coherence(self) -> "RequeteBloquer":
        if self.reprise_le is not None and self.genre != "quota":
            raise ValueError("« reprise_le » : réservé au genre « quota »")
        return self


class ReponseBloquer(_Contrat):
    etat: str
    deja_recu: bool = False

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        return _choix(valeur, "etat", ("bloquee", "planifiee", "triage"))

    @field_validator("deja_recu", mode="before")
    @classmethod
    def _deja(cls, valeur: Any) -> bool:
        return _booleen(valeur, "deja_recu")


class RequeteReprendre(_RequeteCarte):
    """Rend la carte (``reclaim_task``) après un redémarrage ou une réclamation perdue ; le greffon la ressert en
    priorité à cette machine, avec ``reprise: true``."""

    motif: str

    @field_validator("motif", mode="before")
    @classmethod
    def _motif(cls, valeur: Any) -> str:
        return _choix(valeur, "motif", MOTIFS_REPRENDRE)


class RequeteArret(_RequeteCarte):
    """Envoyée AVANT l'arrêt (marge de 90 s sur Railway) : même effet que ``reprendre``, et la présence note un
    arrêt propre (« Exécutant en redéploiement » plutôt que « hors ligne » pendant 10 min)."""

    motif: str

    @field_validator("motif", mode="before")
    @classmethod
    def _motif(cls, valeur: Any) -> str:
        return _choix(valeur, "motif", MOTIFS_ARRET)


class ReponseReprise(_Contrat):
    """``rendue`` : la carte est revenue à ``ready`` (compteur d'échecs remis à zéro) ; ``deja_libre`` : elle
    n'était plus à cet exécutant (TTL expiré), rien n'a été fait."""

    etat: str
    deja_recu: bool = False

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> str:
        return _choix(valeur, "etat", ("rendue", "deja_libre"))

    @field_validator("deja_recu", mode="before")
    @classmethod
    def _deja(cls, valeur: Any) -> bool:
        return _booleen(valeur, "deja_recu")


# Route P6 → (modèle de requête, modèle de réponse, borne du corps en octets).
MODELES_P6 = {
    ROUTE_BATTEMENT: ("RequeteBattement", "ReponseBattement", TAILLE_MAX_EVENEMENT),
    ROUTE_TERMINER: ("RequeteTerminer", "ReponseTerminer", TAILLE_MAX_ISSUE),
    ROUTE_QUESTION: ("RequeteQuestion", "ReponseQuestion", TAILLE_MAX_ISSUE),
    ROUTE_BLOQUER: ("RequeteBloquer", "ReponseBloquer", TAILLE_MAX_EVENEMENT),
    ROUTE_REPRENDRE: ("RequeteReprendre", "ReponseReprise", TAILLE_MAX_EVENEMENT),
    ROUTE_ARRET: ("RequeteArret", "ReponseReprise", TAILLE_MAX_EVENEMENT),
}


def valider(modele, donnees: Any, *, quoi: str):
    """``modele`` validé, ou ``ValueError`` au message français (« <quoi> refusé(e) : … »)."""
    try:
        return modele.model_validate(donnees)
    except ValidationError as exc:
        details = "; ".join(_message(e) for e in exc.errors()[:5])
        raise ValueError(f"{quoi} : {details}.") from None
