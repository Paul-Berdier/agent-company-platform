"""Paquet d'installation du poste (``packaging/poste``, cahier P5 § 8) : définition de la tâche planifiée, groupes et ACL
désignés par SID, lanceur ``python -I`` sans venv, modèles. L'installeur lui-même n'est éprouvé qu'EN SIMULATION
(``packaging/poste/tests/Test-InstallationPoste.ps1``, windows-2022) : aucun compte, aucune tâche ni ACL réels ici."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
PAQUET = RACINE / "packaging" / "poste"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _tache() -> ET.Element:
    texte = (PAQUET / "tache-poste.xml.modele").read_text(encoding="utf-8")
    for gabarit, valeur in {"__SID_COMPTE__": "S-1-5-21-1-2-3-1001", "__PYTHON__": r"C:\Program Files\Python312\python.exe",
                            "__LANCEUR__": r"C:\Program Files\ACP\poste\lancer.py",
                            "__DOSSIER_TRAVAIL__": r"C:\ProgramData\ACP"}.items():
        texte = texte.replace(gabarit, valeur)
    assert "__" not in re.sub(r"<!--.*?-->", "", texte, flags=re.S)
    return ET.fromstring(texte)


def test_definition_de_tache():
    tache = _tache()
    principal = tache.find("t:Principals/t:Principal", NS)
    assert principal.find("t:LogonType", NS).text == "Password"
    assert principal.find("t:RunLevel", NS).text == "LeastPrivilege"
    assert principal.find("t:UserId", NS).text.startswith("S-1-5-21-")
    assert tache.find("t:Triggers/t:BootTrigger/t:Delay", NS).text == "PT1M"
    repetition = tache.find("t:Triggers/t:TimeTrigger/t:Repetition", NS)
    assert repetition.find("t:Interval", NS).text == "PT15M"
    assert repetition.find("t:Duration", NS) is None, "garde sans fin : aucune durée de répétition"
    reglages = tache.find("t:Settings", NS)
    assert reglages.find("t:MultipleInstancesPolicy", NS).text == "IgnoreNew"
    assert reglages.find("t:ExecutionTimeLimit", NS).text == "PT0S"
    assert reglages.find("t:WakeToRun", NS).text == "false"
    assert reglages.find("t:DisallowStartIfOnBatteries", NS).text == "false"
    assert reglages.find("t:StopIfGoingOnBatteries", NS).text == "false"
    assert reglages.find("t:Hidden", NS).text == "true"
    assert reglages.find("t:RestartOnFailure/t:Count", NS).text == "3"
    action = tache.find("t:Actions/t:Exec", NS)
    assert action.find("t:Arguments", NS).text == r'-I "C:\Program Files\ACP\poste\lancer.py" servir'
    assert "Password" not in ET.tostring(tache, encoding="unicode").replace("<ns0:LogonType>Password", "")


def test_groupes_et_acl_par_sid():
    """Le PC est en français, le runner en anglais : aucun nom de groupe localisé ne sert d'identité."""
    for nom in ("Installer-PosteAcp.ps1", "Desinstaller-PosteAcp.ps1"):
        code = "\n".join(l for l in (PAQUET / nom).read_text(encoding="utf-8-sig").splitlines()
                         if not l.lstrip().startswith("#"))
        assert not re.search(r"Get-LocalGroup(Member)?\s+-Name", code), nom
        assert not re.search(r"(?i)['\"](BUILTIN\\)?(Administrateurs|Administrators|Utilisateurs|Users|"
                             r"Utilisateurs du Bureau à distance|Remote Desktop Users|SYSTEM|Système)['\"]", code), nom
    installeur = (PAQUET / "Installer-PosteAcp.ps1").read_text(encoding="utf-8-sig")
    for sid in ("S-1-5-32-544", "S-1-5-32-545", "S-1-5-32-555", "S-1-5-18"):
        assert sid in installeur
    octrois = re.findall(r'"(\*[^"]*?:\(OI\)\(CI\)[A-Z]+)"', installeur)
    assert octrois and all(o.startswith(("*S-1-", "*${")) for o in octrois), octrois
    assert "Get-LocalGroup -SID" in installeur and "/inheritance:r" in installeur


def test_scripts_powershell_en_utf8_avec_bom():
    """Windows PowerShell 5.1 lit un script sans BOM en ANSI : les accents des messages seraient illisibles."""
    for chemin in [*PAQUET.glob("*.ps1"), *PAQUET.glob("tests/*.ps1")]:
        assert chemin.read_bytes().startswith(b"\xef\xbb\xbf"), chemin.name


def test_modele_de_commande_ascii():
    modele = (PAQUET / "acp-poste.cmd.modele").read_bytes()
    assert modele.isascii()
    assert b'"__PYTHON__" -I "__LANCEUR__" %*' in modele


def test_lanceur_isole_sans_venv(tmp_path):
    """``lancer.py`` n'ajoute que ``lib`` à côté de lui : copié avec les sources, ``python -I lancer.py`` démarre le
    poste (sans venv, sans ``PYTHONPATH``)."""
    import acp_poste
    import acp_poste_contrat

    poste = tmp_path / "Program Files" / "ACP" / "poste"
    lib = poste / "lib"
    lib.mkdir(parents=True)
    shutil.copy(PAQUET / "lancer.py", poste / "lancer.py")
    for paquet in (acp_poste, acp_poste_contrat):
        source = Path(paquet.__file__).resolve().parent
        shutil.copytree(source, lib / source.name, ignore=shutil.ignore_patterns("__pycache__"))
    sortie = subprocess.run([sys.executable, "-I", str(poste / "lancer.py"), "--version"], capture_output=True,
                            text=True, cwd=tmp_path, env={"PYTHONPATH": "ne-doit-pas-servir", "SYSTEMROOT": __import__(
                                "os").environ.get("SYSTEMROOT", "")}, timeout=60)
    assert sortie.returncode == 0, sortie.stderr
    assert sortie.stdout.strip() == "acp-poste 1.0.0"
    # Écrivain de la ligne d'état (vos sessions Claude Code) : même disposition ; entrée illisible, code 0, rien écrit.
    shutil.copy(PAQUET / "ligne_etat.py", poste / "ligne_etat.py")
    cible = tmp_path / "quotas" / "claude-code.json"
    ligne = subprocess.run([sys.executable, "-I", str(poste / "ligne_etat.py")], input="{}", capture_output=True,
                           text=True, cwd=tmp_path, timeout=60,
                           env={"ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT": str(cible),
                                "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert ligne.returncode == 0 and not cible.exists()


def test_modele_de_politique_sans_secret():
    modele = (PAQUET / "poste.toml.modele").read_text(encoding="utf-8")
    from acp_poste_contrat.motifs_secrets import motif_trouve

    assert motif_trouve(modele) is None
    for gabarit in ("__ORIGINE__", "__PROGRAMFILES_ACP__", "__PROGRAMDATA_ACP__", "__VERSION_CODEX__",
                    "__VERSION_CLAUDE__", "__PROFIL_PROPRIETAIRE__"):
        assert gabarit in modele
