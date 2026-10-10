"""Preuves de la sentinelle externe, sans compte ni Docker. Procfs est ici factice.

Le test de chemin couvre séparément tous ses composants ; les tests d'identité
remplacent seulement cette frontière pour pouvoir utiliser le répertoire pytest.
Les droits réels root/non-root sont éprouvés sur l'image dans test_init_plateforme.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

RACINE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('preuve_s6', RACINE / 'hermes/plugins/acp-poste/acp_supervision.py')
sp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sp)
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='supervision Linux et droits POSIX')


def processus(proc, pid, parent, debut=250):
    dossier = proc / str(pid)
    dossier.mkdir(exist_ok=True)
    champs = ['S', str(parent), str(pid)] + ['0'] * 16 + [str(debut)]
    (dossier / 'stat').write_text(f'{pid} (nom compliqué ) avec espaces) ' + ' '.join(champs))
    (dossier / 'cmdline').write_bytes(b'\0'.join(s.encode() for s in sp.COMMANDE_S6) + b'\0')


@pytest.fixture
def preuve(tmp_path, monkeypatch):
    proc = tmp_path / 'proc'
    (proc / 'sys/kernel/random').mkdir(parents=True)
    (proc / 'sys/kernel/random/boot_id').write_text('noyau-test\n')
    processus(proc, 42, 1)
    processus(proc, 43, 42)
    processus(proc, 44, 43)
    (tmp_path / 'etat.json').write_text(json.dumps({'version': 1, 'pid': 42, 'debut': 250, 'boot_id': 'noyau-test'}))
    os.chmod(tmp_path / 'etat.json', 0o644)
    monkeypatch.setattr(sp, 'UID_ATTENDU', os.getuid())
    monkeypatch.setattr(sp, '_chemin_root', lambda p, **k: not p.is_symlink())
    return {'attestation': tmp_path / 'etat.json', 'proc': proc}


def test_pid_debut_et_ascendance_obligatoires(preuve):
    assert sp.lire_stat(42, preuve['proc']) == (1, 42, 250)
    assert sp.superviseur_actif(**preuve) == 42
    assert sp.dans_la_chaine(pid=44, **preuve)
    processus(preuve['proc'], 50, 1)
    assert not sp.dans_la_chaine(pid=50, **preuve)  # même environnement, session hors arbre


@pytest.mark.parametrize('cle,valeur', [('version', 2), ('pid', True), ('pid', 1), ('pid', 666),
                                       ('debut', 251), ('debut', '250'), ('boot_id', 'autre-noyau')])
def test_identite_perimee_ou_alteree_refusee(preuve, cle, valeur):
    chemin = preuve['attestation']
    data = json.loads(chemin.read_text())
    data[cle] = valeur
    chemin.write_text(json.dumps(data))
    assert sp.superviseur_actif(**preuve) is None
    assert not sp.dans_la_chaine(pid=44, **preuve)


@pytest.mark.parametrize('contenu', ['{', '[]', '{}', 'x' * 4097])
def test_format_refuse(preuve, contenu):
    preuve['attestation'].write_text(contenu)
    assert sp.superviseur_actif(**preuve) is None


def test_attestation_modifiable_ou_lien_refusee(preuve):
    chemin = preuve['attestation']
    os.chmod(chemin, 0o666)
    assert sp.superviseur_actif(**preuve) is None
    os.chmod(chemin, 0o644)
    cible = chemin.with_suffix('.cible')
    chemin.rename(cible)
    chemin.symlink_to(cible)
    assert sp.superviseur_actif(**preuve) is None


def test_commande_non_s6_et_cycle_refuses(preuve):
    cmd = preuve['proc'] / '42/cmdline'
    cmd.write_bytes(b'/bin/sleep\0infinity\0')
    assert sp.superviseur_actif(**preuve) is None
    processus(preuve['proc'], 42, 1)
    processus(preuve['proc'], 43, 44)
    assert not sp.dans_la_chaine(pid=44, **preuve)


@pytest.mark.parametrize('chemin,mode,uid', [('/run', stat.S_IFLNK | 0o777, 0),
    ('/run/acp-supervision', stat.S_IFDIR | 0o775, 0),
    ('/run/acp-supervision/etat.json', stat.S_IFREG | 0o644, 10000),
    ('/run/acp-supervision/etat.json', stat.S_IFIFO | 0o644, 0)])
def test_chaque_composant_du_chemin_est_verifie(monkeypatch, chemin, mode, uid):
    cible = Path('/run/acp-supervision/etat.json')
    def lstat(path):
        if str(path) == chemin:
            return SimpleNamespace(st_mode=mode, st_uid=uid)
        return SimpleNamespace(st_mode=(stat.S_IFREG | 0o444) if path == cible else (stat.S_IFDIR | 0o755), st_uid=0)
    monkeypatch.setattr(Path, 'lstat', lstat)
    assert not sp._chemin_root(cible, repertoire=False)


def test_aucune_autorisation_par_variable(preuve, monkeypatch):
    preuve['attestation'].unlink()
    for nom in ('ACP_S6_PID', 'HERMES_S6_SUPERVISED_CHILD', 'S6_KEEP_ENV'):
        monkeypatch.setenv(nom, '1')
    assert sp.superviseur_actif(**preuve) is None
    assert not sp.dans_la_chaine(pid=44, **preuve)


def test_les_deux_modes_passent_par_une_chaine_supervisee():
    entree = (RACINE / 'hermes/image/acp-entree').read_text()
    # Le bootstrap externe quitte par exec dans le if ; seul PID 1 atteint
    # l'exec historique final. Vérifier tout le routage, pas un ancien fragment.
    lignes = [ligne.strip() for ligne in entree.splitlines()
              if ligne.strip() and not ligne.lstrip().startswith('#')]
    assert lignes == [
        'if [ "$$" -ne 1 ]; then',
        'exec /opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_init_plateforme.py \\',
        '/opt/hermes/docker/main-wrapper.sh "$@"',
        'fi',
        'exec /opt/hermes/docker/entrypoint-dispatch.sh "$@"',
    ]
    init = (RACINE / 'hermes/image/acp_init_plateforme.py').read_text()
    assert init.index('gardes.commande_gardes(') < init.index('for nom in INIT:') < init.index("ecrire(RUNTIME / 'etat.json'") < init.index('os.execve(')
    assert "'05-acp'" in init and 'PR_SET_CHILD_SUBREAPER' in init
    assert '/opt/acp/bin/verifier-superviseur' in (RACINE / 'executant/bin/acp-entree-executant').read_text()
