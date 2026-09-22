"""Contrats publics de l'authentification propriétaire."""

from datetime import datetime

from pydantic import Field, SecretStr, field_validator

from .limits import DatabaseModel as BaseModel


class AuthStatusResponse(BaseModel):
    bootstrap_required: bool


class OwnerBootstrapRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    display_name: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=12, max_length=256)

    @field_validator("login")
    @classmethod
    def strip_login(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError("L'identifiant ne peut pas contenir d'espace")
        return value

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom ne peut pas être vide")
        return value


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("login")
    @classmethod
    def strip_login(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("L'identifiant ne peut pas être vide")
        return value


class AuthenticatedUser(BaseModel):
    id: str
    login: str
    display_name: str
    role: str


class AuthSessionResponse(BaseModel):
    user: AuthenticatedUser
    csrf_token: str
    expires_at: datetime


class LogoutResponse(BaseModel):
    status: str = "signed_out"
