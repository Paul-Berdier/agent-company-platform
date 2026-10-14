"""Le bundle facultatif de notes ne livre aucune commande de worker."""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_modules_livres_sans_worker_et_operations_notes(tmp_path):
    spec = importlib.util.spec_from_file_location("package_coffre", ROOT / "scripts/package_coffre.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packages = tmp_path / "packages"
    module.copier_modules_coffre(ROOT, packages)
    # Un nouveau processus ne peut retomber sur les sources de l'exécutant.
    probe = """
import importlib.util, pathlib, sys, time
from uuid import uuid4
sys.path.insert(0, sys.argv[1])
from acp_poste.obsidian import CoffreNotes, creer_coffre
from acp_poste.coffre_cli import main
for nom in ('cli', 'execution', 'service', 'service_executant', 'app_server', 'comptes_codex', 'contexte', 'local_runner', 'commandes_agents'):
    assert importlib.util.find_spec('acp_poste.' + nom) is None, nom
root = pathlib.Path(sys.argv[2]) / 'notes-jetables'
notes = CoffreNotes(root, creer_coffre(root))
resultat = notes.executer(dict(id_operation=str(uuid4()), coffre_id=notes.coffre_id,
    action='creer', parametres=dict(chemin='Preuve.md', contenu='# Notes préservées'),
    expire_le=int(time.time())+60))
assert resultat['etat'] == 'reussie', resultat
assert (root / 'Preuve.md').read_text(encoding='utf-8') == '# Notes préservées'
try:
    main(['servir'])
except SystemExit as exc:
    assert exc.code == 2
else:
    raise AssertionError('Une commande worker ne doit pas exister')
assert not any(n in sys.modules for n in ('acp_poste.execution', 'acp_poste.contexte'))
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", probe, str(packages), str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
