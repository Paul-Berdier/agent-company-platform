"""Issue 26 : contrats réels sous Docker --init, sans compte ni volume de production.

Les tests historiques PID 1 restent dans les autres modules. Ceux-ci attestent un
superviseur vivant, le refus des voies non supervisées, les mêmes gardes et l'arrêt.
"""
from __future__ import annotations

import json
import time

import pytest

from conftest import ENV_VALIDE, SANS_CONTEXT7, docker, lancer, options_env
import test_sans_shell_contrat as historique

PYTHON = '/opt/hermes/.venv/bin/python'
PREUVE = ('import sys,json; sys.path.insert(0,"/opt/acp/bin"); '
          'import acp_supervision as s; '
          'print(json.dumps({"pid":s.superviseur_actif(), "chaine":s.dans_la_chaine()}))')


@pytest.fixture(scope='module')
def pile_externe(ressources, image_tests):
    return historique.construire_pile(ressources, image_tests, init_externe=True)


def test_supervision_reelle_et_diagnostic(pile_externe):
    c = pile_externe
    preuve = json.loads(c.executer([PYTHON, '-I', '-c', PREUVE], verifier=True).stdout)
    assert isinstance(preuve['pid'], int) and preuve['pid'] > 1
    assert preuve['chaine'] is False, 'docker exec ne descend pas de notre s6'
    pid = preuve['pid']
    rapport = c.sh(f'cat /proc/1/comm; cat /proc/{pid}/comm; '
                   'stat -c "%u %a" /run/acp-supervision/etat.json', verifier=True).stdout
    print(rapport)
    assert rapport.splitlines()[0].strip() != 's6-svscan'
    assert 's6-svscan' in rapport and '0 444' in rapport
    assert json.loads(c.executer([PYTHON, '-I', '-c', PREUVE], utilisateur='hermes',
                                verifier=True).stdout)['pid'] == pid
    diagnostic = c.executer(['env', '-i', PYTHON, '-I', '-B', '/opt/acp/bin/acp_demarrage.py',
                             'diagnostiquer'])
    print(diagnostic.stdout, diagnostic.stderr)
    assert diagnostic.returncode == 0
    assert 's6 attesté sous init externe' in diagnostic.stdout
    assert 'Initialisation plateforme validée' in c.journaux()
    # Une attestation lisible n'est pas une capacité d'écriture ou de lancement.
    for commande in ('mkdir /run/service/intrus', 'echo x >> /run/acp-supervision/etat.json',
                      'echo x >> /run/service/dashboard/run'):
        assert c.sh(commande, utilisateur='hermes').returncode != 0
    code, _, _ = c.http('/api/plugins/acp-poste/v1/meta')
    assert code in (401, 403), 'la façade reste protégée sans session'
    # Même une attestation existante ne permet pas une entrée hors de la chaîne.
    r = c.executer(['/opt/hermes/.venv/bin/hermes', 'dashboard', '--host', '127.0.0.1',
                    '--port', '9120'], utilisateur='hermes', delai=60)
    assert r.returncode == 78, r.stdout[-2000:] + r.stderr[-3000:]


def test_session_sans_execution_sous_init_externe(pile_externe):
    historique.test_session_du_tableau_de_bord_sans_outil_d_execution(pile_externe)
    historique.test_meta_garde_execution_dans_le_tableau_de_bord(pile_externe)


def test_preview_sous_init_externe_refuse_execution(pile_externe):
    historique.test_preview_restart_par_api_ws(pile_externe)


def test_volume_piege_relance_et_redemarrage_sous_init_externe(pile_externe):
    historique.test_volume_piege_apres_relance(pile_externe)
    historique.test_volume_piege_aucune_valeur_publiee_apres_relance(pile_externe)


@pytest.mark.parametrize('fichiers,env,motif', [
    ({'.env': 'HERMES_MANAGED_DIR=/opt/data/faux\n'}, {}, 'HERMES_MANAGED_DIR'),
    ({'hooks/intrus/handler.py': 'raise RuntimeError("ne doit pas tourner")\n'}, {}, 'hooks'),
    ({'config.yaml': 'secrets:\n  command:\n    enabled: true\n    command: "touch /opt/data/interdit"\n'},
     {}, 'source externe de secrets'),
    ({}, {'S6_KEEP_ENV': '1'}, 'S6_KEEP_ENV'),
    ({}, {'S6_PROFILE_GATEWAY_SCANDIR': '/opt/data/services'}, 'répertoire de supervision'),
])
def test_gardes_avant_service_sous_init_externe(ressources, image, fichiers, env, motif):
    volume = ressources.volume(image, fichiers)
    nom = ressources.nom('init-refus')
    ressources.conteneurs.append(nom)
    r = docker('run', '--init', '--name', nom, '-v', f'{volume}:/opt/data', *SANS_CONTEXT7,
               *options_env(dict(ENV_VALIDE, **env)), image, verifier=False, delai=90)
    journal = r.stdout + r.stderr
    assert r.returncode == 1, journal[-4000:]
    assert motif in journal and 'REFUS' in journal
    assert '[stage2]' not in journal and 'Initialisation plateforme validée' not in journal
    temoin = docker('run', '--rm', '-v', f'{volume}:/opt/data', '--entrypoint', 'sh', image,
                    '-c', 'test ! -e /opt/data/interdit', verifier=False)
    assert temoin.returncode == 0


def test_subreaper_relance_et_arret_borne(ressources, image):
    """Un double-fork devient enfant de s6 ; sa relance nettoie le même PGID.

    La sonde est déposée en root dans un conteneur de TEST, pas dans l'image livrée.
    Le helper finish et les réglages d'arrêt sont ceux de la production.
    """
    c = lancer(ressources, image, dict(ENV_VALIDE, RAILWAY_DEPLOYMENT_ID='test-init',
                                      RAILWAY_VOLUME_MOUNT_PATH='/opt/data'), init_externe=True)
    installation = r'''
import os, pathlib, sys
sys.path.insert(0, '/opt/acp/bin')
import acp_init_plateforme as boot
base=pathlib.Path('/run/service/sonde-test')
base.mkdir()
probe=base/'sonde.py'
probe.write_text("""import os, signal, time
from pathlib import Path
if os.fork()==0:
    if os.fork()==0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open('/tmp/acp-orphelins', 'a') as f:
            f.write(str(os.getpid())+'\\n')
            f.flush()
        while True: time.sleep(1)
    os._exit(0)
os.wait()
while True: time.sleep(1)
""")
(base/'run').write_text('#!/bin/sh\nexec /opt/hermes/.venv/bin/python -I '+str(probe)+'\n')
(base/'run').chmod(0o755)
boot.borner_arret(base)
'''
    c.executer([PYTHON, '-I', '-c', installation], verifier=True)
    c.executer(['/command/s6-svscanctl', '-a', '/run/service'], verifier=True)
    def orphelins():
        brut=c.sh('cat /tmp/acp-orphelins 2>/dev/null || true').stdout
        return [int(x) for x in brut.splitlines() if x.isdecimal()]
    limite=time.monotonic()+25
    while not orphelins() and time.monotonic()<limite:
        time.sleep(.2)
    assert orphelins(), c.journaux()[-4000:]
    ancien=orphelins()[0]
    pid=json.loads(c.executer([PYTHON,'-I','-c',PREUVE],verifier=True).stdout)['pid']
    parent=c.python(f"from pathlib import Path; print(Path('/proc/{ancien}/stat').read_text().rsplit(')',1)[1].split()[1])",verifier=True)
    assert int(parent.stdout.strip())==pid, 'orphelin non adopté par le subreaper'
    c.executer(['/command/s6-svc','-k','/run/service/sonde-test'],verifier=True)
    limite=time.monotonic()+25
    while len(orphelins())<2 and time.monotonic()<limite:
        time.sleep(.2)
    assert len(orphelins())>=2, c.journaux()[-4000:]
    limite=time.monotonic()+10
    while c.sh(f'test -e /proc/{ancien}').returncode==0 and time.monotonic()<limite:
        time.sleep(.2)
    assert c.sh(f'test -e /proc/{ancien}').returncode!=0, 'ancien orphelin encore présent, zombie compris'
    t=time.monotonic()
    docker('stop','--time','35',c.nom,delai=50)
    etat=json.loads(docker('inspect','-f','{{json .State}}',c.nom).stdout)
    print({'arret_s':round(time.monotonic()-t,2), 'etat':etat})
    assert not etat['Running'] and etat['ExitCode']==0 and not etat['OOMKilled']
    assert etat['Pid']==0
