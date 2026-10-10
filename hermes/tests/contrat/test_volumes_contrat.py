"""Aller-retour d'un volume par les outils des tests de restauration (étape P9, cahier P9 § 3.2), piloté depuis l'hôte.

Un volume jetable garni comme les vrais (racine à l'UID 10000 comme /opt/data, dossier root 0755, secret root 0600,
fichiers des UID 10001 et 10002, lien symbolique, base SQLite en WAL laissée ouverte par un processus gelé, prise Unix)
est archivé à chaud (``docker pause`` du conteneur qui tient la base), puis restauré dans un volume NEUF :
- couche 1 : manifeste restauré ÉGAL au manifeste pris pendant la pause, propriétaires numériques et modes compris ;
  la prise Unix, ignorée par tar, est relevée et exclue de l'égalité ;
- couche 2 : empreinte logique de la base identique, ``integrity_check`` = ok, journal WAL non vide à l'instantané ;
- témoin : un octet changé dans le volume source APRÈS l'instantané est vu par la comparaison (elle n'est pas vide
  par construction).
"""

from __future__ import annotations

import json
import time

from conftest import afficher, docker
from volumes import Archives, a_chaud, bases, comparer_bases, comparer_manifestes, manifeste, resume_manifeste

PYTHON = "/opt/hermes/.venv/bin/python"
GARNIR = r"""
set -eu
mkdir -p /v/acp/secrets /v/donnees /v/plugins
chown 10000:10000 /v /v/donnees
chmod 0755 /v/plugins
printf 'secret-factice' > /v/acp/secrets/jeton && chmod 0600 /v/acp/secrets/jeton && chmod 0700 /v/acp/secrets
printf 'codex' > /v/donnees/a && chown 10001:10001 /v/donnees/a && chmod 0640 /v/donnees/a
printf 'claude' > /v/donnees/b && chown 10002:10100 /v/donnees/b
ln -s ../acp/secrets/jeton /v/donnees/lien
"""
TENIR = r"""
import socket, sqlite3, time
prise = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
prise.bind('/v/gateway.sock')
c = sqlite3.connect('/v/donnees/state.db', isolation_level=None)
c.execute('PRAGMA journal_mode=WAL')
c.execute('PRAGMA wal_autocheckpoint=0')
c.execute('CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, x TEXT)')
c.executemany('INSERT INTO t (x) VALUES (?)', [('ligne %d' % i,) for i in range(200)])
open('/tmp/pret', 'w').close()
time.sleep(3600)
"""


def test_aller_retour_a_chaud_dans_un_volume_neuf(ressources, image_tests):
    source = ressources.nom("vol-source")
    docker("volume", "create", source)
    ressources.volumes.append(source)
    docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{source}:/v", "--entrypoint", "sh", image_tests,
           "-c", GARNIR)
    teneur = ressources.nom("teneur")
    ressources.conteneurs.append(teneur)
    docker("run", "-d", "--name", teneur, "-u", "10000", "--network", "none", "-v", f"{source}:/v", "--entrypoint",
           PYTHON, image_tests, "-c", TENIR)
    for _ in range(60):
        if docker("exec", teneur, "test", "-f", "/tmp/pret", verifier=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise AssertionError(f"la base n'a pas été écrite :\n{docker('logs', teneur, verifier=False).stderr[-2000:]}")
    archives = Archives(ressources, image_tests)
    with a_chaud([teneur]):
        avant = manifeste(image_tests, source)
        bases_avant = bases(image_tests, source)
        archive = archives.instantane(source, "synthetique")
    restaure = archives.volume_restaure("synthetique", "restaure")
    apres, bases_apres = manifeste(image_tests, restaure), bases(image_tests, restaure)
    afficher("aller-retour d'un volume synthétique", json.dumps({
        "archive": archive, "source": resume_manifeste(avant), "restaure": resume_manifeste(apres),
        "racine": {k: avant["entrees"]["."][k] for k in ("mode", "uid", "gid")},
        "base": {k: bases_avant["bases"]["donnees/state.db"][k] for k in ("integrite", "annexes")}},
        ensure_ascii=False, indent=1))
    assert avant["prises"] == ["gateway.sock"] and apres["prises"] == []
    assert any(l.endswith("./gateway.sock: socket ignored") for l in archive["tar"]), archive
    assert comparer_manifestes(avant, apres) == []
    assert (avant["entrees"]["."]["uid"], avant["entrees"]["acp/secrets/jeton"]["mode"]) == (10000, "0600")
    assert (avant["entrees"]["donnees/b"]["uid"], avant["entrees"]["donnees/b"]["gid"]) == (10002, 10100)
    assert bases_avant["bases"]["donnees/state.db"]["annexes"]["-wal"] > 0
    assert bases_avant["bases"]["donnees/state.db"]["tables"]["t"]["lignes"] == 200
    assert bases_avant["bases"]["donnees/state.db"]["integrite"] == "ok"
    assert comparer_bases(bases_avant, bases_apres) == []
    # Témoin : un octet changé dans la source après l'instantané est vu.
    docker("run", "--rm", "-u", "0", "--network", "none", "-v", f"{source}:/v", "--entrypoint", "sh", image_tests,
           "-c", "printf 'codeX' > /v/donnees/a")
    ecarts = comparer_manifestes(manifeste(image_tests, source), apres)
    assert len(ecarts) == 1 and ecarts[0].startswith("donnees/a : sha256 "), ecarts
