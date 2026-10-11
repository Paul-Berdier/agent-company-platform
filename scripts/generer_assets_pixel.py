#!/usr/bin/env python3
"""Génère les assets pixel art d'ACP depuis leurs sources texte (``design/pixel``).

Les sources sont des grilles de caractères éditables à la main (un caractère par pixel, ``.`` pour
la transparence), associées à une palette nommée de ``design/pixel/manifeste.json``. Ce script en
tire, de façon déterministe :

- les PNG RGBA de l'emblème (agrandissement au plus proche voisin, jamais lissé) ;
- l'icône Windows multirésolution (``.ico``, entrées 32 bits : 16, 20, 24, 32, 40, 48, 64 et 128 px
  en DIB, 256 px en PNG), chaque taille venant de la grille dessinée pour elle ou de son multiple entier ;
- les planches de sprites (portraits d'agents, pictogrammes, glyphes de la police pixel) et leurs
  métadonnées JSON (taille d'une case, images, durées, état réel associé).

Aucune dépendance hors bibliothèque standard : ``zlib`` et ``struct`` suffisent à écrire et relire
un PNG. Le mode ``--check`` relit chaque fichier versionné et compare ses **pixels** décodés (pas
ses octets : deux versions de zlib peuvent compresser différemment la même image) et le JSON
canonique des métadonnées ; il échoue sur toute dérive, sans rien écrire.

Usage :
    python scripts/generer_assets_pixel.py            # écrit les sorties
    python scripts/generer_assets_pixel.py --check    # échoue si une sortie est périmée

Code de sortie : 0 si tout est cohérent, 1 en cas de refus explicite (message en français).
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

RACINE = Path(__file__).resolve().parents[1]
MANIFESTE = RACINE / "design" / "pixel" / "manifeste.json"
COULEURS = RACINE / "design" / "tokens" / "colors.json"

Pixel = Tuple[int, int, int, int]
Grille = List[List[Pixel]]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_TRANSPARENT: Pixel = (0, 0, 0, 0)
#: Tailles d'une icône Windows retenues (Microsoft, « App icon construction » : 16, 20, 24, 32, 40,
#: 48, 64 et 256 ; 128 ajouté pour les vues « grandes icônes » de l'explorateur).
TAILLES_ICO = (16, 20, 24, 32, 40, 48, 64, 128, 256)
#: Plafond d'une planche : un asset d'interface reste petit (chargé à la demande, libéré avec la vue).
PLAFOND_PLANCHE = 2048


class Refus(RuntimeError):
    """Refus explicite : une source est hors contrat et rien ne sera écrit."""


# --- Palettes et grilles -------------------------------------------------------------------------


def couleur(valeur: str, contexte: str) -> Pixel:
    if not isinstance(valeur, str) or not _HEX.match(valeur):
        raise Refus(f"{contexte} : couleur attendue en #rrggbb ou #rrggbbaa, reçu {valeur!r}")
    r, g, b = int(valeur[1:3], 16), int(valeur[3:5], 16), int(valeur[5:7], 16)
    a = int(valeur[7:9], 16) if len(valeur) == 9 else 255
    return (r, g, b, a)


def couleur_de_jeton(reference: str, contexte: str) -> Pixel:
    """« jeton:<thème>:<jeton> » : la couleur vient de design/tokens/colors.json, jamais recopiée."""

    try:
        _, theme, jeton = reference.split(":", 2)
    except ValueError as erreur:
        raise Refus(f"{contexte} : référence de jeton {reference!r} mal formée") from erreur
    jetons = json.loads(COULEURS.read_text(encoding="utf-8")).get("tokens", {})
    valeur = jetons.get(jeton, {}).get(theme)
    if valeur is None:
        raise Refus(f"{contexte} : le jeton {jeton!r} n'a pas de valeur pour le thème {theme!r}")
    return couleur(valeur, contexte)


def charger_palettes(manifeste: dict) -> Dict[str, Dict[str, Pixel]]:
    palettes: Dict[str, Dict[str, Pixel]] = {}
    for nom, table in manifeste.get("palettes", {}).items():
        if nom.startswith("$"):
            continue
        if not isinstance(table, dict):
            raise Refus(f"palette {nom!r} : objet attendu")
        entrees: Dict[str, Pixel] = {".": _TRANSPARENT}
        for cle, valeur in table.items():
            if cle.startswith("$"):
                continue
            if len(cle) != 1 or cle == "." or cle.isspace():
                raise Refus(f"palette {nom!r} : clé {cle!r} invalide (un caractère, ni « . » ni espace)")
            contexte = f"palette {nom!r}, clé {cle!r}"
            if isinstance(valeur, str) and valeur.startswith("jeton:"):
                entrees[cle] = couleur_de_jeton(valeur, contexte)
            else:
                entrees[cle] = couleur(valeur, contexte)
        palettes[nom] = entrees
    if not palettes:
        raise Refus("manifeste : aucune palette déclarée")
    return palettes


def lire_images(chemin: Path) -> Dict[str, List[str]]:
    """Lit un fichier source : une ou plusieurs images nommées ``== nom`` ; ``#`` commente une ligne."""

    if not chemin.is_file():
        raise Refus(f"source introuvable : {chemin.relative_to(RACINE)}")
    images: Dict[str, List[str]] = {}
    courante: Optional[str] = None
    for numero, brute in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        ligne = brute.rstrip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.startswith("=="):
            courante = ligne[2:].strip()
            if not courante or courante in images:
                raise Refus(f"{chemin.name}:{numero} : nom d'image vide ou en double")
            images[courante] = []
            continue
        if courante is None:
            raise Refus(f"{chemin.name}:{numero} : ligne de pixels avant tout en-tête « == nom »")
        images[courante].append(ligne)
    for nom, lignes in images.items():
        if not lignes:
            raise Refus(f"{chemin.name} : l'image {nom!r} est vide")
        largeurs = {len(ligne) for ligne in lignes}
        if len(largeurs) != 1:
            raise Refus(f"{chemin.name} : l'image {nom!r} a des lignes de largeurs différentes {sorted(largeurs)}")
    return images


def grille(lignes: Sequence[str], palette: Dict[str, Pixel], contexte: str) -> Grille:
    resultat: Grille = []
    for y, ligne in enumerate(lignes):
        rangee: List[Pixel] = []
        for x, caractere in enumerate(ligne):
            if caractere not in palette:
                raise Refus(f"{contexte} : caractère {caractere!r} absent de la palette (x={x}, y={y})")
            rangee.append(palette[caractere])
        resultat.append(rangee)
    return resultat


def agrandir(source: Grille, echelle: int) -> Grille:
    if echelle < 1:
        raise Refus(f"échelle {echelle} invalide")
    sortie: Grille = []
    for rangee in source:
        etiree = [pixel for pixel in rangee for _ in range(echelle)]
        sortie.extend([list(etiree) for _ in range(echelle)])
    return sortie


def dimensions(image: Grille) -> Tuple[int, int]:
    return (len(image[0]) if image else 0, len(image))


# --- PNG : écriture et lecture -------------------------------------------------------------------


def _bloc(type_bloc: bytes, donnees: bytes) -> bytes:
    return (struct.pack(">I", len(donnees)) + type_bloc + donnees
            + struct.pack(">I", zlib.crc32(type_bloc + donnees) & 0xFFFFFFFF))


def encoder_png(image: Grille) -> bytes:
    largeur, hauteur = dimensions(image)
    brut = bytearray()
    for rangee in image:
        brut.append(0)  # filtre « aucun » : sortie stable et simple à relire
        for r, g, b, a in rangee:
            brut.extend((r, g, b, a))
    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _bloc(b"IHDR", entete)
            + _bloc(b"IDAT", zlib.compress(bytes(brut), 9)) + _bloc(b"IEND", b""))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decoder_png(donnees: bytes) -> Grille:
    """Décode un PNG RGBA 8 bits non entrelacé (le seul format que ce script écrit)."""

    if donnees[:8] != b"\x89PNG\r\n\x1a\n":
        raise Refus("signature PNG absente")
    position, idat, entete = 8, bytearray(), None
    while position < len(donnees):
        (longueur,) = struct.unpack(">I", donnees[position:position + 4])
        type_bloc = donnees[position + 4:position + 8]
        contenu = donnees[position + 8:position + 8 + longueur]
        position += 12 + longueur
        if type_bloc == b"IHDR":
            entete = struct.unpack(">IIBBBBB", contenu)
        elif type_bloc == b"IDAT":
            idat.extend(contenu)
        elif type_bloc == b"IEND":
            break
    if entete is None:
        raise Refus("bloc IHDR absent")
    largeur, hauteur, profondeur, type_couleur, _, _, entrelace = entete
    if (profondeur, type_couleur, entrelace) != (8, 6, 0):
        raise Refus("seul le RGBA 8 bits non entrelacé est relu")
    brut = zlib.decompress(bytes(idat))
    pas = largeur * 4
    precedente = bytearray(pas)
    image: Grille = []
    for y in range(hauteur):
        debut = y * (pas + 1)
        filtre, ligne = brut[debut], bytearray(brut[debut + 1:debut + 1 + pas])
        for i in range(pas):
            gauche = ligne[i - 4] if i >= 4 else 0
            haut = precedente[i]
            diag = precedente[i - 4] if i >= 4 else 0
            if filtre == 1:
                ligne[i] = (ligne[i] + gauche) & 0xFF
            elif filtre == 2:
                ligne[i] = (ligne[i] + haut) & 0xFF
            elif filtre == 3:
                ligne[i] = (ligne[i] + ((gauche + haut) >> 1)) & 0xFF
            elif filtre == 4:
                ligne[i] = (ligne[i] + _paeth(gauche, haut, diag)) & 0xFF
            elif filtre != 0:
                raise Refus(f"filtre PNG {filtre} inconnu")
        image.append([tuple(ligne[x * 4:x * 4 + 4]) for x in range(largeur)])  # type: ignore[misc]
        precedente = ligne
    return image


# --- ICO -----------------------------------------------------------------------------------------


def _encoder_dib(image: Grille) -> bytes:
    """Entrée DIB d'icône : BITMAPINFOHEADER (hauteur doublée), BGRA de bas en haut, masque ET à zéro."""

    largeur, hauteur = dimensions(image)
    entete = struct.pack("<IiiHHIIiiII", 40, largeur, hauteur * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    couleurs = b"".join(bytes((b, g, r, a)) for rangee in reversed(image) for r, g, b, a in rangee)
    # Masque ET : un bit par pixel, rangées alignées sur 32 bits. L'alpha fait foi (32 bits).
    masque = bytes(((largeur + 31) // 32) * 4 * hauteur)
    return entete + couleurs + masque


def _decoder_dib(donnees: bytes) -> Grille:
    taille_entete, largeur, hauteur_double, _, bits, compression = struct.unpack("<IiiHHI", donnees[:20])
    if taille_entete != 40 or bits != 32 or compression != 0 or hauteur_double != largeur * 2:
        raise Refus("entrée DIB d'icône : seul le BGRA 32 bits non compressé est relu")
    hauteur = hauteur_double // 2
    pixels = donnees[40:40 + largeur * hauteur * 4]
    rangees = []
    for y in range(hauteur):
        ligne = pixels[y * largeur * 4:(y + 1) * largeur * 4]
        rangees.append([(ligne[x + 2], ligne[x + 1], ligne[x], ligne[x + 3]) for x in range(0, len(ligne), 4)])
    return list(reversed(rangees))


def encoder_ico(images: Sequence[Grille]) -> bytes:
    """ICONDIR + entrées 32 bits : DIB jusqu'à 128 px, PNG pour 256 px.

    Microsoft recommande la compression PNG pour la seule entrée 256 px (« Icons », Windows App
    Development) : les entrées plus petites restent en DIB, lues par tous les composants de Windows
    (explorateur, barre des tâches, rc.exe, Inno Setup)."""

    for image in images:
        largeur, hauteur = dimensions(image)
        if largeur != hauteur or largeur > 256:
            raise Refus(f"entrée d'icône {largeur}×{hauteur} : carrée et au plus 256 px")
    corps = [encoder_png(image) if dimensions(image)[0] == 256 else _encoder_dib(image) for image in images]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire = bytearray()
    for image, contenu in zip(images, corps):
        largeur, hauteur = dimensions(image)
        repertoire.extend(struct.pack("<BBBBHHII", largeur % 256, hauteur % 256, 0, 0, 1, 32, len(contenu), decalage))
        decalage += len(contenu)
    return entete + bytes(repertoire) + b"".join(corps)


def decoder_ico(donnees: bytes) -> List[Grille]:
    reserve, type_ico, nombre = struct.unpack("<HHH", donnees[:6])
    if reserve != 0 or type_ico != 1:
        raise Refus("en-tête ICO invalide")
    images = []
    for i in range(nombre):
        _, _, _, _, _, _, taille, decalage = struct.unpack("<BBBBHHII", donnees[6 + 16 * i:22 + 16 * i])
        contenu = donnees[decalage:decalage + taille]
        images.append(decoder_png(contenu) if contenu.startswith(b"\x89PNG") else _decoder_dib(contenu))
    return images


# --- Construction des sorties --------------------------------------------------------------------


class Sorties:
    """Accumule les sorties (chemin relatif -> contenu attendu) avant toute écriture."""

    def __init__(self) -> None:
        self.images: Dict[str, Grille] = {}
        self.icones: Dict[str, List[Grille]] = {}
        self.textes: Dict[str, str] = {}

    def chemins(self) -> List[str]:
        return sorted([*self.images, *self.icones, *self.textes])

    def ajouter(self, table: dict, chemin: str, valeur) -> None:
        if chemin in self.images or chemin in self.icones or chemin in self.textes:
            raise Refus(f"sortie {chemin} déclarée deux fois")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", chemin) or ".." in chemin or chemin.startswith("/"):
            raise Refus(f"sortie {chemin!r} : chemin relatif confiné attendu")
        table[chemin] = valeur


def json_canonique(objet: object) -> str:
    return json.dumps(objet, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def construire(manifeste: dict) -> Sorties:
    palettes = charger_palettes(manifeste)
    sorties = Sorties()
    sources: Dict[str, Dict[str, List[str]]] = {}

    def image(source: str, nom, palette: str) -> Grille:
        """Une image nommée, ou la superposition d'une liste de calques (« . » laisse voir dessous)."""

        if palette not in palettes:
            raise Refus(f"palette {palette!r} inconnue")
        if source not in sources:
            sources[source] = lire_images(RACINE / "design" / "pixel" / source)
        noms = [nom] if isinstance(nom, str) else list(nom)
        if not noms:
            raise Refus(f"{source} : liste de calques vide")
        resultat: Optional[Grille] = None
        for calque in noms:
            if calque not in sources[source]:
                raise Refus(f"{source} : image {calque!r} absente")
            lignes = sources[source][calque]
            couche = grille(lignes, palettes[palette], f"{source}:{calque}")
            if resultat is None:
                resultat = couche
                continue
            if dimensions(couche) != dimensions(resultat):
                raise Refus(f"{source} : le calque {calque!r} n'a pas la taille de {noms[0]!r}")
            for y, ligne in enumerate(lignes):
                for x, caractere in enumerate(ligne):
                    if caractere != ".":
                        resultat[y][x] = couche[y][x]
        assert resultat is not None
        return resultat

    # Emblème : chaque taille d'export vient d'une grille dessinée pour elle, à échelle entière.
    for export in manifeste.get("embleme", {}).get("exports", []):
        base = image(export["source"], export["image"], export["palette"])
        sortie = agrandir(base, int(export["echelle"]))
        largeur, hauteur = dimensions(sortie)
        if largeur != hauteur or largeur != int(export["taille"]):
            raise Refus(f"emblème {export['fichier']} : {largeur}×{hauteur} au lieu de {export['taille']} px")
        sorties.ajouter(sorties.images, export["fichier"], sortie)

    icone = manifeste.get("icone")
    if icone:
        entrees = []
        tailles = []
        for entree in icone["entrees"]:
            base = image(entree["source"], entree["image"], entree["palette"])
            agrandie = agrandir(base, int(entree["echelle"]))
            entrees.append(agrandie)
            tailles.append(dimensions(agrandie)[0])
        if tuple(sorted(tailles)) != TAILLES_ICO:
            raise Refus(f"icône : tailles {sorted(tailles)} au lieu de {list(TAILLES_ICO)}")
        sorties.ajouter(sorties.icones, icone["fichier"], [entrees[tailles.index(t)] for t in TAILLES_ICO])

    # Planches : cases de même taille, une rangée par séquence ; métadonnées JSON à côté.
    listes = {nom: valeur for nom, valeur in manifeste.get("listes", {}).items() if not nom.startswith("$")}

    def images_de(sequence: dict) -> list:
        images = sequence["images"]
        if isinstance(images, str):
            if not images.startswith("@") or images[1:] not in listes:
                raise Refus(f"séquence {sequence.get('id')!r} : liste {images!r} inconnue")
            return listes[images[1:]]
        return images

    resume_qml: Dict[str, dict] = {}
    for planche in manifeste.get("planches", []):
        case_l, case_h = int(planche["case"][0]), int(planche["case"][1])
        echelle = int(planche.get("echelle", 1))
        sequences = [dict(sequence, images=images_de(sequence), liste=sequence["images"] if isinstance(sequence["images"], str) else None)
                     for sequence in planche["sequences"]]
        colonnes = max(len(sequence["images"]) for sequence in sequences)
        largeur, hauteur = colonnes * case_l * echelle, len(sequences) * case_h * echelle
        if largeur > PLAFOND_PLANCHE or hauteur > PLAFOND_PLANCHE:
            raise Refus(f"planche {planche['id']} : {largeur}×{hauteur} dépasse {PLAFOND_PLANCHE} px")
        toile: Grille = [[_TRANSPARENT] * largeur for _ in range(hauteur)]
        meta_sequences = []
        listes_meta: Dict[str, list] = {}
        glyphes: Dict[str, int] = {}
        for rang, sequence in enumerate(sequences):
            images_meta = []
            for colonne, trame in enumerate(sequence["images"]):
                base = image(planche["source"], trame["image"], sequence.get("palette", planche["palette"]))
                bl, bh = dimensions(base)
                if (bl, bh) != (case_l, case_h):
                    raise Refus(f"planche {planche['id']} : {trame['image']} mesure {bl}×{bh}, case {case_l}×{case_h}")
                agrandie = agrandir(base, echelle)
                ox, oy = colonne * case_l * echelle, rang * case_h * echelle
                for y, rangee in enumerate(agrandie):
                    toile[oy + y][ox:ox + len(rangee)] = rangee
                duree = int(trame.get("duree", 0))
                if duree and not 60 <= duree <= 4000:
                    raise Refus(f"planche {planche['id']} : durée {duree} ms hors de [60, 4000]")
                nom_trame = trame["image"] if isinstance(trame["image"], str) else "+".join(trame["image"])
                images_meta.append({"image": nom_trame, "duree": duree})
                if "car" in trame:
                    car = trame["car"]
                    if not isinstance(car, str) or len(car) != 1:
                        raise Refus(f"planche {planche['id']} : caractère {car!r} invalide")
                    if glyphes.get(car, colonne) != colonne:
                        raise Refus(f"planche {planche['id']} : le caractère {car!r} change de colonne")
                    glyphes[car] = colonne
            if sequence["liste"]:
                listes_meta.setdefault(sequence["liste"][1:], images_meta)
            meta_sequences.append({
                "id": sequence["id"],
                "rang": rang,
                "etat": sequence.get("etat", ""),
                "boucle": bool(sequence.get("boucle", False)),
                "decoratif": bool(sequence.get("decoratif", False)),
                "images": images_meta,
            })
        sorties.ajouter(sorties.images, planche["fichier"], toile)
        meta = {
            "$schema": "acp.pixel-planche/1",
            "$source": f"design/pixel/{planche['source']}",
            "$genere": "scripts/generer_assets_pixel.py — NE PAS MODIFIER À LA MAIN",
            "id": planche["id"],
            "case": [case_l * echelle, case_h * echelle],
            "echelleSource": echelle,
            "colonnes": colonnes,
            "sequences": [
                dict(s, images=f"@{nom}") if nom else s
                for s, nom in zip(meta_sequences, [seq["liste"][1:] if seq["liste"] else None for seq in sequences])
            ],
        }
        if listes_meta:
            meta["listes"] = listes_meta
        if glyphes:
            meta["glyphes"] = glyphes
        sorties.ajouter(sorties.textes, planche["metadonnees"], json_canonique(meta))
        resume_qml[planche["id"]] = {
            "fichier": Path(planche["fichier"]).name,
            "case": [case_l * echelle, case_h * echelle],
            "colonnes": colonnes,
            "sequences": {
                s["id"]: {"rang": s["rang"], "etat": s["etat"], "boucle": s["boucle"], "decoratif": s["decoratif"],
                          "durees": [image["duree"] for image in s["images"]]}
                for s in meta_sequences
            },
            **({"glyphes": glyphes} if glyphes else {}),
        }

    qml = manifeste.get("qml")
    if qml:
        tailles = sorted(int(export["taille"]) for export in manifeste.get("embleme", {}).get("exports", []))
        resume_qml["embleme"] = {"tailles": tailles}
        sorties.ajouter(sorties.textes, qml["fichier"], singleton_qml(qml["singleton"], resume_qml))
    return sorties


def singleton_qml(nom: str, resume: Dict[str, dict]) -> str:
    """Singleton QML des métadonnées de planches : la vue lit un rang et des durées, jamais un chemin libre."""

    lignes = [
        "// Fichier généré — NE PAS MODIFIER À LA MAIN.",
        "// Source    : design/pixel/manifeste.json et design/pixel/sources/*.txt",
        "// Générateur : scripts/generer_assets_pixel.py",
        "",
        "pragma Singleton",
        "",
        "import QtQuick",
        "",
        "QtObject {",
    ]
    for cle in sorted(resume):
        texte = json.dumps(resume[cle], ensure_ascii=False, sort_keys=True, separators=(", ", ": "))
        # Une liaison qui commence par « { » serait lue comme un bloc : l'objet est entre parenthèses.
        lignes.append(f"    readonly property var {cle}: ({texte})")
    lignes.append("}")
    return "\n".join(lignes) + "\n"


# --- Écriture et contrôle ------------------------------------------------------------------------


def verifier(sorties: Sorties) -> List[str]:
    perimes: List[str] = []
    for chemin, attendue in sorties.images.items():
        fichier = RACINE / chemin
        if not fichier.is_file():
            perimes.append(f"{chemin} : absent")
        elif decoder_png(fichier.read_bytes()) != attendue:
            perimes.append(f"{chemin} : pixels différents")
    for chemin, attendues in sorties.icones.items():
        fichier = RACINE / chemin
        if not fichier.is_file():
            perimes.append(f"{chemin} : absent")
        elif decoder_ico(fichier.read_bytes()) != attendues:
            perimes.append(f"{chemin} : entrées différentes")
    for chemin, attendu in sorties.textes.items():
        fichier = RACINE / chemin
        if not fichier.is_file():
            perimes.append(f"{chemin} : absent")
        elif fichier.read_text(encoding="utf-8").replace("\r\n", "\n") != attendu:
            perimes.append(f"{chemin} : contenu périmé")
    return perimes


def ecrire(sorties: Sorties) -> None:
    for chemin, image in sorties.images.items():
        (RACINE / chemin).parent.mkdir(parents=True, exist_ok=True)
        (RACINE / chemin).write_bytes(encoder_png(image))
    for chemin, images in sorties.icones.items():
        (RACINE / chemin).parent.mkdir(parents=True, exist_ok=True)
        (RACINE / chemin).write_bytes(encoder_ico(images))
    for chemin, texte in sorties.textes.items():
        (RACINE / chemin).parent.mkdir(parents=True, exist_ok=True)
        (RACINE / chemin).write_text(texte, encoding="utf-8", newline="\n")


def main(arguments: Sequence[str]) -> int:
    analyseur = argparse.ArgumentParser(description="Génère les assets pixel art d'ACP depuis design/pixel.")
    analyseur.add_argument("--check", action="store_true", help="ne rien écrire ; échouer si une sortie est périmée")
    analyseur.add_argument("--manifeste", type=Path, default=MANIFESTE, help=argparse.SUPPRESS)
    options = analyseur.parse_args(arguments)
    try:
        manifeste = json.loads(options.manifeste.read_text(encoding="utf-8"))
        sorties = construire(manifeste)
    except (Refus, KeyError, ValueError, OSError) as erreur:
        print(f"REFUS : {erreur}", file=sys.stderr)
        return 1
    if options.check:
        try:
            perimes = verifier(sorties)
        except Refus as erreur:
            print(f"REFUS : {erreur}", file=sys.stderr)
            return 1
        if perimes:
            print("REFUS : les assets versionnés ne correspondent plus à leurs sources.", file=sys.stderr)
            for ligne in perimes:
                print(f"  - {ligne}", file=sys.stderr)
            print("  Régénérez avec : python scripts/generer_assets_pixel.py", file=sys.stderr)
            return 1
        print(f"{len(sorties.chemins())} assets pixel à jour.")
        return 0
    ecrire(sorties)
    print(f"{len(sorties.chemins())} assets pixel écrits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
