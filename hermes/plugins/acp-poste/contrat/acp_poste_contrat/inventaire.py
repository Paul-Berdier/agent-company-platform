"""Contrat du relevé du poste (« inventaire ») : modèles, efforts, paliers, quotas et dépôts autorisés
d'une voie (``poste-codex`` ou ``poste-claude``), étape P4 du plan d'autonomie (décision D21).

Une seule source pour les deux côtés :

- le **poste** (P5) le produit à partir de ce que Codex CLI (``model/list`` de l'app-server) et Claude
  Code déclarent, puis le publie sur ``/machine/v1/inventaire`` ;
- le **greffon** ``acp-poste`` le valide avant de l'enregistrer (table ``releves``) et ne route une étape
  que vers un modèle, un effort et un palier qui y figurent. Rien n'est inventé : sans relevé, le
  catalogue est « Inconnu » et une étape du poste est refusée.

En P4, aucun relevé réel n'existe : les tests déposent un relevé ``source: "releve_factice"`` aux
identifiants manifestement factices, par la même fonction que la route P5.

Étape P5 (cahier P5 § 11.1) : le contrat est **élargi sans rien restreindre** — tout relevé que P4 acceptait
reste accepté (relevés factices, lignes déjà en base). Trois champs sont élargis (``id`` admet ``[`` et ``]``
pour ``opus[1m]``, ``isDefault`` et ``supportedReasoningEfforts`` admettent ``None`` : « la source ne désigne
pas », « inconnus ») ; des champs à valeur par défaut sont ajoutés (origine de la liste, état du relevé,
compteurs de quotas…) ; :class:`InventairePoste` est le corps de ``POST /machine/v1/inventaire``.

Les champs des modèles gardent les noms de Codex (``displayName``, ``isDefault``,
``supportedReasoningEfforts``…) pour qu'un relevé se lise sans traduction. Les refus sont en français,
y compris pour un champ inconnu ou manquant (:func:`valider_releve`).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from ._validation import ContratValide
from .motifs_secrets import motif_trouve
from .quotas import QUOTA_BATCH_MAX, SubscriptionQuotaReport

VOIES = ("poste-codex", "poste-claude")
SOURCES = ("poste", "releve_factice")
MODELES_MAX = 200
DEPOTS_MAX = 100
EFFORTS_MAX = 16
PALIERS_MAX = 16

# Étape P5 : « [ » et « ] » admis (alias documentés de Claude Code : opus[1m], sonnet[1m]).
_ID_MODELE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,127}")
_EFFORT = re.compile(r"[a-z][a-z0-9_-]{0,19}")
_PALIER = re.compile(r"[a-z][a-z0-9_-]{0,31}")
ALIAS_DEPOT = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,63}")


def _texte(valeur: Any, *, champ: str, maximum: int, motif: Optional[re.Pattern] = None) -> str:
    if not isinstance(valeur, str):
        raise ValueError(f"« {champ} » doit être une chaîne de caractères")
    if "\x00" in valeur:
        raise ValueError(f"« {champ} » : le caractère NUL (\\x00) est interdit")
    if not valeur.strip():
        raise ValueError(f"« {champ} » ne peut pas être vide")
    if len(valeur) > maximum:
        raise ValueError(f"« {champ} » : au maximum {maximum} caractères")
    if motif is not None and motif.fullmatch(valeur) is None:
        raise ValueError(f"« {champ} » : format invalide (« {valeur[:40]} »)")
    return valeur


def _liste_de_textes(valeur: Any, *, champ: str, maximum: int, motif: re.Pattern) -> List[str]:
    if not isinstance(valeur, list):
        raise ValueError(f"« {champ} » doit être une liste")
    if len(valeur) > maximum:
        raise ValueError(f"« {champ} » : au plus {maximum} éléments")
    textes = [_texte(v, champ=champ, maximum=32, motif=motif) for v in valeur]
    if len(set(textes)) != len(textes):
        raise ValueError(f"« {champ} » contient un doublon")
    return textes


def _instant(valeur: Any, *, champ: str) -> datetime:
    if isinstance(valeur, str):
        try:
            valeur = datetime.fromisoformat(valeur)
        except ValueError:
            raise ValueError(f"« {champ} » : horodatage ISO 8601 illisible") from None
    if not isinstance(valeur, datetime):
        raise ValueError(f"« {champ} » doit être un horodatage ISO 8601")
    if valeur.tzinfo is None or valeur.utcoffset() is None:
        raise ValueError(f"« {champ} » doit porter son fuseau (UTC attendu)")
    try:
        return valeur.astimezone(UTC)
    except (OverflowError, ValueError):
        raise ValueError(f"« {champ} » : horodatage hors de la plage UTC lisible") from None


class _Contrat(ContratValide):
    """Frontière JSON stricte : tout écart est refusé avec un message français."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _champs_declares_seulement(cls, donnees: Any) -> Any:
        if isinstance(donnees, BaseModel):
            donnees = donnees.model_dump()
        if not isinstance(donnees, Mapping):
            raise ValueError("un objet JSON est attendu")
        inconnus = sorted(str(cle) for cle in donnees if cle not in cls.model_fields)
        if inconnus:
            raise ValueError("champ inconnu refusé : " + ", ".join(f"« {nom} »" for nom in inconnus))
        manquants = [nom for nom, info in cls.model_fields.items() if info.is_required() and nom not in donnees]
        if manquants:
            raise ValueError("champ obligatoire absent : " + ", ".join(f"« {nom} »" for nom in manquants))
        return donnees


NATURES = ("catalogue_compte", "alias_documente")
SOURCES_EFFORTS = ("releve", "documentation")


class ModeleReleve(_Contrat):
    """Un modèle tel que la CLI de la voie le déclare (champs de Codex ``model/list``).

    Étape P5 : ``isDefault`` à ``None`` = la source ne désigne pas de modèle par défaut (alias documentés de
    Claude Code) ; ``supportedReasoningEfforts`` à ``None`` = efforts INCONNUS (``[]`` = aucun effort). Les
    champs ajoutés ont une valeur par défaut : un relevé de P4 reste valide tel quel."""

    id: str
    displayName: Optional[str] = None  # noqa: N815 — nom de Codex
    isDefault: Optional[bool] = False  # noqa: N815
    supportedReasoningEfforts: Optional[List[str]] = []  # noqa: N815
    defaultReasoningEffort: Optional[str] = None  # noqa: N815
    serviceTiers: List[str] = []  # noqa: N815
    defaultServiceTier: Optional[str] = None  # noqa: N815
    # Étape P5, à valeur par défaut (cahier P5 § 11.1) : ``model``, ``hidden``, ``upgrade`` et
    # ``upgradeInfo.retirementAt`` de Codex ; nature et source des efforts ; résolution documentée d'un alias.
    modele: Optional[str] = None
    cache: bool = False
    remplace_par: Optional[str] = None
    retrait_le: Optional[datetime] = None
    nature: Literal["catalogue_compte", "alias_documente"] = "catalogue_compte"
    resolution_documentee: Optional[str] = None
    source_efforts: Literal["releve", "documentation"] = "releve"

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valeur: Any) -> str:
        return _texte(valeur, champ="id", maximum=128, motif=_ID_MODELE)

    @field_validator("modele", "remplace_par", "resolution_documentee", mode="before")
    @classmethod
    def _identifiants_facultatifs(cls, valeur: Any, info) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ=info.field_name, maximum=128, motif=_ID_MODELE)

    @field_validator("displayName", mode="before")
    @classmethod
    def _nom(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="displayName", maximum=200)

    @field_validator("isDefault", mode="before")
    @classmethod
    def _defaut(cls, valeur: Any) -> Optional[bool]:
        if valeur is not None and type(valeur) is not bool:
            raise ValueError("« isDefault » doit être un booléen (true ou false) ou null")
        return valeur

    @field_validator("cache", mode="before")
    @classmethod
    def _cache(cls, valeur: Any) -> bool:
        if type(valeur) is not bool:
            raise ValueError("« cache » doit être un booléen (true ou false)")
        return valeur

    @field_validator("retrait_le", mode="before")
    @classmethod
    def _retrait(cls, valeur: Any) -> Optional[datetime]:
        return None if valeur is None else _instant(valeur, champ="retrait_le")

    @field_validator("nature", mode="before")
    @classmethod
    def _nature(cls, valeur: Any) -> str:
        if valeur not in NATURES:
            raise ValueError(f"« nature » : valeurs admises : {', '.join(NATURES)}")
        return valeur

    @field_validator("source_efforts", mode="before")
    @classmethod
    def _source_efforts(cls, valeur: Any) -> str:
        if valeur not in SOURCES_EFFORTS:
            raise ValueError(f"« source_efforts » : valeurs admises : {', '.join(SOURCES_EFFORTS)}")
        return valeur

    @field_validator("supportedReasoningEfforts", mode="before")
    @classmethod
    def _efforts(cls, valeur: Any) -> Optional[List[str]]:
        if valeur is None:
            return None
        return _liste_de_textes(valeur, champ="supportedReasoningEfforts", maximum=EFFORTS_MAX, motif=_EFFORT)

    @field_validator("serviceTiers", mode="before")
    @classmethod
    def _paliers(cls, valeur: Any) -> List[str]:
        return _liste_de_textes(valeur, champ="serviceTiers", maximum=PALIERS_MAX, motif=_PALIER)

    @field_validator("defaultReasoningEffort", mode="before")
    @classmethod
    def _effort_defaut(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="defaultReasoningEffort", maximum=20, motif=_EFFORT)

    @field_validator("defaultServiceTier", mode="before")
    @classmethod
    def _palier_defaut(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="defaultServiceTier", maximum=32, motif=_PALIER)

    @model_validator(mode="after")
    def _coherence(self) -> "ModeleReleve":
        if self.supportedReasoningEfforts is None and self.defaultReasoningEffort is not None:
            raise ValueError(f"modèle « {self.id} » : un effort par défaut exige des efforts connus "
                             "(« supportedReasoningEfforts » est null)")
        if self.defaultReasoningEffort and self.defaultReasoningEffort not in (self.supportedReasoningEfforts or []):
            raise ValueError(f"modèle « {self.id} » : l'effort par défaut « {self.defaultReasoningEffort} » ne "
                             "figure pas parmi ses efforts pris en charge")
        if self.defaultServiceTier and self.defaultServiceTier not in self.serviceTiers:
            raise ValueError(f"modèle « {self.id} » : le palier par défaut « {self.defaultServiceTier} » ne "
                             "figure pas parmi ses paliers")
        return self


class Quotas(_Contrat):
    """Part utilisée de l'abonnement de la voie et prochaine remise à zéro, telles que relevées
    (``None`` : inconnu, jamais estimé)."""

    pourcentage_utilise: Optional[float] = None
    remise_a_zero: Optional[datetime] = None

    @field_validator("pourcentage_utilise", mode="before")
    @classmethod
    def _pourcentage(cls, valeur: Any) -> Optional[float]:
        if valeur is None:
            return None
        if type(valeur) not in (int, float) or not math.isfinite(valeur) or not 0 <= valeur <= 100:
            raise ValueError("« pourcentage_utilise » doit être un nombre fini compris entre 0 et 100")
        return float(valeur)

    @field_validator("remise_a_zero", mode="before")
    @classmethod
    def _remise(cls, valeur: Any) -> Optional[datetime]:
        return None if valeur is None else _instant(valeur, champ="remise_a_zero")


class Depot(_Contrat):
    """Un dépôt autorisé par le poste, connu du greffon par son seul alias (jamais un chemin)."""

    alias: str

    @field_validator("alias", mode="before")
    @classmethod
    def _alias(cls, valeur: Any) -> str:
        return _texte(valeur, champ="alias", maximum=32, motif=ALIAS_DEPOT)


ORIGINES_LISTE = ("compte", "catalogue_embarque", "identique_au_catalogue_embarque", "alias_documentes", "aucune")
ETATS_RELEVE = ("ok", "cli_absente", "cli_hors_version", "non_connecte", "indisponible")
PROVIDER_PAR_VOIE = {"poste-codex": "codex", "poste-claude": "claude_code"}
DETAIL_MAX = 300


class ResolutionObservee(_Contrat):
    """Résolution d'un alias OBSERVÉE à l'exécution (``system/init`` de Claude Code) : étape P6. La forme est
    réservée dès P5 pour que le contrat ne change pas ; la liste reste vide en P5."""

    alias: str
    modele: str
    observe_le: datetime

    @field_validator("alias", "modele", mode="before")
    @classmethod
    def _ids(cls, valeur: Any, info) -> str:
        return _texte(valeur, champ=info.field_name, maximum=128, motif=_ID_MODELE)

    @field_validator("observe_le", mode="before")
    @classmethod
    def _quand(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="observe_le")


class Releve(_Contrat):
    """Relevé complet d'une voie du poste.

    Étape P5 : ``compteurs`` (relevés de quotas du contrat ``quotas.py``), ``origine_liste``, ``etat``,
    ``detail``, ``documentation_lue_le`` et ``resolutions_observees``, tous à valeur par défaut. Un relevé
    ``source: "poste"`` exige ``origine_liste`` et ``etat`` (``None`` reste admis pour les relevés factices de P4
    et les lignes antérieures) ; ``modeles`` vide n'est admis que pour un relevé en échec (``etat`` ≠ ``ok``).
    ``quotas`` reste le RÉSUMÉ lu par le routage : le greffon le calcule depuis ``compteurs`` à la réception
    (:func:`resume_quotas`) ; le poste l'envoie à ``null`` (:class:`InventairePoste`)."""

    voie: str
    source: str
    version_cli: Optional[str] = None
    releve_le: datetime
    modeles: List[ModeleReleve]
    quotas: Optional[Quotas] = None
    depots: List[Depot] = []
    compteurs: List[SubscriptionQuotaReport] = []
    origine_liste: Optional[Literal["compte", "catalogue_embarque", "identique_au_catalogue_embarque",
                                    "alias_documentes", "aucune"]] = None
    etat: Optional[Literal["ok", "cli_absente", "cli_hors_version", "non_connecte", "indisponible"]] = None
    detail: Optional[str] = None
    documentation_lue_le: Optional[date] = None
    resolutions_observees: List[ResolutionObservee] = []

    @field_validator("origine_liste", mode="before")
    @classmethod
    def _origine(cls, valeur: Any) -> Optional[str]:
        if valeur is not None and valeur not in ORIGINES_LISTE:
            raise ValueError(f"« origine_liste » : valeurs admises : {', '.join(ORIGINES_LISTE)}")
        return valeur

    @field_validator("etat", mode="before")
    @classmethod
    def _etat(cls, valeur: Any) -> Optional[str]:
        if valeur is not None and valeur not in ETATS_RELEVE:
            raise ValueError(f"« etat » : valeurs admises : {', '.join(ETATS_RELEVE)}")
        return valeur

    @field_validator("detail", mode="before")
    @classmethod
    def _detail(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="detail", maximum=DETAIL_MAX)

    @field_validator("documentation_lue_le", mode="before")
    @classmethod
    def _documentation(cls, valeur: Any) -> Optional[date]:
        if valeur is None:
            return None
        if isinstance(valeur, str):
            try:
                return date.fromisoformat(valeur)
            except ValueError:
                raise ValueError("« documentation_lue_le » : date ISO 8601 (AAAA-MM-JJ) illisible") from None
        if isinstance(valeur, date) and not isinstance(valeur, datetime):
            return valeur
        raise ValueError("« documentation_lue_le » doit être une date ISO 8601 (AAAA-MM-JJ)")

    @field_validator("compteurs", mode="before")
    @classmethod
    def _compteurs(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list):
            raise ValueError("« compteurs » doit être une liste")
        if len(valeur) > QUOTA_BATCH_MAX:
            raise ValueError(f"« compteurs » : au plus {QUOTA_BATCH_MAX} relevés de quotas")
        return valeur

    @field_validator("resolutions_observees", mode="before")
    @classmethod
    def _resolutions(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list):
            raise ValueError("« resolutions_observees » doit être une liste")
        if valeur:
            raise ValueError("« resolutions_observees » : réservé à l'étape P6 (première exécution), vide en P5")
        return valeur

    @field_validator("voie", mode="before")
    @classmethod
    def _voie(cls, valeur: Any) -> str:
        if valeur not in VOIES:
            raise ValueError(f"« voie » : valeurs admises : {', '.join(VOIES)}")
        return valeur

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, valeur: Any) -> str:
        if valeur not in SOURCES:
            raise ValueError(f"« source » : valeurs admises : {', '.join(SOURCES)}")
        return valeur

    @field_validator("version_cli", mode="before")
    @classmethod
    def _version(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="version_cli", maximum=64, motif=_VERSION)

    @field_validator("releve_le", mode="before")
    @classmethod
    def _releve_le(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="releve_le")

    @field_validator("modeles", mode="before")
    @classmethod
    def _modeles(cls, valeur: Any) -> Any:
        # Liste VIDE : décidée par _uniques, qui connaît l'état du relevé (vide admis seulement en échec, P5).
        if not isinstance(valeur, list):
            raise ValueError("« modeles » doit être une liste non vide")
        if len(valeur) > MODELES_MAX:
            raise ValueError(f"« modeles » : au plus {MODELES_MAX} modèles")
        return valeur

    @field_validator("depots", mode="before")
    @classmethod
    def _depots(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list):
            raise ValueError("« depots » doit être une liste")
        if len(valeur) > DEPOTS_MAX:
            raise ValueError(f"« depots » : au plus {DEPOTS_MAX} dépôts")
        return valeur

    @model_validator(mode="after")
    def _uniques(self) -> "Releve":
        if not self.modeles and self.etat in (None, "ok"):
            raise ValueError("« modeles » doit être une liste non vide (vide admis seulement pour un relevé en "
                             "échec, « etat » différent de « ok »)")
        if self.source == "poste" and (self.origine_liste is None or self.etat is None):
            raise ValueError("un relevé du poste exige « origine_liste » et « etat »")
        if self.etat not in (None, "ok") and self.detail is None:
            raise ValueError(f"« detail » : un relevé à l'état {self.etat} doit expliquer pourquoi")
        attendu = PROVIDER_PAR_VOIE[self.voie]
        vus: set = set()
        issues: set = set()
        for compteur in self.compteurs:
            if compteur.provider != attendu:
                raise ValueError(f"« compteurs » : la voie {self.voie} ne porte que des quotas {attendu}")
            if compteur.limit_id in vus:
                raise ValueError(f"« compteurs » : relevé en double pour {compteur.provider}/{compteur.limit_id}")
            vus.add(compteur.limit_id)
            issues.add(compteur.status == "ok")
        if len(issues) > 1:
            raise ValueError("« compteurs » : mêle des compteurs relevés et un échec de lecture")
        ids = [m.id for m in self.modeles]
        if len(set(ids)) != len(ids):
            raise ValueError("« modeles » : identifiant de modèle en double")
        if sum(1 for m in self.modeles if m.isDefault) > 1:
            raise ValueError("« modeles » : un seul modèle peut être le modèle par défaut")
        alias = [d.alias for d in self.depots]
        if len(set(alias)) != len(alias):
            raise ValueError("« depots » : alias en double")
        return self

    def modele(self, identifiant: str) -> Optional[ModeleReleve]:
        return next((m for m in self.modeles if m.id == identifiant), None)

    def modele_par_defaut(self) -> Optional[ModeleReleve]:
        return next((m for m in self.modeles if m.isDefault), None)


_TYPES_FRANCAIS = {
    "list_type": "type invalide", "dict_type": "type invalide", "model_type": "type invalide",
    "model_attributes_type": "type invalide", "bool_type": "booléen attendu (true ou false)",
    "bool_parsing": "booléen attendu (true ou false)", "int_type": "entier attendu", "int_parsing": "entier attendu",
    "int_from_float": "entier attendu", "string_type": "chaîne de caractères attendue",
    "literal_error": "valeur non admise", "greater_than_equal": "valeur trop petite",
    "less_than_equal": "valeur trop grande", "too_short": "trop peu d'éléments", "too_long": "trop d'éléments",
}


def _message(erreur: Mapping[str, Any]) -> str:
    """Message FRANÇAIS d'une erreur de validation : ceux des validateurs du contrat tels quels, les autres
    (types de pydantic, en anglais) remplacés par un libellé français."""
    texte = str(erreur.get("msg") or "valeur refusée")
    for prefixe in ("Value error, ", "Assertion failed, "):
        if texte.startswith(prefixe):
            texte = texte[len(prefixe):]
    lieu = ".".join(str(p) for p in erreur.get("loc") or () if p != "__root__")
    genre = erreur.get("type")
    if genre == "missing":
        texte = "champ obligatoire absent"
    elif genre not in ("value_error", "assertion_error"):
        texte = _TYPES_FRANCAIS.get(str(genre), "valeur refusée")
    return f"{lieu} : {texte}" if lieu else texte


def valider_releve(donnees: Any) -> Releve:
    """Relevé validé, ou ``ValueError`` au message français (« Relevé refusé : … »)."""
    try:
        return Releve.model_validate(donnees)
    except ValidationError as exc:
        details = "; ".join(_message(e) for e in exc.errors()[:5])
        raise ValueError(f"Relevé refusé : {details}.") from None


def resume_quotas(compteurs: List[SubscriptionQuotaReport]) -> Optional[Quotas]:
    """Résumé lu par le routage (``Releve.quotas``), calculé par le GREFFON à la réception : la plus grande part
    utilisée parmi les fenêtres des compteurs RELEVÉS (``status == "ok"``), avec la remise à zéro de cette
    fenêtre. ``None`` si aucune fenêtre n'a de part utilisée lue : jamais estimé."""
    meilleure = None
    for compteur in compteurs:
        if compteur.status != "ok":
            continue
        for fenetre in compteur.windows:
            if fenetre.used_percent is None:
                continue
            if meilleure is None or float(fenetre.used_percent) > float(meilleure.used_percent):
                meilleure = fenetre
    if meilleure is None:
        return None
    return Quotas(pourcentage_utilise=float(meilleure.used_percent), remise_a_zero=meilleure.resets_at)


# ============================================================ inventaire du poste (étape P5, § 11.1)

PROTOCOLE = "acp-machine/1"
_NOM_POSTE = re.compile(r"[^\x00-\x1f\x7f]{1,60}")
_WINDOWS = re.compile(r"\d{1,5}\.\d{1,5}\.\d{1,6}")
_EMPREINTE_POLITIQUE = re.compile(r"[0-9a-f]{12}")
_VALEUR_POLITIQUE = re.compile(r"[a-z0-9][a-z0-9._\[\]-]{0,63}")
POLITIQUE_MAX = 64


def _choix(valeur: Any, *, champ: str, admis: tuple) -> str:
    if not isinstance(valeur, str) or valeur not in admis:
        raise ValueError(f"« {champ} » : valeurs admises : {', '.join(admis)}")
    return valeur


def _booleen(valeur: Any, *, champ: str) -> bool:
    if type(valeur) is not bool:
        raise ValueError(f"« {champ} » doit être un booléen (true ou false)")
    return valeur


class BacASableCodex(_Contrat):
    """Mode du bac à sable Codex tel que lu par ``config/read`` et ``windowsSandbox/readiness`` (cahier P5 § 9.5).
    ``ecriture_admise`` (exigé par P6) n'est vrai QUE pour readiness ``ready``, mode ``elevated`` posé par le poste
    (origine ``sessionFlags``) et stockage des identifiants ``keyring`` ; sinon ``raison`` dit pourquoi."""

    READINESS: ClassVar[tuple] = ("ready", "notConfigured", "updateRequired", "inconnu")
    MODES: ClassVar[tuple] = ("elevated", "unelevated", "mxc", "absent", "inconnu")
    ORIGINES: ClassVar[tuple] = ("sessionFlags", "user", "system", "autre", "inconnu")

    readiness: str
    mode_lu: str
    origine_mode: str
    palier_lu: Optional[str] = None
    stockage_identifiants_lu: Optional[str] = None
    ecriture_admise: bool
    raison: Optional[str] = None
    lu_le: datetime

    @field_validator("readiness", mode="before")
    @classmethod
    def _readiness(cls, valeur: Any) -> str:
        return _choix(valeur, champ="readiness", admis=cls.READINESS)

    @field_validator("mode_lu", mode="before")
    @classmethod
    def _mode(cls, valeur: Any) -> str:
        return _choix(valeur, champ="mode_lu", admis=cls.MODES)

    @field_validator("origine_mode", mode="before")
    @classmethod
    def _origine(cls, valeur: Any) -> str:
        return _choix(valeur, champ="origine_mode", admis=cls.ORIGINES)

    @field_validator("palier_lu", "stockage_identifiants_lu", mode="before")
    @classmethod
    def _lus(cls, valeur: Any, info) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ=info.field_name, maximum=64)

    @field_validator("ecriture_admise", mode="before")
    @classmethod
    def _ecriture(cls, valeur: Any) -> bool:
        return _booleen(valeur, champ="ecriture_admise")

    @field_validator("raison", mode="before")
    @classmethod
    def _raison(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="raison", maximum=DETAIL_MAX)

    @field_validator("lu_le", mode="before")
    @classmethod
    def _lu_le(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="lu_le")

    @model_validator(mode="after")
    def _matrice(self) -> "BacASableCodex":
        if self.ecriture_admise and not (self.readiness == "ready" and self.mode_lu == "elevated"
                                         and self.origine_mode == "sessionFlags"
                                         and self.stockage_identifiants_lu == "keyring"):
            raise ValueError("« ecriture_admise » vrai exige readiness « ready », mode « elevated » posé par le "
                             "poste (origine « sessionFlags ») et stockage des identifiants « keyring »")
        if not self.ecriture_admise and self.raison is None:
            raise ValueError("« raison » : une écriture refusée doit dire pourquoi")
        return self


class Connexions(_Contrat):
    """Connexion de chaque CLI au compte de l'abonnement, sans aucun identifiant (cahier P5 § 9.4, § 10.2)."""

    CODEX: ClassVar[tuple] = ("compte_chatgpt", "cle_api", "autre", "non_connecte", "inconnu")
    CLAUDE: ClassVar[tuple] = ("jeton_reconnu", "jeton_present_non_verifie", "refuse", "jeton_absent", "inconnu")

    codex: str
    plan_codex: Optional[str] = None
    claude: str

    @field_validator("codex", mode="before")
    @classmethod
    def _codex(cls, valeur: Any) -> str:
        return _choix(valeur, champ="codex", admis=cls.CODEX)

    @field_validator("claude", mode="before")
    @classmethod
    def _claude(cls, valeur: Any) -> str:
        return _choix(valeur, champ="claude", admis=cls.CLAUDE)

    @field_validator("plan_codex", mode="before")
    @classmethod
    def _plan(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="plan_codex", maximum=40)


class VersionCli(_Contrat):
    """Version lue d'une CLI, version testée par le poste (``poste.toml``) et leur concordance."""

    lue: Optional[str] = None
    testee: str
    conforme: bool

    @field_validator("lue", mode="before")
    @classmethod
    def _lue(cls, valeur: Any) -> Optional[str]:
        return None if valeur is None else _texte(valeur, champ="lue", maximum=64, motif=_VERSION)

    @field_validator("testee", mode="before")
    @classmethod
    def _testee(cls, valeur: Any) -> str:
        return _texte(valeur, champ="testee", maximum=64, motif=_VERSION)

    @field_validator("conforme", mode="before")
    @classmethod
    def _conforme(cls, valeur: Any) -> bool:
        return _booleen(valeur, champ="conforme")

    @model_validator(mode="after")
    def _concordance(self) -> "VersionCli":
        if self.conforme != (self.lue is not None and self.lue == self.testee):
            raise ValueError("« conforme » doit valoir vrai exactement quand la version lue est la version testée")
        return self


class PolitiquePoste(_Contrat):
    """Ce que ``poste.toml`` refuse toujours (cahier P5 § 7.2, [politique]) : Railway ne peut pas le lever."""

    executants: List[str]
    efforts_interdits: List[str]
    paliers_admis: List[str]
    modeles_codex_permis: List[str]
    alias_claude_permis: List[str]
    reseau_executants: bool

    @field_validator("executants", mode="before")
    @classmethod
    def _executants(cls, valeur: Any) -> List[str]:
        if not isinstance(valeur, list):
            raise ValueError("« executants » doit être une liste")
        propres = [_choix(v, champ="executants", admis=("codex", "claude")) for v in valeur]
        if len(set(propres)) != len(propres):
            raise ValueError("« executants » contient un doublon")
        return propres

    @field_validator("efforts_interdits", "paliers_admis", "modeles_codex_permis", "alias_claude_permis",
                     mode="before")
    @classmethod
    def _listes(cls, valeur: Any, info) -> List[str]:
        if not isinstance(valeur, list):
            raise ValueError(f"« {info.field_name} » doit être une liste")
        if len(valeur) > POLITIQUE_MAX:
            raise ValueError(f"« {info.field_name} » : au plus {POLITIQUE_MAX} éléments")
        propres = [_texte(v, champ=info.field_name, maximum=64, motif=_VALEUR_POLITIQUE) for v in valeur]
        if len(set(propres)) != len(propres):
            raise ValueError(f"« {info.field_name} » contient un doublon")
        return propres

    @field_validator("reseau_executants", mode="before")
    @classmethod
    def _reseau(cls, valeur: Any) -> bool:
        return _booleen(valeur, champ="reseau_executants")


class InfosPoste(_Contrat):
    """Le poste lui-même, sans nom réseau ni chemin (cahier P5 § 11.1)."""

    nom: str
    compte: str
    windows: str
    python: str
    politique_empreinte: str
    hermes_meme_enveloppe_que_codex: bool

    @field_validator("nom", mode="before")
    @classmethod
    def _nom(cls, valeur: Any) -> str:
        return _texte(valeur, champ="nom", maximum=60, motif=_NOM_POSTE)

    @field_validator("compte", mode="before")
    @classmethod
    def _compte(cls, valeur: Any) -> str:
        return _choix(valeur, champ="compte", admis=("dedie", "proprietaire"))

    @field_validator("windows", mode="before")
    @classmethod
    def _windows(cls, valeur: Any) -> str:
        return _texte(valeur, champ="windows", maximum=20, motif=_WINDOWS)

    @field_validator("python", mode="before")
    @classmethod
    def _python(cls, valeur: Any) -> str:
        return _texte(valeur, champ="python", maximum=64, motif=_VERSION)

    @field_validator("politique_empreinte", mode="before")
    @classmethod
    def _empreinte(cls, valeur: Any) -> str:
        return _texte(valeur, champ="politique_empreinte", maximum=12, motif=_EMPREINTE_POLITIQUE)

    @field_validator("hermes_meme_enveloppe_que_codex", mode="before")
    @classmethod
    def _enveloppe(cls, valeur: Any) -> bool:
        return _booleen(valeur, champ="hermes_meme_enveloppe_que_codex")


class InventairePoste(_Contrat):
    """Corps de ``POST /machine/v1/inventaire`` (protocole ``acp-machine/1``) : le contrat D21 étendu, validé
    par le poste avant l'envoi et par le greffon à la réception. Chaque relevé est ``source: "poste"``, porte
    ``quotas: null`` (le greffon le calcule) et recopie les dépôts de la racine."""

    protocole: str
    version_poste: str
    releve_le: datetime
    poste: InfosPoste
    depots: List[Depot]
    releves: List[Releve]
    bac_a_sable_codex: BacASableCodex
    connexions: Connexions
    versions: Dict[Literal["codex", "claude"], VersionCli]
    politique: PolitiquePoste

    @field_validator("protocole", mode="before")
    @classmethod
    def _protocole(cls, valeur: Any) -> str:
        return _choix(valeur, champ="protocole", admis=(PROTOCOLE,))

    @field_validator("version_poste", mode="before")
    @classmethod
    def _version(cls, valeur: Any) -> str:
        return _texte(valeur, champ="version_poste", maximum=64, motif=_VERSION)

    @field_validator("releve_le", mode="before")
    @classmethod
    def _releve_le(cls, valeur: Any) -> datetime:
        return _instant(valeur, champ="releve_le")

    @field_validator("depots", mode="before")
    @classmethod
    def _depots(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list):
            raise ValueError("« depots » doit être une liste")
        if len(valeur) > DEPOTS_MAX:
            raise ValueError(f"« depots » : au plus {DEPOTS_MAX} dépôts")
        return valeur

    @field_validator("releves", mode="before")
    @classmethod
    def _releves(cls, valeur: Any) -> Any:
        if not isinstance(valeur, list) or not 1 <= len(valeur) <= 2:
            raise ValueError("« releves » doit compter un ou deux relevés (une voie chacun)")
        return valeur

    @field_validator("versions", mode="before")
    @classmethod
    def _versions(cls, valeur: Any) -> Any:
        if not isinstance(valeur, Mapping):
            raise ValueError("« versions » doit être un objet")
        inconnues = sorted(str(k) for k in valeur if k not in ("codex", "claude"))
        if inconnues:
            raise ValueError("« versions » : clé inconnue refusée : " + ", ".join(inconnues))
        return valeur

    @model_validator(mode="after")
    def _coherence(self) -> "InventairePoste":
        alias = [d.alias for d in self.depots]
        if len(set(alias)) != len(alias):
            raise ValueError("« depots » : alias en double")
        voies = [r.voie for r in self.releves]
        if len(set(voies)) != len(voies):
            raise ValueError("« releves » : une seule entrée par voie")
        for releve in self.releves:
            if releve.source != "poste":
                raise ValueError(f"« releves » : le poste ne publie que des relevés « poste » ({releve.voie})")
            if releve.quotas is not None:
                raise ValueError(f"« quotas » ({releve.voie}) : résumé calculé par le greffon depuis « compteurs » ; "
                                 "le poste l'envoie à null")
            if [d.alias for d in releve.depots] != alias:
                raise ValueError(f"« depots » ({releve.voie}) : chaque relevé recopie les dépôts de l'inventaire")
        return self


def valider_inventaire(donnees: Any) -> InventairePoste:
    """Inventaire validé, ou ``ValueError`` au message français (« Inventaire refusé : … »)."""
    try:
        return InventairePoste.model_validate(donnees)
    except ValidationError as exc:
        details = "; ".join(_message(e) for e in exc.errors()[:5])
        raise ValueError(f"Inventaire refusé : {details}.") from None


# ============================================================ garde « aucun identifiant » (§ 11.3)

_LECTEUR = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC = re.compile(r"(?:^|\s)\\\\[^\\\s]")
_PROFIL = re.compile(r"[\\/]users[\\/]", re.IGNORECASE)


def _raison_valeur(texte: str, valeurs_exactes) -> Optional[str]:
    nom = motif_trouve(texte)
    if nom is not None:
        return f"ce qui ressemble à un secret ({nom})"
    if "acpm_" in texte or "acpe_" in texte:
        return "jeton machine ou code d'enrôlement d'ACP"
    if "@" in texte:
        return "adresse électronique (« @ »)"
    if _LECTEUR.search(texte):
        return "chemin de lecteur"
    if _UNC.search(texte):
        return "chemin réseau (UNC)"
    if _PROFIL.search(texte):
        return "chemin de profil utilisateur"
    for valeur in valeurs_exactes:
        if valeur and valeur in texte:
            return "valeur du coffre du poste"
    return None


def identifiant_trouve(objet: Any, *, valeurs_exactes=(), _chemin: str = "") -> Optional[str]:
    """Garde « aucun identifiant » (cahier P5 § 11.3), appliquée par le poste AVANT l'envoi et par le greffon à
    la réception (422) : chaque valeur de chaîne DÉCODÉE (et chaque clé) est examinée — jamais le texte JSON, où
    « \\ » est doublé. Rend « <chemin> : <raison> » pour la première trouvée, ou ``None``. ``valeurs_exactes`` :
    valeurs du coffre du poste (jeton machine, jeton Claude), jamais transmises au greffon."""
    if isinstance(objet, str):
        raison = _raison_valeur(objet, valeurs_exactes)
        return f"{_chemin or 'valeur'} : {raison}" if raison else None
    if isinstance(objet, Mapping):
        for cle, valeur in objet.items():
            chemin = f"{_chemin}.{cle}" if _chemin else str(cle)
            raison_cle = _raison_valeur(cle, valeurs_exactes) if isinstance(cle, str) else None
            if raison_cle:
                return f"{chemin} : clé refusée ({raison_cle})"
            trouve = identifiant_trouve(valeur, valeurs_exactes=valeurs_exactes, _chemin=chemin)
            if trouve:
                return trouve
        return None
    if isinstance(objet, (list, tuple)):
        for i, valeur in enumerate(objet):
            trouve = identifiant_trouve(valeur, valeurs_exactes=valeurs_exactes, _chemin=f"{_chemin}[{i}]")
            if trouve:
                return trouve
    return None
