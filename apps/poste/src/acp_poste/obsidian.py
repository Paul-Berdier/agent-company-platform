"""Coffre Markdown ACP neuf, indépendant des comptes et processus Obsidian.

Le graphe couvre les wikiliens et liens Markdown textuels, pas les plugins Obsidian.
Une archive précède chaque remplacement ; un traitement interrompu n'est jamais rejoué.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import stat
import time
import unicodedata
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from acp_poste_contrat.motifs_secrets import motif_trouve
from acp_poste_contrat.coffre import resultat_valide

from .obsidian_fichiers import RefusFichier, dossier_epingle, fichier_epingle, renommer_handle

CAPACITES = ("lister", "lire", "rechercher", "creer", "ecrire", "archiver", "renommer", "graphe", "backlinks")
NOTE_MAX = 128 * 1024
REPONSE_MAX = 192 * 1024
FICHIERS_MAX = 1000
PARCOURS_MAX = 5000
PORTEE = "Liens Markdown et wikiliens ; extensions Obsidian non interprétées."
_INTERDITS = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f]')
_DEVICES = re.compile(r"^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", re.I)


class RefusNotes(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def chemin_note(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 240 or _INTERDITS.search(value) or unicodedata.normalize("NFC", value) != value:
        raise RefusNotes("chemin_refuse", "Chemin de note refusé ; utilisez un chemin relatif en .md.")
    parts = value.split("/")
    if any(not p or p.startswith(".") or p.endswith((" ", ".")) or _DEVICES.match(p) for p in parts) or not value.lower().endswith(".md"):
        raise RefusNotes("chemin_refuse", "Dossier réservé, nom ambigu ou extension autre que .md refusés.")
    return value


def _contenu(value):
    if not isinstance(value, str) or any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in value):
        raise RefusNotes("contenu_refuse", "La note doit être du texte UTF-8 sans caractères de contrôle.")
    try:
        data = value.encode("utf-8")
    except UnicodeError:
        raise RefusNotes("contenu_refuse", "La note doit être du texte UTF-8 valide.") from None
    if len(data) > NOTE_MAX:
        raise RefusNotes("trop_volumineux", "La note dépasse 128 Kio.")
    return data


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _lire(path, maximum=NOTE_MAX):
    with fichier_epingle(path) as (f, _):
        data = f.read(maximum + 1)
    if len(data) > maximum:
        raise RefusNotes("trop_volumineux", "Le fichier dépasse la taille admise.")
    return data


def _creer(path, data):
    with fichier_epingle(path, ecriture=True, creer=True) as (f, _):
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _mkdir(path):
    with dossier_epingle(path.parent) as parent:
        if os.name == "nt":
            path.mkdir()
        else:
            os.mkdir(path.name, 0o700, dir_fd=parent)


def creer_coffre(racine: Path) -> str:
    """Geste local explicite : exige une racine inexistante, ne réutilise aucun coffre."""
    racine = Path(racine)
    if not racine.is_absolute() or ".." in racine.parts:
        raise RefusNotes("chemin_refuse", "Choisissez un chemin absolu local neuf.")
    identifiant = str(uuid4())
    _mkdir(racine)
    for p in (racine / ".acp", racine / ".acp" / "archives", racine / ".acp" / "operations"):
        _mkdir(p)
    _creer(racine / ".acp" / "coffre.json", _json({"protocole": "acp-coffre/1", "coffre_id": identifiant, "alias": "acp"}))
    _creer(racine / ".acp" / "verrou", b"ACP")
    _creer(racine / "Accueil.md", "# Coffre ACP\n\nNotes de travail du coffre ACP.\n\n- [[Projets]]\n- [[Journal]]\n".encode())
    _creer(racine / "Projets.md", "# Projets\n\nConsignez ici les objectifs et les décisions.\n\n[[Accueil]]\n".encode())
    _creer(racine / "Journal.md", "# Journal\n\nAjoutez ici vos notes datées et leurs sources.\n\n[[Accueil]]\n".encode())
    return identifiant


class CoffreNotes:
    def __init__(self, racine: Path, coffre_id: str):
        self.racine = Path(racine)
        self.coffre_id = str(UUID(coffre_id))
        if not self.racine.is_absolute() or ".." in self.racine.parts:
            raise RefusNotes("chemin_refuse", "Chemin local absolu requis.")
        self._identite()

    def _identite(self):
        try:
            marker = json.loads(_lire(self.racine / ".acp" / "coffre.json", 2048))
        except (ValueError, OSError, RefusFichier):
            raise RefusNotes("coffre_refuse", "Identité du coffre ACP illisible.") from None
        if marker != {"protocole": "acp-coffre/1", "coffre_id": self.coffre_id, "alias": "acp"}:
            raise RefusNotes("coffre_refuse", "Ce dossier n'est pas le coffre ACP associé.")

    def _path(self, nom):
        return self.racine.joinpath(*chemin_note(nom).split("/"))

    def _parents(self, path):
        current = self.racine
        for part in path.parent.relative_to(self.racine).parts:
            current /= part
            try:
                _mkdir(current)
            except FileExistsError:
                with dossier_epingle(current):
                    pass

    def _liste(self):
        trouves, visites, tronque = [], 0, False
        attente = [self.racine]
        while attente:
            directory = attente.pop()
            with dossier_epingle(directory) as fd:
                with os.scandir(directory if os.name == "nt" else fd) as entries:
                    for entry in entries:
                        visites += 1
                        if visites > PARCOURS_MAX or len(trouves) >= FICHIERS_MAX:
                            return sorted(trouves, key=lambda x: x["chemin"]), True
                        if entry.name.startswith("."):
                            continue
                        st = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
                            raise RefusNotes("chemin_refuse", "Le coffre contient un lien ou une jonction ; retirez-le pour continuer.")
                        path = directory / entry.name
                        if stat.S_ISDIR(st.st_mode):
                            attente.append(path)
                        elif entry.name.lower().endswith(".md"):
                            nom = path.relative_to(self.racine).as_posix()
                            chemin_note(nom)
                            with fichier_epingle(path) as (note, _):
                                taille = os.fstat(note.fileno()).st_size
                            if taille > NOTE_MAX:
                                raise RefusNotes("trop_volumineux", "Une note du coffre dépasse 128 Kio ; déplacez-la hors du coffre pour continuer.")
                            trouves.append({"chemin": nom, "octets": taille})
        return sorted(trouves, key=lambda x: x["chemin"]), tronque

    def _note(self, nom):
        data = _lire(self._path(nom))
        try:
            contenu = data.decode("utf-8")
        except UnicodeError:
            raise RefusNotes("contenu_refuse", "La note existante n'est pas du texte UTF-8.") from None
        _contenu(contenu)
        return {"chemin": nom, "contenu": contenu, "empreinte": _hash(data), "octets": len(data)}

    def _archive(self, nom, data, identifiant):
        fichier = identifiant + ".md"
        _creer(self.racine / ".acp" / "archives" / fichier, data)
        _creer(self.racine / ".acp" / "archives" / (identifiant + ".json"),
               _json({"chemin": nom, "empreinte": _hash(data), "archive_id": identifiant}))
        return identifiant

    def _modifier(self, action, params, identifiant):
        nom = chemin_note(params.get("chemin"))
        path = self._path(nom)
        if action == "creer":
            data = _contenu(params.get("contenu"))
            self._parents(path)
            _creer(path, data)
            return {"chemin": nom, "empreinte": _hash(data), "octets": len(data)}
        attendu = params.get("empreinte_attendue")
        if not isinstance(attendu, str) or not re.fullmatch("[0-9a-f]{64}", attendu):
            raise RefusNotes("conflit", "Relisez la note avant toute modification.")
        data = _contenu(params.get("contenu")) if action == "ecrire" else None
        destination = self._path(params.get("destination")) if action == "renommer" else None
        if destination == path:
            raise RefusNotes("deja_existant", "La destination est identique à la note actuelle.")
        with fichier_epingle(path, deplacer=True) as (f, parent):
            old = f.read(NOTE_MAX + 1)
            if len(old) > NOTE_MAX:
                raise RefusNotes("trop_volumineux", "La note dépasse 128 Kio.")
            if _hash(old) != attendu:
                raise RefusNotes("conflit", "La note a changé ; relisez-la avant d'enregistrer votre brouillon.")
            if action == "ecrire":
                archive = self.racine / ".acp" / "archives" / (identifiant + ".md")
                prochain = archive.with_name(identifiant + ".nouveau.md")
                # Ne jamais réécrire l'inode existant : Windows permet l'ajout d'un
                # hardlink même sous un handle sans partage WRITE/DELETE. L'ancienne
                # version devient l'archive ; la nouvelle a son propre inode.
                with fichier_epingle(prochain, ecriture=True, creer=True, deplacer=True) as (nouveau, parent_nouveau):
                    nouveau.write(data)
                    nouveau.flush()
                    os.fsync(nouveau.fileno())
                    _creer(archive.with_suffix(".json"), _json({"chemin": nom, "empreinte": attendu, "archive_id": identifiant}))
                    renommer_handle(f, path, archive, parent)
                    try:
                        renommer_handle(nouveau, prochain, path, parent_nouveau)
                    except (OSError, RefusFichier):
                        raise RefusNotes("indeterminee", "Publication interrompue : l'ancienne version et la note préparée sont conservées dans les archives.") from None
                    nouveau.seek(0)
                    if nouveau.read(NOTE_MAX + 1) != data:
                        raise RefusNotes("indeterminee", "L'écriture n'a pas pu être vérifiée ; une archive est conservée.")
                return {"chemin": nom, "empreinte": _hash(data), "octets": len(data), "archive_id": identifiant}
            if action == "archiver":
                destination = self.racine / ".acp" / "archives" / (identifiant + ".md")
                _creer(destination.with_suffix(".json"), _json({"chemin": nom, "empreinte": attendu, "archive_id": identifiant}))
            else:
                self._parents(destination)
            renommer_handle(f, path, destination, parent)
            if action == "archiver":
                return {"chemin": nom, "archive_id": identifiant}
            return {"chemin": nom, "destination": params["destination"], "empreinte": attendu, "liens_modifies": False}

    def _graphe(self, limit):
        notes, tronque = self._liste()
        tronque |= len(notes) > limit
        notes = notes[:limit]
        names = {n["chemin"] for n in notes}
        links, unresolved = [], []
        for note in notes:
            text = self._note(note["chemin"])["contenu"]
            text = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$|`[^`\n]*`|<!--.*?-->", "", text)
            targets = [(m.group(1).split("|", 1)[0], True) for m in re.finditer(r"(?<!!)\[\[([^]\n]+)\]\]", text)]
            targets += [(m.group(1), False) for m in re.finditer(r"(?<!!)\[[^]\n]*\]\(([^)\n]+)\)", text)]
            for raw, wiki in targets:
                raw = raw.strip().strip("<>")
                if not wiki and re.search(r'\s+[\"\']', raw):
                    raw = re.split(r'\s+[\"\']', raw, 1)[0]
                if urlsplit(raw).scheme or raw.startswith("//"):
                    continue
                target = unquote(raw.split("#", 1)[0])
                if not target:
                    target = note["chemin"]
                if not target.endswith(".md"):
                    if PurePosixPath(target).suffix:
                        continue
                    target += ".md"
                candidates = []
                if not wiki:
                    relative = posixpath.normpath((PurePosixPath(note["chemin"]).parent / target).as_posix())
                    if relative in names:
                        candidates.append(relative)
                if not candidates and target in names:
                    candidates.append(target)
                if not candidates and "/" not in target:
                    candidates = sorted(n for n in names if PurePosixPath(n).name == target)
                if len(candidates) == 1:
                    links.append({"source": note["chemin"], "cible": candidates[0]})
                else:
                    if len(raw) > 500:
                        tronque = True
                    unresolved.append({"source": note["chemin"], "cible": raw[:500]})
                if len(links) + len(unresolved) >= 2000:
                    return {"noeuds": [{"chemin": n["chemin"]} for n in notes], "liens": links,
                            "non_resolus": unresolved, "tronque": True, "portee": PORTEE}
        return {"noeuds": [{"chemin": n["chemin"]} for n in notes], "liens": links,
                "non_resolus": unresolved, "tronque": bool(tronque), "portee": PORTEE}

    def _action(self, action, params, identifiant):
        limit = params.get("limite", 100 if action in ("lister", "rechercher") else 500)
        maximum = 100 if action == "rechercher" else 200 if action == "lister" else 500
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
            raise RefusNotes("parametres_refuses", "Limite de lecture invalide.")
        if action in ("creer", "ecrire", "archiver", "renommer"):
            return self._modifier(action, params, identifiant)
        if action == "lire":
            return self._note(chemin_note(params.get("chemin")))
        if action == "lister":
            notes, tronque = self._liste()
            prefix = params.get("prefixe", "")
            if not isinstance(prefix, str) or len(prefix) > 240:
                raise RefusNotes("chemin_refuse", "Préfixe de recherche invalide.")
            notes = [n for n in notes if n["chemin"].startswith(prefix)]
            return {"notes": notes[:limit], "tronque": tronque or len(notes) > limit}
        if action == "rechercher":
            query = params.get("texte")
            if not isinstance(query, str) or not 1 <= len(query) <= 200:
                raise RefusNotes("parametres_refuses", "La recherche attend de 1 à 200 caractères.")
            notes, tronque = self._liste()
            results = []
            for note in notes:
                for number, line in enumerate(self._note(note["chemin"])["contenu"].splitlines(), 1):
                    if query.casefold() in line.casefold():
                        if len(results) == limit:
                            return {"resultats": results, "tronque": True}
                        results.append({"chemin": note["chemin"], "ligne": number, "extrait": line[:240]})
            return {"resultats": results, "tronque": tronque}
        if action in ("graphe", "backlinks"):
            graph = self._graphe(limit)
            if action == "graphe":
                return graph
            nom = chemin_note(params.get("chemin"))
            self._note(nom)
            return {"chemin": nom, "liens": [edge for edge in graph["liens"] if edge["cible"] == nom],
                    "tronque": graph["tronque"]}
        raise RefusNotes("operation_inconnue", "Opération de coffre inconnue.")

    def executer(self, operation: dict) -> dict:
        identifiant = str(UUID(operation["id_operation"]))
        response = {"protocole": "acp-coffre/1", "coffre_id": self.coffre_id, "id_operation": identifiant,
                    "etat": "refusee", "resultat": None, "erreur": None}
        commence = False
        ledger = None
        request_hash = None
        try:
            if operation.get("coffre_id") != self.coffre_id:
                raise RefusNotes("coffre_refuse", "L'opération ne vise pas ce coffre.")
            if operation.get("action") not in CAPACITES or not isinstance(operation.get("parametres"), dict):
                raise RefusNotes("operation_inconnue", "Opération ou paramètres inconnus.")
            if motif_trouve(_json(operation["parametres"]).decode("utf-8")):
                raise RefusNotes("secret", "La demande contient ce qui ressemble à un secret ; rien n'a été écrit.")
            self._identite()
            ledger = self.racine / ".acp" / "operations" / (identifiant + ".json")
            request_hash = _hash(_json(operation))
            with fichier_epingle(self.racine / ".acp" / "verrou", ecriture=True):
                try:
                    saved = json.loads(_lire(ledger, REPONSE_MAX))
                except FileNotFoundError:
                    saved = None
                except (ValueError, RefusNotes):
                    raise RefusNotes("indeterminee", "Preuve locale illisible ; inspectez la note et ses archives avant toute nouvelle action.") from None
                if saved:
                    if saved.get("demande") != request_hash:
                        raise RefusNotes("conflit", "Identifiant d'opération déjà utilisé pour une autre demande.")
                    if "reponse" in saved:
                        return saved["reponse"]
                    raise RefusNotes("indeterminee", "Une tentative a été interrompue ; inspectez la note et ses archives avant une nouvelle action.")
                if type(operation.get("expire_le")) is not int or operation["expire_le"] <= time.time():
                    raise RefusNotes("expiree", "Cette opération a expiré ; aucune note n'a été modifiée.")
                # Journal avant mutation : un arrêt inattendu interdit toute répétition automatique.
                mutation = operation["action"] in ("creer", "ecrire", "archiver", "renommer")
                if mutation:
                    with dossier_epingle(ledger.parent):
                        if sum(1 for _ in ledger.parent.iterdir()) >= 4096:
                            raise RefusNotes("indisponible", "Journal local plein ; archivez les preuves avec le propriétaire avant de continuer.")
                    _creer(ledger, _json({"demande": request_hash}))
                    commence = True
                result = self._action(operation["action"], operation["parametres"], identifiant)
                if motif_trouve(_json(result).decode("utf-8")):
                    raise RefusNotes("secret", "Le résultat contient ce qui ressemble à un secret ; son contenu n'est ni enregistré ni transmis.")
                resultat_valide(operation["action"], result)
                response.update(etat="reussie", resultat=result)
                if len(_json(response)) > REPONSE_MAX:
                    raise RefusNotes("trop_volumineux", "Le résultat dépasse la taille admise ; réduisez la sélection.")
                if mutation:
                    # Même fichier protégé, résultat final vérifié avant remise au bridge.
                    with fichier_epingle(ledger, ecriture=True) as (f, _):
                        f.write(_json({"demande": request_hash, "reponse": response}))
                        f.truncate()
                        f.flush()
                        os.fsync(f.fileno())
                return response
        except RefusNotes as exc:
            code, message = exc.code, str(exc)
        except FileNotFoundError:
            code, message = "absent", "La note ou son dossier est absent."
        except FileExistsError:
            code, message = "deja_existant", "Une note existe déjà à cette destination."
        except (RefusFichier, OSError, ValueError):
            code, message = "indisponible", "Accès au coffre refusé ou occupé ; aucune réussite n'est confirmée."
        response.update(etat="indeterminee" if code == "indeterminee" or (commence and code == "indisponible") else "refusee", resultat=None,
                        erreur={"code": code, "message": message})
        if commence and ledger is not None:
            try:
                with fichier_epingle(self.racine / ".acp" / "verrou", ecriture=True):
                    with fichier_epingle(ledger, ecriture=True) as (f, _):
                        f.write(_json({"demande": request_hash, "reponse": response}))
                        f.truncate()
                        f.flush()
                        os.fsync(f.fileno())
            except (OSError, RefusFichier):
                pass  # La marque commencée empêche toujours un nouveau passage.
        return response
