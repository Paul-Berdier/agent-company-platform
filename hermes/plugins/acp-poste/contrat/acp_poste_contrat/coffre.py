"""Contrat du bridge de coffre Markdown ACP, distinct du poste d’exécution."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOLE = "acp-coffre/1"
PREFIXE_ROUTES = "/api/plugins/acp-poste/coffre/v1"
ROUTE_ENROLEMENT = PREFIXE_ROUTES + "/enrolement"
ROUTE_RECLAMER = PREFIXE_ROUTES + "/reclamer"
ROUTE_RESULTAT = PREFIXE_ROUTES + "/resultat"
ROUTES = (ROUTE_ENROLEMENT, ROUTE_RECLAMER, ROUTE_RESULTAT)
TAILLE_MAX_CORPS = 192 * 1024
TAILLE_MAX_NOTE = 128 * 1024
ACTIONS = ("lister", "lire", "rechercher", "creer", "ecrire", "archiver", "renommer", "backlinks", "graphe")
CODE_ENROLEMENT = re.compile(r"^acpce_[A-Za-z0-9_-]{43}$")
JETON_COFFRE = re.compile(r"^acpct_[A-Za-z0-9_-]{43}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_RESERVE = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


def identifiant(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ValueError("identifiant UUID attendu")
    return str(UUID(valeur))


def chemin_relatif(valeur: Any, *, note: bool = True, vide: bool = False) -> str:
    if vide and valeur == "":
        return ""
    if not isinstance(valeur, str) or not 1 <= len(valeur) <= 240 or unicodedata.normalize("NFC", valeur) != valeur:
        raise ValueError("chemin relatif canonique de 1 à 240 caractères attendu")
    if any(c in valeur for c in "\\:*?\"<>|\x00") or any(ord(c) < 32 or ord(c) == 127 for c in valeur):
        raise ValueError("chemin contenant un caractère refusé")
    if any(not p or p.startswith(".") or p.endswith((".", " ")) or _RESERVE.match(p) for p in valeur.split("/")):
        raise ValueError("chemin absolu, caché, réservé ou traversant refusé")
    if note and not valeur.lower().endswith(".md"):
        raise ValueError("seules les notes Markdown .md sont admises")
    return valeur


def borner_json(valeur: Any) -> None:
    def profondeur(v, n=0):
        if n > 16:
            raise ValueError("JSON trop imbriqué")
        if isinstance(v, dict):
            if len(v) > 32:
                raise ValueError("objet trop large")
            for x in v.values():
                profondeur(x, n + 1)
        elif isinstance(v, list):
            if len(v) > 2000:
                raise ValueError("liste trop longue")
            for x in v:
                profondeur(x, n + 1)
    profondeur(valeur)
    if len(json.dumps(valeur, ensure_ascii=False, allow_nan=False).encode("utf-8")) > TAILLE_MAX_CORPS:
        raise ValueError("corps JSON supérieur à 192 Kio")


def parametres_valides(action: str, p: Any) -> dict[str, Any]:
    schemas = {
        "lister": (set(), {"prefixe", "limite"}), "lire": ({"chemin"}, set()),
        "rechercher": ({"texte"}, {"limite"}), "creer": ({"chemin", "contenu"}, set()),
        "ecrire": ({"chemin", "contenu", "empreinte_attendue"}, set()),
        "archiver": ({"chemin", "empreinte_attendue"}, set()),
        "renommer": ({"chemin", "destination", "empreinte_attendue"}, set()),
        "backlinks": ({"chemin"}, {"limite"}), "graphe": (set(), {"limite"}),
    }
    if action not in schemas or not isinstance(p, dict):
        raise ValueError("action ou paramètres inconnus")
    requis, facultatifs = schemas[action]
    if not requis <= set(p) or set(p) - requis - facultatifs:
        raise ValueError("paramètres absents ou inconnus")
    for cle in ("chemin", "destination"):
        if cle in p:
            chemin_relatif(p[cle])
    if "prefixe" in p:
        chemin_relatif(p["prefixe"], note=False, vide=True)
    if "empreinte_attendue" in p and (not isinstance(p["empreinte_attendue"], str) or not _SHA.fullmatch(p["empreinte_attendue"])):
        raise ValueError("empreinte SHA-256 attendue")
    if "contenu" in p:
        t = p["contenu"]
        if (not isinstance(t, str) or len(t.encode("utf-8")) > TAILLE_MAX_NOTE
                or any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in t)):
            raise ValueError("note UTF-8 de 128 Kio maximum, sans caractères de contrôle")
    if "texte" in p and (not isinstance(p["texte"], str) or not 1 <= len(p["texte"].strip()) <= 200):
        raise ValueError("recherche de 1 à 200 caractères attendue")
    maximum = {"lister": 200, "rechercher": 100, "backlinks": 500, "graphe": 500}.get(action)
    if "limite" in p and (type(p["limite"]) is not int or not 1 <= p["limite"] <= maximum):
        raise ValueError("limite de résultats refusée")
    if action == "renommer" and p["chemin"].casefold() == p["destination"].casefold():
        raise ValueError("destination identique au chemin source")
    borner_json(p)
    return p


class Contrat(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Enrolement(Contrat):
    protocole: Literal["acp-coffre/1"]
    version_bridge: str = Field(min_length=1, max_length=40, pattern=r"^[0-9][0-9A-Za-z.+-]*$")
    coffre_id: str
    alias: Literal["acp"]
    _id = field_validator("coffre_id")(identifiant)


class ReponseEnrolement(Contrat):
    protocole: Literal["acp-coffre/1"]
    coffre_id: str
    jeton: str = Field(pattern=JETON_COFFRE.pattern)
    empreinte: str = Field(pattern=r"^[0-9A-F]{4}-[0-9A-F]{4}$")
    etat: Literal["a_confirmer"]
    _id = field_validator("coffre_id")(identifiant)


class RequeteReclamer(Contrat):
    protocole: Literal["acp-coffre/1"]
    coffre_id: str
    capacites: list[str] = Field(max_length=9)
    attente_max_s: int = Field(default=0, ge=0, le=25)
    _id = field_validator("coffre_id")(identifiant)

    @field_validator("capacites")
    @classmethod
    def _capacites(cls, v):
        if len(set(v)) != len(v) or not set(v) <= set(ACTIONS):
            raise ValueError("capacités inconnues ou dupliquées")
        return v


class DemandeOperation(Contrat):
    id_operation: str
    coffre_id: str
    action: str
    parametres: dict[str, Any]
    _ids = field_validator("id_operation", "coffre_id")(identifiant)

    @model_validator(mode="after")
    def _coherence(self):
        parametres_valides(self.action, self.parametres)
        borner_json(self.model_dump())
        return self


class Operation(DemandeOperation):
    expire_le: int = Field(ge=0)


class ReponseReclamer(Contrat):
    protocole: Literal["acp-coffre/1"]
    etat: Literal["a_confirmer", "actif"]
    operation: Operation | None = None


class Erreur(Contrat):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1, max_length=500)


class Resultat(Contrat):
    protocole: Literal["acp-coffre/1"]
    coffre_id: str
    id_operation: str
    etat: Literal["reussie", "refusee", "indeterminee"]
    resultat: dict[str, Any] | None = None
    erreur: Erreur | None = None
    _ids = field_validator("id_operation", "coffre_id")(identifiant)

    @model_validator(mode="after")
    def _coherence(self):
        if (self.etat == "reussie") != (self.resultat is not None) or (self.etat != "reussie") != (self.erreur is not None):
            raise ValueError("résultat et erreur incohérents avec l’état")
        borner_json(self.model_dump())
        return self


class ReponseResultat(Contrat):
    ok: Literal[True]
    id_operation: str
    deja: bool
    _id = field_validator("id_operation")(identifiant)


def resultat_valide(action: str, r: Any) -> None:
    """Valide les projections du bridge ; aucune donnée HTML ni chemin exécutable n’est interprété."""
    if not isinstance(r, dict):
        raise ValueError("résultat objet attendu")
    requis = {"lister": {"notes", "tronque"}, "lire": {"chemin", "contenu", "empreinte", "octets"},
              "rechercher": {"resultats", "tronque"}, "graphe": {"noeuds", "liens", "non_resolus", "tronque", "portee"},
              "backlinks": {"chemin", "liens", "tronque"}, "creer": {"chemin", "empreinte"},
              "ecrire": {"chemin", "empreinte"}, "archiver": {"chemin", "archive_id"},
              "renommer": {"chemin", "destination", "liens_modifies"}}
    facultatifs = {"creer": {"octets"}, "ecrire": {"octets", "archive_id"}, "archiver": {"empreinte"},
                   "renommer": {"empreinte"}}
    if action not in requis or not requis[action] <= set(r) or set(r) - requis[action] - facultatifs.get(action, set()):
        raise ValueError("champs du résultat inconnus ou absents")
    for cle in ("chemin", "destination"):
        if cle in r:
            chemin_relatif(r[cle])
    if "empreinte" in r and (not isinstance(r["empreinte"], str) or not _SHA.fullmatch(r["empreinte"])):
        raise ValueError("empreinte de résultat invalide")
    if "octets" in r and (type(r["octets"]) is not int or not 0 <= r["octets"] <= TAILLE_MAX_NOTE):
        raise ValueError("taille de note invalide")
    if "tronque" in r and type(r["tronque"]) is not bool:
        raise ValueError("indicateur de borne invalide")
    if action == "lire":
        import hashlib
        parametres_valides("creer", {"chemin": r["chemin"], "contenu": r["contenu"]})
        octets = r["contenu"].encode("utf-8")
        if len(octets) != r["octets"] or hashlib.sha256(octets).hexdigest() != r["empreinte"]:
            raise ValueError("contenu, taille et empreinte de lecture incohérents")
    if action == "renommer" and r["liens_modifies"] is not False:
        raise ValueError("réécriture de liens non prise en charge")
    if "archive_id" in r and (not isinstance(r["archive_id"], str) or not 1 <= len(r["archive_id"]) <= 100):
        raise ValueError("identifiant d’archive invalide")
    for cle, limite in (("notes", 200), ("resultats", 100), ("noeuds", 500), ("liens", 2000), ("non_resolus", 2000)):
        if cle not in r:
            continue
        elements = r[cle]
        if not isinstance(elements, list) or len(elements) > limite:
            raise ValueError("liste de résultats hors borne")
        for e in elements:
            if not isinstance(e, dict):
                raise ValueError("entrée de résultat invalide")
            if cle in ("notes", "noeuds", "resultats"):
                attendues = {"notes": {"chemin", "octets"}, "noeuds": {"chemin"}, "resultats": {"chemin", "ligne", "extrait"}}[cle]
                if set(e) != attendues:
                    raise ValueError("entrée de résultat hors schéma")
                chemin_relatif(e["chemin"])
                if cle == "notes" and (type(e["octets"]) is not int or not 0 <= e["octets"] <= TAILLE_MAX_NOTE):
                    raise ValueError("taille de note invalide")
                if cle == "resultats" and (type(e["ligne"]) is not int or e["ligne"] < 1 or not isinstance(e["extrait"], str)
                                            or len(e["extrait"]) > 500):
                    raise ValueError("extrait de recherche invalide")
            else:
                if set(e) != {"source", "cible"}:
                    raise ValueError("lien hors schéma")
                chemin_relatif(e["source"])
                if cle == "non_resolus":
                    if not isinstance(e["cible"], str) or not 1 <= len(e["cible"]) <= 500:
                        raise ValueError("cible non résolue invalide")
                else:
                    chemin_relatif(e["cible"])
    if action == "graphe" and r["portee"] != "Liens Markdown et wikiliens ; extensions Obsidian non interprétées.":
        raise ValueError("portée du graphe inconnue")
    borner_json(r)
