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

``lignes`` (montée de données, cahier P9 § 5.6) : même copie, puis LIGNE À LIGNE : objets de ``sqlite_master`` (le
SQL du schéma, jamais une donnée), compteurs ``AUTOINCREMENT`` (``sqlite_sequence``) et, par table, l'empreinte
courte de chaque ligne par ``rowid``. Avec ``-`` en dernier argument, une PROJECTION est lue sur l'entrée standard (JSON
{base: {table: [colonnes]}}) : les colonnes d'AVANT une montée, pour qu'une ligne qu'une migration a élargie se compare
à elle-même. ``comparer_lignes``, ``comparer_schemas``, ``changements_propres`` et ``defauts_de_montee`` jugent deux
relevés : lignes d'avant perdues ou modifiées, objets du schéma ajoutés, retirés ou modifiés, hors ce que change aussi
un simple redémarrage (relevé de CONTRÔLE).

  … empreinte_volume.py lignes /v [-]

Aucun contenu n'est imprimé : seulement des empreintes, des tailles et des noms (et le SQL du schéma). Sortie : JSON
trié sur la sortie standard. Codes : 0, 2 (usage, racine illisible ou projection illisible).
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
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

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


@contextmanager
def _copie(chemin: str) -> Iterator[Tuple[str, Dict[str, int]]]:
    """Copie de la base et de ses ``-wal``, ``-shm`` et ``-journal`` dans un dossier temporaire : (chemin de la copie,
    tailles des annexes copiées). La base d'origine n'est jamais ouverte."""
    with tempfile.TemporaryDirectory(prefix="acp-empreinte-") as dossier:
        copie = os.path.join(dossier, "base.db")
        shutil.copyfile(chemin, copie)
        annexes = {}
        for suffixe in ("-wal", "-shm", "-journal"):
            if os.path.exists(chemin + suffixe):
                shutil.copyfile(chemin + suffixe, copie + suffixe)
                annexes[suffixe] = os.path.getsize(chemin + suffixe)
        yield copie, annexes


def empreinte_base(chemin: str) -> Dict[str, Any]:
    """Empreinte logique d'une base, lue sur une COPIE (avec -wal et -shm) : la base d'origine n'est jamais ouverte."""
    with _copie(chemin) as (copie, annexes):
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


# ------------------------------------------------------------------ montée de données (étape P9, cahier P9 § 5.6)

Projection = Dict[str, Dict[str, List[str]]]  # {base: {table: [colonnes]}}


def _condense(valeurs: Any) -> str:
    """Empreinte courte d'une ligne aux valeurs TYPÉES (64 bits : une collision entre deux versions d'UNE ligne est
    sans objet à l'échelle d'un volume de test)."""
    texte = json.dumps([_valeur(v) for v in valeurs], ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def _lignes_table(conn: sqlite3.Connection, nom: str, projection: Optional[List[str]]) -> Dict[str, Any]:
    colonnes = [str(ligne[1]) for ligne in conn.execute(f"PRAGMA table_info({_identifiant(nom)})")]
    retenues = colonnes if projection is None else [c for c in projection if c in colonnes]
    absentes = [] if projection is None else [c for c in projection if c not in colonnes]
    nouvelles = [] if projection is None else [c for c in colonnes if c not in projection]
    selection = ", ".join(_identifiant(c) for c in retenues) or "NULL"
    lignes: Dict[str, str] = {}
    try:
        curseur = conn.execute(f"SELECT rowid, {selection} FROM {_identifiant(nom)}")
        cle = "rowid"
    except sqlite3.OperationalError:
        # Table WITHOUT ROWID : la ligne entière sert de clé (une ligne modifiée se lit perdue puis ajoutée).
        curseur = conn.execute(f"SELECT NULL, {selection} FROM {_identifiant(nom)}")
        cle = "ligne"
    nombre = 0
    for ligne in curseur:
        condense = _condense(ligne[1:])
        lignes[str(ligne[0]) if cle == "rowid" else condense] = condense
        nombre += 1
    non_nulles = {c: conn.execute(f"SELECT COUNT(*) FROM {_identifiant(nom)} WHERE {_identifiant(c)} IS NOT NULL")
                  .fetchone()[0] for c in nouvelles}
    return {"colonnes": retenues, "colonnes_absentes": absentes, "nouvelles_colonnes": non_nulles, "cle": cle,
            "nombre": nombre, "lignes": lignes}


def lignes_base(chemin: str, projection: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """Relevé LIGNE À LIGNE d'une base, lu sur une COPIE : intégrité, ``user_version``, version du greffon
    (``meta_schema``), objets de ``sqlite_master`` (« type:nom » → SQL), compteurs ``AUTOINCREMENT`` et, par table, les
    colonnes lues et l'empreinte de chaque ligne. ``projection`` ({table: colonnes}) : seulement ces colonnes, dans cet
    ordre ; une colonne projetée absente et chaque colonne nouvelle (avec son nombre de valeurs non nulles) sont dites.
    Une table hors de la projection (nouvelle) est lue entière."""
    with _copie(chemin) as (copie, _annexes):
        try:
            conn = sqlite3.connect(copie, isolation_level=None)
        except sqlite3.Error as exc:
            return {"integrite": [f"ouverture impossible : {exc}"]}
        resultat: Dict[str, Any] = {}
        try:
            integrite = [ligne[0] for ligne in conn.execute("PRAGMA integrity_check")]
            resultat["integrite"] = "ok" if integrite == ["ok"] else integrite
            resultat["user_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
            maitre = conn.execute(
                "SELECT type, name, COALESCE(sql, '') FROM sqlite_master ORDER BY type, name").fetchall()
            resultat["objets"] = {f"{genre}:{nom}": sql for genre, nom, sql in maitre}
            tables: Dict[str, Any] = {}
            for genre, nom, sql in maitre:
                if genre != "table":
                    continue
                if sql.upper().startswith("CREATE VIRTUAL TABLE"):
                    tables[nom] = {"virtuelle": True}
                    continue
                tables[nom] = _lignes_table(conn, nom, (projection or {}).get(nom))
            resultat["tables"] = tables
            resultat["sequences"] = ({str(n): s for n, s in conn.execute("SELECT name, seq FROM sqlite_sequence")}
                                     if "sqlite_sequence" in tables else {})
            resultat["meta_schema"] = None
            if "meta_schema" in tables:
                ligne = conn.execute("SELECT valeur FROM meta_schema WHERE cle = 'version'").fetchone()
                resultat["meta_schema"] = ligne[0] if ligne else None
        except sqlite3.DatabaseError as exc:
            resultat["integrite"] = [f"lecture impossible : {exc}"]
        finally:
            conn.close()
        return resultat


def lignes(racine: str, projection: Optional[Projection] = None) -> Dict[str, Any]:
    trouvees = {}
    for relatif, absolu in _parcourir(racine):
        if relatif != "." and stat.S_ISREG(os.lstat(absolu).st_mode) and _est_sqlite(absolu):
            trouvees[relatif] = lignes_base(absolu, (projection or {}).get(relatif))
    return {"racine": racine, "bases": trouvees}


def projection_de(releve: Dict[str, Any]) -> Projection:
    """Colonnes de chaque table d'un relevé ``lignes`` : la projection qui compare un relevé APRÈS à celui-ci."""
    return {base: {table: list(t["colonnes"]) for table, t in (e.get("tables") or {}).items() if not t.get("virtuelle")}
            for base, e in releve["bases"].items()}


def _tri(cles: List[str]) -> List[str]:
    return sorted(cles, key=lambda c: (0, int(c), "") if c.isdigit() else (1, 0, c))


def comparer_lignes(avant: Dict[str, Any], apres: Dict[str, Any], exemples: int = 5) -> Dict[str, Dict[str, Any]]:
    """Écarts LIGNE À LIGNE entre deux relevés ``lignes`` (le second projeté sur les colonnes du premier). Seules les
    bases et tables qui diffèrent figurent : ``{"base": "absente"}``, ``{"base": "nouvelle", "tables_nouvelles": […]}``
    ou ``{"tables": {table: écart}}``, où un écart est ``{"table": "absente"}``,
    ``{"table": "nouvelle", "ajoutees": n}`` ou les nombres de lignes d'avant ``perdues`` et ``modifiees``, de lignes
    ``ajoutees``, les ``colonnes_absentes`` et quelques clés en ``exemples``. Les tables virtuelles ne se comparent pas
    (leurs tables d'ombre, si)."""
    ecarts: Dict[str, Dict[str, Any]] = {}
    a, b = avant["bases"], apres["bases"]
    for base in sorted(set(a) | set(b)):
        if base not in b:
            ecarts[base] = {"base": "absente"}
            continue
        if base not in a:
            ecarts[base] = {"base": "nouvelle", "tables_nouvelles": sorted(b[base].get("tables") or {})}
            continue
        tables: Dict[str, Any] = {}
        ta, tb = a[base].get("tables") or {}, b[base].get("tables") or {}
        for table in sorted(set(ta) | set(tb)):
            if table not in tb:
                tables[table] = {"table": "absente"}
                continue
            if table not in ta:
                tables[table] = {"table": "nouvelle", "ajoutees": len(tb[table].get("lignes") or {})}
                continue
            if ta[table].get("virtuelle") or tb[table].get("virtuelle"):
                continue
            la, lb = ta[table]["lignes"], tb[table]["lignes"]
            perdues = [k for k in la if k not in lb]
            modifiees = [k for k in la if k in lb and la[k] != lb[k]]
            ajoutees = [k for k in lb if k not in la]
            absentes = tb[table].get("colonnes_absentes") or []
            if perdues or modifiees or ajoutees or absentes:
                tables[table] = {"perdues": len(perdues), "modifiees": len(modifiees), "ajoutees": len(ajoutees),
                                 "colonnes_absentes": absentes,
                                 "exemples": {"perdues": _tri(perdues)[:exemples],
                                              "modifiees": _tri(modifiees)[:exemples],
                                              "ajoutees": _tri(ajoutees)[:exemples]}}
        if tables:
            ecarts[base] = {"tables": tables}
    return ecarts


def comparer_schemas(avant: Dict[str, Any], apres: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Changements de SCHÉMA entre deux relevés ``lignes`` : ``user_version`` et version du greffon ([avant, après]),
    objets de ``sqlite_master`` ajoutés, retirés ou dont le SQL a changé (« type:nom ») ; bases absentes ou nouvelles.
    Seules les bases qui changent figurent."""
    ecarts: Dict[str, Dict[str, Any]] = {}
    a, b = avant["bases"], apres["bases"]
    for base in sorted(set(a) | set(b)):
        if base not in b:
            ecarts[base] = {"base": "absente"}
            continue
        if base not in a:
            ecarts[base] = {"base": "nouvelle", "objets_ajoutes": sorted(b[base].get("objets") or {})}
            continue
        ea, eb = a[base], b[base]
        ecart: Dict[str, Any] = {}
        for cle in ("user_version", "meta_schema"):
            if ea.get(cle) != eb.get(cle):
                ecart[cle] = [ea.get(cle), eb.get(cle)]
        oa, ob = ea.get("objets") or {}, eb.get("objets") or {}
        for cle, liste in (("objets_ajoutes", sorted(set(ob) - set(oa))), ("objets_retires", sorted(set(oa) - set(ob))),
                           ("objets_modifies", sorted(o for o in set(oa) & set(ob) if oa[o] != ob[o]))):
            if liste:
                ecart[cle] = liste
        if ecart:
            ecarts[base] = ecart
    return ecarts


def changements_propres(montee: Dict[str, Dict[str, Any]], controle: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Ce que la MONTÉE change (``comparer_schemas`` ou ``comparer_lignes``) et qu'un simple redémarrage sur la même
    image (CONTRÔLE) ne change pas : versions différentes de celles du contrôle, objets ou tables absents du
    contrôle."""
    propres: Dict[str, Any] = {}
    for base, ecart in montee.items():
        temoin = controle.get(base) or {}
        if "base" in ecart:
            if temoin.get("base") != ecart["base"]:
                propres[base] = ecart
            continue
        reste: Dict[str, Any] = {}
        for cle, valeur in ecart.items():
            if isinstance(valeur, dict):  # tables de comparer_lignes
                tables = {t: e for t, e in valeur.items() if t not in (temoin.get(cle) or {})}
                if tables:
                    reste[cle] = tables
            elif cle in ("user_version", "meta_schema"):
                if temoin.get(cle) != valeur:
                    reste[cle] = valeur
            else:
                autres: Set[str] = set(temoin.get(cle) or [])
                liste = [o for o in valeur if o not in autres]
                if liste:
                    reste[cle] = liste
        if reste:
            propres[base] = reste
    return propres


def defauts_de_montee(avant: Dict[str, Any], apres: Dict[str, Any], montee: Dict[str, Dict[str, Any]],
                      controle: Dict[str, Dict[str, Any]]) -> List[str]:
    """Défauts NOMMÉS d'une montée de données (vide : aucune donnée d'avant perdue ni altérée) :

    - base d'avant disparue, ou dont ``integrity_check`` n'est plus « ok » ;
    - table d'avant disparue, colonne d'avant disparue, ligne d'avant perdue ou modifiée (comparée sur les colonnes
      d'AVANT : ``montee`` = ``comparer_lignes(avant, apres)``, ``apres`` projeté), dans toute table qu'un simple
      redémarrage ne change pas (``controle`` = ``comparer_lignes`` du contrôle : tables « vivantes » exclues). Seule
      exception : la ligne de version de ``meta_schema`` quand la version du greffon change ;
    - compteur ``AUTOINCREMENT`` perdu ou revenu en arrière (des identifiants déjà servis le seraient de nouveau).
    Les lignes AJOUTÉES ne sont pas des défauts (l'activité après le redémarrage en ajoute) : elles sont dites par
    ``comparer_lignes``."""
    defauts: List[str] = []
    vivantes = {(base, table) for base, e in controle.items() for table in (e.get("tables") or {})}
    for base, ea in avant["bases"].items():
        eb = apres["bases"].get(base)
        if eb is None:
            defauts.append(f"{base} : base disparue")
            continue
        if eb.get("integrite") != "ok":
            defauts.append(f"{base} : integrity_check {eb.get('integrite')!r}")
        for nom, seq in (ea.get("sequences") or {}).items():
            apres_seq = (eb.get("sequences") or {}).get(nom)
            if apres_seq is None or apres_seq < seq:
                defauts.append(f"{base} : compteur AUTOINCREMENT de {nom} {seq} → {apres_seq}")
        version_changee = ea.get("meta_schema") != eb.get("meta_schema")
        for table, ecart in ((montee.get(base) or {}).get("tables") or {}).items():
            if (base, table) in vivantes or table == "sqlite_sequence" or ecart.get("table") == "nouvelle":
                continue
            if ecart.get("table") == "absente":
                defauts.append(f"{base} : table {table} disparue")
                continue
            if ecart["colonnes_absentes"]:
                defauts.append(f"{base} : table {table}, colonnes disparues {ecart['colonnes_absentes']}")
            if ecart["perdues"]:
                defauts.append(f"{base} : table {table}, {ecart['perdues']} ligne(s) d'avant perdue(s) "
                               f"{ecart['exemples']['perdues']}")
            tolerees = 1 if table == "meta_schema" and version_changee else 0
            if ecart["modifiees"] > tolerees:
                defauts.append(f"{base} : table {table}, {ecart['modifiees']} ligne(s) d'avant modifiée(s) "
                               f"{ecart['exemples']['modifiees']}")
    return defauts


def main(argv: List[str]) -> int:
    projection: Optional[Projection] = None
    if len(argv) == 3 and argv[0] == "lignes" and argv[2] == "-":
        try:
            projection = json.loads(sys.stdin.read())
        except ValueError as exc:
            print(f"Projection illisible sur l'entrée standard : {exc}", file=sys.stderr)
            return 2
        if not isinstance(projection, dict):
            print("Projection illisible sur l'entrée standard : objet JSON attendu.", file=sys.stderr)
            return 2
        argv = argv[:2]
    if len(argv) != 2 or argv[0] not in ("manifeste", "sqlite", "lignes"):
        print("Usage : empreinte_volume.py manifeste|sqlite <racine> | lignes <racine> [-]", file=sys.stderr)
        return 2
    commande, racine = argv
    if not os.path.isdir(racine):
        print(f"Racine illisible : {racine}", file=sys.stderr)
        return 2
    if commande == "manifeste":
        resultat: Dict[str, Any] = manifeste(racine)
    elif commande == "sqlite":
        resultat = bases(racine)
    else:
        resultat = lignes(racine, projection)
    sys.stdout.write(json.dumps(resultat, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
