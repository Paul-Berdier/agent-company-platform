"""Adaptation minimale de la détection s6 amont, contrôlée à la construction.

Le parent Docker reste épinglé. Une montée amont change ces scripts => arrêt du build
pour refaire la revue de l'ordre d'initialisation, pas une substitution approximative.
"""
from pathlib import Path
import hashlib

EMPREINTES = {'/opt/hermes/hermes_cli/service_manager.py': '9f1e567f9c77f4bd697844feac59e57736df84ed96f9e99723372f5590bf604c', '/opt/hermes/hermes_cli/container_boot.py': 'f0fe720ac657391193da0e95df9b54b62a2396ece212036166b94d8531f9a99a', '/opt/hermes/docker/stage2-hook.sh': 'af949cb3b09c1079b0988d82b242a4faef4cf0ffbeb9f781f2c2e3af484677c2', '/etc/cont-init.d/01-hermes-setup': 'f0678efed0a89ca0548aee1a57952de21eb556cd8c52ff80ff87b224989fa90c', '/etc/cont-init.d/015-supervise-perms': '8b99cf1f4479da7084ec4560ff5d6af8d6aacb4147da857808913d1fad52221d', '/etc/cont-init.d/02-reconcile-profiles': 'ed54309bdda54ec78243751b011f726fb9f87a3d6e46a103d7045903e7e18340', '/etc/s6-overlay/s6-rc.d/main-hermes/run': 'dbc6680fc3f6ac89ad66ce5c0aa15660717edced4ec133de83834a6688b519e6', '/etc/s6-overlay/s6-rc.d/dashboard/run': '491fce603b16603ba64e0ddfb43ee11f2a2e77b6de701a433045e88232c09568', '/etc/s6-overlay/s6-rc.d/dashboard/finish': '5971f24a3e19aff1249fae8ec9fa26d19e3cbd0fa375e9d0c701930b413d0597'}

def main():
    for nom, attendu in EMPREINTES.items():
        if hashlib.sha256(Path(nom).read_bytes()).hexdigest() != attendu:
            raise SystemExit(f'[acp] REFUS : script amont modifié : {nom}. Revoir le démarrage plateforme.')
    cible = Path('/opt/hermes/hermes_cli/service_manager.py')
    texte = cible.read_text()
    ancien = '    try:\n        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()'
    if texte.count(ancien) != 1:
        raise SystemExit('[acp] REFUS : détection s6 amont non reconnue.')
    nouveau = ('    from hermes_cli.acp_supervision import superviseur_actif\n'
               '    if superviseur_actif() is not None:\n'
               '        return True\n' + ancien)
    cible.write_text(texte.replace(ancien, nouveau))
    print('[acp] Compatibilité s6 sous init externe installée sur les scripts amont vérifiés.')

if __name__ == '__main__':
    main()
