"""Détecteur de capture blanche de parcours.py (relecture de P3 : la capture « portail » du format
bureau était une page blanche de 5 851 octets, prise avant le rendu du formulaire). Sans navigateur
ni pile : PNG synthétiques écrits par la bibliothèque standard."""

from __future__ import annotations

import struct
import zlib

import pytest

from parcours import png_uniforme


def _png(largeur: int, hauteur: int, pixel) -> bytes:
    """PNG RVB 8 bits, filtre 0 sur chaque ligne ; ``pixel(x, y)`` rend (r, v, b)."""
    brut = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(largeur)) for y in range(hauteur))

    def bloc(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(brut))
            + bloc(b"IEND", b""))


def test_une_page_blanche_est_uniforme():
    assert png_uniforme(_png(64, 48, lambda x, y: (255, 255, 255)))


def test_une_page_rendue_ne_l_est_pas():
    # Texte lissé : des dizaines de niveaux de gris sur un fond clair.
    assert not png_uniforme(_png(64, 48, lambda x, y: ((x * 7 + y * 3) % 256,) * 3))


def test_un_fichier_qui_n_est_pas_un_png_est_refuse():
    with pytest.raises(ValueError):
        png_uniforme(b"GIF89a")
