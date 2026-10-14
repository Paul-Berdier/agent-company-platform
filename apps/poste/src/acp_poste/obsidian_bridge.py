"""Bridge HTTPS sortant du coffre ACP, sous le compte Windows propriétaire.

Identité distincte du poste exécutant : aucune politique, aucun jeton machine, aucun
processus d'agent. Aucun port entrant, aucun lancement automatique d'Obsidian.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

from pydantic import ValidationError
from acp_poste_contrat import coffre as contrat

from . import __version__
from .client_hermes import ClientHermes, ErreurReseau
from .coffre import CoffreErreur, ecrire_atomiquement
from .obsidian import CAPACITES, CoffreNotes, RefusNotes, creer_coffre, _mkdir
from .obsidian_fichiers import RefusFichier, dossier_epingle, fichier_epingle, renommer_handle
from .verrou import Verrou, VerrouOccupe


MAX_RESULTATS_NON_ACQUITTES = 128


class RefusBridge(RuntimeError):
    def __init__(self, message, *, code="refus", temporaire=False):
        super().__init__(message)
        self.code, self.temporaire = code, temporaire


def origine_valide(value):
    try:
        u = urlsplit(value)
        if (u.scheme != "https" or not u.hostname or u.username or u.password or u.path not in ("", "/")
                or u.query or u.fragment or any(c.isspace() for c in value) or u.port == 0):
            raise ValueError()
        return value.rstrip("/")
    except (ValueError, TypeError):
        raise RefusBridge("Origine refusée : une origine HTTPS sans chemin ni identifiants est requise.") from None


class ProtocoleCoffre:
    def __init__(self, client):
        self.client = client

    def _poster(self, route, body, bearer, modele, statut=200):
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(data) > contrat.TAILLE_MAX_CORPS:
            raise RefusBridge("Le corps dépasse 192 Kio ; rien n'a été envoyé.")
        try:
            response = self.client.echanger("POST", route, corps=data, delai_lecture_s=40,
                entetes={"Authorization": "Bearer " + bearer, "Content-Type": "application/json",
                         "Accept": "application/json", "X-ACP-Protocole": contrat.PROTOCOLE,
                         "User-Agent": f"acp-coffre/{__version__}"})
        except ErreurReseau:
            raise RefusBridge("Hermes indisponible ; le résultat local reste conservé.", temporaire=True) from None
        try:
            payload = json.loads(response.corps)
        except (ValueError, UnicodeError):
            raise RefusBridge("Réponse de Hermes illisible ; aucune opération nouvelle n'est exécutée.") from None
        if response.statut != statut:
            detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
            code = detail.get("code") if isinstance(detail, dict) else None
            if response.statut == 401 and code == "coffre_revoque":
                raise RefusBridge("Association du coffre révoquée ; arrêt du bridge.", code="coffre_revoque")
            if response.statut == 401:
                raise RefusBridge("Identité du coffre refusée ; jeton conservé. Vérifiez l'association dans ACP.", code="identite_refusee")
            if route == contrat.ROUTE_RESULTAT and response.statut == 404 and code == "operation_inconnue":
                raise RefusBridge("Hermes ne retrouve plus cette opération ; son résultat n'est pas acquitté.",
                                  code="operation_inconnue")
            if route == contrat.ROUTE_RESULTAT and response.statut == 409 and code == "coffre_a_confirmer":
                raise RefusBridge("Confirmez l'empreinte dans ACP, puis redémarrez le bridge ; le résultat local reste conservé.")
            if response.statut >= 500 or response.statut == 429:
                raise RefusBridge("Hermes temporairement indisponible ; nouvel essai différé.", temporaire=True)
            raise RefusBridge(f"Hermes a refusé l'échange (HTTP {response.statut}) ; arrêt sans redirection.")
        try:
            return modele.model_validate(payload)
        except (ValidationError, ValueError):
            raise RefusBridge("Réponse de Hermes hors contrat ; aucune nouvelle opération n'est exécutée.") from None

    def associer(self, code, coffre_id):
        if not contrat.CODE_ENROLEMENT.fullmatch(code):
            raise RefusBridge("Code d'association invalide.")
        body = contrat.Enrolement(protocole=contrat.PROTOCOLE, version_bridge=__version__, coffre_id=coffre_id, alias="acp")
        result = self._poster(contrat.ROUTE_ENROLEMENT, body.model_dump(), code, contrat.ReponseEnrolement, 201)
        if result.coffre_id != coffre_id:
            raise RefusBridge("Hermes a répondu pour un autre coffre ; association refusée.")
        return result

    def reclamer(self, token, coffre_id, attente=25):
        if not contrat.JETON_COFFRE.fullmatch(token):
            raise RefusBridge("Jeton du coffre invalide.")
        body = contrat.RequeteReclamer(protocole=contrat.PROTOCOLE, coffre_id=coffre_id,
                                      capacites=list(CAPACITES), attente_max_s=attente)
        result = self._poster(contrat.ROUTE_RECLAMER, body.model_dump(), token, contrat.ReponseReclamer)
        if result.operation and (result.etat != "actif" or result.operation.coffre_id != coffre_id):
            raise RefusBridge("Opération reçue avant confirmation ou pour un autre coffre : refus.")
        return result

    def resultat(self, token, result):
        body = contrat.Resultat.model_validate(result)
        response = self._poster(contrat.ROUTE_RESULTAT, body.model_dump(), token, contrat.ReponseResultat)
        if response.id_operation != body.id_operation:
            raise RefusBridge("Accusé de réception d'une autre opération ; résultat local conservé.")
        return response


def _charger_json(path, maximum=contrat.TAILLE_MAX_CORPS):
    with fichier_epingle(path) as (f, _):
        raw = f.read(maximum + 1)
    if len(raw) > maximum:
        raise RefusBridge("Fichier local trop volumineux.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise RefusBridge("Fichier local illisible ; aucune reprise automatique.") from None


class BridgeCoffre:
    def __init__(self, contexte, *, fabrique_client=ClientHermes):
        self.contexte = contexte
        self.dossier = contexte.emplacements.acp_local / "coffre-notes"
        self.configuration = self.dossier / "configuration.json"
        self.sortie = self.dossier / "resultat-en-attente.json"
        self.fabrique_client = fabrique_client

    def _preparer(self):
        # Racine système du compte courant ; jamais un chemin reçu de Hermes.
        current = Path(self.dossier.anchor)
        for part in self.dossier.parts[1:]:
            current /= part
            try:
                _mkdir(current)
            except FileExistsError:
                with dossier_epingle(current):
                    pass

    def _sauver(self, path, value):
        with dossier_epingle(self.dossier):
            ecrire_atomiquement(path, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def charger(self):
        data = _charger_json(self.configuration, 4096)
        if not isinstance(data, dict) or set(data) != {"coffre_id", "racine"}:
            raise RefusBridge("Configuration locale du coffre invalide.")
        return CoffreNotes(Path(data["racine"]), data["coffre_id"])

    def creer(self, path):
        self._preparer()
        if self.configuration.exists():
            raise RefusBridge("Un coffre ACP est déjà configuré dans ce compte ; aucune autre racine n'est créée.")
        identifiant = creer_coffre(Path(path))
        self._sauver(self.configuration, {"coffre_id": identifiant, "racine": str(path)})
        return identifiant

    def _protocole(self, origine):
        return ProtocoleCoffre(self.fabrique_client(origine_valide(origine), delai_connexion_s=10,
            options=self.contexte.options_client, limite_reponse=contrat.TAILLE_MAX_CORPS))

    def associer(self, origine, code):
        self._preparer()
        notes = self.charger()
        if self.contexte.coffre.present("jeton-coffre"):
            raise RefusBridge("Une association existe déjà. Révoquez-la dans ACP, puis utilisez « obsidian oublier ».")
        origine = origine_valide(origine)
        result = self._protocole(origine).associer(code, notes.coffre_id)
        # Origine et identité sont protégées AVEC le jeton : une modification du JSON
        # de configuration ne permet pas de rediriger un secret vers un autre serveur.
        self.contexte.coffre.ecrire("jeton-coffre", json.dumps({"origine": origine, "coffre_id": notes.coffre_id,
            "jeton": result.jeton, "empreinte": result.empreinte}))
        return result.empreinte

    def identite(self, notes):
        raw = self.contexte.coffre.lire("jeton-coffre")
        if not raw:
            raise RefusBridge("Coffre non associé : lancez « obsidian associer » après avoir généré un code dans ACP.")
        try:
            data = json.loads(raw)
            if (set(data) != {"origine", "coffre_id", "jeton", "empreinte"} or data["coffre_id"] != notes.coffre_id
                    or not contrat.JETON_COFFRE.fullmatch(data["jeton"])):
                raise ValueError()
            origine_valide(data["origine"])
            return data
        except (ValueError, TypeError):
            raise RefusBridge("Identité protégée du coffre invalide ; aucune connexion n'est tentée.") from None

    def _transmettre_resultat(self, protocole, token, pending):
        try:
            protocole.resultat(token, pending)
        except RefusBridge as exc:
            if exc.code != "operation_inconnue":
                raise
            # Une absence explicite après purge ne vaut pas un acquittement. Garder
            # le fichier exact, sans rejouer la mutation, avant de débloquer la file.
            archives = self.dossier / "resultats-non-acquittes"
            try:
                try:
                    _mkdir(archives)
                except FileExistsError:
                    pass
                with dossier_epingle(archives):
                    if sum(1 for _ in archives.iterdir()) >= MAX_RESULTATS_NON_ACQUITTES:
                        raise RefusBridge("Archives des résultats non acquittés pleines ; résultat en attente conservé. Rangez les copies avant de redémarrer.")
                    destination = archives / (pending["id_operation"] + ".json")
                    with fichier_epingle(self.sortie, deplacer=True) as (stream, parent):
                        actuel = contrat.Resultat.model_validate(json.loads(stream.read(contrat.TAILLE_MAX_CORPS + 1))).model_dump()
                        if actuel != pending:
                            raise RefusBridge("Le résultat local a changé ; aucune copie n'est déplacée.")
                        renommer_handle(stream, self.sortie, destination, parent)
            except (OSError, RefusFichier, ValueError):
                raise RefusBridge("Archivage du résultat non acquitté impossible ou copie déjà présente ; résultat en attente conservé. Vérifiez les copies locales avant de redémarrer.") from None
            return "resultat_non_acquitte"
        with dossier_epingle(self.dossier):
            self.sortie.unlink()
        return "resultat_transmis"

    def cycle(self, protocole, notes, token, *, attente=25):
        # Une réponse non acquittée est prioritaire sur toute nouvelle opération.
        if self.sortie.exists():
            pending = contrat.Resultat.model_validate(_charger_json(self.sortie)).model_dump()
            if pending["coffre_id"] != notes.coffre_id:
                raise RefusBridge("Le résultat local appartient à un autre coffre ; envoi refusé.")
            return self._transmettre_resultat(protocole, token, pending)
        response = protocole.reclamer(token, notes.coffre_id, attente)
        if response.operation is None:
            return response.etat
        result = notes.executer(response.operation.model_dump())
        contrat.Resultat.model_validate(result)
        self._sauver(self.sortie, result)
        return self._transmettre_resultat(protocole, token, result)

    def servir(self, *, une_fois=False, pause=time.sleep):
        self._preparer()
        notes = self.charger()
        identite = self.identite(notes)
        protocole = self._protocole(identite["origine"])
        previous, retries = None, 0
        with Verrou(self.dossier / "bridge.verrou"):
            while True:
                try:
                    state = self.cycle(protocole, notes, identite["jeton"], attente=0 if une_fois else 25)
                    retries = 0
                    if state != previous:
                        print({"a_confirmer": "Association reçue ; comparez l'empreinte et confirmez dans ACP.",
                               "actif": "Coffre associé : le bridge attend les opérations ACP.",
                               "resultat_transmis": "Résultat du coffre acquitté par Hermes.",
                               "resultat_non_acquitte": "Résultat non acquitté par Hermes, conservé dans coffre-notes/resultats-non-acquittes. Relisez la note avant toute nouvelle modification ; la liaison continue."}[state])
                        previous = state
                    if une_fois:
                        return 0
                    pause(1)
                except RefusBridge as exc:
                    if exc.code == "coffre_revoque":
                        self.contexte.coffre.effacer("jeton-coffre")
                    if not exc.temporaire or une_fois:
                        raise
                    retries += 1
                    if retries == 1:
                        print(str(exc), file=sys.stderr)
                    pause(min(60, 2 ** min(retries, 6)))


def ajouter_commandes(commandes):
    p = commandes.add_parser("obsidian", help="Coffre Markdown ACP : bridge distinct de l'exécutant")
    sub = p.add_subparsers(dest="geste_coffre", required=True)
    create = sub.add_parser("creer", help="Créer un coffre ACP neuf, sans ouvrir Obsidian")
    create.add_argument("--dossier", required=True, help="Chemin absolu local inexistant du nouveau coffre")
    associate = sub.add_parser("associer", help="Associer le coffre à Hermes avec un code saisi de façon masquée")
    associate.add_argument("--origine", required=True, help="Origine HTTPS de Hermes")
    associate.add_argument("--code-stdin", action="store_true", help="Lire le code sur stdin, jamais en argument")
    serve = sub.add_parser("servir", help="Faire tourner le bridge sortant sous le compte propriétaire")
    serve.add_argument("--une-fois", action="store_true", help="Un cycle sans attente longue")
    sub.add_parser("diagnostic", help="Afficher l'état local, sans secret ni chemin du coffre")
    sub.add_parser("oublier", help="Effacer seulement l'identité locale du bridge, sans toucher aux notes")


def executer_cli(args, contexte):
    if contexte.plateforme != "windows":
        print("Le bridge Obsidian de ce lot nécessite le compte propriétaire Windows et DPAPI.", file=sys.stderr)
        return 2
    try:
        bridge = BridgeCoffre(contexte)
        if args.geste_coffre == "creer":
            bridge.creer(Path(args.dossier))
            print("Coffre ACP neuf créé. Associez-le à Hermes, puis ouvrez ce dossier dans Obsidian si souhaité.")
        elif args.geste_coffre == "associer":
            code = sys.stdin.readline(256).strip() if args.code_stdin else getpass.getpass("Code d'association ACP (saisie masquée) : ").strip()
            empreinte = bridge.associer(args.origine, code)
            print(f"Association en attente. Empreinte : {empreinte}. Comparez-la dans ACP avant de confirmer.")
        elif args.geste_coffre == "servir":
            return bridge.servir(une_fois=args.une_fois)
        elif args.geste_coffre == "oublier":
            bridge._preparer()
            with Verrou(bridge.dossier / "bridge.verrou"):
                contexte.coffre.effacer("jeton-coffre")
            print("Identité locale du bridge effacée ; les notes restent conservées. Révoquez aussi l'association dans ACP.")
        else:
            notes = bridge.charger()
            linked = contexte.coffre.present("jeton-coffre")
            print("Coffre ACP présent ; identité locale " + ("présente. La connexion n'a pas été vérifiée." if linked else "absente."))
        return 0
    except (RefusBridge, RefusNotes, RefusFichier, CoffreErreur, ErreurReseau, OSError, ValueError, VerrouOccupe) as exc:
        # Aucun détail brut de path/JSON/ValidationError ne doit rejoindre les logs.
        message = str(exc) if isinstance(exc, (RefusBridge, RefusNotes, RefusFichier, CoffreErreur, ErreurReseau)) else "Opération du coffre refusée ; vérifiez la configuration locale et l'association dans ACP."
        print(message, file=sys.stderr)
        return 2
