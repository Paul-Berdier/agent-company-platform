"""Tini subreaper réel sous Docker --init ; ni compte ni dépôt confié."""
from __future__ import annotations

import json
import time

from outils_image import docker


def test_init_externe_tini_authentique_et_arret(image, ressources):
    volume=ressources.volume()
    nom=ressources.nom('init')
    ressources.conteneurs.append(nom)
    docker('run','-d','--init','--name',nom,'-v',f'{volume}:/donnees',image,verifier=True)
    limite=time.monotonic()+60
    journal=''
    while time.monotonic()<limite:
        r=docker('logs',nom)
        journal=r.stdout+r.stderr
        if 'Exécutant non enrôlé' in journal:
            break
        assert docker('inspect','-f','{{.State.Running}}',nom).stdout.strip()=='true', journal
        time.sleep(.5)
    assert 'Exécutant non enrôlé' in journal, journal
    print(journal)
    r=docker('exec',nom,'/usr/local/bin/python3.12','-I','-c',
             "import pathlib,json; print(json.dumps({p.name:(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode() "
             "for p in pathlib.Path('/proc').iterdir() if p.name.isdecimal() and (p/'comm').exists() "
             "and (p/'comm').read_text().strip()=='tini'}))",verifier=True)
    processus=json.loads(r.stdout)
    assert any(int(pid)>1 and '/usr/bin/tini -s -- /opt/acp/bin/acp-entree-executant' in cmd
               for pid,cmd in processus.items()), processus
    assert docker('exec',nom,'stat','-c','%u %a','/donnees/acp').stdout.strip()=='0 700'
    docker('stop','--time','25',nom,verifier=True,delai=35)
    etat=json.loads(docker('inspect','-f','{{json .State}}',nom,verifier=True).stdout)
    assert not etat['Running'] and etat['ExitCode']==0 and not etat['OOMKilled']


def test_vrai_tini_sans_subreaper_est_refuse(image):
    r=docker('run','--rm','--init','--entrypoint','/usr/bin/tini',image,'--',
             '/opt/acp/bin/acp-entree-executant')
    assert r.returncode==2, r.stdout+r.stderr
    assert 'superviseur de processus' in r.stderr
