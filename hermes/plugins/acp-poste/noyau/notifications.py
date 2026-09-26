"""Notifications du propriétaire (cahier P4 § 12.5) : file en base, canal Telegram ou ntfy.

- **File** : table ``notifications``, UNE ligne par clé (``INSERT OR IGNORE``) : un événement rejoué ne
  notifie jamais deux fois. N'importe quel processus peut enfiler (outil d'un worker, route, émetteur).
- **Envoi** : SEULEMENT dans la passerelle, par le fil de l'émetteur (:mod:`emetteur`), qui seul garde la
  configuration du canal en mémoire.
- **Contenu minimal** (décision D32) : genre, titre du projet, titre de carte tronqué à 80 caractères,
  lien vers la page Projets ; jamais la consigne ni le texte d'une question ; texte masqué, 300
  caractères au plus.
- **Canal désactivé tant que rien n'est configuré** : ``ACP_NOTIFICATIONS`` vaut ``aucune`` par défaut ;
  une notification enfilée sans canal passe ``desactivee`` (la ligne existe, rien n'est envoyé).

Secrets (``ACP_TELEGRAM_JETON``, ``ACP_NTFY_JETON``) : lus par ``register()`` dans CHAQUE processus, gardés
en mémoire dans la passerelle seulement, puis RETIRÉS de ``os.environ`` (:func:`retirer_de_l_environnement`)
pour que les workers lancés ensuite n'en héritent pas. Aucune URL ni aucun jeton dans les journaux.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Tuple

from . import base
from . import kanban_adapter as ka

VARIABLES = ("ACP_NOTIFICATIONS", "ACP_TELEGRAM_JETON", "ACP_TELEGRAM_DISCUSSION", "ACP_NTFY_SERVEUR",
             "ACP_NTFY_SUJET", "ACP_NTFY_JETON")
CANAUX = ("aucune", "telegram", "ntfy")
SERVEUR_NTFY_PAR_DEFAUT = "https://ntfy.sh"
GENRES_PRIORITAIRES = {"question", "triage", "hors_ligne", "crochets"}
LONGUEUR_TEXTE = 300
LONGUEUR_CARTE = 80
DELAI_ENVOI_S = 10
TENTATIVES_MAX = 5
REPRISE_BASE_S = 30

_JETON = re.compile(r"^\S{1,256}$")
_DISCUSSION = re.compile(r"^-?\d{1,20}$")
_SUJET = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_URL = re.compile(r"^[A-Za-z0-9._~:/%-]+$")


@dataclass(frozen=True)
class Configuration:
    canal: str = "aucune"
    jeton: Optional[str] = None
    discussion: Optional[str] = None
    serveur: Optional[str] = None
    sujet: Optional[str] = None

    @property
    def configure(self) -> bool:
        return self.canal in ("telegram", "ntfy")

    def publique(self) -> Dict[str, Any]:
        """Ce qui peut être montré (aucun jeton, aucun sujet ntfy : le sujet donne accès au fil)."""
        return {"canal": self.canal, "configure": self.configure,
                "serveur": self.serveur if self.canal == "ntfy" else None}


def valider_url_https(valeur: str) -> Optional[str]:
    """Même règle que ``HERMES_DASHBOARD_PUBLIC_URL`` (acp_demarrage.valider_url_https) : https, hôte
    public, ni requête, ni fragment, ni identifiants. Rend la raison du refus, ou None."""
    if not valeur or valeur != valeur.strip() or len(valeur) > 2048 or not _URL.match(valeur):
        return "URL https attendue, sans requête, fragment ni identifiants"
    parties = urllib.parse.urlsplit(valeur)
    if parties.scheme != "https" or not parties.hostname:
        return "URL https attendue"
    hote = parties.hostname.lower().rstrip(".")
    if hote == "localhost" or hote.endswith(".localhost") or hote.endswith(".railway.internal"):
        return "hôte local ou privé interdit"
    try:
        if not ipaddress.ip_address(hote).is_global:
            return "adresse IP non publique interdite"
    except ValueError:
        pass
    return None


def lire_configuration(environ: Mapping[str, str]) -> Tuple[Configuration, List[str]]:
    """Configuration du canal lue dans ``environ`` ; ``(Configuration(canal="aucune"), erreurs)`` si
    elle est invalide. Les gardes de démarrage (acp_demarrage.py) appliquent les mêmes règles et
    refusent de démarrer : ceci n'est qu'une défense en profondeur."""
    canal = (environ.get("ACP_NOTIFICATIONS") or "aucune").strip()
    erreurs: List[str] = []
    if canal not in CANAUX:
        return Configuration(), [f"ACP_NOTIFICATIONS vaut « {canal[:20]} » (attendu : {', '.join(CANAUX)})."]
    if canal == "aucune":
        return Configuration(), []
    if canal == "telegram":
        jeton = environ.get("ACP_TELEGRAM_JETON") or ""
        discussion = (environ.get("ACP_TELEGRAM_DISCUSSION") or "").strip()
        if not _JETON.match(jeton):
            erreurs.append("ACP_TELEGRAM_JETON est absente, vide, trop longue ou contient une espace.")
        if not _DISCUSSION.match(discussion):
            erreurs.append("ACP_TELEGRAM_DISCUSSION doit être un identifiant numérique de discussion.")
        if erreurs:
            return Configuration(), erreurs
        return Configuration(canal="telegram", jeton=jeton, discussion=discussion), []
    serveur = (environ.get("ACP_NTFY_SERVEUR") or SERVEUR_NTFY_PAR_DEFAUT).strip().rstrip("/")
    sujet = (environ.get("ACP_NTFY_SUJET") or "").strip()
    jeton = environ.get("ACP_NTFY_JETON") or ""
    raison = valider_url_https(serveur)
    if raison:
        erreurs.append(f"ACP_NTFY_SERVEUR : {raison}.")
    if not _SUJET.match(sujet):
        erreurs.append("ACP_NTFY_SUJET doit compter de 16 à 64 caractères parmi lettres, chiffres, « _ » et « - ».")
    if not _JETON.match(jeton):
        erreurs.append("ACP_NTFY_JETON est exigée (un sujet sans jeton serait lisible par des tiers).")
    if erreurs:
        return Configuration(), erreurs
    return Configuration(canal="ntfy", jeton=jeton, serveur=serveur, sujet=sujet), []


def retirer_de_l_environnement(environ: MutableMapping[str, str]) -> None:
    for nom in VARIABLES:
        environ.pop(nom, None)


# ------------------------------------------------------------------ file


def url_publique() -> Optional[str]:
    valeur = (os.environ.get("HERMES_DASHBOARD_PUBLIC_URL") or "").strip().rstrip("/")
    return valeur if valeur and valider_url_https(valeur) is None else None


def lien_projets(projet_id: Optional[str] = None) -> Optional[str]:
    racine = url_publique()
    if not racine:
        return None
    return f"{racine}/projets" + (f"?projet={projet_id}" if projet_id else "")


def texte(modele: str, **valeurs: Any) -> str:
    """Texte d'une notification : modèle de :mod:`textes` sans le lien (porté à part), titre de carte
    tronqué, masqué, 300 caractères au plus."""
    if "carte" in valeurs and valeurs["carte"] is not None:
        valeurs["carte"] = str(valeurs["carte"])[:LONGUEUR_CARTE]
    brut = modele.format(lien="", **valeurs).strip()
    return ka.masquer(brut)[:LONGUEUR_TEXTE]


def enfiler(conn, *, cle: str, genre: str, texte_notif: str, projet_id: Optional[str] = None,
            lien: Optional[str] = None) -> bool:
    """Enfile UNE notification par clé ; rend True si elle est nouvelle."""
    with base.transaction(conn):
        return enfiler_dans(conn, cle=cle, genre=genre, texte_notif=texte_notif, projet_id=projet_id, lien=lien)


def enfiler_dans(conn, *, cle: str, genre: str, texte_notif: str, projet_id: Optional[str] = None,
                 lien: Optional[str] = None) -> bool:
    """Comme :func:`enfiler`, DANS une transaction ouverte par l'appelant."""
    curseur = conn.execute(
        "INSERT OR IGNORE INTO notifications (cle, genre, projet_id, texte, lien, etat, tentatives, "
        "prochaine_tentative, cree_le) VALUES (?, ?, ?, ?, ?, 'en_attente', 0, ?, ?)",
        (cle[:300], genre, projet_id, texte_notif[:LONGUEUR_TEXTE], lien or lien_projets(projet_id),
         base.maintenant(), base.maintenant()))
    return curseur.rowcount == 1


def compter(conn) -> Dict[str, int]:
    return {etat: n for etat, n in conn.execute("SELECT etat, COUNT(*) FROM notifications GROUP BY etat")}


# ------------------------------------------------------------------ envoi (passerelle seulement)

Transport = Callable[[str, str, Dict[str, str], bytes, float], Tuple[int, str]]


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Aucune redirection suivie (relecture de P4) : l'ouvreur par défaut de urllib suit un 301/302/303 d'un
    POST en gardant l'en-tête ``Authorization`` (jeton ntfy) — vers un autre hôte, voire de https vers http.
    Ici, un 3xx reste une réponse : l'envoi échoue « HTTP 3xx » et se réessaie vers la MÊME URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102, N802
        return None


def transport_urllib(methode: str, url: str, entetes: Dict[str, str], corps: bytes, delai: float) -> Tuple[int, str]:
    """POST HTTPS, certificat vérifié par le magasin du système (épinglé par l'image), JAMAIS de
    redirection suivie (le jeton ne part que vers l'URL configurée)."""
    requete = urllib.request.Request(url, data=corps, method=methode, headers=entetes)
    ouvreur = urllib.request.build_opener(_SansRedirection(),
                                          urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with ouvreur.open(requete, timeout=delai) as reponse:  # noqa: S310
            return int(reponse.status), reponse.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), ""


def requete(config: Configuration, notif: Mapping[str, Any]) -> Tuple[str, str, Dict[str, str], bytes]:
    """(méthode, URL, en-têtes, corps) de l'envoi de ``notif`` par le canal configuré."""
    lien = notif.get("lien")
    if config.canal == "telegram":
        corps = {"chat_id": config.discussion, "text": notif["texte"] + (f" {lien}" if lien else ""),
                 "disable_web_page_preview": True}
        return ("POST", f"https://api.telegram.org/bot{config.jeton}/sendMessage",
                {"Content-Type": "application/json"}, json.dumps(corps, ensure_ascii=False).encode("utf-8"))
    if config.canal == "ntfy":
        entetes = {"Authorization": f"Bearer {config.jeton}", "Title": "ACP",
                   "Priority": "4" if notif.get("genre") in GENRES_PRIORITAIRES else "3",
                   "Content-Type": "text/plain; charset=utf-8"}
        if lien:
            entetes["Click"] = lien
        return "POST", f"{config.serveur}/{config.sujet}", entetes, str(notif["texte"]).encode("utf-8")
    raise ValueError("aucun canal configuré")


def envoyer_en_attente(conn, config: Configuration, transport: Transport = transport_urllib,
                       limite: int = 20) -> Dict[str, int]:
    """Envoie les notifications ``en_attente`` échues. Sans canal : ``desactivee``. Échec : reprise à
    30 s × 2ⁿ, 5 tentatives au plus, puis ``echec`` (alerte de /v1/meta). Jamais d'URL ni de jeton
    dans ``derniere_erreur``."""
    bilan = {"envoyees": 0, "echecs": 0, "desactivees": 0, "reportees": 0}
    maintenant = base.maintenant()
    lignes = [base.ligne_en_dict(l) for l in conn.execute(
        "SELECT * FROM notifications WHERE etat = 'en_attente' AND COALESCE(prochaine_tentative, 0) <= ? "
        "ORDER BY id LIMIT ?", (maintenant, limite))]
    for notif in lignes:
        if not config.configure:
            with base.transaction(conn):
                conn.execute("UPDATE notifications SET etat = 'desactivee' WHERE id = ? AND etat = 'en_attente'",
                             (notif["id"],))
            bilan["desactivees"] += 1
            continue
        if not notif.get("lien"):
            notif["lien"] = lien_projets(notif.get("projet_id"))
        erreur: Optional[str] = None
        try:
            methode, url, entetes, corps = requete(config, notif)
            code, _ = transport(methode, url, entetes, corps, DELAI_ENVOI_S)
            if not 200 <= code < 300:
                erreur = f"HTTP {code}"
        except Exception as exc:  # noqa: BLE001 — le type seul, jamais le message (il peut porter l'URL)
            erreur = type(exc).__name__
        tentatives = int(notif["tentatives"]) + 1
        with base.transaction(conn):
            if erreur is None:
                conn.execute("UPDATE notifications SET etat = 'envoyee', tentatives = ?, envoyee_le = ?, "
                             "derniere_erreur = NULL WHERE id = ?", (tentatives, base.maintenant(), notif["id"]))
                bilan["envoyees"] += 1
            elif tentatives >= TENTATIVES_MAX:
                conn.execute("UPDATE notifications SET etat = 'echec', tentatives = ?, derniere_erreur = ? WHERE id = ?",
                             (tentatives, erreur, notif["id"]))
                bilan["echecs"] += 1
            else:
                conn.execute("UPDATE notifications SET tentatives = ?, derniere_erreur = ?, prochaine_tentative = ? "
                             "WHERE id = ?", (tentatives, erreur,
                                              base.maintenant() + REPRISE_BASE_S * (2 ** (tentatives - 1)), notif["id"]))
                bilan["reportees"] += 1
    return bilan
