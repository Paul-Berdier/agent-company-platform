"""Empreinte d'un volume, par ses octets et par le contenu de ses bases SQLite (étape P9, cahier P9 § 3.1-3.2).

Bibliothèque standard seule. Lancé dans l'image de test SOUS ROOT (``/donnees/acp/secrets`` et ``/config/secrets`` sont
en 0600), le volume monté EN LECTURE SEULE ; rien n'est jamais écrit sous la racine lue :

  docker run --rm -u 0 -v <volume>:/v:ro --entrypoint /opt/hermes/.venv/bin/python <image de test> \\
      /opt/acp-tests/outils/empreinte_volume.py manifeste /v
  … empreinte_volume.py sqlite /v

``manifeste`` : une entrée par chemin relatif (« . » pour la racine) : type (d, f, l, s pour une prise Unix, p, c, b),
mode (bits de permission et spéciaux, en octal), uid, gid numériques, et selon le type taille et SHA-256 (fichier) ou
cible (lien symbolique, jamais suivi). Les prises Unix (``gateway.sock`` de Hermes, cahier § 3.1) sont relevées à part :
GNU tar les ignore, elles sont donc EXCLUES de l'égalité (``comparer_manifestes``) et seulement imprimées.

``sqlite`` : chaque fichier qui commence par l'en-tête « SQLite format 3 » est COPIÉ (avec ses ``-wal``, ``-shm`` et
``-journal``)
dans un dossier temporaire, puis ouvert : ``PRAGMA integrity_check``, ``PRAGMA user_version``, version du schéma du
greffon (table ``meta_schema``, clé ``version`` : le greffon n'emploie pas ``user_version``), empreinte du schéma
(``sqlite_master`` trié) et, par table, nombre de lignes et SHA-256 des lignes TRIÉES (par ``rowid``, sinon par toutes
les colonnes) aux valeurs TYPÉES. C'est l'empreinte LOGIQUE : une base prise en marche (journal WAL non intégré) et la
même après ``wal_checkpoint`` ont des octets différents et la même empreinte. Les tables virtuelles (FTS) ne sont pas
lues : leur contenu est dans leurs tables d'ombre, qui le sont.

Aucun contenu n'est imprimé : seulement des empreintes, des tailles et des noms. Sortie : JSON trié sur la sortie
standard. Codes : 0, 2 (usage ou racine illisible).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from typing import Any, Dict, Iterator, List, Optional, Tuple

EN_TETE_SQLITE = b"SQLite format 3\x00"
TYPES = ((stat.S_ISDIR, "d"), (stat.S_ISREG, "f"), (stat.S_ISLNK, "l"), (stat.S_ISSOCK, "s"), (stat.S_ISFIFO, "p"),
         (stat.S_ISCHR, "c"), (stat.S_ISBLK, "b"))


def _type(mode: int) -> str:
    for predicat, lettre in TYPES:
        if predicat(mode):
            return lettre
    return "?"


def _sha256(chemin: str) -> str:
    empreinte = hashlib.sha256()
    with open(chemin, "rb") as flux:
        for bloc in iter(lambda: flux.read(1 << 20), b""):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def _parcourir(racine: str) -> Iterator[Tuple[str, str]]:
    """(chemin relatif, chemin absolu) de la racine et de tout ce qu'elle contient, liens jamais suivis, trié."""
    yield ".", racine
    pile = [""]
    while pile:
        relatif = pile.pop()
        dossier = os.path.join(racine, relatif) if relatif else racine
        with os.scandir(dossier) as entrees:
            noms = sorted(e.name for e in entrees)
        for nom in noms:
            enfant = f"{relatif}/{nom}" if relatif else nom
            absolu = os.path.join(racine, enfant)
            yield enfant, absolu
            if stat.S_ISDIR(os.lstat(absolu).st_mode):
                pile.append(enfant)


def entree(absolu: str) -> Dict[str, Any]:
    infos = os.lstat(absolu)
    genre = _type(infos.st_mode)
    resultat: Dict[str, Any] = {"type": genre, "mode": format(stat.S_IMODE(infos.st_mode), "04o"),
                                "uid": infos.st_uid, "gid": infos.st_gid}
    if genre == "f":
        resultat["taille"] = infos.st_size
        resultat["sha256"] = _sha256(absolu)
    elif genre == "l":
        resultat["cible"] = os.readlink(absolu)
    elif genre in ("c", "b"):
        resultat["peripherique"] = [os.major(infos.st_rdev), os.minor(infos.st_rdev)]
    return resultat


def manifeste(racine: str) -> Dict[str, Any]:
    entrees = {relatif: entree(absolu) for relatif, absolu in _parcourir(racine)}
    decompte: Dict[str, int] = {}
    for valeur in entrees.values():
        decompte[valeur["type"]] = decompte.get(valeur["type"], 0) + 1
    return {"racine": racine, "entrees": entrees, "decompte": dict(sorted(decompte.items())),
            "prises": sorted(c for c, v in entrees.items() if v["type"] == "s")}


def comparer_manifestes(attendu: Dict[str, Any], obtenu: Dict[str, Any]) -> List[str]:
    """Écarts NOMMÉS entre deux manifestes (vide : égaux). Les prises Unix sont exclues des deux côtés."""
    def sans_prises(m: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {c: v for c, v in m["entrees"].items() if v["type"] != "s"}

    a, b = sans_prises(attendu), sans_prises(obtenu)
    ecarts: List[str] = []
    for chemin in sorted(set(a) | set(b)):
        if chemin not in b:
            ecarts.append(f"absent : {chemin}")
        elif chemin not in a:
            ecarts.append(f"en trop : {chemin}")
        else:
            for cle in sorted(set(a[chemin]) | set(b[chemin])):
                if a[chemin].get(cle) != b[chemin].get(cle):
                    ecarts.append(f"{chemin} : {cle} {a[chemin].get(cle)!r} → {b[chemin].get(cle)!r}")
    return ecarts


def _valeur(valeur: Any) -> List[Any]:
    """Valeur TYPÉE et sérialisable : un entier 1 et un texte « 1 » ne se confondent pas."""
    if valeur is None:
        return ["null", None]
    if isinstance(valeur, bool):
        return ["integer", int(valeur)]
    if isinstance(valeur, int):
        return ["integer", valeur]
    if isinstance(valeur, float):
        return ["real", repr(valeur)]
    if isinstance(valeur, bytes):
        return ["blob", valeur.hex()]
    return ["text", str(valeur)]


def _identifiant(nom: str) -> str:
    return '"' + nom.replace('"', '""') + '"'


def _table(conn: sqlite3.Connection, nom: str) -> Dict[str, Any]:
    colonnes = [ligne[1] for ligne in conn.execute(f"PRAGMA table_info({_identifiant(nom)})")]
    try:
        conn.execute(f"SELECT rowid FROM {_identifiant(nom)} LIMIT 0")
        ordre = "rowid"
    except sqlite3.OperationalError:
        ordre = ", ".join(str(i) for i in range(1, len(colonnes) + 1)) or "1"
    empreinte = hashlib.sha256()
    lignes = 0
    for ligne in conn.execute(f"SELECT * FROM {_identifiant(nom)} ORDER BY {ordre}"):
        empreinte.update(json.dumps([_valeur(v) for v in ligne], ensure_ascii=False).encode("utf-8") + b"\n")
        lignes += 1
    return {"lignes": lignes, "sha256": empreinte.hexdigest(), "colonnes": len(colonnes)}


def empreinte_base(chemin: str) -> Dict[str, Any]:
    """Empreinte logique d'une base, lue sur une COPIE (avec -wal et -shm) : la base d'origine n'est jamais ouverte."""
    with tempfile.TemporaryDirectory(prefix="acp-empreinte-") as dossier:
        copie = os.path.join(dossier, "base.db")
        shutil.copyfile(chemin, copie)
        annexes = {}
        for suffixe in ("-wal", "-shm", "-journal"):
            if os.path.exists(chemin + suffixe):
                shutil.copyfile(chemin + suffixe, copie + suffixe)
                annexes[suffixe] = os.path.getsize(chemin + suffixe)
        resultat: Dict[str, Any] = {"octets": os.path.getsize(chemin), "annexes": annexes}
        try:
            conn = sqlite3.connect(copie, isolation_level=None)
        except sqlite3.Error as exc:
            return dict(resultat, integrite=[f"ouverture impossible : {exc}"])
        try:
            integrite = [ligne[0] for ligne in conn.execute("PRAGMA integrity_check")]
            resultat["integrite"] = "ok" if integrite == ["ok"] else integrite
            resultat["user_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
            maitre = conn.execute("SELECT type, name, tbl_name, COALESCE(sql, '') FROM sqlite_master "
                                  "ORDER BY type, name").fetchall()
            resultat["schema"] = hashlib.sha256(json.dumps(maitre, ensure_ascii=False).encode("utf-8")).hexdigest()
            tables: Dict[str, Any] = {}
            for genre, nom, _table_de, sql in maitre:
                if genre != "table":
                    continue
                if sql.upper().startswith("CREATE VIRTUAL TABLE"):
                    tables[nom] = {"virtuelle": True}
                    continue
                tables[nom] = _table(conn, nom)
            resultat["tables"] = tables
            resultat["meta_schema"] = None
            if "meta_schema" in tables:
                ligne = conn.execute("SELECT valeur FROM meta_schema WHERE cle = 'version'").fetchone()
                resultat["meta_schema"] = ligne[0] if ligne else None
        except sqlite3.DatabaseError as exc:
            resultat["integrite"] = [f"lecture impossible : {exc}"]
        finally:
            conn.close()
        return resultat


def _est_sqlite(chemin: str) -> bool:
    try:
        with open(chemin, "rb") as flux:
            return flux.read(len(EN_TETE_SQLITE)) == EN_TETE_SQLITE
    except OSError:
        return False


def bases(racine: str) -> Dict[str, Any]:
    trouvees = {}
    for relatif, absolu in _parcourir(racine):
        if relatif != "." and stat.S_ISREG(os.lstat(absolu).st_mode) and _est_sqlite(absolu):
            trouvees[relatif] = empreinte_base(absolu)
    return {"racine": racine, "bases": trouvees}


def comparer_bases(attendu: Dict[str, Any], obtenu: Dict[str, Any], *, tables_seules: bool = False) -> List[str]:
    """Écarts NOMMÉS entre deux relevés ``sqlite`` (vide : mêmes bases, même contenu logique). Les octets et les
    fichiers annexes ne comptent pas (c'est tout l'objet de la couche 2). ``tables_seules`` : seulement le contenu des
    tables communes (montée de données : schéma et tables nouvelles comparés à part)."""
    ecarts: List[str] = []
    a, b = attendu["bases"], obtenu["bases"]
    for base in sorted(set(a) | set(b)):
        if base not in b:
            ecarts.append(f"base absente : {base}")
            continue
        if base not in a:
            ecarts.append(f"base en trop : {base}")
            continue
        ea, eb = a[base], b[base]
        cles = ("tables",) if tables_seules else ("integrite", "user_version", "meta_schema", "schema", "tables")
        for cle in cles:
            if cle == "tables":
                ta, tb = ea.get("tables") or {}, eb.get("tables") or {}
                noms = (set(ta) & set(tb)) if tables_seules else (set(ta) | set(tb))
                for table in sorted(noms):
                    if ta.get(table) != tb.get(table):
                        ecarts.append(f"{base} : table {table} {ta.get(table)!r} → {tb.get(table)!r}")
            elif ea.get(cle) != eb.get(cle):
                ecarts.append(f"{base} : {cle} {ea.get(cle)!r} → {eb.get(cle)!r}")
    return ecarts


def main(argv: List[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("manifeste", "sqlite"):
        print("Usage : empreinte_volume.py manifeste|sqlite <racine>", file=sys.stderr)
        return 2
    commande, racine = argv
    if not os.path.isdir(racine):
        print(f"Racine illisible : {racine}", file=sys.stderr)
        return 2
    resultat: Optional[Dict[str, Any]] = manifeste(racine) if commande == "manifeste" else bases(racine)
    sys.stdout.write(json.dumps(resultat, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
