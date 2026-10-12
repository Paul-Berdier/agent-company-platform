"""Copie un Python Windows installé et les dépendances verrouillées du bridge coffre.

Aucun téléchargement, installation ni exécution personnelle. La preuve fonctionnelle
utilise uniquement un coffre temporaire et le runtime empaqueté, sans site externe.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

DISTRIBUTIONS = ("annotated-types", "pydantic", "pydantic-core", "typing-extensions", "typing-inspection")


def construire(repo: Path, output: Path):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise RuntimeError("Le bundle exige Python 3.12 x64 Windows.")
    repo = repo.resolve(strict=True)
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Le dossier de sortie doit être neuf ou vide ; aucun contenu existant n'est supprimé.")
    output.mkdir(parents=True, exist_ok=True)
    lock = (repo / "requirements/poste-3.12.lock.txt").read_text(encoding="utf-8")
    versions = dict(re.findall(r"^([a-z0-9-]+)==([^\s\\]+)", lock, flags=re.M))
    deps = []
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        if distribution.version != versions.get(name):
            raise RuntimeError(f"Dépendance {name} : version installée différente du verrou du dépôt.")
        deps.append(distribution)
    base = Path(sys.base_prefix)
    runtime = output / "runtime"
    packages = runtime / "packages"
    packages.mkdir(parents=True)
    for name in ("python.exe", "python312.dll", "python3.dll", "LICENSE.txt"):
        shutil.copy2(base / name, runtime / name)
    for library in base.glob("vcruntime*.dll"):
        shutil.copy2(library, runtime / library.name)
    shutil.copytree(base / "DLLs", runtime / "DLLs", ignore=shutil.ignore_patterns("*.pdb", "*.lib", "*.exp", "__pycache__"))
    shutil.copytree(base / "Lib", runtime / "Lib", ignore=shutil.ignore_patterns(
        "site-packages", "__pycache__", "*.pyc", "test", "tests", "idlelib", "turtledemo", "ensurepip", "venv", "tkinter"))
    for distribution in deps:
        for file in distribution.files or ():
            parts = Path(str(file)).parts
            if not parts or ".." in parts or Path(str(file)).is_absolute() or str(file).endswith((".pyc", ".pth")):
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file():
                continue
            target = packages.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.copytree(repo / "apps/poste/src/acp_poste", packages / "acp_poste", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(repo / "hermes/plugins/acp-poste/contrat/acp_poste_contrat", packages / "acp_poste_contrat", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    paths = "Lib\nDLLs\npackages\n"
    # Aucun import site : ni .pth, ni site utilisateur, ni PYTHONPATH, ni répertoire courant.
    (runtime / "python312._pth").write_text(paths, encoding="ascii")
    (runtime / "python._pth").write_text(paths, encoding="ascii")
    for name in ("Demarrer-Coffre-ACP.ps1", "Lancer-Coffre-ACP.cmd", "LISEZ-MOI.txt"):
        shutil.copy2(repo / "packaging/coffre" / name, output / name)
    licenses = output / "licences"
    licenses.mkdir()
    shutil.copy2(base / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    for source in (repo / "LICENSE", repo / "LICENSE.md", repo / "LICENSE.txt"):
        if source.is_file():
            shutil.copy2(source, licenses / ("ACP-" + source.name))
            break
    for distribution in deps:
        for file in distribution.files or ():
            if "license" in str(file).lower() or "copying" in str(file).lower():
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, licenses / (distribution.metadata["Name"] + "-" + source.name))
    probe = r"""
import ctypes, hashlib, json, pathlib, ssl, sys, tempfile, time
from uuid import uuid4
import pydantic
from acp_poste.obsidian import CoffreNotes, creer_coffre
from acp_poste.obsidian_bridge import ProtocoleCoffre
from acp_poste_contrat.coffre import Operation, Resultat
assert sys.flags.isolated and sys.flags.no_site
assert not any('site-packages' in p or p == '' for p in sys.path)
with tempfile.TemporaryDirectory(prefix='acp-coffre-paquet-') as temp:
    root = pathlib.Path(temp) / 'Coffre neuf'
    vault = CoffreNotes(root, creer_coffre(root))
    def run(action, **params):
        op = Operation(id_operation=str(uuid4()), coffre_id=vault.coffre_id, action=action,
                       parametres=params, expire_le=int(time.time())+60)
        result = Resultat.model_validate(vault.executer(op.model_dump()))
        assert result.etat == 'reussie', result.erreur
        return result.resultat
    run('creer', chemin='Preuve.md', contenu='# Test\n[[Accueil]]\n')
    note = run('lire', chemin='Preuve.md')
    saved = run('ecrire', chemin='Preuve.md', contenu='# Test modifié\n', empreinte_attendue=note['empreinte'])
    run('archiver', chemin='Preuve.md', empreinte_attendue=saved['empreinte'])
    assert not (root/'Preuve.md').exists()
    assert run('graphe')['liens']
print(json.dumps({'python':sys.version.split()[0], 'pydantic':pydantic.__version__, 'isolated':True,
                  'coffre_jetable':'creer/lire/ecrire/archiver/graphe réussis'}))
"""
    completed = subprocess.run([str(runtime / "python.exe"), "-I", "-B", "-c", probe],
        cwd=str(output), capture_output=True, text=True, encoding="utf-8", timeout=60)
    if completed.returncode:
        raise RuntimeError("La vérification fonctionnelle du runtime a échoué : " + completed.stderr[-3000:])
    evidence = json.loads(completed.stdout)
    # La CLI complète doit elle aussi s'importer sans l'environnement de build.
    cli = subprocess.run([str(runtime / "python.exe"), "-I", "-B", "-m", "acp_poste.cli", "obsidian", "--help"],
        cwd=str(output), capture_output=True, timeout=30)
    if cli.returncode:
        raise RuntimeError("Le lanceur autonome du coffre ne s'importe pas.")
    systeme = ctypes.create_unicode_buffer(32768)
    longueur = ctypes.windll.kernel32.GetSystemDirectoryW(systeme, len(systeme))
    if not 0 < longueur < len(systeme):
        raise RuntimeError("Dossier système de Windows introuvable pour vérifier le menu.")
    powershell = Path(systeme.value) / "WindowsPowerShell/v1.0/powershell.exe"
    menu = subprocess.run([str(powershell), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(output / "Demarrer-Coffre-ACP.ps1"), "-VerifierLanceur"], cwd=str(output), capture_output=True, timeout=30)
    if menu.returncode:
        raise RuntimeError("Le passage des arguments du menu PowerShell 5.1 a échoué.")
    evidence["menu_powershell"] = "creer --help reçu sans création ni configuration personnelle"
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files.append({"fichier": path.relative_to(output).as_posix(), "octets": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {"version": (repo / "VERSION").read_text().strip(), "python": sys.version.split()[0],
                "dependances": {d.metadata["Name"]: d.version for d in deps}, "preuve": evidence, "fichiers": files}
    (output / "manifest-coffre.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Bridge autonome : {len(files)} fichiers ; preuve de coffre jetable réussie.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        construire(args.repo, args.output)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
