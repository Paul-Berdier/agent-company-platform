"""Postes enrôlés et codes d'enrôlement (étape P5, cahier P5 § 4.3, § 5 ; décisions D48 à D50).

- Le propriétaire crée un code à usage unique (``acpe_…``, 10 min) depuis la page Poste : :func:`creer_code`. Le
  code n'est rendu qu'UNE fois ; la base n'en garde que le SHA-256.
- Le poste le présente à ``/machine/v1/enrolement`` : :func:`enroler_dans` crée la machine ``a_confirmer`` et rend
  le jeton machine (``acpm_…``, 256 bits) UNE fois ; la base n'en garde que le SHA-256.
- Le propriétaire compare l'empreinte ``XXXX-XXXX`` affichée par le poste et confirme : :func:`confirmer`.
- :func:`revoquer` : ``revoque`` en base, présence supprimée (aucune notification « hors ligne » ensuite) ; la route
  réveille l'attente en cours, qui rend 401 ``poste_revoque``.

Un seul poste ``actif`` (index unique partiel ``un_seul_poste_actif``) ; un nouvel enrôlement révoque un poste
encore ``a_confirmer`` (réponse perdue, code volé non confirmé). Jamais le jeton ni le code dans la base, le journal
ou une réponse autre que celle qui les crée.
"""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Dict, Optional

from . import base, contrat_partage  # noqa: F401 — contrat_partage met le contrat sur sys.path
from . import textes as T
from .textes import RefusACP, refus

from acp_poste_contrat.machine import (  # noqa: E402
    PROTOCOLE,
    empreinte_courte,
    empreinte_courte_normalisee,
    empreinte_jeton,
)

ETATS = ("a_confirmer", "actif", "revoque")
CONSERVATION_CODES_S = 24 * 3600


def _date(epoch: Optional[int]) -> str:
    from .routage import date_lisible

    return date_lisible(epoch)


def nouveau_jeton() -> str:
    """Jeton machine : ``acpm_`` + 43 caractères base64url (32 octets d'aléa, sans remplissage)."""
    return "acpm_" + secrets.token_urlsafe(32)


def nouveau_code() -> str:
    """Code d'enrôlement : même forme et même force que le jeton, préfixe ``acpe_``."""
    return "acpe_" + secrets.token_urlsafe(32)


def nouvel_identifiant() -> str:
    """``m`` + 11 caractères hexadécimaux (le réclamant de P6 sera ``acp-poste:<machine>``)."""
    return "m" + secrets.token_hex(6)[:11]


def machine(conn, machine_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not machine_id:
        return None
    return base.ligne_en_dict(conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone())


def machine_active(conn) -> Optional[Dict[str, Any]]:
    return base.ligne_en_dict(conn.execute("SELECT * FROM machines WHERE etat = 'actif'").fetchone())


def machine_courante(conn) -> Optional[Dict[str, Any]]:
    """Le poste à montrer : l'actif, sinon le dernier à confirmer, sinon le dernier révoqué ; None si aucun."""
    ligne = conn.execute(
        "SELECT * FROM machines ORDER BY CASE etat WHEN 'actif' THEN 0 WHEN 'a_confirmer' THEN 1 ELSE 2 END, "
        "cree_le DESC, rowid DESC LIMIT 1").fetchone()
    return base.ligne_en_dict(ligne)


def empreinte_affichee(ligne: Dict[str, Any]) -> str:
    """``XXXX-XXXX`` tirée du SHA-256 stocké (32 bits d'un condensat : rien du jeton)."""
    return empreinte_courte(str(ligne["empreinte_jeton"]))


def purger_codes_dans(conn) -> int:
    """Codes utilisés ou expirés depuis plus de 24 h : supprimés (la comparaison de verify_token reste courte)."""
    limite = base.maintenant() - CONSERVATION_CODES_S
    return conn.execute("DELETE FROM enrolements WHERE (utilise_le IS NOT NULL AND utilise_le < ?) OR expire_le < ?",
                        (limite, limite)).rowcount


def creer_code(conn, auteur: str) -> Dict[str, Any]:
    """Code d'enrôlement à usage unique (page Poste). Refusé si un poste est déjà actif (D50)."""
    maintenant = base.maintenant()
    validite = int(base.reglage(conn, "enrolement_validite_s") or 600)
    code = nouveau_code()
    with base.transaction(conn):
        actif = machine_active(conn)
        if actif is not None:
            raise RefusACP("poste_deja_enrole", T.POSTE_DEJA_ENROLE.format(nom=actif["nom"]))
        purger_codes_dans(conn)
        conn.execute("INSERT INTO enrolements (empreinte_code, cree_le, expire_le, cree_par) VALUES (?, ?, ?, ?)",
                     (empreinte_jeton(code), maintenant, maintenant + validite, auteur))
        base.journaliser(conn, auteur, "code_enrolement", detail={"expire_le": maintenant + validite})
    return {"code": code, "expire_le": maintenant + validite, "validite_s": validite, "protocole": PROTOCOLE}


def code_utilisable(conn, empreinte_code: str) -> Optional[Dict[str, Any]]:
    ligne = conn.execute("SELECT * FROM enrolements WHERE empreinte_code = ?", (empreinte_code,)).fetchone()
    if ligne is None or ligne["utilise_le"] is not None or int(ligne["expire_le"]) <= base.maintenant():
        return None
    return base.ligne_en_dict(ligne)


def enroler_dans(conn, empreinte_code: str, *, nom: str, version_poste: str, protocole: str) -> Dict[str, Any]:
    """Enrôlement, SOUS la transaction ``IMMEDIATE`` de la route (le code est relu dedans : un code utilisé entre
    la couture et le gestionnaire est vu). Rend la réponse 201, seul message qui contienne le jeton."""
    if code_utilisable(conn, empreinte_code) is None:
        raise RefusACP("non_authentifie", T.CODE_REFUSE)
    actif = machine_active(conn)
    if actif is not None:
        raise RefusACP("poste_deja_enrole", T.POSTE_DEJA_ENROLE.format(nom=actif["nom"]))
    maintenant = base.maintenant()
    remplaces = [l[0] for l in conn.execute("SELECT id FROM machines WHERE etat = 'a_confirmer'").fetchall()]
    for ancien in remplaces:
        conn.execute("UPDATE machines SET etat = 'revoque', revoque_le = ?, revoque_par = ?, motif_revocation = ? "
                     "WHERE id = ?", (maintenant, "acp-poste:enrolement", T.MOTIF_REMPLACE, ancien))
        conn.execute("DELETE FROM presence WHERE machine_id = ?", (ancien,))
        base.journaliser(conn, "acp-poste:enrolement", "revocation", cible=ancien, detail=T.MOTIF_REMPLACE)
    jeton = nouveau_jeton()
    empreinte = empreinte_jeton(jeton)
    for _essai in range(3):
        identifiant = nouvel_identifiant()
        try:
            conn.execute("INSERT INTO machines (id, nom, empreinte_jeton, etat, protocole, version_poste, cree_le) "
                         "VALUES (?, ?, ?, 'a_confirmer', ?, ?, ?)",
                         (identifiant, nom, empreinte, protocole, version_poste, maintenant))
            break
        except sqlite3.IntegrityError:
            continue
    else:  # pragma: no cover — trois collisions d'identifiant sur 44 bits
        raise RuntimeError("identifiant de machine indisponible")
    conn.execute("UPDATE enrolements SET utilise_le = ?, machine_id = ? WHERE empreinte_code = ?",
                 (maintenant, identifiant, empreinte_code))
    base.journaliser(conn, f"poste:{identifiant}", "enrolement", cible=identifiant,
                     detail={"nom": nom, "version_poste": version_poste, "remplaces": remplaces})
    return {"machine_id": identifiant, "jeton": jeton, "empreinte": empreinte_courte(empreinte),
            "etat": "a_confirmer", "protocole": PROTOCOLE}


def exiger_machine(conn, machine_id: Any) -> Dict[str, Any]:
    ligne = machine(conn, machine_id) if isinstance(machine_id, str) else None
    if ligne is None:
        raise refus("machine_inconnue", T.MACHINE_INCONNUE.format(m=str(machine_id)[:40]))
    return ligne


def confirmer(conn, machine_id: Any, empreinte: Any, auteur: str) -> Dict[str, Any]:
    """``a_confirmer`` → ``actif`` si l'empreinte saisie (casse et tiret indifférents) est celle du poste."""
    saisie = empreinte_courte_normalisee(empreinte)
    if saisie is None:
        raise refus("empreinte_illisible", T.EMPREINTE_ILLISIBLE)
    with base.transaction(conn):
        ligne = exiger_machine(conn, machine_id)
        if ligne["etat"] != "a_confirmer":
            raise refus("pas_a_confirmer", T.MACHINE_PAS_A_CONFIRMER.format(nom=ligne["nom"], etat=ligne["etat"]))
        if saisie != empreinte_affichee(ligne):
            base.journaliser(conn, auteur, "confirmation_refusee", cible=ligne["id"])
            raise RefusACP("empreinte_differente", T.EMPREINTE_DIFFERENTE)
        actif = machine_active(conn)
        if actif is not None:
            raise RefusACP("poste_deja_enrole", T.POSTE_DEJA_ENROLE.format(nom=actif["nom"]))
        conn.execute("UPDATE machines SET etat = 'actif', confirme_le = ?, confirme_par = ? WHERE id = ?",
                     (base.maintenant(), auteur, ligne["id"]))
        base.journaliser(conn, auteur, "confirmation", cible=ligne["id"])
    return etat(conn)


def revoquer(conn, machine_id: Any, motif: Any, auteur: str) -> Dict[str, Any]:
    """Révocation : ``revoque`` en base et présence supprimée DANS la même transaction."""
    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 200:
        raise refus("motif", T.MOTIF_REVOCATION)
    with base.transaction(conn):
        ligne = exiger_machine(conn, machine_id)
        if ligne["etat"] == "revoque":
            raise refus("deja_revoque", T.MACHINE_DEJA_REVOQUEE.format(nom=ligne["nom"]))
        conn.execute("UPDATE machines SET etat = 'revoque', revoque_le = ?, revoque_par = ?, motif_revocation = ? "
                     "WHERE id = ?", (base.maintenant(), auteur, motif.strip(), ligne["id"]))
        conn.execute("DELETE FROM presence WHERE machine_id = ?", (ligne["id"],))
        conn.execute("UPDATE ordres SET abandonne_le = ? WHERE machine_id = ? AND acquitte_le IS NULL AND "
                     "abandonne_le IS NULL", (base.maintenant(), ligne["id"]))
        base.journaliser(conn, auteur, "revocation", cible=ligne["id"], detail=motif.strip())
    return etat(conn)


def vue(ligne: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ce que la page Poste montre d'une machine : jamais l'empreinte complète du jeton."""
    if ligne is None:
        return None
    return {
        "id": ligne["id"], "nom": ligne["nom"], "etat": ligne["etat"], "empreinte": empreinte_affichee(ligne),
        "protocole": ligne["protocole"], "version_poste": ligne["version_poste"], "cree_le": ligne["cree_le"],
        "confirme_le": ligne["confirme_le"], "revoque_le": ligne["revoque_le"],
        "motif_revocation": ligne["motif_revocation"], "derniere_requete": ligne["derniere_requete"],
        "politique_valide": bool(ligne["politique_valide"]),
        # Étape P6 : plateforme et hôte publiés par l'inventaire (« Exécutant Railway » ou « Poste Windows »).
        "plateforme": ligne.get("plateforme") or "windows", "hote": ligne.get("hote") or "pc",
    }


def etat(conn) -> Dict[str, Any]:
    """Machine courante (vue), nombre de postes par état et codes encore utilisables."""
    comptes = {e: 0 for e in ETATS}
    for ligne in conn.execute("SELECT etat, COUNT(*) FROM machines GROUP BY etat").fetchall():
        comptes[str(ligne[0])] = int(ligne[1])
    codes = conn.execute("SELECT COUNT(*) FROM enrolements WHERE utilise_le IS NULL AND expire_le > ?",
                         (base.maintenant(),)).fetchone()[0]
    return {"machine": vue(machine_courante(conn)), "machines": comptes, "codes_utilisables": int(codes)}


def date_revocation(ligne: Dict[str, Any]) -> str:
    return _date(ligne.get("revoque_le"))
