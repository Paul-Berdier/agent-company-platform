"""Contrat borné du contrôle propriétaire des comptes sur un exécutant distant."""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOLE = "acp-comptes/1"
ROUTE_MACHINE = "/api/plugins/acp-poste/machine/v1/comptes"
URL_CODEX = "https://auth.openai.com/codex/device"
TERMINAUX = frozenset({"connecte", "annulee", "expiree", "interrompue", "erreur"})
ETATS = Literal["en_attente", "demarrage", "code_disponible", "verification", "connecte", "annulation_demandee", "annulee", "expiree", "interrompue", "erreur"]
MOTIFS = Literal["attente", "demarrage", "code", "verification", "connecte", "annulation", "annulee", "expiree", "interrompue", "indisponible", "occupe", "refuse", "incompatible"]


def identifiant(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Identifiant UUID canonique requis.")
    return value


class Contrat(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Observation(Contrat):
    operation_id: str
    numero: int = Field(ge=1, le=10000)
    etat: Literal["demarrage", "code_disponible", "verification", "connecte", "annulee", "expiree", "interrompue", "erreur"]
    motif: MOTIFS
    compte_connecte: bool | None = None
    verification_url: str | None = None
    code_utilisateur: str | None = None

    @field_validator("operation_id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value)

    @model_validator(mode="after")
    def verifier(self):
        if self.etat == "code_disponible":
            if self.verification_url != URL_CODEX or not isinstance(self.code_utilisateur, str) or not re.fullmatch(r"[A-Z0-9-]{4,32}", self.code_utilisateur):
                raise ValueError("Défi officiel Codex invalide.")
        elif self.verification_url is not None or self.code_utilisateur is not None:
            raise ValueError("Défi hors de son état d’attente.")
        motifs = {"demarrage": {"demarrage"}, "code_disponible": {"code"}, "verification": {"verification"},
                  "connecte": {"connecte"}, "annulee": {"annulee"}, "expiree": {"expiree"},
                  "interrompue": {"interrompue"}, "erreur": {"indisponible", "occupe", "refuse", "incompatible"}}
        if self.motif not in motifs[self.etat]:
            raise ValueError("Motif incohérent avec l’état de connexion.")
        if self.compte_connecte is True and self.etat != "connecte":
            raise ValueError("Compte connecté hors de son état confirmé.")
        if self.etat == "connecte" and self.compte_connecte is not True:
            raise ValueError("Compte ChatGPT non confirmé.")
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
    action: Literal["demarrer", "reconcilier", "annuler", "attendre"]
    limite_attente_le: int

    @field_validator("id")
    @classmethod
    def uuid(cls, value):
        return identifiant(value)


class Reponse(Contrat):
    protocole: Literal["acp-comptes/1"] = PROTOCOLE
    operation: Commande | None = None
