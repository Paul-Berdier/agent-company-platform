"""Contrat borné du contrôle propriétaire des comptes sur un exécutant distant."""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOLE = "acp-comptes/2"
ROUTE_MACHINE = "/api/plugins/acp-poste/machine/v1/comptes"
URL_CODEX = "https://auth.openai.com/codex/device"
URL_CLAUDE = "https://claude.com/cai/oauth/authorize"
URL_MAX = 8192
CODE_MAX = 2048
MOTEURS = Literal["codex", "claude_code"]
TERMINAUX = frozenset({"connecte", "annulee", "expiree", "interrompue", "erreur"})
ETATS = Literal["en_attente", "demarrage", "code_disponible", "verification", "connecte", "annulation_demandee", "annulee", "expiree", "interrompue", "erreur"]
MOTIFS = Literal["attente", "demarrage", "code", "verification", "connecte", "annulation", "annulee", "expiree", "interrompue", "indisponible", "occupe", "refuse", "incompatible"]


def identifiant(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Identifiant UUID canonique requis.")
    return value


def code_retour_valide(value: str) -> bool:
    """Code opaque transmis tel quel, jamais normalisé ou interprété comme un jeton."""
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 or c in "\u0085\u2028\u2029" for c in value):
        return False
    try:
        return 1 <= len(value.encode("utf-8")) <= CODE_MAX
    except UnicodeError:
        return False


def url_claude_valide(value: str) -> bool:
    # Cette route littérale doit rester confirmée par le témoin du CLI épinglé.
    if not isinstance(value, str) or len(value) > URL_MAX or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.netloc == "claude.com" and url.path == "/cai/oauth/authorize"
                and bool(url.query) and not url.fragment and "#" not in value and url.username is None and url.password is None)
    except ValueError:
        return False


class Contrat(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AccuseCode(Contrat):
    defi_id: str
    soumission_id: str

    @field_validator("defi_id", "soumission_id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value)


class RetourCode(AccuseCode):
    code: str = Field(repr=False)

    @field_validator("code")
    @classmethod
    def verifier_code(cls, value):
        if not code_retour_valide(value):
            raise ValueError("Code de retour invalide ou hors limites.")
        return value


class Observation(Contrat):
    operation_id: str
    moteur: MOTEURS
    numero: int = Field(ge=1, le=10000)
    etat: Literal["demarrage", "code_disponible", "verification", "connecte", "annulee", "expiree", "interrompue", "erreur"]
    motif: MOTIFS
    compte_connecte: bool | None = None
    defi_id: str | None = None
    defi_type: Literal["codex_device", "claude_oauth_code"] | None = None
    verification_url: str | None = Field(default=None, max_length=URL_MAX, repr=False)
    code_utilisateur: str | None = Field(default=None, repr=False)
    code_transmis: AccuseCode | None = None

    @field_validator("operation_id", "defi_id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value) if value is not None else value

    @model_validator(mode="after")
    def verifier(self):
        if self.etat == "code_disponible":
            if self.defi_id is None:
                raise ValueError("Identité du défi requise.")
            if self.moteur == "codex":
                if (self.defi_type != "codex_device" or self.verification_url != URL_CODEX
                        or not isinstance(self.code_utilisateur, str)
                        or not re.fullmatch(r"[A-Z0-9-]{4,32}", self.code_utilisateur)):
                    raise ValueError("Défi officiel Codex invalide.")
            elif (self.defi_type != "claude_oauth_code" or not url_claude_valide(self.verification_url)
                  or self.code_utilisateur is not None):
                raise ValueError("Défi officiel Claude invalide.")
        elif any(v is not None for v in (self.defi_id, self.defi_type, self.verification_url, self.code_utilisateur)):
            raise ValueError("Défi hors de son état d’attente.")
        if self.code_transmis is not None and self.moteur != "claude_code":
            raise ValueError("Accusé de code réservé à Claude.")
        motifs = {"demarrage": {"demarrage"}, "code_disponible": {"code"}, "verification": {"verification"},
                  "connecte": {"connecte"}, "annulee": {"annulee"}, "expiree": {"expiree"},
                  "interrompue": {"interrompue"}, "erreur": {"indisponible", "occupe", "refuse", "incompatible"}}
        if self.motif not in motifs[self.etat]:
            raise ValueError("Motif incohérent avec l’état de connexion.")
        # L’annulation d’une reconnexion n’efface pas nécessairement l’ancien compte.
        if self.etat == "connecte" and self.compte_connecte is not True:
            raise ValueError("Compte fournisseur non confirmé.")
        return self


class Echange(Contrat):
    instance_id: str
    libre: bool
    observation: Observation | None = None

    @field_validator("instance_id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value)


class Commande(Contrat):
    id: str
    moteur: MOTEURS
    action: Literal["demarrer", "reconcilier", "annuler", "attendre", "fournir_code"]
    limite_attente_le: int
    retour_code: RetourCode | None = Field(default=None, repr=False)

    @field_validator("id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value)

    @model_validator(mode="after")
    def verifier(self):
        if self.action == "fournir_code":
            if self.moteur != "claude_code" or self.retour_code is None:
                raise ValueError("Code de retour Claude requis.")
        elif self.retour_code is not None:
            raise ValueError("Code de retour hors de sa commande.")
        return self


class Reponse(Contrat):
    protocole: Literal["acp-comptes/2"] = PROTOCOLE
    operation: Commande | None = None
