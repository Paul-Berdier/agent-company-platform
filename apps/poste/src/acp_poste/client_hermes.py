"""Client HTTPS sortant du poste vers Hermes (cahier P5 § 4.1, décision D61 : bibliothèque standard seule).

- ``http.client`` et ``ssl`` : aucune dépendance ajoutée ; sous Windows, ``ssl.create_default_context()`` charge le
  magasin de certificats du système. Python ne déclenche pas le téléchargement automatique des racines que fait
  CryptoAPI : une racine jamais téléchargée sur ce PC donne un refus TLS en français (« acp-poste diagnostic
  --reseau », cahier P5 § 20).
- **HTTPS seulement**, TLS 1.2 au moins, nom d'hôte vérifié. Jamais de redirection suivie (``http.client`` n'en
  suit aucune ; une réponse 3xx est refusée par :mod:`protocole`). Jamais de mandataire d'environnement
  (``HTTPS_PROXY`` n'est lu que par ``urllib``, que le poste n'emploie pas) : le jeton ne part que vers l'origine
  de ``poste.toml``.
- Réponse bornée (64 Kio, vérifiée à la lecture), délais de connexion et de lecture explicites, connexion fermée
  après chaque échange.

Les seuls réglages hors de ``poste.toml`` (:class:`OptionsClient`) servent aux tests : une autorité de test et une
résolution de nom forcée vers la boucle locale ; ils ne sont jamais lus dans un fichier ni dans l'environnement.
"""

from __future__ import annotations

import http.client
import socket
import ssl
import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from acp_poste_contrat.machine import TAILLE_MAX_REPONSE


class ErreurReseau(Exception):
    """Échange impossible avec Hermes (réseau, TLS, délai, réponse illisible) : message français."""


@dataclass(frozen=True)
class OptionsClient:
    """Injection de test seulement (jamais ``poste.toml``) : autorité de test, résolution forcée."""

    fichier_autorite: str | None = None
    resolution: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReponseHTTP:
    statut: int
    corps: bytes
    entetes: dict[str, str]


class _ConnexionTLS(http.client.HTTPSConnection):
    """Connexion TLS qui peut joindre une adresse forcée tout en vérifiant le nom d'hôte de l'origine."""

    def __init__(self, hote: str, port: int, *, contexte: ssl.SSLContext, delai_s: float, adresse: str | None):
        super().__init__(hote, port, context=contexte, timeout=delai_s)
        self._adresse = adresse
        self._contexte_tls = contexte

    def connect(self) -> None:
        brut = socket.create_connection((self._adresse or self.host, self.port), self.timeout)
        try:
            brut.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock = self._contexte_tls.wrap_socket(brut, server_hostname=self.host)
        except BaseException:
            brut.close()
            raise


def _message_tls(exc: ssl.SSLError) -> str:
    if isinstance(exc, ssl.SSLCertVerificationError):
        code = getattr(exc, "verify_code", None)
        if code in (18, 19, 20, 21):
            raison = "autorité de certification inconnue du magasin de Windows"
        elif code == 62:
            raison = "le certificat ne correspond pas au nom d'hôte de l'origine"
        elif code in (9, 10):
            raison = "certificat expiré ou pas encore valide"
        else:
            raison = "certificat refusé"
        return (f"Certificat de Hermes refusé ({raison}) : aucun échange. Lancez « acp-poste diagnostic --reseau » "
                "dans le compte du poste (racines TLS du magasin de Windows).")
    return "Négociation TLS avec Hermes impossible : aucun échange."


class ClientHermes:
    """Échanges HTTPS du poste avec l'origine de Hermes ; un échange à la fois par client."""

    def __init__(self, origine: str, *, delai_connexion_s: float, options: OptionsClient | None = None) -> None:
        decoupe = urlsplit(origine)
        if decoupe.scheme != "https" or not decoupe.hostname:
            raise ErreurReseau("Origine de Hermes refusée : HTTPS exigé (poste.toml, [hermes] origine).")
        self.origine = origine
        self.hote = decoupe.hostname
        self.port = decoupe.port or 443
        self.delai_connexion_s = float(delai_connexion_s)
        self.options = options or OptionsClient()
        contexte = ssl.create_default_context(cafile=self.options.fichier_autorite) \
            if self.options.fichier_autorite else ssl.create_default_context()
        contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        contexte.check_hostname = True
        contexte.verify_mode = ssl.CERT_REQUIRED
        self._contexte = contexte
        self._verrou = threading.Lock()
        self._en_cours: _ConnexionTLS | None = None

    def interrompre(self) -> None:
        """Coupe l'échange en cours (appelé depuis un autre fil pour arrêter une attente longue)."""
        with self._verrou:
            connexion = self._en_cours
        if connexion is not None and connexion.sock is not None:
            try:
                connexion.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def echanger(self, methode: str, chemin: str, *, corps: bytes | None = None, entetes: dict[str, str] | None = None,
                 delai_lecture_s: float) -> ReponseHTTP:
        connexion = _ConnexionTLS(self.hote, self.port, contexte=self._contexte, delai_s=self.delai_connexion_s,
                                  adresse=self.options.resolution.get(self.hote))
        with self._verrou:
            self._en_cours = connexion
        try:
            try:
                connexion.connect()
                connexion.sock.settimeout(delai_lecture_s)
                connexion.request(methode, chemin, body=corps, headers=dict(entetes or {}))
                reponse = connexion.getresponse()
                contenu = reponse.read(TAILLE_MAX_REPONSE + 1)
            except ssl.SSLError as exc:
                raise ErreurReseau(_message_tls(exc)) from None
            except (socket.timeout, TimeoutError):
                raise ErreurReseau("Hermes n'a pas répondu dans le délai imparti : nouvel essai plus tard.") from None
            except socket.gaierror:
                raise ErreurReseau("Nom d'hôte de Hermes introuvable (DNS) : nouvel essai plus tard.") from None
            except ConnectionRefusedError:
                raise ErreurReseau("Connexion à Hermes refusée : nouvel essai plus tard.") from None
            except http.client.HTTPException:
                raise ErreurReseau("Réponse HTTP de Hermes illisible : nouvel essai plus tard.") from None
            except OSError as exc:
                raise ErreurReseau(f"Connexion à Hermes impossible ({type(exc).__name__}) : nouvel essai plus "
                                   "tard.") from None
            if len(contenu) > TAILLE_MAX_REPONSE:
                raise ErreurReseau(f"Réponse de Hermes trop volumineuse (plus de {TAILLE_MAX_REPONSE // 1024} Kio) : "
                                   "refusée.")
            gardes = {cle.lower(): valeur for cle, valeur in reponse.getheaders()
                      if cle.lower() in ("content-type", "retry-after", "location", "cache-control")}
            return ReponseHTTP(statut=reponse.status, corps=contenu, entetes=gardes)
        finally:
            with self._verrou:
                self._en_cours = None
            connexion.close()
