"""Authentification du bridge du coffre : identité dédiée, jamais un poste d’exécution."""
from __future__ import annotations

import hmac
import sqlite3

from . import auth_adapter as aa, base, coffres
from acp_poste_contrat import coffre as C

NOM = "acp-coffre"


class FournisseurCoffre(aa.DashboardAuthProvider):
    name = NOM
    display_name = "Coffre ACP (bridge local)"
    supports_password = False
    supports_token = True
    supports_session = False

    def verify_token(self, *, token: str):
        if not isinstance(token, str):
            return None
        if C.CODE_ENROLEMENT.fullmatch(token):
            portee = "coffre_enrolement"
        elif C.JETON_COFFRE.fullmatch(token):
            portee = "coffre"
        else:
            return None
        chemin = base.chemin_base()
        if not chemin.is_file():
            return None
        try:
            with sqlite3.connect(chemin.as_uri() + "?mode=ro", uri=True, timeout=0.25) as conn:
                table = "coffres_codes" if portee == "coffre_enrolement" else "coffres_identites"
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    return None
                lignes = (conn.execute("SELECT empreinte,empreinte FROM coffres_codes WHERE utilise_le IS NULL AND expire_le>?",
                                       (base.maintenant(),)).fetchall() if portee == "coffre_enrolement" else
                          conn.execute("SELECT id,empreinte_jeton FROM coffres_identites").fetchall())
                calcule, identifiant = coffres.empreinte(token), None
                for cle, digest in lignes:
                    if hmac.compare_digest(digest, calcule):
                        identifiant = cle
                if identifiant is not None:
                    # La génération du jeton suit la requête jusqu’à la transaction du coffre.
                    principal = identifiant if portee == "coffre_enrolement" else identifiant + ":" + calcule
                    return aa.TokenPrincipal(principal="coffre:" + principal, provider=NOM, scopes=(portee,))
        except Exception as exc:
            raise aa.ProviderError("Base du coffre indisponible (" + type(exc).__name__ + ")") from None
        return None

    def start_login(self, *, redirect_uri):
        raise NotImplementedError("Le coffre n’offre aucune session interactive.")

    def complete_login(self, *, code, state, code_verifier, redirect_uri):
        raise NotImplementedError("Le coffre n’offre aucune session interactive.")

    def verify_session(self, *, access_token):
        return None

    def refresh_session(self, *, refresh_token):
        raise NotImplementedError("Le coffre n’offre aucune session interactive.")

    def revoke_session(self, *, refresh_token):
        return None

    def authenticate_password(self, **kwargs):
        raise aa.ProviderError("Le coffre n’offre aucune connexion par mot de passe.")


def enregistrer(ctx):
    ctx.register_dashboard_auth_provider(FournisseurCoffre())
    for chemin in C.ROUTES:
        aa.register_token_route(chemin)
