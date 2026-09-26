"""Politique locale ``poste.toml`` (cahier P5 § 7, décision D52) : schéma v1, refus en français, droits (Windows)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from acp_poste import politique as module
from acp_poste.politique import (
    PolitiqueRefusee,
    analyser,
    charger,
    droits_d_ecriture,
    empreinte_du_fichier,
    verifier_compte,
    verifier_droits,
)

WINDOWS_SEULEMENT = pytest.mark.skipif(os.name != "nt", reason="propre à Windows (exécuté sur windows-2022)")


def _jeton_eleve() -> bool:
    """Jeton administrateur élevé (exécuteurs de CI Windows) : ses privilèges contournent les ACL de test (écriture et
    liste constatées malgré un ACE limité ou refusé, run 36279917625) ; le compte dédié du poste est un compte standard."""
    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


ACL_NON_ELEVE = pytest.mark.skipif(
    os.name != "nt" or _jeton_eleve(),
    reason="ACL réelles : exige Windows et un jeton NON élevé (le jeton élevé de la CI contourne les ACL) ; éprouvé sur "
           "le poste de développement")
RACINE = Path(__file__).resolve().parents[3]
MODELE = RACINE / "packaging" / "poste" / "poste.toml.modele"


def _refus(poste, texte: str) -> str:
    poste.ecrire_politique(texte)
    with pytest.raises(PolitiqueRefusee) as exc:
        charger(poste.emplacements)
    return str(exc.value)


def test_modele_livre_valide(poste, tmp_path):
    """Le modèle livré, rempli comme le fait l'installeur, est accepté tel quel."""
    outils = poste.emplacements.outils
    (outils / "codex" / "bin").mkdir(parents=True)
    (outils / "claude").mkdir(parents=True)
    (outils / "codex" / "bin" / "codex.exe").write_bytes(b"")
    (outils / "claude" / "claude.exe").write_bytes(b"")
    texte = MODELE.read_text(encoding="utf-8")
    for gabarit, valeur in {"__ORIGINE__": "https://hermes-acp.test", "__PROGRAMFILES_ACP__": str(
            poste.emplacements.acp_programfiles), "__PROGRAMDATA_ACP__": str(poste.emplacements.acp_programdata),
            "__VERSION_CODEX__": "0.156.1", "__VERSION_CLAUDE__": "2.1.280",
            "__PROFIL_PROPRIETAIRE__": str(tmp_path / "profil-proprietaire")}.items():
        texte = texte.replace(gabarit, valeur)
    assert "__" not in re.sub(r"#.*", "", texte), "gabarit non rempli dans le modèle"
    if os.name != "nt":  # sous Linux, les « \ » du modèle Windows ne sont pas des séparateurs
        texte = texte.replace("\\", "/")
    poste.ecrire_politique(texte)
    politique = charger(poste.emplacements)
    assert politique.poste.compte == "dedie" and politique.poste.compte_attendu == "acp-poste"
    assert politique.codex.executable == outils / "codex" / "bin" / "codex.exe"
    assert politique.codex.home == poste.emplacements.localappdata / "ACP" / "codex-home"
    assert politique.claude.config_dir == poste.emplacements.localappdata / "ACP" / "claude-config"
    assert politique.politique.efforts_interdits == ("max", "ultra", "ultracode")
    assert politique.depots == ()


def test_defauts(poste):
    texte = "version = 1\n[hermes]\norigine = 'https://hermes-acp.test'\n[sondes]\ncodex = false\nclaude = false\n"
    politique = analyser(texte.encode(), poste.emplacements)
    assert politique.poste.nom == "Poste Windows"
    assert politique.poste.compte == "dedie" and politique.poste.compte_attendu == "acp-poste"
    assert (politique.hermes.attente_max_s, politique.hermes.delai_connexion_s) == (25, 10)
    assert (politique.sondes.intervalle_s, politique.sondes.delai_sonde_s) == (1800, 30)
    assert politique.codex is None and politique.claude is None
    assert politique.politique.executants == ("codex", "claude")
    assert politique.politique.paliers_admis == ("default",)
    assert (politique.politique.concurrence, politique.politique.reseau_executants) == (1, False)
    assert (politique.journal.niveau, politique.journal.taille_max_mo, politique.journal.fichiers) == ("info", 1, 5)
    assert politique.hermes_meme_enveloppe_que_codex is False
    assert re.fullmatch(r"[0-9a-f]{12}", politique.empreinte)


def test_cle_inconnue_refusee(poste):
    message = _refus(poste, poste.toml(sections={"hermes": {"proxy": "x"}}))
    assert message == "poste.toml : clé inconnue [hermes] proxy."
    assert _refus(poste, poste.toml() + "\n[inconnue]\nx = 1\n") == "poste.toml : clé inconnue « inconnue »."


@pytest.mark.parametrize("section, cle, valeur, attendu", [
    ("hermes", "attente_max_s", 4, "un entier entre 5 et 50"),
    ("hermes", "attente_max_s", "25", "un entier entre 5 et 50"),
    ("hermes", "delai_connexion_s", 31, "un entier entre 2 et 30"),
    ("sondes", "intervalle_s", 599, "un entier entre 600 et 86400"),
    ("sondes", "codex", "oui", "un booléen (true ou false)"),
    ("politique", "concurrence", 2, "l'entier 1 (seule valeur admise en v1)"),
    ("politique", "reseau_executants", True, "false (seule valeur admise en v1)"),
    ("politique", "efforts_interdits", ["MAX"], "une liste d'au plus 64 chaînes"),
    ("journal", "niveau", "bavard", "l'une des valeurs « info », « detail »"),
    ("codex", "bac_a_sable", "unelevated", "l'une des valeurs « elevated »"),
    ("poste", "compte", "invite", "l'une des valeurs « dedie », « proprietaire »"),
])
def test_types_et_bornes(poste, section, cle, valeur, attendu):
    message = _refus(poste, poste.toml(sections={section: {cle: valeur}}))
    assert message.startswith(f"poste.toml : [{section}] {cle} doit être {attendu}")


def test_toml_illisible_ligne(poste):
    message = _refus(poste, "version = 1\n[hermes]\norigine = \n")
    assert message == "poste.toml illisible à la ligne 3 : valeur invalide."


def test_version_exigee(poste):
    assert "version doit être l'entier 1" in _refus(poste, poste.toml().replace("version = 1", "version = 2"))


def test_origine_http_hors_boucle_refusee(poste):
    message = _refus(poste, poste.toml(sections={"hermes": {"origine": "http://hermes.example"}}))
    assert "HTTPS" in message and "hermes.example" not in message


def test_origine_boucle_locale_http_refusee(poste):
    """``normalize_service_origin`` admet http:// sur la boucle locale ; la politique, jamais (§ 7.3)."""
    message = _refus(poste, poste.toml(sections={"hermes": {"origine": "http://127.0.0.1:9119"}}))
    assert message == ("poste.toml : [hermes] origine doit être une origine HTTPS (https://…), boucle locale "
                       "comprise.")


def test_origine_avec_chemin_refusee(poste):
    assert "sans chemin" in _refus(poste, poste.toml(sections={"hermes": {"origine": "https://h.test/api"}}))


def test_chemin_unc_refuse(poste):
    message = _refus(poste, poste.toml(sections={"codex": {"executable": r"\\serveur\partage\codex.exe"}}))
    assert message == "poste.toml : [codex] executable doit être un chemin local (chemin réseau UNC refusé)."
    assert "serveur" not in message


def test_variable_hors_localappdata_refusee(poste):
    message = _refus(poste, poste.toml(sections={"codex": {"home": r"%USERPROFILE%\codex"}}))
    assert "seule %LOCALAPPDATA% est admise ici" in message
    message = _refus(poste, poste.toml(sections={"codex": {"executable": r"%LOCALAPPDATA%\codex.exe"}}))
    assert "aucune variable admise ici" in message


def test_expansion_localappdata(poste):
    politique = analyser(poste.toml(sections={"codex": {"home": r"%LOCALAPPDATA%\ACP\codex-home"}}).encode(),
                         poste.emplacements)
    assert politique.codex.home == poste.emplacements.localappdata / "ACP" / "codex-home"


def test_alias_hors_contrat_refuse(poste):
    depot = poste.racine / "depots" / "a"
    (depot / ".git").mkdir(parents=True)
    message = _refus(poste, poste.toml() + f"\n[depots.Majuscule]\nchemin = '{depot}'\n")
    assert "alias de dépôt refusé" in message


def test_depot_sans_git_refuse(poste):
    depot = poste.racine / "depots" / "sans-git"
    depot.mkdir(parents=True)
    assert "dépôt git (.git absent)" in _refus(poste, poste.toml() + f"\n[depots.jetable]\nchemin = '{depot}'\n")


def test_racines_chevauchantes_refusees(poste):
    parent = poste.racine / "depots" / "parent"
    enfant = parent / "enfant"
    (parent / ".git").mkdir(parents=True)
    (enfant / ".git").mkdir(parents=True)
    texte = poste.toml() + f"\n[depots.parent]\nchemin = '{parent}'\n[depots.enfant]\nchemin = '{enfant}'\n"
    assert "se chevauchent" in _refus(poste, texte)
    dans_le_poste = poste.emplacements.acp_local / "depot"
    (dans_le_poste / ".git").mkdir(parents=True)
    assert "chevauche le dossier du poste" in _refus(poste, poste.toml() + f"\n[depots.x]\nchemin = '{dans_le_poste}'\n")


def test_executable_dans_un_depot_refuse(poste):
    depot = poste.racine / "depots" / "jetable"
    (depot / ".git").mkdir(parents=True)
    faux = depot / "codex.exe"
    faux.write_bytes(b"")
    texte = poste.toml(sections={"codex": {"executable": str(faux)}}) + f"\n[depots.jetable]\nchemin = '{depot}'\n"
    assert "[codex] executable ne peut pas se trouver dans le dépôt" in _refus(poste, texte)


def test_depot_valide_et_verification_argv(poste):
    depot = poste.racine / "depots" / "jetable"
    (depot / ".git").mkdir(parents=True)
    texte = poste.toml() + f"\n[depots.jetable]\nchemin = '{depot}'\nverification = ['python', '-m', 'pytest']\n"
    politique = analyser(texte.encode(), poste.emplacements)
    assert politique.depots[0].alias == "jetable" and politique.depots[0].verification == ("python", "-m", "pytest")
    assert "une liste d'arguments" in _refus(poste, poste.toml() + f"\n[depots.jetable]\nchemin = '{depot}'\n"
                                             "verification = 'python -m pytest'\n")


def test_version_claude_trop_ancienne(poste):
    message = _refus(poste, poste.toml(sections={"claude": {"version_testee": "2.1.247"}}))
    assert "égale ou postérieure à 2.1.248" in message


def test_section_exigee_par_la_sonde(poste):
    assert _refus(poste, poste.toml(supprimer=("codex",))) == \
        "poste.toml : [sondes] codex = true exige la section [codex]."


def test_compte_attendu_different_refuse(poste):
    politique = analyser(poste.toml(compte="dedie").encode(), poste.emplacements)
    with pytest.raises(PolitiqueRefusee, match="doit tourner sous « acp-poste »"):
        verifier_compte(politique, "Paul")
    verifier_compte(politique, "ACP-POSTE")
    verifier_compte(analyser(poste.toml(compte="proprietaire").encode(), poste.emplacements), "Paul")


def test_empreinte_ignore_les_fins_de_ligne():
    assert empreinte_du_fichier(b"a\r\nb\r\n") == empreinte_du_fichier(b"a\nb\n")
    assert empreinte_du_fichier(b"a\n") != empreinte_du_fichier(b"b\n")


def test_politique_absente_refus_francais(poste):
    with pytest.raises(PolitiqueRefusee, match="poste.toml absent"):
        charger(poste.emplacements)


def test_resume_contrat(poste):
    politique = analyser(poste.toml().encode(), poste.emplacements)
    assert politique.resume_contrat() == {
        "executants": ["codex", "claude"], "efforts_interdits": ["max", "ultra", "ultracode"],
        "paliers_admis": ["default"], "modeles_codex_permis": [], "alias_claude_permis": ["opus", "sonnet", "haiku",
                                                                                          "fable"],
        "reseau_executants": False}


# ------------------------------------------------------------------ droits (logique, toutes plateformes)


@pytest.mark.parametrize("droit", ["GENERIC_WRITE", "DELETE", "WRITE_DAC", "WRITE_OWNER"])
def test_un_seul_droit_sur_le_fichier_suffit_a_refuser(poste, monkeypatch, droit):
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    valeur = dict(module.DROITS_FICHIER)[droit]
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: (
        "ouvert" if (not dossier and acces == valeur) else "refuse"))
    obtenus = droits_d_ecriture(chemin)
    assert obtenus == [f"{droit} (fichier)"]


@pytest.mark.parametrize("droit", ["FILE_ADD_FILE", "DELETE", "WRITE_DAC", "WRITE_OWNER"])
def test_un_seul_droit_sur_le_dossier_suffit_a_refuser(poste, monkeypatch, droit):
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    valeur = dict(module.DROITS_DOSSIER)[droit]
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: (
        "ouvert" if (dossier and acces == valeur) else "refuse"))
    assert droits_d_ecriture(chemin) == [f"{droit} (dossier)"]


def test_partage_refuse_vaut_indetermine_et_refuse(poste, monkeypatch):
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: (
        "indetermine" if acces == module.GENERIC_WRITE and not dossier else "refuse"))
    assert droits_d_ecriture(chemin) == ["GENERIC_WRITE (fichier, indéterminé)"]


def test_verifier_droits_refuse_en_dedie_et_pas_en_proprietaire(poste, monkeypatch):
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: "ouvert")
    dedie = analyser(poste.toml(compte="dedie").encode(), poste.emplacements, chemin=poste.ecrire_politique())
    with pytest.raises(PolitiqueRefusee, match="modifiable ou remplaçable par le compte du poste"):
        verifier_droits(dedie)
    proprietaire = analyser(poste.toml().encode(), poste.emplacements, chemin=poste.emplacements.politique)
    verifier_droits(proprietaire)  # repli D51 : rien n'est vérifié


def test_binaire_de_cli_modifiable_refuse(poste, monkeypatch):
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    politique = charger(poste.emplacements)
    monkeypatch.setattr(module, "_ouverture", lambda cible, acces, dossier: (
        "ouvert" if Path(cible) == Path(politique.codex.executable) and acces == module.GENERIC_WRITE else "refuse"))
    with pytest.raises(PolitiqueRefusee, match=r"\[codex\] executable : un binaire de la CLI est modifiable"):
        verifier_droits(politique)
    assert chemin.exists()


# ------------------------------------------------------------------ droits réels (Windows)


@WINDOWS_SEULEMENT
def test_politique_ecrivable_refusee(poste):
    """Vrai ``CreateFileW`` : un poste.toml du compte courant (le cas d'un fichier laissé au compte du poste) est
    modifiable, donc refusé en mode dédié."""
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    politique = charger(poste.emplacements)
    obtenus = droits_d_ecriture(chemin)
    assert any(o.startswith("GENERIC_WRITE (fichier") for o in obtenus)
    with pytest.raises(PolitiqueRefusee, match="modifiable ou remplaçable"):
        verifier_droits(politique)


@ACL_NON_ELEVE
def test_politique_remplacable_refusee(poste):
    """Vrai ``CreateFileW`` : écriture retirée par l'ACL, mais le compte PROPRIÉTAIRE du fichier garde ``WRITE_DAC``
    (droits implicites du propriétaire) : il pourrait réécrire la DACL puis le fichier. ``GENERIC_WRITE`` seul ne le
    voyait pas ; le poste refuse quand même."""
    chemin = poste.ecrire_politique(poste.toml(compte="dedie"))
    utilisateur = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["icacls", str(chemin), "/inheritance:r", "/grant:r", f"{utilisateur}:(R)"], check=True,
                   capture_output=True)
    try:
        obtenus = droits_d_ecriture(chemin)
        assert not any(o.startswith("GENERIC_WRITE (fichier") for o in obtenus), obtenus
        assert any(o.startswith("WRITE_DAC (fichier") for o in obtenus), obtenus
        with pytest.raises(PolitiqueRefusee, match="WRITE_DAC"):
            verifier_droits(charger(poste.emplacements))
    finally:
        subprocess.run(["icacls", str(chemin), "/reset"], capture_output=True)
