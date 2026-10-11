"""Générateur des assets pixel art (scripts/generer_assets_pixel.py) : sorties à jour, icône Windows
multirésolution, PNG relus pixel par pixel, couleurs tirées des jetons, refus explicites en français
et dérive détectée par ``--check`` sans rien écrire. Bibliothèque standard seulement, comme le script."""

from __future__ import annotations

import importlib.util
import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("generer_assets_pixel", RACINE / "scripts" / "generer_assets_pixel.py")
assert _SPEC is not None and _SPEC.loader is not None
gap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gap)

MANIFESTE = json.loads((RACINE / "design" / "pixel" / "manifeste.json").read_text(encoding="utf-8"))
ICONE = RACINE / "apps" / "desktop" / "resources" / "windows" / "AgentCompanyPlatform.ico"


def _couleur_jeton(theme: str, jeton: str) -> tuple:
    jetons = json.loads((RACINE / "design" / "tokens" / "colors.json").read_text(encoding="utf-8"))["tokens"]
    return gap.couleur(jetons[jeton][theme], "test")


@pytest.fixture
def racine_jetable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Une racine de dépôt jetable : sources copiées, sorties écrites ailleurs que dans le dépôt."""

    shutil.copytree(RACINE / "design" / "pixel", tmp_path / "design" / "pixel")
    monkeypatch.setattr(gap, "RACINE", tmp_path)
    return tmp_path


def test_les_assets_versionnes_sont_a_jour(capsys: pytest.CaptureFixture[str]):
    assert gap.main(["--check"]) == 0
    assert "assets pixel à jour" in capsys.readouterr().out


def test_icone_windows_porte_toutes_les_tailles_nettes():
    entrees = gap.decoder_ico(ICONE.read_bytes())
    assert [gap.dimensions(image) for image in entrees] == [(t, t) for t in gap.TAILLES_ICO]
    for image in entrees:
        alphas = {pixel[3] for rangee in image for pixel in rangee}
        # Pixel art : chaque pixel est plein ou transparent, jamais lissé.
        assert alphas <= {0, 255}
        assert 255 in alphas
    par_taille = dict(zip(gap.TAILLES_ICO, entrees))
    # Les grandes tailles sont des multiples entiers de la grille 32 (plus proche voisin).
    assert par_taille[64] == gap.agrandir(par_taille[32], 2)
    assert par_taille[256] == gap.agrandir(par_taille[32], 8)
    # 16, 20, 24 et 32 sont dessinées pour elles-mêmes : jamais une réduction de la grande.
    assert par_taille[16] != par_taille[32][::2]


def test_les_png_de_l_embleme_suivent_leur_nom():
    for export in MANIFESTE["embleme"]["exports"]:
        image = gap.decoder_png((RACINE / export["fichier"]).read_bytes())
        assert gap.dimensions(image) == (export["taille"], export["taille"]), export["fichier"]


def _png_filtre(image: list) -> bytes:
    """PNG RGBA dont chaque rangée utilise un filtre différent (0 à 4), comme un outil tiers peut l'écrire."""

    largeur, hauteur = len(image[0]), len(image)
    brut = [bytes(c for pixel in rangee for c in pixel) for rangee in image]
    donnees = bytearray()
    precedente = bytes(largeur * 4)
    for y, rangee in enumerate(brut):
        filtre = y % 5
        donnees.append(filtre)
        for x, valeur in enumerate(rangee):
            a = rangee[x - 4] if x >= 4 else 0
            b = precedente[x]
            c = precedente[x - 4] if x >= 4 else 0
            if filtre == 0:
                predit = 0
            elif filtre == 1:
                predit = a
            elif filtre == 2:
                predit = b
            elif filtre == 3:
                predit = (a + b) // 2
            else:
                predit = gap._paeth(a, b, c)
            donnees.append((valeur - predit) & 0xFF)
        precedente = rangee

    def bloc(type_bloc: bytes, contenu: bytes) -> bytes:
        return struct.pack(">I", len(contenu)) + type_bloc + contenu + struct.pack(">I", zlib.crc32(type_bloc + contenu))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(bytes(donnees))) + bloc(b"IEND", b"")


def test_png_relu_pixel_par_pixel_quel_que_soit_le_filtre():
    image = [[((x * 37 + y * 11) % 256, (x * 5) % 256, (y * 29) % 256, 255 if (x + y) % 3 else 0) for x in range(7)]
             for y in range(10)]
    assert gap.decoder_png(gap.encoder_png(image)) == image
    assert gap.decoder_png(_png_filtre(image)) == image
    with pytest.raises(gap.Refus, match="signature PNG absente"):
        gap.decoder_png(b"pas un png")


def test_police_couvre_les_glyphes_et_tire_ses_couleurs_des_jetons():
    police = json.loads((RACINE / "design" / "pixel" / "generes" / "police.json").read_text(encoding="utf-8"))
    attendus = {trame["car"] for trame in MANIFESTE["listes"]["glyphes"]}
    assert set(police["glyphes"]) == attendus
    for caractere in "ÉÈÊËÀÂÎÏÔÙÛÜÇ?!":
        assert caractere in police["glyphes"]
    # Une séquence par thème et par couleur ; la couleur de l'encre est celle du jeton, jamais recopiée.
    themes = json.loads((RACINE / "design" / "tokens" / "colors.json").read_text(encoding="utf-8"))["$themes"]
    for theme in themes:
        for teinte in ("texte", "attenue", "accent"):
            assert any(s["id"] == f"{theme}.{teinte}" for s in police["sequences"])
    palettes = gap.charger_palettes(MANIFESTE)
    assert palettes["police-atelier-nuit-texte"]["X"] == _couleur_jeton("atelier-nuit", "text.primary")
    assert palettes["police-studio-papier-accent"]["X"] == _couleur_jeton("studio-papier", "accent.primary")


def test_portraits_couvrent_chaque_role_et_chaque_etat():
    portraits = json.loads((RACINE / "design" / "pixel" / "generes" / "portraits.json").read_text(encoding="utf-8"))
    ids = {s["id"]: s for s in portraits["sequences"]}
    for role in ("coordinateur", "developpeur", "relecteur", "explorateur", "testeur", "inconnu"):
        for etat in ("repos", "travail", "attente", "echec", "termine", "arrete"):
            assert f"{role}.{etat}" in ids
    # Seuls le travail observé et l'ambiance au repos bouclent ; l'ambiance est marquée décorative.
    assert ids["developpeur.travail"]["boucle"] and not ids["developpeur.travail"]["decoratif"]
    assert ids["developpeur.repos"]["decoratif"]
    assert not ids["developpeur.echec"]["boucle"]


def test_singleton_qml_genere():
    texte = (RACINE / MANIFESTE["qml"]["fichier"]).read_text(encoding="utf-8")
    assert texte.startswith("// Fichier généré — NE PAS MODIFIER À LA MAIN.")
    assert "pragma Singleton" in texte
    for cle in ("embleme", "pictogrammes", "police", "portraits"):
        assert f"readonly property var {cle}: (" in texte


def test_sources_editables_en_lf_sans_tabulation():
    for chemin in sorted((RACINE / "design" / "pixel").rglob("*")):
        if chemin.is_file() and chemin.suffix in {".txt", ".json"}:
            octets = chemin.read_bytes()
            assert b"\r\n" not in octets and b"\t" not in octets, chemin
            assert octets.endswith(b"\n"), chemin


def test_check_detecte_une_derive_sans_rien_ecrire(racine_jetable: Path, capsys: pytest.CaptureFixture[str]):
    sorties = gap.construire(MANIFESTE)
    # Toutes les sorties absentes de la racine jetable.
    assert all(ligne.endswith(": absent") for ligne in gap.verifier(sorties))
    gap.ecrire(sorties)
    assert gap.verifier(sorties) == []
    # Un pixel changé dans une planche, une ligne changée dans le singleton.
    planche = racine_jetable / "apps" / "desktop" / "qml" / "pixel" / "assets" / "portraits.png"
    image = gap.decoder_png(planche.read_bytes())
    image[3][3] = (1, 2, 3, 255)
    planche.write_bytes(gap.encoder_png(image))
    singleton = racine_jetable / MANIFESTE["qml"]["fichier"]
    singleton.write_text(singleton.read_text(encoding="utf-8") + "// ajout\n", encoding="utf-8")
    assert sorted(gap.verifier(sorties)) == sorted([
        "apps/desktop/qml/pixel/assets/portraits.png : pixels différents",
        f"{MANIFESTE['qml']['fichier']} : contenu périmé",
    ])
    avant = planche.read_bytes()
    assert gap.main(["--check"]) == 1
    erreurs = capsys.readouterr().err
    assert "REFUS : les assets versionnés ne correspondent plus à leurs sources." in erreurs
    assert "python scripts/generer_assets_pixel.py" in erreurs
    assert planche.read_bytes() == avant  # --check n'écrit rien


def test_fins_de_ligne_crlf_toleres_pour_le_texte(racine_jetable: Path):
    sorties = gap.construire(MANIFESTE)
    gap.ecrire(sorties)
    singleton = racine_jetable / MANIFESTE["qml"]["fichier"]
    singleton.write_bytes(singleton.read_bytes().replace(b"\n", b"\r\n"))
    assert gap.verifier(sorties) == []


def _manifeste_minimal(source: str = "sources/essai.txt", **planche) -> dict:
    return {
        "palettes": {"p": {"A": "#ff0000", "B": "#00ff00"}},
        "planches": [dict({
            "id": "essai", "source": source, "palette": "p", "case": [2, 2],
            "fichier": "sortie/essai.png", "metadonnees": "sortie/essai.json",
            "sequences": [{"id": "s", "images": [{"image": "un", "duree": 200}]}],
        }, **planche)],
    }


def _ecrire_source(racine: Path, texte: str, nom: str = "essai.txt") -> None:
    (racine / "design" / "pixel" / "sources" / nom).write_text(texte, encoding="utf-8")


def test_manifeste_minimal_construit(racine_jetable: Path):
    _ecrire_source(racine_jetable, "== un\nAB\nB.\n")
    sorties = gap.construire(_manifeste_minimal())
    assert sorties.chemins() == ["sortie/essai.json", "sortie/essai.png"]
    assert sorties.images["sortie/essai.png"] == [[(255, 0, 0, 255), (0, 255, 0, 255)], [(0, 255, 0, 255), (0, 0, 0, 0)]]


@pytest.mark.parametrize(
    ("source", "manifeste", "message"),
    [
        ("== un\nAB\nB\n", None, "lignes de largeurs différentes"),
        ("AB\nBA\n", None, "ligne de pixels avant tout en-tête"),
        ("== un\nAB\n== un\nAB\n", None, "nom d'image vide ou en double"),
        ("== un\nAZ\nBA\n", None, "caractère 'Z' absent de la palette"),
        ("== un\nABA\nBAB\n", None, "mesure 3×2, case 2×2"),
        ("== un\nAB\nBA\n", {"sequences": [{"id": "s", "images": [{"image": "un", "duree": 5000}]}]},
         "durée 5000 ms hors de [60, 4000]"),
        ("== un\nAB\nBA\n", {"sequences": [{"id": "s", "images": [{"image": "deux"}]}]}, "image 'deux' absente"),
        ("== un\nAB\nBA\n", {"sequences": [{"id": "s", "images": "@absente"}]}, "liste '@absente' inconnue"),
        ("== un\nAB\nBA\n", {"fichier": "../hors.png"}, "chemin relatif confiné attendu"),
        ("== un\nAB\nBA\n", {"metadonnees": "sortie/essai.png"}, "déclarée deux fois"),
        ("== un\nAB\nBA\n", {"palette": "absente"}, "palette 'absente' inconnue"),
    ],
)
def test_refus_explicites(racine_jetable: Path, source: str, manifeste: dict | None, message: str):
    _ecrire_source(racine_jetable, source)
    with pytest.raises(gap.Refus, match=message.replace("[", r"\[").replace("]", r"\]").replace("(", r"\(")):
        gap.construire(_manifeste_minimal(**(manifeste or {})))


def test_refus_de_palette_et_de_jeton():
    with pytest.raises(gap.Refus, match="clé 'AB' invalide"):
        gap.charger_palettes({"palettes": {"p": {"AB": "#000000"}}})
    with pytest.raises(gap.Refus, match="clé '.' invalide"):
        gap.charger_palettes({"palettes": {"p": {".": "#000000"}}})
    with pytest.raises(gap.Refus, match="couleur attendue en #rrggbb"):
        gap.charger_palettes({"palettes": {"p": {"A": "rouge"}}})
    with pytest.raises(gap.Refus, match="n'a pas de valeur pour le thème 'atelier-nuit'"):
        gap.charger_palettes({"palettes": {"p": {"A": "jeton:atelier-nuit:inexistant"}}})
    with pytest.raises(gap.Refus, match="n'a pas de valeur pour le thème 'theme-absent'"):
        gap.charger_palettes({"palettes": {"p": {"A": "jeton:theme-absent:text.primary"}}})
    with pytest.raises(gap.Refus, match="aucune palette déclarée"):
        gap.charger_palettes({"palettes": {}})


def test_refus_d_une_icone_incomplete():
    manifeste = dict(MANIFESTE, embleme={}, planches=[], qml=None)
    manifeste["icone"] = dict(MANIFESTE["icone"], entrees=MANIFESTE["icone"]["entrees"][:-1])
    with pytest.raises(gap.Refus, match="icône : tailles"):
        gap.construire(manifeste)
    with pytest.raises(gap.Refus, match="carrée et au plus 256 px"):
        gap.encoder_ico([[[(0, 0, 0, 0)] * 300] * 300])


def test_refus_rend_un_code_un_en_francais(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    faux = tmp_path / "manifeste.json"
    faux.write_text(json.dumps({"palettes": {}}), encoding="utf-8")
    assert gap.main(["--check", "--manifeste", str(faux)]) == 1
    assert capsys.readouterr().err.startswith("REFUS : manifeste : aucune palette déclarée")
