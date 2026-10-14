"""Identité et file du coffre ACP : aucun accès aux fichiers depuis Hermes."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from typing import Any

from . import base, contrat_partage
from .textes import refus
from .motifs_secrets import motif_trouve
from acp_poste_contrat import coffre as C

VALIDITE_CODE = 600
VALIDITE_OPERATION = 600
PRESENCE_MAX = 75
MAX_EN_ATTENTE = 32

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS coffres_codes (empreinte TEXT PRIMARY KEY, cree_le INTEGER NOT NULL, "
    "expire_le INTEGER NOT NULL, auteur TEXT NOT NULL, utilise_le INTEGER)",
    "CREATE TABLE IF NOT EXISTS coffres_identites (id TEXT PRIMARY KEY, alias TEXT NOT NULL, empreinte_jeton TEXT NOT NULL UNIQUE, "
    "etat TEXT NOT NULL CHECK(etat IN ('a_confirmer','actif','revoque')), version_bridge TEXT NOT NULL, cree_le INTEGER NOT NULL, "
    "derniere_vue INTEGER, capacites TEXT NOT NULL DEFAULT '[]', revoque_le INTEGER)",
    "CREATE UNIQUE INDEX IF NOT EXISTS un_seul_coffre_actif ON coffres_identites(alias) WHERE etat='actif'",
    "CREATE TABLE IF NOT EXISTS coffres_operations (id TEXT PRIMARY KEY, coffre_id TEXT NOT NULL REFERENCES coffres_identites(id), "
    "action TEXT NOT NULL, empreinte_demande TEXT NOT NULL, parametres TEXT, etat TEXT NOT NULL, auteur TEXT NOT NULL, "
    "cree_le INTEGER NOT NULL, expire_le INTEGER NOT NULL, livree_le INTEGER, resultat TEXT, empreinte_resultat TEXT)",
)


def initialiser(conn):
    for instruction in _SCHEMA:
        conn.execute(instruction)


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _empreinte_affichee(e):
    return (e[:4] + "-" + e[4:8]).upper()


def _nettoyer(conn):
    now = base.maintenant()
    conn.execute("UPDATE coffres_operations SET etat=CASE WHEN livree_le IS NULL THEN 'expiree' ELSE 'indeterminee' END, "
                 "parametres=NULL WHERE expire_le<=? AND etat IN ('en_attente','en_cours')", (now,))
    # Les textes ne restent pas indéfiniment dans la file de transport.
    conn.execute("UPDATE coffres_operations SET parametres=NULL,resultat=NULL,etat='expiree' WHERE expire_le<?", (now - 3600,))
    conn.execute("DELETE FROM coffres_operations WHERE expire_le<?", (now - 86400,))
    conn.execute("DELETE FROM coffres_codes WHERE expire_le<?", (now - 86400,))


def _identite(conn, identifiant):
    return base.ligne_en_dict(conn.execute("SELECT * FROM coffres_identites WHERE id=?", (identifiant,)).fetchone())


def exiger(conn, identifiant, *, actif=False, empreinte_auth=None):
    ligne = _identite(conn, identifiant)
    if ligne is None or ligne["etat"] == "revoque":
        raise refus("coffre_revoque", "Ce bridge de coffre est inconnu ou révoqué ; aucun échange n’est autorisé.")
    if empreinte_auth is not None and not hmac.compare_digest(ligne["empreinte_jeton"], empreinte_auth):
        raise refus("coffre_revoque", "Cette identité du bridge a été remplacée ; aucun échange n’est autorisé.")
    if actif and ligne["etat"] != "actif":
        raise refus("coffre_a_confirmer", "Comparez puis confirmez l’empreinte du bridge de coffre.")
    return ligne


def etat(conn):
    initialiser(conn)
    _nettoyer(conn)
    ligne = base.ligne_en_dict(conn.execute("SELECT * FROM coffres_identites ORDER BY CASE etat WHEN 'actif' THEN 0 "
                                           "WHEN 'a_confirmer' THEN 1 ELSE 2 END, cree_le DESC, rowid DESC LIMIT 1").fetchone())
    if ligne is None:
        return {"protocole": C.PROTOCOLE, "etat": "non_configure", "coffre": None}
    statut = ligne["etat"]
    if statut == "actif":
        statut = "pret" if ligne["derniere_vue"] is not None and base.maintenant() - ligne["derniere_vue"] <= PRESENCE_MAX else "hors_ligne"
    return {"protocole": C.PROTOCOLE, "etat": statut, "coffre": {
        "coffre_id": ligne["id"], "alias": ligne["alias"], "empreinte": _empreinte_affichee(ligne["empreinte_jeton"]),
        "etat": ligne["etat"], "derniere_vue": ligne["derniere_vue"], "capacites": json.loads(ligne["capacites"])}}


def creer_code(conn, auteur):
    initialiser(conn)
    code, maintenant = "acpce_" + secrets.token_urlsafe(32), base.maintenant()
    with base.transaction(conn):
        if conn.execute("SELECT 1 FROM coffres_identites WHERE etat='actif'").fetchone():
            raise refus("coffre_deja_enrole", "Un coffre ACP est déjà actif ; révoquez-le avant d’en associer un autre.")
        conn.execute("UPDATE coffres_codes SET utilise_le=? WHERE utilise_le IS NULL", (maintenant,))
        conn.execute("INSERT INTO coffres_codes VALUES (?,?,?,?,NULL)", (empreinte(code), maintenant, maintenant + VALIDITE_CODE, auteur))
        base.journaliser(conn, auteur, "coffre_code_cree")
    return {"code": code, "expire_le": maintenant + VALIDITE_CODE, "validite_s": VALIDITE_CODE, "protocole": C.PROTOCOLE}


def enroler(conn, empreinte_code, demande: C.Enrolement):
    initialiser(conn)
    now, jeton = base.maintenant(), "acpct_" + secrets.token_urlsafe(32)
    with base.transaction(conn):
        code = conn.execute("SELECT * FROM coffres_codes WHERE empreinte=? AND utilise_le IS NULL AND expire_le>?",
                             (empreinte_code, now)).fetchone()
        if code is None:
            raise refus("code_refuse", "Code du coffre expiré, inconnu ou déjà utilisé.")
        if conn.execute("SELECT 1 FROM coffres_identites WHERE etat='actif'").fetchone():
            raise refus("coffre_deja_enrole", "Un coffre ACP est déjà actif.")
        conn.execute("UPDATE coffres_identites SET etat='revoque',revoque_le=? WHERE etat='a_confirmer'", (now,))
        conn.execute("INSERT INTO coffres_identites (id,alias,empreinte_jeton,etat,version_bridge,cree_le) "
                     "VALUES (?,?,?,'a_confirmer',?,?) ON CONFLICT(id) DO UPDATE SET "
                     "empreinte_jeton=excluded.empreinte_jeton,etat='a_confirmer',version_bridge=excluded.version_bridge,"
                     "cree_le=excluded.cree_le,derniere_vue=NULL,capacites='[]',revoque_le=NULL",
                     (demande.coffre_id, demande.alias, empreinte(jeton), demande.version_bridge, now))
        conn.execute("UPDATE coffres_codes SET utilise_le=? WHERE empreinte=?", (now, empreinte_code))
        base.journaliser(conn, "coffre:enrolement", "coffre_enrole", cible=demande.coffre_id)
    return {"protocole": C.PROTOCOLE, "coffre_id": demande.coffre_id, "jeton": jeton,
            "empreinte": _empreinte_affichee(empreinte(jeton)), "etat": "a_confirmer"}


def confirmer(conn, coffre_id, saisie, auteur):
    initialiser(conn)
    if not isinstance(saisie, str) or not hmac.compare_digest(saisie.replace("-", "").upper(),
                                                            _empreinte_affichee(exiger(conn, coffre_id)["empreinte_jeton"]).replace("-", "")):
        raise refus("empreinte_differente", "L’empreinte saisie diffère de celle du bridge ; rien n’est confirmé.")
    with base.transaction(conn):
        ligne = exiger(conn, coffre_id)
        if ligne["etat"] != "a_confirmer":
            raise refus("coffre_pas_a_confirmer", "Ce coffre n’attend pas de confirmation.")
        conn.execute("UPDATE coffres_identites SET etat='actif' WHERE id=?", (coffre_id,))
        base.journaliser(conn, auteur, "coffre_confirme", cible=coffre_id)
    return etat(conn)


def revoquer(conn, coffre_id, motif, auteur):
    initialiser(conn)
    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 200:
        raise refus("motif", "Le motif doit compter de 1 à 200 caractères.")
    with base.transaction(conn):
        exiger(conn, coffre_id)
        conn.execute("UPDATE coffres_identites SET etat='revoque',revoque_le=? WHERE id=?", (base.maintenant(), coffre_id))
        conn.execute("UPDATE coffres_operations SET etat=CASE WHEN livree_le IS NULL THEN 'refusee' ELSE 'indeterminee' END, "
                     "parametres=NULL WHERE coffre_id=? AND etat IN ('en_attente','en_cours')", (coffre_id,))
        base.journaliser(conn, auteur, "coffre_revoque", cible=coffre_id)
    return etat(conn)


def _projection(ligne):
    if ligne is None:
        raise refus("operation_inconnue", "Cette opération de coffre n’existe pas ou son délai de conservation est dépassé.")
    r = json.loads(ligne["resultat"]) if ligne["resultat"] else {}
    erreur = r.get("erreur")
    if not erreur and ligne["etat"] in ("expiree", "indeterminee", "refusee"):
        erreur = {"code": ligne["etat"], "message": "Opération non confirmée ; relisez la note avant une nouvelle modification."}
    return {"id_operation": ligne["id"], "coffre_id": ligne["coffre_id"], "action": ligne["action"],
            "etat": ligne["etat"], "cree_le": ligne["cree_le"], "expire_le": ligne["expire_le"],
            "resultat": r.get("resultat"), "erreur": erreur}


def operation(conn, identifiant):
    initialiser(conn)
    _nettoyer(conn)
    return _projection(conn.execute("SELECT * FROM coffres_operations WHERE id=?", (C.identifiant(identifiant),)).fetchone())


def creer_operation(conn, demande: C.DemandeOperation, auteur):
    initialiser(conn)
    corps, now = demande.model_dump(), base.maintenant()
    digest = empreinte(_json(corps))
    # Le transport des notes n’est pas un moyen de déposer des identifiants dans la base ou les journaux.
    if motif_trouve(_json(demande.parametres)):
        raise refus("secret", "La note contient ce qui ressemble à un secret ; retirez-le avant de l’envoyer.")
    with base.transaction(conn):
        _nettoyer(conn)
        ancien = conn.execute("SELECT * FROM coffres_operations WHERE id=?", (demande.id_operation,)).fetchone()
        if ancien:
            if ancien["empreinte_demande"] != digest:
                raise refus("idempotence", "Cet identifiant d’opération désigne déjà une autre demande.")
            return _projection(ancien)
        coffre = exiger(conn, demande.coffre_id, actif=True)
        if demande.action not in json.loads(coffre["capacites"]):
            raise refus("capacite_absente", "Le bridge n’a pas annoncé cette capacité ; vérifiez sa version et sa configuration.")
        if conn.execute("SELECT COUNT(*) FROM coffres_operations WHERE coffre_id=? AND etat IN ('en_attente','en_cours')",
                        (demande.coffre_id,)).fetchone()[0] >= MAX_EN_ATTENTE:
            raise refus("file_pleine", "La file du coffre contient déjà 32 opérations ; attendez leur résultat.")
        conn.execute("INSERT INTO coffres_operations (id,coffre_id,action,empreinte_demande,parametres,etat,auteur,cree_le,expire_le) "
                     "VALUES (?,?,?,?,?,'en_attente',?,?,?)", (demande.id_operation, demande.coffre_id, demande.action,
                     digest, _json(demande.parametres), auteur, now, now + VALIDITE_OPERATION))
        base.journaliser(conn, auteur, "coffre_operation", cible=demande.id_operation, detail={"action": demande.action})
    return operation(conn, demande.id_operation)


def reclamer(conn, identifiant, demande: C.RequeteReclamer, empreinte_auth: str):
    initialiser(conn)
    if identifiant != demande.coffre_id:
        raise refus("coffre_interdit", "Ce jeton n’est pas celui du coffre demandé.")
    with base.transaction(conn):
        coffre = exiger(conn, identifiant, empreinte_auth=empreinte_auth)
        _nettoyer(conn)
        conn.execute("UPDATE coffres_identites SET derniere_vue=?,capacites=? WHERE id=?",
                     (base.maintenant(), _json(demande.capacites), identifiant))
        op = None
        if coffre["etat"] == "actif":
            ligne = conn.execute("SELECT * FROM coffres_operations WHERE coffre_id=? AND etat IN ('en_attente','en_cours') "
                                  "ORDER BY cree_le,rowid LIMIT 1", (identifiant,)).fetchone()
            if ligne and ligne["action"] in demande.capacites:
                conn.execute("UPDATE coffres_operations SET etat='en_cours',livree_le=COALESCE(livree_le,?) WHERE id=?",
                             (base.maintenant(), ligne["id"]))
                op = {"id_operation": ligne["id"], "coffre_id": identifiant, "action": ligne["action"],
                      "parametres": json.loads(ligne["parametres"]), "expire_le": ligne["expire_le"]}
    return {"protocole": C.PROTOCOLE, "etat": coffre["etat"], "operation": op}


def resultat(conn, identifiant, demande: C.Resultat, empreinte_auth: str):
    initialiser(conn)
    if identifiant != demande.coffre_id:
        raise refus("coffre_interdit", "Ce jeton n’est pas celui du coffre demandé.")
    corps = demande.model_dump()
    digest = empreinte(_json(corps))
    secret = motif_trouve(_json(corps.get("resultat"))) or motif_trouve(_json(corps.get("erreur")))
    if secret:
        # Le corps original n’est jamais conservé, mais sa réception clôt la file
        # avec un refus explicite ; son empreinte seule permet le même accusé au rejeu.
        corps.update(etat="refusee", resultat=None, erreur={"code": "secret",
            "message": "Le résultat contient ce qui ressemble à un secret ; son contenu n’a pas été conservé."})
    with base.transaction(conn):
        exiger(conn, identifiant, actif=True, empreinte_auth=empreinte_auth)
        _nettoyer(conn)
        ligne = conn.execute("SELECT * FROM coffres_operations WHERE id=? AND coffre_id=?",
                              (demande.id_operation, identifiant)).fetchone()
        if ligne is None or ligne["livree_le"] is None:
            raise refus("operation_inconnue", "Aucune opération livrée de ce coffre ne correspond au résultat.")
        if ligne["empreinte_resultat"]:
            if ligne["empreinte_resultat"] != digest:
                raise refus("idempotence", "Cette opération a déjà un résultat différent.")
            return {"ok": True, "id_operation": demande.id_operation, "deja": True}
        if corps["resultat"] is not None:
            C.resultat_valide(ligne["action"], corps["resultat"])
        conn.execute("UPDATE coffres_operations SET etat=?,resultat=?,empreinte_resultat=?,parametres=NULL WHERE id=?",
                     (corps["etat"], _json(corps), digest, demande.id_operation))
        base.journaliser(conn, "coffre:" + identifiant, "coffre_resultat", cible=demande.id_operation,
                         detail={"etat": corps["etat"]})
    return {"ok": True, "id_operation": demande.id_operation, "deja": False}
