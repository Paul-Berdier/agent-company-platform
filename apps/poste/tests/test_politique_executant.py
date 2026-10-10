"""Politique de l'exécutant Linux : ``executant.toml`` (cahier P6 § 7.2, décision D78).

Le fichier versionné du dépôt est lu tel quel (refusé tant que son origine vaut le gabarit, comme l'IaC), puis avec
une origine de test ; chaque refus du § 7.2 est éprouvé, et les droits du fichier et des binaires au démarrage.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pytest

from acp_poste.plateforme.linux import EmplacementsLinux
from acp_poste.politique import PolitiqueRefusee, analyser_executant, charger, verifier_droits
from acp_poste_contrat.inventaire import PolitiquePoste

RACINE_DEPOT = Path(__file__).resolve().parents[3]
VERSIONNEE = RACINE_DEPOT / "executant" / "politique" / "executant.toml"
POSIX = pytest.mark.skipif(os.name != "posix", reason="droits POSIX (propriétaire, modes) : Linux seulement")
ORIGINE_TEST = 'origine = "https://hermes-acp-test.up.railway.app"'


def _emplacements(tmp_path: Path) -> EmplacementsLinux:
    emplacements = EmplacementsLinux.de_test(tmp_path)
    for binaire in (emplacements.codex_par_defaut, emplacements.claude_par_defaut):
        binaire.parent.mkdir(parents=True, exist_ok=True)
        binaire.write_bytes(b"binaire factice")
    return emplacements


def _texte_valide(emplacements: EmplacementsLinux, *, depot: str = "", binaires: bool = False) -> str:
    """Le fichier versionné, origine de test ; ``binaires`` : exécutables de la racine jetable (Linux seulement : un
    chemin de Windows n'est pas un chemin POSIX absolu, et l'absence d'un binaire reste admise à la lecture)."""
    texte = re.sub(r'(?m)^origine = "[^"\n]*"$', ORIGINE_TEST, VERSIONNEE.read_text(encoding="utf-8"), count=1)
    if binaires:
        texte = texte.replace('"/opt/acp/outils/codex/codex"', f'"{emplacements.codex_par_defaut.as_posix()}"')
        texte = texte.replace('"/opt/acp/outils/claude/claude"', f'"{emplacements.claude_par_defaut.as_posix()}"')
    return texte + depot


DEPOT = """
[depots.jetable]
url = "https://github.com/proprietaire-factice/depot-jetable.git"
branche_base = "main"
acces = "jeton_lecture"
preparation = ["uv", "sync", "--frozen"]
verification = ["uv", "run", "pytest", "-q"]
"""


def _analyser(texte: str, emplacements: EmplacementsLinux):
    return analyser_executant(texte.encode("utf-8"), emplacements)


# ------------------------------------------------------------------ fichier versionné


def test_fichier_versionne_a_son_origine_de_production(tmp_path):
    politique = analyser_executant(VERSIONNEE.read_bytes(), _emplacements(tmp_path))
    assert politique.hermes.origine == "https://hermes-production-2d4e.up.railway.app"


def test_origine_au_gabarit_reste_refusee(tmp_path):
    with pytest.raises(PolitiqueRefusee, match=r"^executant\.toml : \[hermes\] origine vaut encore le gabarit"):
        texte = re.sub(r'(?m)^origine = "[^"\n]*"$',
                       'origine = "https://<libellé-hermes>.up.railway.app"', VERSIONNEE.read_text(), count=1)
        analyser_executant(texte.encode(), _emplacements(tmp_path))


def test_libelle_egal_a_celui_de_l_iac():
    origine = re.search(r'^origine = "https://([^"]+)\.up\.railway\.app"$',
                        VERSIONNEE.read_text(encoding="utf-8"), re.MULTILINE)
    iac = re.search(r'^const LIBELLE_HERMES = "([^"]+)";$',
                    (RACINE_DEPOT / ".railway" / "railway.ts").read_text(encoding="utf-8"), re.MULTILINE)
    assert origine and iac and origine.group(1) == iac.group(1)


def test_fichier_versionne_valide_avec_une_origine(tmp_path):
    emplacements = _emplacements(tmp_path)
    politique = _analyser(_texte_valide(emplacements), emplacements)
    assert politique.plateforme == "linux" and politique.nom_fichier == "executant.toml"
    assert politique.poste.compte == "uid_dedie" and politique.poste.nom == "Exécutant Railway"
    # D83 et D84 appliquées (consignées le 1er octobre 2026).
    assert politique.conditions == {"codex": date(2026, 10, 1), "claude": date(2026, 10, 1)}
    assert politique.codex.version_testee == "0.156.1" and politique.codex.sans_bac_a_sable == "refuse"
    assert politique.claude.version_testee == "2.1.283" and politique.claude.alias_permis == ("opus", "sonnet")
    assert politique.claude.authentification == "abonnement"
    assert politique.politique.cartes_par_jour == 20 and politique.politique.heures_agent_par_jour == 8
    assert politique.hermes_meme_enveloppe_que_codex is True
    assert politique.disque.seuil_libre_mio == 1024 and politique.git.hotes_admis == ("github.com",)
    assert (politique.git.auteur_nom, politique.git.auteur_courriel) == ("ACP exécutant", "executant@acp.invalid")
    assert politique.depots == ()
    resume = PolitiquePoste.model_validate(politique.resume_contrat())
    assert resume.conditions == {"codex": date(2026, 10, 1), "claude": date(2026, 10, 1)}
    assert (resume.cartes_par_jour, resume.duree_max_carte_s, resume.concurrence) == (20, 3600, 1)


def test_depot_distant_complet(tmp_path):
    emplacements = _emplacements(tmp_path)
    politique = _analyser(_texte_valide(emplacements, depot=DEPOT), emplacements)
    depot = politique.depot("jetable")
    assert depot.url.endswith("depot-jetable.git") and depot.branche_base == "main"
    assert depot.preparation == ("uv", "sync", "--frozen") and depot.verification == ("uv", "run", "pytest", "-q")
    assert (depot.verification_max_s, depot.reprises_verification) == (900, 2)
    assert depot.verification_sans_bac_a_sable is False and depot.liens_symboliques is False
    assert politique.depot("inconnu") is None


def test_charger_choisit_executant_toml_sous_linux(tmp_path):
    emplacements = _emplacements(tmp_path)
    emplacements.politique.parent.mkdir(parents=True)
    with pytest.raises(PolitiqueRefusee, match="executant.toml absent"):
        charger(emplacements)
    emplacements.politique.write_text(_texte_valide(emplacements), encoding="utf-8")
    assert charger(emplacements).plateforme == "linux"


# ------------------------------------------------------------------ refus


@pytest.mark.parametrize(("remplacer", "par", "motif"), [
    ('compte = "uid_dedie"', 'compte = "dedie"', "uid_dedie"),
    ('compte = "uid_dedie"', 'compte = "proprietaire"', "uid_dedie"),
    ('sans_bac_a_sable = "refuse"', 'bac_a_sable = "elevated"', r"clé inconnue \[codex\] bac_a_sable"),
    ('sans_bac_a_sable = "refuse"', 'sans_bac_a_sable = "tout"', "sans_bac_a_sable"),
    ('sans_bac_a_sable = "refuse"', 'sans_bac_a_sable = "acces_complet"', "non prise en charge en P6"),
    ('sans_bac_a_sable = "refuse"', 'sans_bac_a_sable = "edition_seule"', "non prise en charge en P6"),
    ('authentification = "abonnement"', 'authentification = "cle_api"', "non prise en charge"),
    ('codex_decide_le = "2026-10-01"', 'codex_decide_le = "01/10/2026"', "AAAA-MM-JJ"),
    ('home = "/donnees/codex"', 'home = "donnees/codex"', "chemin absolu POSIX"),
    ('home = "/donnees/codex"', 'home = "/donnees/../etc"', "sans « .. »"),
    ('heures_agent_par_jour = 8', 'heures_agent_par_jour = 30', "entre 1 et 24"),
    ('reseau_executants = false', 'reseau_executants = true', "seule valeur admise"),
    ('auteur = "ACP exécutant <executant@acp.invalid>"', 'auteur = "sans courriel"', "Nom <courriel>"),
    (ORIGINE_TEST, 'origine = "http://hermes-acp-test.up.railway.app"', "HTTPS"),
    ('[journal]', '[inconnue]\ncle = 1\n[journal]', "clé inconnue « inconnue »"),
])
def test_refus_du_schema(tmp_path, remplacer, par, motif):
    emplacements = _emplacements(tmp_path)
    texte = _texte_valide(emplacements)
    assert remplacer in texte
    with pytest.raises(PolitiqueRefusee, match=motif) as exc:
        _analyser(texte.replace(remplacer, par, 1), emplacements)
    assert str(exc.value).startswith("executant.toml")
    assert "poste.toml" not in str(exc.value)


@pytest.mark.parametrize(("remplacer", "par", "motif"), [
    ('url = "https://github.com/proprietaire-factice/depot-jetable.git"',
     'url = "https://jeton@github.com/proprietaire-factice/depot-jetable.git"', "sans identifiant"),
    ('url = "https://github.com/proprietaire-factice/depot-jetable.git"',
     'url = "http://github.com/proprietaire-factice/depot-jetable.git"', "https://"),
    ('url = "https://github.com/proprietaire-factice/depot-jetable.git"',
     'url = "https://gitlab.com/proprietaire-factice/depot-jetable.git"', "hotes_admis"),
    ('url = "https://github.com/proprietaire-factice/depot-jetable.git"',
     'url = "https://github.com/<propriétaire>/<dépôt-jetable>.git"', "gabarit"),
    ('url = "https://github.com/proprietaire-factice/depot-jetable.git"',
     'url = "https://github.com/proprietaire-factice/depot-jetable.git?ref=x"', "requête"),
    ('branche_base = "main"', 'branche_base = "../main"', "branche git valide"),
    ('branche_base = "main"', 'branche_base = "main.lock"', "branche git valide"),
    ('verification = ["uv", "run", "pytest", "-q"]', 'verification = []', "argv non vide"),
    ('verification = ["uv", "run", "pytest", "-q"]', 'verification = "uv run pytest"', "argv"),
    ('acces = "jeton_lecture"', 'acces = "jeton_ecriture"', "acces"),
])
def test_refus_des_depots(tmp_path, remplacer, par, motif):
    emplacements = _emplacements(tmp_path)
    assert remplacer in DEPOT
    # Remplacement dans le seul bloc du dépôt : le fichier versionné en porte un exemple en commentaire.
    with pytest.raises(PolitiqueRefusee, match=motif):
        _analyser(_texte_valide(emplacements, depot=DEPOT.replace(remplacer, par, 1)), emplacements)


def test_preparation_facultative_et_url_en_double(tmp_path):
    emplacements = _emplacements(tmp_path)
    sans = DEPOT.replace('preparation = ["uv", "sync", "--frozen"]\n', "")
    assert _analyser(_texte_valide(emplacements, depot=sans), emplacements).depot("jetable").preparation == ()
    double = DEPOT + DEPOT.replace("[depots.jetable]", "[depots.autre]").replace(".git\"", "\"")
    with pytest.raises(PolitiqueRefusee, match="même URL"):
        _analyser(_texte_valide(emplacements, depot=double), emplacements)


# ------------------------------------------------------------------ droits au démarrage


@POSIX
def test_droits_du_fichier_et_des_binaires(tmp_path):
    emplacements = _emplacements(tmp_path)
    fichier = emplacements.politique
    fichier.parent.mkdir(parents=True)
    fichier.write_text(_texte_valide(emplacements, binaires=True), encoding="utf-8")
    for chemin, mode in ((fichier, 0o444), (fichier.parent, 0o755), (emplacements.codex_par_defaut, 0o755),
                         (emplacements.claude_par_defaut, 0o755), (emplacements.codex_par_defaut.parent, 0o755),
                         (emplacements.claude_par_defaut.parent, 0o755)):
        os.chmod(chemin, mode)
    moi = os.geteuid()
    politique = charger(emplacements)
    verifier_droits(politique, proprietaire=moi)
    with pytest.raises(PolitiqueRefusee, match="autre propriétaire que root"):
        verifier_droits(politique, proprietaire=moi + 1)
    os.chmod(fichier, 0o666)
    with pytest.raises(PolitiqueRefusee, match="executant.toml modifiable"):
        verifier_droits(politique, proprietaire=moi)
    os.chmod(fichier, 0o444)
    os.chmod(fichier.parent, 0o777)
    with pytest.raises(PolitiqueRefusee, match="executant.toml modifiable"):
        verifier_droits(politique, proprietaire=moi)
    os.chmod(fichier.parent, 0o755)
    os.chmod(emplacements.claude_par_defaut, 0o775)
    with pytest.raises(PolitiqueRefusee, match=r"\[claude\] executable : binaire de la CLI modifiable"):
        verifier_droits(politique, proprietaire=moi)
    os.chmod(emplacements.claude_par_defaut, 0o755)
    emplacements.codex_par_defaut.unlink()
    with pytest.raises(PolitiqueRefusee, match=r"\[codex\] executable : fichier introuvable"):
        verifier_droits(politique, proprietaire=moi)


def forme_commentee() -> str:
    """Bloc ``[depots.jetable]`` commenté de la politique versionnée, décommenté, gabarits remplacés."""
    texte = (RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8")
    lignes = texte.split("# [depots.jetable]", 1)[1].splitlines()
    bloc = ["[depots.jetable]"] + [l[2:] for l in lignes if l.startswith("# ")]
    return "\n".join(bloc).replace("<propriétaire>", "proprietaire").replace("<dépôt-jetable>", "jetable") + "\n"


def test_forme_commentee_du_depot_acceptee(tmp_path):
    """La forme commentée que railway.md § 13.6 fait reprendre est acceptée par la politique ; sa vérification
    n'exige que des outils de l'image (ni uv, ni pytest : relecture de P6), éprouvée dans l'image par
    executant/tests/test_image.py::test_forme_commentee_du_depot_dans_l_image."""
    emplacements = EmplacementsLinux.de_test(tmp_path)
    texte = re.sub(r'(?m)^origine = "[^"\n]*"$', 'origine = "https://hermes-acp-test.up.railway.app"', (RACINE_DEPOT / "executant" / "politique" / "executant.toml").read_text(encoding="utf-8"), count=1)
    politique = analyser_executant((texte + "\n" + forme_commentee()).encode("utf-8"), emplacements)
    depot = politique.depot("jetable")
    assert depot.verification[0] == "python3.12" and depot.preparation == ()
    assert not {"uv", "pytest", "npm", "node"} & set(depot.verification)
