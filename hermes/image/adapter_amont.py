"""Adaptations amont bornées, contrôlées avant toute écriture à la construction.

Le parent Docker reste épinglé. Une montée amont change les scripts ou la fonction
SQLite contrôlés => arrêt du build et nouvelle revue, jamais de substitution floue.
"""
from pathlib import Path
import ast
import hashlib

EMPREINTES = {'/opt/hermes/hermes_cli/service_manager.py': '9f1e567f9c77f4bd697844feac59e57736df84ed96f9e99723372f5590bf604c', '/opt/hermes/hermes_cli/container_boot.py': 'f0fe720ac657391193da0e95df9b54b62a2396ece212036166b94d8531f9a99a', '/opt/hermes/docker/stage2-hook.sh': 'af949cb3b09c1079b0988d82b242a4faef4cf0ffbeb9f781f2c2e3af484677c2', '/etc/cont-init.d/01-hermes-setup': 'f0678efed0a89ca0548aee1a57952de21eb556cd8c52ff80ff87b224989fa90c', '/etc/cont-init.d/015-supervise-perms': '8b99cf1f4479da7084ec4560ff5d6af8d6aacb4147da857808913d1fad52221d', '/etc/cont-init.d/02-reconcile-profiles': 'ed54309bdda54ec78243751b011f726fb9f87a3d6e46a103d7045903e7e18340', '/etc/s6-overlay/s6-rc.d/main-hermes/run': 'dbc6680fc3f6ac89ad66ce5c0aa15660717edced4ec133de83834a6688b519e6', '/etc/s6-overlay/s6-rc.d/dashboard/run': '491fce603b16603ba64e0ddfb43ee11f2a2e77b6de701a433045e88232c09568', '/etc/s6-overlay/s6-rc.d/dashboard/finish': '5971f24a3e19aff1249fae8ec9fa26d19e3cbd0fa375e9d0c701930b413d0597'}

# SHA-256 du segment AST complet de preflight_db_writability dans le commit Hermes
# f97608f178d1ffeca59860195ab7da295f7c8e5f (image déjà épinglée par SHA-256).
# Le reste du module demeure octet pour octet identique ; seule cette fonction change.
PREVOL_SQLITE_SHA256 = '3dea9516f70ff69ce2b1abde73aff3ff87c1cc75936fd2b3ed7d6eb10b41c9f5'
ANCRE_PREVOL = '        wal_note = (" Do NOT delete the -wal file — it contains committed data that "'
CORRECTION_PREVOL = '''        # ACP : SQLite peut retirer un sidecar entre is_file() et access().
        # Seule une disparition confirmée est admise, jamais un refus de permission.
        # lstat() conserve le refus d'un lien symbolique pendant ou cassé.
        if not is_dir and p in sidecars:
            try:
                p.lstat()
            except FileNotFoundError:
                continue
'''


def adapter_prevol_sqlite(texte: str) -> str:
    """Corriger la course de suppression WAL/SHM sans changer les droits ni les refus."""
    fonctions = [n for n in ast.parse(texte).body
                 if isinstance(n, ast.FunctionDef) and n.name == 'preflight_db_writability']
    if len(fonctions) != 1:
        raise ValueError('fonction preflight_db_writability absente ou dupliquée')
    original = ast.get_source_segment(texte, fonctions[0])
    if original is None or hashlib.sha256(original.encode('utf-8')).hexdigest() != PREVOL_SQLITE_SHA256:
        raise ValueError('fonction preflight_db_writability amont modifiée : nouvelle revue nécessaire')
    if original.count(ANCRE_PREVOL) != 1 or texte.count(original) != 1:
        raise ValueError('ancre du prévol SQLite non unique')
    corrige = original.replace(ANCRE_PREVOL, CORRECTION_PREVOL + ANCRE_PREVOL, 1)
    resultat = texte.replace(original, corrige, 1)
    ast.parse(resultat)
    return resultat


def main():
    for nom, attendu in EMPREINTES.items():
        if hashlib.sha256(Path(nom).read_bytes()).hexdigest() != attendu:
            raise SystemExit(f'[acp] REFUS : script amont modifié : {nom}. Revoir le démarrage plateforme.')
    cible = Path('/opt/hermes/hermes_cli/service_manager.py')
    texte = cible.read_text(encoding='utf-8')
    ancien = '    try:\n        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()'
    if texte.count(ancien) != 1:
        raise SystemExit('[acp] REFUS : détection s6 amont non reconnue.')
    nouveau = ('    from hermes_cli.acp_supervision import superviseur_actif\n'
               '    if superviseur_actif() is not None:\n'
               '        return True\n' + ancien)
    sqlite = Path('/opt/hermes/hermes_state_repair.py')
    try:
        prevol = adapter_prevol_sqlite(sqlite.read_text(encoding='utf-8'))
    except (ValueError, SyntaxError) as exc:
        raise SystemExit(f'[acp] REFUS : adaptation du prévol SQLite : {exc}') from exc
    # Toutes les validations précèdent les écritures ; toute exception fait échouer le build.
    cible.write_text(texte.replace(ancien, nouveau), encoding='utf-8')
    sqlite.write_text(prevol, encoding='utf-8')
    print('[acp] Compatibilité s6 sous init externe installée sur les scripts amont vérifiés.')
    print('[acp] Prévol SQLite : disparition concurrente WAL/SHM traitée ; refus de permissions conservés.')


if __name__ == '__main__':
    main()
