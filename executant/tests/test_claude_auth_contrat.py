"""Contrat du vrai Claude Code 2.1.283 : image CI, UID 10002, sans compte ni réseau.

Le tag officiel confirme auth login/status/logout depuis 2.1.41, retour de code OAuth par le terminal depuis
2.1.126, configDirectory dans auth status depuis 2.1.268. Les tests mesurent options, état vierge et arrêt :
aucune connexion réussie ou rotation de jeton n'est prouvée. Une sortie précoce hors ligne est explicitement
séparée d'une interruption. Ni URL complète, ni code, ni texte libre de login ne sortent du conteneur.
Sources : https://code.claude.com/docs/en/cli-reference ; https://code.claude.com/docs/en/authentication ;
https://github.com/anthropics/claude-code/blob/v2.1.283/CHANGELOG.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outils_image import afficher, docker  # noqa: E402


# Mesure indépendante du contrôleur ACP, exécutée uniquement dans un conteneur jetable. tini recueille les
# descendants. Chaque invocation Claude passe par setpriv ; aucun fichier ou compte de l'hôte n'est monté.
MESURE = r'''
import errno, fcntl, json, os, pty, re, select, signal, subprocess, sys, tempfile, termios, time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

CLAUDE = '/opt/acp/outils/claude/claude'
base = Path(tempfile.mkdtemp(prefix='acp-auth-contrat-'))
for d in (base, base / 'home', base / 'config', base / 'travail', base / 'tmp'):
    d.mkdir(exist_ok=True, mode=0o700)
    os.chown(d, 10002, 10002)
    os.chmod(d, 0o700)
env = {'HOME': str(base / 'home'), 'CLAUDE_CONFIG_DIR': str(base / 'config'), 'TMPDIR': str(base / 'tmp'),
       'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TERM': 'xterm',
       'DISABLE_UPDATES': '1', 'DISABLE_AUTOUPDATER': '1', 'DISABLE_TELEMETRY': '1'}
prefixe = ['/usr/bin/setpriv', '--reuid=10002', '--regid=10002', '--groups=10100',
           '--inh-caps=-all', '--bounding-set=-all', '--no-new-privs', '--']

def commande(*args):
    try:
        p = subprocess.run([*prefixe, CLAUDE, *args], stdin=subprocess.DEVNULL, capture_output=True,
                           cwd=base / 'travail', env=env, timeout=12, start_new_session=True)
    except subprocess.TimeoutExpired:
        raise AssertionError('délai auth dépassé (sortie non publiée)') from None
    assert len(p.stdout) + len(p.stderr) <= 65536, 'sortie auth trop longue'
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')

def etat():
    code, sortie, erreur = commande('auth', 'status')
    assert code == 1, 'auth status vierge ne rend pas 1'
    try:
        valeur = json.loads(sortie)
    except ValueError:
        raise AssertionError('auth status ne rend pas du JSON') from None
    assert isinstance(valeur, dict), 'auth status doit être un objet'
    assert valeur.get('authMethod') == 'none', 'magasin vierge reconnu comme authentifié'
    assert valeur.get('configDirectory') == str(base / 'config'), 'mauvais magasin consulté'
    if 'loggedIn' in valeur:
        assert valeur['loggedIn'] is False, 'loggedIn contredit le magasin vierge'
    # Mesure du littéral requis par l'adaptateur, pas seulement du type str ; aucun jeton synthétique
    # injecté au magasin et aucune identité personnelle. La voie positive exige encore une preuve OAuth.
    assert valeur.get('apiProvider') == 'firstParty', 'provenance CLI inattendue (valeur non publiée)'
    sys.path.insert(0, '/opt/acp/lib')
    from acp_poste.comptes_claude import analyser_etat
    interprete = analyser_etat(sortie.encode('utf-8'), code, str(base / 'config'))
    assert interprete.reconnu is False and interprete.type_auth == 'none', 'interprétation ACP incorrecte'
    # Les champs supplémentaires non documentés sont relevés par nom/type, pas traités comme une API stable.
    return {'code': code, 'authMethod': valeur['authMethod'], 'bon_magasin': True,
            'apiProvider': 'firstParty', 'adaptateur_reconnu': interprete.reconnu,
            'champs': {cle: type(v).__name__ for cle, v in sorted(valeur.items())},
            'stderr_present': bool(erreur)}

def processus_uid():
    resultat = []
    for d in Path('/proc').iterdir():
        if not d.name.isdigit():
            continue
        try:
            lignes = (d / 'status').read_text().splitlines()
            uid = next(l for l in lignes if l.startswith('Uid:')).split()[1:]
            if any(int(n) == 10002 for n in uid):
                resultat.append(int(d.name))
        except (OSError, StopIteration):
            pass
    return resultat

def nettoyer_uid():
    # UID exclusivement réservé à cet essai. Les petits-enfants éventuels sont recueillis par tini.
    for pid in processus_uid():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    limite = time.monotonic() + 3
    while processus_uid() and time.monotonic() < limite:
        time.sleep(.05)
    return processus_uid()

def login(mode):
    donnees = bytearray()
    maitre = esclave = None
    params = dict(cwd=base / 'travail', env=env)
    if mode == 'pty':
        maitre, esclave = pty.openpty()
        options = termios.tcgetattr(esclave)
        options[3] &= ~termios.ECHO
        termios.tcsetattr(esclave, termios.TCSANOW, options)
        def terminal():
            os.setsid()
            fcntl.ioctl(esclave, termios.TIOCSCTTY, 0)
        params.update(stdin=esclave, stdout=esclave, stderr=esclave, preexec_fn=terminal)
    else:
        params.update(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      start_new_session=True)
    p = subprocess.Popen([*prefixe, CLAUDE, 'auth', 'login', '--claudeai'], **params)
    if esclave is not None:
        os.close(esclave)
    fd = maitre if maitre is not None else p.stdout.fileno()
    os.set_blocking(fd, False)
    debut = time.monotonic()
    interrompu, trop_longue, escalade = False, False, []
    try:
        # Stdin reste ouvert sans code. Le réseau est coupé au niveau Docker, pas par un faux endpoint OAuth.
        while p.poll() is None and time.monotonic() - debut < 6:
            if select.select([fd], [], [], .1)[0]:
                try:
                    bloc = os.read(fd, 8192)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                donnees.extend(bloc)
                if len(donnees) > 65536:
                    trop_longue = True
                    break
        if p.poll() is None:
            interrompu = True
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except ProcessLookupError:
                    pass
                escalade.append(signal.Signals(sig).name)
                try:
                    p.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    pass
        p.wait(timeout=2)
        while len(donnees) <= 65536 and select.select([fd], [], [], 0)[0]:
            try:
                bloc = os.read(fd, 8192)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                break
            if not bloc:
                break
            donnees.extend(bloc)
    finally:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait(timeout=2)
        if maitre is not None:
            os.close(maitre)
        else:
            p.stdin.close()
            p.stdout.close()
    assert not trop_longue and len(donnees) <= 65536, 'sortie login trop longue'
    restants_avant_balai = len(processus_uid())
    assert not nettoyer_uid(), 'descendant Claude survivant après arrêt'
    texte = donnees.decode('utf-8', 'replace')
    # Ne publie ni query values, ni fragment, ni code ni message libre. OSC8/ANSI ne sont pas interprétés.
    texte = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', texte)
    texte = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', texte)
    urls = []
    for brut in re.findall(r'https?://[^\s<>\x00-\x1f]+', texte):
        try:
            u = urlsplit(brut)
            # Liste de divulgation minimale, pas un contrat inventé pour accepter un défi OAuth : tout
            # autre hôte/chemin observé reste masqué, même si le binaire décide de changer sa route.
            chemin_attendu = (u.scheme == 'https' and u.hostname == 'claude.com'
                              and u.path == '/cai/oauth/authorize' and u.port in (None, 443)
                              and u.username is None and u.password is None)
            url = {'schema': u.scheme, 'hote': u.hostname,
                   'parametres': sorted({cle for cle, _ in parse_qsl(u.query)})}
            if chemin_attendu:
                url['chemin'] = u.path
            else:
                url['chemin_masque'] = True
            urls.append(url)
        except ValueError:
            pass
    assert 'unknown command' not in texte.lower(), 'auth login non reconnu'
    return {'transport': mode, 'interruption_demandee': interrompu,
            'sortie_avant_delai': not interrompu, 'code': p.returncode, 'signaux': escalade,
            'duree_s': round(time.monotonic() - debut, 2), 'url_sans_valeurs': urls,
            'invite_code_observee': 'paste code' in texte.lower(), 'sortie_octets': len(donnees),
            'descendants_avant_balai': restants_avant_balai, 'aucun_processus_restant': True}

try:
    uid = subprocess.run([*prefixe, '/usr/bin/id', '-u'], capture_output=True, timeout=5, check=True)
    assert uid.stdout.strip() == b'10002', 'mauvais UID du témoin'
    code, version, _ = commande('--version')
    assert code == 0 and version.strip() == '2.1.283 (Claude Code)', 'mauvais binaire testé'
    action = sys.argv[1]
    if action == 'aide':
        rapport = {}
        for sous_commande in ('login', 'status', 'logout'):
            code, sortie, erreur = commande('auth', sous_commande, '--help')
            texte = sortie + erreur
            assert code == 0 and 'Usage:' in texte, 'aide auth absente'
            assert sous_commande in texte, 'aide de la mauvaise sous-commande'
            attendues = {'login': ('--claudeai', '--email', '--sso', '--console'), 'status': ('--text',), 'logout': ()}
            assert all(n in texte for n in attendues[sous_commande]), 'option officielle absente'
            rapport[sous_commande] = {'code': code, 'options': sorted(set(re.findall(r'--[a-z][a-z-]*', texte)))}
    elif action == 'etat':
        avant = etat()
        code, _, _ = commande('auth', 'logout')
        assert code == 0, 'logout sans compte a échoué'
        rapport = {'avant': avant, 'logout_code': code, 'apres': etat()}
    else:
        avant = etat()
        essai = login(action)
        rapport = {'avant': avant, 'login': essai, 'apres': etat()}
    credential = base / 'config' / '.credentials.json'
    # Certains logout peuvent laisser un objet vide ; un magasin non vide n'est jamais accepté ici.
    assert not credential.exists() or json.loads(credential.read_text()) == {}, 'credential créé sans compte'
    rapport.update(uid=int(uid.stdout), version=version.strip(), magasin_vierge=True)
finally:
    assert not nettoyer_uid(), 'processus Claude survivant dans le conteneur'
print(json.dumps(rapport, sort_keys=True))
'''


def _mesurer(image, ressources, action: str) -> dict:
    nom = ressources.nom()
    ressources.conteneurs.append(nom)
    r = docker('run', '--rm', '--name', nom, '--network', 'none', '--entrypoint', '/usr/bin/tini', image,
               '-s', '--', '/usr/local/bin/python3.12', '-I', '-c', MESURE, action, delai=75)
    assert r.returncode == 0, f'témoin auth {action} en échec (code {r.returncode}) : {r.stderr[-2000:]}'
    try:
        resultat = json.loads(r.stdout)
    except ValueError:
        pytest.fail(f'rapport JSON absent du témoin auth {action} (sortie non publiée)')
    afficher(f'Claude officiel — auth {action}, sans compte, sans réseau', json.dumps(resultat, indent=2))
    assert resultat['uid'] == 10002 and resultat['magasin_vierge'] is True
    return resultat


def test_claude_auth_aide_officielle(image, ressources):
    _mesurer(image, ressources, 'aide')


def test_claude_auth_etat_sans_compte_et_logout(image, ressources):
    resultat = _mesurer(image, ressources, 'etat')
    assert resultat['avant'] == resultat['apres']
    assert resultat['avant']['apiProvider'] == 'firstParty'
    assert resultat['avant']['adaptateur_reconnu'] is False


@pytest.mark.parametrize('transport', ['pipes', 'pty'])
def test_claude_auth_login_hors_ligne_borne_et_arrete(image, ressources, transport):
    resultat = _mesurer(image, ressources, transport)
    assert resultat['avant'] == resultat['apres']
    assert resultat['login']['aucun_processus_restant'] is True
    assert resultat['login']['interruption_demandee'] is True
    assert resultat['login']['invite_code_observee'] is True
    # Le candidat exact n'est admis qu'une fois mesuré sur le binaire épinglé ; aucune valeur query publiée.
    assert any(u.get('schema') == 'https' and u.get('hote') == 'claude.com'
               and u.get('chemin') == '/cai/oauth/authorize'
               for u in resultat['login']['url_sans_valeurs'])
