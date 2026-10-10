"""Bootstrap root pour les plateformes qui gardent le PID 1.

Garder s6-supervise et les scripts épinglés, sans lancer s6-overlay hors PID 1.
Ordre impératif : gardes -> environnement -> initialisation amont -> 05-acp ->
attestation -> exec s6-svscan. Aucun superviseur n'existe pendant l'initialisation.
Le mode PID 1 continue d'utiliser l'entrée s6-overlay historique.
"""
from __future__ import annotations

import ctypes
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys

BIN = Path('/opt/acp/bin')
RUNTIME = Path('/run/acp-supervision')
SCAN = Path('/run/service')
ENV_S6 = Path('/run/s6/container_environment')
PYTHON = '/opt/hermes/.venv/bin/python'
INIT = ('01-hermes-setup', '015-supervise-perms', '02-reconcile-profiles', '05-acp')


def charger(nom: str):
    spec = importlib.util.spec_from_file_location(nom, BIN / f'{nom}.py')
    if spec is None or spec.loader is None:
        raise RuntimeError(f'module de démarrage absent : {nom}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def dossier_root(chemin: Path) -> None:
    """Créer uniquement sous un parent réel, root et non inscriptible par les agents."""
    st = chemin.parent.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise RuntimeError(f'parent non sûr : {chemin.parent}')
    chemin.mkdir(mode=0o755, exist_ok=True)
    st = chemin.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise RuntimeError(f'répertoire non sûr : {chemin}')


def ecrire(chemin: Path, contenu: bytes, mode: int = 0o644) -> None:
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as flux:
        flux.write(contenu)
        os.fchmod(flux.fileno(), mode)


def nettoyer_groupe(pgid_texte: str) -> None:
    """Le 4e argument de finish est le groupe du run terminé, fourni par s6."""
    if os.geteuid() != 0 or not pgid_texte.isdecimal():
        raise RuntimeError('nettoyage de groupe réservé au superviseur root')
    pgid = int(pgid_texte)
    preuve = charger('acp_supervision')
    superviseur = preuve.superviseur_actif()
    if superviseur is None:
        raise RuntimeError('superviseur absent pendant le nettoyage')
    if pgid <= 1 or pgid in {os.getpgrp(), preuve.lire_stat(superviseur)[1]}:
        raise RuntimeError('groupe de processus protégé')
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def borner_arret(service: Path) -> None:
    """Arrêt borné, descendants du même groupe nettoyés avant toute relance."""
    ecrire(service / 'timeout-kill', b'15000\n')
    ecrire(service / 'flag-timeout-killpg', b'')
    # La sortie 125 du finish amont (arrêt volontaire/configuration fatale) reste intacte.
    ancien = service / 'finish'
    suite = 'exit 0\n'
    if ancien.exists():
        ancien.rename(service / '.acp-amont-finish')
        suite = f'exec {service}/.acp-amont-finish "$@"\n'
    ecrire(ancien, ('#!/bin/sh\n'
        f'{PYTHON} -I -B {BIN}/acp_init_plateforme.py nettoyer-groupe "$4" || exit 125\n'
        + suite).encode(), 0o755)


def initialiser() -> None:
    # La borne main-wrapper est conservée pour container_boot._read_container_argv :
    # elle représente le CMD, mais ce bootstrap ne l'exécute pas comme deuxième passerelle.
    attendu = ['/opt/hermes/docker/main-wrapper.sh', 'gateway', 'run']
    if sys.argv[1:] != attendu or os.geteuid() != 0 or os.getpid() == 1:
        raise RuntimeError('mode plateforme réservé à l’ENTRYPOINT root et au CMD « gateway run »')
    if os.environ.get('S6_KEEP_ENV', '0') != '0':
        raise RuntimeError('S6_KEEP_ENV doit rester à 0 : environnement scellé des services exigé')
    if os.environ.get('S6_PROFILE_GATEWAY_SCANDIR', str(SCAN)) != str(SCAN):
        raise RuntimeError('le répertoire de supervision doit rester /run/service')
    gardes = charger('acp_demarrage')
    # AVANT toute réécriture de PATH ou du volume : validation du vrai environnement reçu.
    gardes.commande_gardes(gardes.Chemins(), dict(os.environ))
    preuve = charger('acp_supervision')
    dossier_root(RUNTIME)
    verrou = os.open(RUNTIME / 'verrou', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if preuve.superviseur_actif() is not None:
        raise RuntimeError('une chaîne s6 attestée tourne déjà : aucun second bootstrap')
    (RUNTIME / 'etat.json').unlink(missing_ok=True)
    # Comme le /run de s6-overlay, ces deux arborescences sont éphémères. Le parent
    # est root ; rmtree ne suit pas les liens laissés dans les sous-répertoires.
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError('suppression sûre des anciens répertoires /run indisponible')
    dossier_root(Path('/run/s6'))
    for chemin in (SCAN, ENV_S6):
        if chemin.is_symlink():
            raise RuntimeError(f'{chemin} est un lien : démarrage refusé')
        if chemin.exists():
            shutil.rmtree(chemin)
        dossier_root(chemin)
    env = dict(os.environ)
    env['PATH'] = '/command:' + env['PATH']
    env['S6_KEEP_ENV'] = '0'
    for nom, valeur in env.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', nom):
            raise RuntimeError('nom de variable incompatible avec l’environnement s6')
        ecrire(ENV_S6 / nom, os.fsencode(valeur) + b'\n', 0o600)
    # Les images épinglées déclarent exactement ces longruns. Les dépendances s6-rc
    # sont remplacées ici par l'ordre synchrone des initialisations, avant svscan.
    for nom in ('dashboard', 'main-hermes'):
        source = Path('/etc/s6-overlay/s6-rc.d') / nom
        dest = SCAN / nom
        dossier_root(dest)
        for fichier in ('run', 'finish'):
            if (source / fichier).exists():
                ecrire(dest / fichier, (source / fichier).read_bytes(), 0o755)
    for nom in INIT:
        subprocess.run(['/command/with-contenv', '/bin/sh', f'/etc/cont-init.d/{nom}'],
                       env=env, cwd='/opt/hermes', check=True)
    # 05-acp a remis les scripts et /run/service à root. Accès aux contrôles
    # statiques identique aux emplacements dynamiques, sans rendre run inscriptible.
    for nom in ('dashboard', 'main-hermes'):
        dest = SCAN / nom
        dossier_root(dest / 'supervise')
        os.mkfifo(dest / 'supervise/control', 0o600)
        os.chown(dest / 'supervise/control', 10000, 10000)
        (dest / 'event').mkdir(mode=0o3730)
        os.chown(dest / 'event', 10000, 10000)
        os.chmod(dest / 'event', 0o3730)
    for service in SCAN.iterdir():
        if service.is_symlink() or not service.is_dir() or service.name.startswith('.'):
            raise RuntimeError(f'emplacement de service inattendu : {service.name}')
        if service.name not in {'dashboard', 'main-hermes'} and not service.name.startswith('gateway-'):
            raise RuntimeError(f'service non déclaré : {service.name}')
        borner_arret(service)
        if (service / 'log').is_dir():
            borner_arret(service / 'log')
    # PR_SET_CHILD_SUBREAPER se conserve à execve : s6 récolte aussi les orphelins
    # quand l'init de la plateforme est PID 1. Refus si le noyau ne le permet pas.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER refusé')
    sous_recolteur = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(sous_recolteur), 0, 0, 0) != 0 or sous_recolteur.value != 1:
        raise RuntimeError('statut subreaper non confirmé')
    attestation = {'version': 1, 'pid': os.getpid(), 'debut': preuve.lire_stat(os.getpid())[2],
                   'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    ecrire(RUNTIME / 'etat.json', json.dumps(attestation).encode() + b'\n', 0o444)
    print('[acp] Initialisation plateforme validée ; lancement de s6-svscan (subreaper, gardes actives).', flush=True)
    # s6 ne doit pas hériter du verrou de préparation : la preuve vivante prend le relais.
    os.close(verrou)
    os.execve(preuve.COMMANDE_S6[0], list(preuve.COMMANDE_S6), env)


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'nettoyer-groupe':
            nettoyer_groupe(sys.argv[2])
        else:
            initialiser()
        return 0
    except Exception as exc:  # Toute erreur, y compris Refus des gardes, ferme le démarrage.
        # Ne jamais afficher l'environnement ni les valeurs des variables.
        print(f'[acp] REFUS : initialisation plateforme : {exc}. Démarrage arrêté (échec fermé).',
              file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
