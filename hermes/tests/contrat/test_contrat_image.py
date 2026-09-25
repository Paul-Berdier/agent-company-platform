"""Tests de contrat de l'image ACP, pilotés depuis l'hôte (voir conftest.py).

Ce qu'ils prouvent, sur l'image réellement construite :
1. l'image : version de Hermes, condensat épinglé, CMD, crochet s6, OpenRPC identique,
   greffon sans ancien chemin (hermes plugins compat) et témoin refusé ;
2. les refus de démarrer, en français, code 1, AVANT l'amorçage de Hermes ;
3. un conteneur en marche : /init d's6 en PID 1, passerelle et tableau de bord sous
   l'uid hermes, api_server en boucle locale, seul fournisseur OIDC, clés épinglées,
   répertoires protégés ;
4. avec un faux fournisseur d'identité (image de test) : route meta authentifiée, jetons
   étrangers refusés, injection dans /opt/data neutralisée après redémarrage du tableau de
   bord par l'agent et après redémarrage du conteneur, mise à jour refusée, carte en triage
   jamais lancée, un tour d'agent sur le modèle factice.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import pytest

from conftest import (
    ENV_VALIDE, RACINE_HERMES, Conteneur, afficher, demarrer_jusqu_a_l_arret, docker, lancer,
    lire_version_epinglee, options_env)

EPINGLE = lire_version_epinglee()


def _texte_json(valeur: object) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=2)


# =========================================================================== 1. l'image


def test_version_de_hermes_et_condensat_epingle(image):
    dockerfile = (RACINE_HERMES / "image" / "Dockerfile").read_text(encoding="utf-8")
    ligne_from = next(l for l in dockerfile.splitlines() if l.startswith("FROM "))
    attendu = (f"FROM {EPINGLE['HERMES_IMAGE']}:{EPINGLE['HERMES_TAG']}@{EPINGLE['HERMES_IMAGE_INDEX']}")
    assert ligne_from == attendu
    version = docker("run", "--rm", "--entrypoint", "/opt/hermes/.venv/bin/hermes", image, "--version").stdout
    afficher("hermes --version", version)
    assert f"Hermes Agent v{EPINGLE['HERMES_VERSION']} (2026.9.24) · upstream {EPINGLE['HERMES_COMMIT'][:8]}" in version
    provenance = json.loads(docker("run", "--rm", "--entrypoint", "cat", image,
                                   "/etc/hermes/image-provenance.json").stdout)
    assert provenance["version"] == EPINGLE["HERMES_VERSION"]
    assert provenance["revision"] == EPINGLE["HERMES_COMMIT"]
    config = json.loads(docker("image", "inspect", "-f", "{{json .Config}}", image).stdout)
    afficher("condensat épinglé", f"{ligne_from}\nprovenance : {provenance}\nCmd : {config['Cmd']}\n"
                                   f"Entrypoint : {config['Entrypoint']}")
    assert config["Cmd"] == ["gateway", "run"]
    # Étape P2 : l'ENTRYPOINT officiel est enveloppé par acp-entree (refus hors PID 1).
    assert config["Entrypoint"] == ["/opt/acp/bin/acp-entree"]
    entree = docker("run", "--rm", "--entrypoint", "sh", image, "-c",
                    "stat -c '%U:%G %a' /opt/acp/bin/acp-entree && tail -1 /opt/acp/bin/acp-entree",
                    verifier=True).stdout.splitlines()
    assert entree == ["root:root 755", 'exec /opt/hermes/docker/entrypoint-dispatch.sh "$@"']
    assert "S6_BEHAVIOUR_IF_STAGE2_FAILS=2" in config["Env"]
    assert "S6_STAGE2_HOOK=/opt/acp/bin/acp-gardes" in config["Env"]


def test_la_copie_de_l_openrpc_est_identique_a_celle_de_l_image(image):
    locale = (RACINE_HERMES / "contrat" / "gateway-contract.openrpc.json").read_bytes()
    dans_image = docker("run", "--rm", "--entrypoint", "sha256sum", image,
                        "/opt/hermes/apps/shared/src/gateway-contract.openrpc.json").stdout.split()[0]
    assert hashlib.sha256(locale).hexdigest() == dans_image == EPINGLE["OPENRPC_SHA256"]
    contrat = json.loads(locale)
    assert contrat["info"]["version"] == EPINGLE["OPENRPC_INFO_VERSION"]
    assert len(contrat["methods"]) == int(EPINGLE["OPENRPC_METHODES"])


def _compat(image: str, chemin: str, *options: str):
    return docker("run", "--rm", "--init", "-e", "COLUMNS=160", "--entrypoint", "/opt/hermes/.venv/bin/hermes",
                  image, "plugins", "compat", *options, chemin, verifier=False)


def test_hermes_plugins_compat_accepte_acp_poste_et_refuse_le_temoin(image_tests):
    greffon = _compat(image_tests, "/opt/hermes/plugins/acp-poste")
    afficher(f"hermes plugins compat /opt/hermes/plugins/acp-poste (code {greffon.returncode})",
             greffon.stdout + greffon.stderr)
    assert greffon.returncode == 0
    assert json.loads(_compat(image_tests, "/opt/hermes/plugins/acp-poste", "--json").stdout)["plugins"] == {}
    temoin = _compat(image_tests, "/opt/acp-tests/outils/temoin_compat")
    afficher(f"hermes plugins compat témoin (code {temoin.returncode})", temoin.stdout + temoin.stderr)
    assert temoin.returncode == 1
    rapport = json.loads(_compat(image_tests, "/opt/acp-tests/outils/temoin_compat", "--json").stdout)
    impacts = rapport["plugins"]["temoin_compat"]
    assert [(i["old"], i["new"]) for i in impacts] == [
        ("hermes_cli.kanban_db.connect", "hermes_cli.kanban_db_connect.connect")]
    assert rapport["in_effect"] is True


def test_l_image_railway_ne_contient_ni_tests_ni_pytest_et_ses_fichiers_sont_en_lecture_seule(image):
    script = ("test ! -e /opt/acp-tests && ! /opt/hermes/.venv/bin/python -c 'import pytest' 2>/dev/null && "
              "find /opt/acp /opt/hermes/plugins/acp-poste /etc/hermes /etc/cont-init.d/05-acp "
              "\\( ! -user root -o -perm /022 \\) -print")
    resultat = docker("run", "--rm", "--entrypoint", "sh", image, "-c", script, verifier=False)
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stdout.strip() == "", resultat.stdout


# =========================================================================== 2. les refus


CAS_DE_REFUS = {
    "variable_interdite": ({"API_SERVER_KEY": "0123456789abcdef0123456789"}, {}, {},
                           "la variable API_SERVER_KEY est interdite"),
    "managed_dir": ({"HERMES_MANAGED_DIR": "/opt/data/scope"}, {}, {},
                    "la variable HERMES_MANAGED_DIR est interdite"),
    "mot_de_passe": ({"HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": "motdepasse"}, {}, {},
                     "la variable HERMES_DASHBOARD_BASIC_AUTH_PASSWORD est interdite"),
    "emetteur_http": ({"HERMES_DASHBOARD_OIDC_ISSUER": "http://idp.acp.test"}, {}, {},
                      "HERMES_DASHBOARD_OIDC_ISSUER doit être une URL en https"),
    "emetteur_local": ({"HERMES_DASHBOARD_OIDC_ISSUER": "https://127.0.0.1:8443"}, {}, {},
                       "adresse IP non publique interdite"),
    "emetteur_absent": ({"HERMES_DASHBOARD_OIDC_ISSUER": None}, {}, {},
                        "la variable HERMES_DASHBOARD_OIDC_ISSUER est obligatoire et absente"),
    "manifeste_acp_poste": ({}, {"plugins/nimportequoi/plugin.yaml": "name: acp-poste\n"}, {},
                            "déclare le nom réservé « acp-poste »"),
    "manifeste_tableau_de_bord": ({}, {"plugins/ui/dashboard/manifest.json": '{"name": "acp-interface"}'}, {},
                                  "déclare le nom réservé « acp-interface »"),
    "lien_symbolique": ({}, {}, {"plugins/raccourci": "/opt/data/ailleurs"}, "est un lien symbolique"),
    "path_du_volume": ({"PATH": "/opt/data/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
                       {}, {}, "la variable PATH contient"),
}


@pytest.mark.parametrize("cas", sorted(CAS_DE_REFUS))
def test_refus_de_demarrer_en_francais_avant_l_amorcage(ressources, image, cas):
    modifications, fichiers, liens, motif = CAS_DE_REFUS[cas]
    env = dict(ENV_VALIDE)
    for cle, valeur in modifications.items():
        if valeur is None:
            env.pop(cle)
        else:
            env[cle] = valeur
    volume = ressources.volume(image, fichiers, liens) if (fichiers or liens) else None
    code, journal = demarrer_jusqu_a_l_arret(ressources, image, env, volume)
    afficher(f"refus « {cas} » : code de sortie {code}", "\n".join(
        l for l in journal.splitlines() if "[acp]" in l or "rc.init" in l))
    assert code == 1
    assert f"[acp] REFUS : " in journal and motif in journal
    assert "[acp] Démarrage arrêté (échec fermé)" in journal
    # Le crochet S6_STAGE2_HOOK a arrêté le conteneur avant tout script cont-init.
    assert "fatal: hook /opt/acp/bin/acp-gardes exited 1" in journal
    assert "[stage2]" not in journal and "cont-init: info: running" not in journal


def test_refus_d_un_fichier_gere_invalide(ressources, image, tmp_path):
    # Le vrai modèle, marqueurs compris, rendu illisible par une ligne YAML fautive.
    modele = (RACINE_HERMES / "gere" / "config.yaml").read_text(encoding="utf-8")
    invalide = tmp_path / "config.yaml"
    invalide.write_text(modele + "\napprovals: [ouvert\n", encoding="utf-8", newline="\n")
    nom = ressources.nom("gere")
    ressources.conteneurs.append(nom)
    volume = ressources.volume(image)
    docker("create", "--name", nom, "-v", f"{volume}:/opt/data", *options_env(ENV_VALIDE), image)
    docker("cp", str(invalide), f"{nom}:/opt/acp/gere/config.yaml")
    resultat = docker("start", "-a", nom, verifier=False, delai=240)
    code = int(docker("inspect", "-f", "{{.State.ExitCode}}", nom).stdout.strip())
    journal = resultat.stdout + resultat.stderr
    afficher(f"refus « fichier géré invalide » : code de sortie {code}",
             "\n".join(l for l in journal.splitlines() if "[acp]" in l or "rc.init" in l))
    assert code == 1
    assert "REFUS : le modèle /opt/acp/gere/config.yaml est invalide" in journal
    assert "YAML" in journal and "[stage2]" not in journal


def test_refus_meme_si_s6_behaviour_a_ete_change(ressources, image):
    env = dict(ENV_VALIDE, S6_BEHAVIOUR_IF_STAGE2_FAILS="0", API_SERVER_KEY="0123456789abcdef0123456789")
    code, journal = demarrer_jusqu_a_l_arret(ressources, image, env)
    afficher(f"refus avec S6_BEHAVIOUR_IF_STAGE2_FAILS=0 : code {code}",
             "\n".join(l for l in journal.splitlines() if "[acp]" in l))
    assert code == 1
    assert "la variable S6_BEHAVIOUR_IF_STAGE2_FAILS vaut « 0 »" in journal
    assert "arrêt explicite du conteneur" in journal
    # Aucun tableau de bord n'a démarré.
    assert "HERMES_DASHBOARD_READY" not in journal


# =========================================================================== 3. en marche


@pytest.fixture(scope="module")
def hermes_en_marche(ressources, image) -> Conteneur:
    return lancer(ressources, image, ENV_VALIDE)


def test_pid1_est_s6_et_les_gardes_ont_tourne(hermes_en_marche):
    pid1 = hermes_en_marche.executer(["cat", "/proc/1/cmdline"], verifier=True).stdout.replace("\x00", " ").strip()
    journal = hermes_en_marche.journaux()
    afficher("/proc/1/cmdline", pid1)
    afficher("journal de démarrage (extraits ACP et s6)", "\n".join(
        l for l in journal.splitlines() if "[acp]" in l or "cont-init" in l or "hook" in l))
    assert pid1.startswith("/package/admin/s6/command/s6-svscan")
    assert "not PID 1" not in journal
    assert "info: hook /opt/acp/bin/acp-gardes exited 0" in journal
    assert "cont-init: info: /etc/cont-init.d/05-acp exited 0" in journal
    assert "[acp] variables validées" in journal
    # Étape P2 : bandeau de la managed scope et commit déployé (inconnu hors Railway).
    assert "[acp] managed scope régénérée : 40 clés de configuration et 38 variables épinglées" in journal
    assert "[acp] commit déployé : inconnu" in journal


def test_passerelle_et_tableau_de_bord_tournent_sous_l_uid_hermes(hermes_en_marche):
    processus = hermes_en_marche.executer(["ps", "-eo", "user,args"], verifier=True).stdout
    afficher("processus", processus)
    lignes = processus.splitlines()
    assert any(l.startswith("hermes") and "hermes dashboard --host 0.0.0.0 --port 9119" in l for l in lignes)
    assert any(l.startswith("hermes") and "hermes gateway run" in l for l in lignes)
    code, statut = hermes_en_marche.json("/api/status")
    assert code == 200 and statut["version"] == "0.21.5"
    assert statut["gateway_running"] is True
    assert statut["gateway_platforms"]["api_server"]["listener_base"] == "http://127.0.0.1:8642"


LIRE_ECOUTES = r"""
import socket, struct
for f, fam in (("/proc/net/tcp", socket.AF_INET), ("/proc/net/tcp6", socket.AF_INET6)):
    for l in open(f).read().splitlines()[1:]:
        p = l.split()
        if p[3] != "0A":
            continue
        a, port = p[1].split(":")
        brut = b"".join(struct.pack("<I", int(a[i:i + 8], 16)) for i in range(0, len(a), 8))
        print(socket.inet_ntop(fam, brut), int(port, 16))
"""


def test_l_api_server_n_ecoute_qu_en_boucle_locale(hermes_en_marche):
    ecoutes = sorted(set(hermes_en_marche.python(LIRE_ECOUTES, verifier=True).stdout.split("\n")) - {""})
    afficher("sockets en écoute (/proc/net/tcp*)", "\n".join(ecoutes))
    assert "127.0.0.1 8642" in ecoutes
    assert "0.0.0.0 9119" in ecoutes
    assert all(e.endswith(" 9119") or e == "127.0.0.1 8642" for e in ecoutes), ecoutes


def test_seul_le_fournisseur_oidc_est_propose_et_la_meta_exige_une_session(hermes_en_marche):
    code, fournisseurs = hermes_en_marche.json("/api/auth/providers")
    afficher("GET /api/auth/providers", _texte_json(fournisseurs))
    assert code == 200
    assert fournisseurs == {"providers": [
        {"name": "self-hosted", "display_name": "Self-Hosted OIDC", "supports_password": False}]}
    code, corps = hermes_en_marche.json("/api/plugins/acp-poste/v1/meta")
    afficher(f"GET /api/plugins/acp-poste/v1/meta sans session : {code}", _texte_json(corps))
    assert code == 401
    code, _ = hermes_en_marche.json("/api/config")
    assert code == 401


def test_les_cles_epinglees_sont_visibles_et_immuables(hermes_en_marche):
    config = hermes_en_marche.executer(["hermes", "config"], utilisateur="hermes", verifier=True).stdout
    bandeau = "\n".join(l for l in config.splitlines() if "managed" in l.lower())
    afficher("hermes config (bandeau de la managed scope)", bandeau)
    for cle in ("kanban.auto_decompose", "kanban.dispatch_profiles", "approvals.mode", "plugins.enabled",
                "plugins.disabled", "plugins.allow_deprecated_imports", "dashboard.oauth.self_hosted.issuer",
                "agent.disabled_toolsets", "platform_toolsets.cli", "hooks_auto_accept"):
        assert cle in bandeau, cle
    valeurs = {}
    for cle in ("kanban.auto_decompose", "approvals.mode", "plugins.allow_deprecated_imports",
                "display.language"):
        valeurs[cle] = hermes_en_marche.executer(["hermes", "config", "get", cle], utilisateur="hermes",
                                                 verifier=True).stdout.strip()
    afficher("hermes config get", "\n".join(f"{k} = {v}" for k, v in valeurs.items()))
    assert valeurs == {"kanban.auto_decompose": "false", "approvals.mode": "manual",
                       "plugins.allow_deprecated_imports": "false", "display.language": "fr"}
    refus = hermes_en_marche.executer(["hermes", "config", "set", "approvals.mode", "off"], utilisateur="hermes")
    afficher(f"hermes config set approvals.mode off : code {refus.returncode}", refus.stdout + refus.stderr)
    assert refus.returncode == 1
    assert "managed by your administrator" in refus.stderr
    assert hermes_en_marche.executer(["hermes", "config", "get", "approvals.mode"], utilisateur="hermes",
                                     verifier=True).stdout.strip() == "manual"


def test_l_agent_ne_peut_ecrire_ni_la_scope_ni_les_greffons_ni_le_theme(hermes_en_marche):
    essais = {
        "créer /opt/data/plugins/intrus": "mkdir /opt/data/plugins/intrus",
        "modifier /opt/data/dashboard-themes/acp.yaml": "echo 'customCSS: x' >> /opt/data/dashboard-themes/acp.yaml",
        "créer /opt/data/dashboard-themes/intrus.yaml": "touch /opt/data/dashboard-themes/intrus.yaml",
        "modifier /etc/hermes/config.yaml": "echo 'approvals: {mode: off}' >> /etc/hermes/config.yaml",
        "modifier /etc/hermes/.env": "echo 'HERMES_DASHBOARD_OIDC_ISSUER=https://x' >> /etc/hermes/.env",
        "modifier /opt/hermes/plugins/acp-poste/meta.py": "echo x >> /opt/hermes/plugins/acp-poste/meta.py",
        "créer /etc/cont-init.d/99-intrus": "touch /etc/cont-init.d/99-intrus",
    }
    rapport = []
    for libelle, commande in essais.items():
        resultat = hermes_en_marche.sh(commande, utilisateur="hermes")
        rapport.append(f"{libelle} : code {resultat.returncode} {resultat.stderr.strip()}")
        assert resultat.returncode != 0, libelle
    # Contrôle positif : l'agent écrit bien dans /opt/data.
    assert hermes_en_marche.sh("touch /opt/data/controle-ecriture", utilisateur="hermes").returncode == 0
    afficher("écritures refusées à l'uid hermes", "\n".join(rapport))
    etat = hermes_en_marche.sh("stat -c '%U:%G %a %n' /etc/hermes /etc/hermes/config.yaml /etc/hermes/.env "
                               "/opt/data/plugins /opt/data/dashboard-themes /opt/data/dashboard-themes/acp.yaml "
                               "/opt/data/acp /run/acp/etat-demarrage.json", verifier=True).stdout
    afficher("propriétaires et droits", etat)
    for ligne in etat.splitlines():
        assert ligne.startswith("root:root 755 ") or ligne.startswith("root:root 644 "), ligne


def test_les_greffons_charges_sont_ceux_attendus(hermes_en_marche):
    liste = hermes_en_marche.executer(["hermes", "plugins", "list"], utilisateur="hermes", verifier=True).stdout
    lignes = {m.group(1): m.group(2) for m in re.finditer(r"│ (\S+)\s+│ (\w+)\s+│", liste)}
    extrait = {k: lignes.get(k) for k in ("acp-poste", "basic", "nous", "drain", "self-hosted")}
    afficher("hermes plugins list (extrait)", _texte_json(extrait))
    assert extrait == {"acp-poste": "enabled", "basic": "disabled", "nous": "disabled", "drain": "disabled",
                       "self-hosted": "enabled"}


def test_l_agent_ne_peut_pas_enregistrer_de_service_supervise_root(hermes_en_marche):
    """s6-supervise tourne en root : un service que l'agent créerait sous /run/service, ou un
    script `run` qu'il réécrirait, serait exécuté en root. 05-acp reprend /run/service et les
    scripts des passerelles à root ; il ne reste à l'agent que la FIFO supervise/control."""
    proprio = hermes_en_marche.sh(
        "stat -c '%U:%G %a' /run/service; stat -c '%U:%G %a' /run/service/gateway-default/run; "
        "stat -c '%U:%G' /run/service/gateway-default/supervise/control", verifier=True).stdout
    afficher("propriétaires des emplacements s6", proprio)
    lignes = proprio.split("\n")
    assert lignes[0].startswith("root:root 755")  # scandir : plus de création de service
    assert lignes[1].startswith("root:root")       # run de la passerelle : plus de réécriture
    assert lignes[2].startswith("hermes:hermes")    # control : la relance par s6-svc reste possible
    essais = {
        "créer un service": "mkdir /run/service/revue-intrus",
        "réécrire le run de la passerelle": "echo x >> /run/service/gateway-default/run",
        "déplacer la passerelle": "mv /run/service/gateway-default /run/service/gateway-vole",
        "réécrire l'amont enveloppé": "echo x >> /run/service/gateway-default/.acp-amont-run",
    }
    rapport = []
    for libelle, commande in essais.items():
        resultat = hermes_en_marche.sh(commande, utilisateur="hermes")
        rapport.append(f"{libelle} : code {resultat.returncode} {resultat.stderr.strip()}")
        assert resultat.returncode != 0, libelle
    afficher("élévation par /run/service refusée à l'uid hermes", "\n".join(rapport))
    # Le run repris est bien enveloppé par la garde de relance d'ACP.
    run = hermes_en_marche.sh("cat /run/service/gateway-default/run", verifier=True).stdout
    assert "acp-garde-relance" in run and "verifier-relance" in run
    # La relance par s6-svc reste possible (la FIFO control appartient à l'agent) : la passerelle
    # repart, ce qui prouve qu'on n'a pas cassé la supervision en reprenant les scripts à root.
    relance = hermes_en_marche.executer(["/command/s6-svc", "-r", "/run/service/gateway-default"],
                                        utilisateur="hermes")
    assert relance.returncode == 0, relance.stderr
    hermes_en_marche.attendre_passerelle()


PIEGE_PATH = r"""
set -eu
mkdir -p /opt/data/.local/bin
cd /opt/data/.local/bin
for d in /usr/local/sbin /usr/local/bin /usr/sbin /usr/bin /sbin /bin; do
  for f in "$d"/*; do
    n=${f##*/}
    [ -e "$n" ] && continue
    printf '#!/bin/sh\n[ "$(/usr/bin/id -u)" = 0 ] && /usr/bin/touch "/opt/data/acp-piege-root-%s"\nexec "%s" "$@"\n' "$n" "$f" > "$n"
    chmod 755 "$n"
  done
done
ls | wc -l
"""


def test_les_scripts_root_n_executent_pas_les_binaires_de_l_agent(ressources, image):
    """L'image officielle met /opt/data/.local/bin, que l'agent possède, dans le PATH de tous
    les scripts root (with-contenv) : un faux `id` déposé là tournait en root à la relance du
    tableau de bord par l'agent (constaté sur 6b5a699). On pose un faux binaire pour CHAQUE
    commande système ; aucun ne doit tourner en root, ni aux relances des services par
    l'agent, ni au redémarrage du conteneur."""
    conteneur = lancer(ressources, image, ENV_VALIDE)
    chemin = conteneur.sh("cat /run/s6/container_environment/PATH", verifier=True).stdout.strip()
    afficher("PATH reçu par les scripts root", chemin)
    assert "/opt/data" not in chemin
    poses = conteneur.sh(PIEGE_PATH, utilisateur="hermes", verifier=True).stdout.strip()
    afficher("faux binaires posés par l'agent dans /opt/data/.local/bin", poses)
    assert int(poses) > 100

    for service in ("dashboard", "gateway-default"):
        relance = conteneur.executer(["/command/s6-svc", "-r", f"/run/service/{service}"],
                                     utilisateur="hermes")
        assert relance.returncode == 0, relance.stderr
    time.sleep(5)
    conteneur.attendre_pret()
    conteneur.attendre_passerelle()
    docker("restart", conteneur.nom, delai=120)
    conteneur.attendre_pret()
    conteneur.attendre_passerelle()

    traces = conteneur.sh("ls /opt/data | grep '^acp-piege-root-' || true", verifier=True).stdout.strip()
    afficher("binaires de l'agent exécutés en root", traces or "aucun")
    assert traces == ""


# =========================================================================== 4. authentifié


MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    """Faux fournisseur d'identité + Hermes (image de test) sur un réseau privé jetable."""
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", "/opt/hermes/.venv/bin/python", image_tests,
           "/opt/acp-tests/outils/idp_factice.py", "--emetteur", "https://idp.acp.test:8443",
           "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem", "--cle", "/opt/acp-tests/ac/idp.key")
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, ENV_VALIDE, volume=volume, reseau=reseau)
    # Modèle factice en boucle locale : Hermes n'a aucun autre fournisseur de modèle.
    docker("exec", "-d", "-u", "hermes", hermes.nom, "/opt/hermes/.venv/bin/python",
           "/opt/acp-tests/outils/modele_factice.py", "--port", "18080", "--journal", "/tmp/modele-factice.jsonl")
    return hermes


def jeton(hermes: Conteneur, **reclamations: str) -> str:
    requete = "&".join(f"{k}={v}" for k, v in {"sub": "proprietaire", "aud": "acp-tableau", **reclamations}.items())
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              f"https://idp.acp.test:8443/emettre?{requete}"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def test_la_meta_repond_avec_une_session_oidc(pile):
    code, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    afficher(f"GET /api/plugins/acp-poste/v1/meta avec session OIDC : {code}", _texte_json(meta))
    assert code == 200
    assert meta["contrat"] == "acp-poste/1"
    assert meta["greffon"] == {"nom": "acp-poste", "version": "0.11.0"}
    assert meta["hermes"]["version"] == meta["hermes"]["version_testee"] == "0.21.5"
    assert meta["hermes"]["conforme"] is True
    assert meta["openrpc"]["identique"] is True and meta["openrpc"]["info_version"] == "1"
    assert meta["image"]["condensat_index"] == EPINGLE["HERMES_IMAGE_INDEX"]
    assert meta["demarrage"]["soul"]["etat"] == "depose"
    # Étape P2 : garde d'exécution présente dans le processus du tableau de bord ; en bouclage
    # local (http), la seule alerte est celle du schéma vu (cookies sans Secure).
    assert meta["garde_execution"]["presente_dans_le_gestionnaire"] is True
    assert meta["garde_execution"]["alerte"] is None
    assert meta["reseau"]["schema_vu"] == "http"
    assert len(meta["alertes"]) == 1 and "en « http » et non en https" in meta["alertes"][0]


@pytest.mark.parametrize("reclamations", [{"cle": "autre"}, {"aud": "intrus"}, {"iss": "https://intrus.example"}])
def test_un_jeton_etranger_est_refuse(pile, reclamations):
    code, corps = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile, **reclamations))
    afficher(f"jeton {reclamations} : {code}", _texte_json(corps))
    # Hermes range un jeton mal signé ou mal adressé en « fournisseur injoignable » (503,
    # plugins/dashboard_auth/_shared.py:192-229) ; dans tous les cas, aucune donnée.
    assert code in (401, 503)
    assert "contrat" not in json.dumps(corps)


EMPREINTE_OPT_HERMES = ("find /opt/hermes -xdev \\( -type f -o -type l -o -type d \\) "
                        "-printf '%p %s %T@ %m %u\\n' 2>/dev/null | LC_ALL=C sort | sha256sum")


def test_la_mise_a_jour_par_le_tableau_de_bord_est_refusee_et_opt_hermes_intact(pile):
    avant = pile.sh(EMPREINTE_OPT_HERMES, verifier=True).stdout.split()[0]
    code, reponse = pile.json("/api/hermes/update", jeton=jeton(pile), methode="POST", corps="{}")
    time.sleep(5)
    apres = pile.sh(EMPREINTE_OPT_HERMES, verifier=True).stdout.split()[0]
    afficher("POST /api/hermes/update", f"code {code}\n{_texte_json(reponse)}\n"
                                         f"empreinte /opt/hermes avant {avant}\n                  après {apres}")
    assert code == 200 and reponse["ok"] is False
    assert avant == apres


ADAPTATEUR = """
import sys, time
sys.path.insert(0, "/opt/hermes/plugins/acp-poste")
import kanban_adapter as k
"""


def test_une_carte_en_triage_du_tableau_poste_n_est_jamais_lancee(pile):
    carte = pile.python(ADAPTATEUR + """
k.assurer_tableau()
print(k.creer_carte_triage(titre="Carte de contrat P1", corps="Doit rester en triage.",
                           cle_idempotence="contrat-p1-triage"))
""", utilisateur="hermes", env={"HERMES_HOME": "/opt/data"}, verifier=True).stdout.strip()
    debut = time.monotonic()
    time.sleep(22)  # plus de quatre ticks du répartiteur (kanban.dispatch_interval_seconds: 5)
    etat = pile.python(ADAPTATEUR + f"""
c = k.lire_carte({carte!r})
print(c.status, c.assignee, c.claim_lock, c.worker_pid, int(time.time()) - c.created_at)
""", utilisateur="hermes", env={"HERMES_HOME": "/opt/data"}, verifier=True).stdout.split()
    journal_gateway = pile.sh("grep -h 'kanban dispatcher: embedded' /opt/data/logs/gateways/default/current "
                              "/opt/data/logs/*.log 2>/dev/null | tail -1").stdout.strip()
    # Journal absent = aucune requête reçue. Constaté localement le 25/09/2026 sur l'image P2 :
    # aucune sonde de métadonnées pendant cette fenêtre, le fichier n'existait pas encore.
    requetes = [json.loads(l) for l in pile.sh("cat /tmp/modele-factice.jsonl 2>/dev/null || true",
                                                verifier=True).stdout.splitlines() if l.strip()]
    appels = [r for r in requetes if r["methode"] == "POST" and r["chemin"].endswith("/chat/completions")]
    afficher("carte en triage sur le tableau poste",
             f"carte {carte} après {time.monotonic() - debut:.0f} s : statut={etat[0]} assigné={etat[1]} "
             f"réclamation={etat[2]} pid={etat[3]} âge={etat[4]} s\n{journal_gateway}\n"
             f"requêtes reçues par le modèle factice : {len(requetes)} sondes de métadonnées "
             f"(GET …/models, POST /api/show), dont {len(appels)} appel(s) de complétion")
    assert "interval=5.0s" in journal_gateway
    assert etat[:4] == ["triage", "poste-windows", "None", "None"]
    # Aucune décomposition : aucune complétion demandée au modèle (seules des sondes de
    # métadonnées, émises par Hermes au démarrage, sont admises).
    assert appels == []


def test_un_tour_d_agent_sur_le_modele_factice(pile):
    tour = pile.sh("cd /opt/data && timeout 120 hermes chat -q 'Dis bonjour.'", utilisateur="hermes", delai=180)
    requetes = pile.sh("cat /tmp/modele-factice.jsonl", verifier=True).stdout
    afficher("hermes chat -q sur le modèle factice", tour.stdout[-1500:] + "\n--- requêtes reçues ---\n" + requetes)
    assert tour.returncode == 0
    assert "Réponse du modèle factice ACP." in tour.stdout
    assert any('"POST"' in l and "/chat/completions" in l for l in requetes.splitlines())


CONFIG_PIEGEE = """\
approvals:
  mode: "off"
kanban:
  auto_decompose: true
  dispatch_interval_seconds: 5
plugins:
  enabled: [acp-poste, outil]
  disabled: []
  allow_deprecated_imports: true
dashboard:
  trusted_proxies: [10.0.0.0/8]
  basic_auth:
    username: intrus
    password: motdepasse-intrus
  oauth:
    client_id: "agent:autre"
    self_hosted:
      issuer: https://intrus.example
      client_id: intrus
platforms:
  api_server:
    enabled: true
    extra:
      host: 0.0.0.0
      port: 8642
      key: cle-intrus-tres-longue-0123456789
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""

ENV_PIEGE = """\
HERMES_DASHBOARD_OIDC_ISSUER=https://intrus.example
HERMES_DASHBOARD_OIDC_CLIENT_ID=intrus
HERMES_DASHBOARD_OAUTH_CLIENT_ID=agent:autre
HERMES_DASHBOARD_BASIC_AUTH_USERNAME=intrus
HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=motdepasse-intrus
HERMES_DASHBOARD_PUBLIC_URL=https://intrus.example
HTTPS_PROXY=http://127.0.0.1:9
SSL_CERT_FILE=/opt/data/intrus.pem
"""


def _ecoutes(conteneur: Conteneur) -> set:
    return set(conteneur.python(LIRE_ECOUTES, verifier=True).stdout.split("\n")) - {""}


def _verifier_connexion_intacte(pile: Conteneur, contexte: str) -> None:
    code, fournisseurs = pile.json("/api/auth/providers")
    code_login, _, redirection = pile.http("/auth/login?provider=self-hosted")
    code_basic, _, _ = pile.http("/auth/login?provider=basic")
    code_meta, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    code_intrus, _ = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile, aud="intrus"))
    afficher(f"connexion après {contexte}",
             f"/api/auth/providers : {code} {json.dumps(fournisseurs)}\n"
             f"/auth/login?provider=self-hosted : {code_login} → {redirection}\n"
             f"/auth/login?provider=basic : {code_basic}\n"
             f"meta, jeton du propriétaire : {code_meta} ; jeton pour « intrus » : {code_intrus}")
    assert [p["name"] for p in fournisseurs["providers"]] == ["self-hosted"]
    assert code_login == 302
    assert redirection.startswith("https://idp.acp.test:8443/authorize?")
    assert "client_id=acp-tableau&" in redirection
    assert "redirect_uri=https%3A%2F%2Fhermes.acp.test%2Fauth%2Fcallback" in redirection
    assert code_basic == 404
    assert code_meta == 200
    assert code_intrus in (401, 503)
    # La portée gérée n'est pas détournée : aucune alerte de portée dans la meta.
    assert isinstance(meta, dict) and not any("Portée gérée détournée" in a for a in meta["alertes"])


def test_une_injection_dans_opt_data_est_neutralisee_quand_l_agent_relance_le_tableau_de_bord(pile):
    pile.executer(["sh", "-c", "cat > /opt/data/config.yaml"], utilisateur="hermes", entree=CONFIG_PIEGEE,
                  verifier=True)
    pile.executer(["sh", "-c", "cat >> /opt/data/.env"], utilisateur="hermes", entree=ENV_PIEGE, verifier=True)
    avant = pile.sh("pgrep -f 'hermes dashboard'", verifier=True).stdout.split()
    # L'agent (uid hermes) peut relancer le tableau de bord ET la passerelle lui-même (la FIFO
    # supervise/control lui reste accessible) ; 05-acp ne tourne pas alors. La config.yaml et
    # le .env piégés ne portent aucune variable d'évasion, donc la garde de relance les laisse
    # repartir ; c'est la managed scope, appliquée par-dessus, qui neutralise l'injection.
    relance = pile.executer(["/command/s6-svc", "-r", "/run/service/dashboard"], utilisateur="hermes")
    assert relance.returncode == 0, relance.stderr
    relance_gw = pile.executer(["/command/s6-svc", "-r", "/run/service/gateway-default"], utilisateur="hermes")
    assert relance_gw.returncode == 0, relance_gw.stderr
    time.sleep(3)
    pile.attendre_pret()
    pile.attendre_passerelle()
    apres = pile.sh("pgrep -f 'hermes dashboard'", verifier=True).stdout.split()
    assert set(avant).isdisjoint(apres), (avant, apres)
    _verifier_connexion_intacte(pile, "injection et relance du tableau de bord et de la passerelle")
    # L'api_server, que la config.yaml piégée place sur 0.0.0.0, reste en boucle locale : le seul
    # écouteur public reste le tableau de bord (9119). (La pile expose aussi le modèle factice en
    # 127.0.0.1:18080 et le résolveur DNS de Docker en 127.0.0.11 ; ni l'un ni l'autre n'est public.)
    ecoutes = _ecoutes(pile)
    afficher("sockets en écoute après injection api_server", "\n".join(sorted(ecoutes)))
    assert "127.0.0.1 8642" in ecoutes
    assert "0.0.0.0 8642" not in ecoutes
    publics = [e for e in ecoutes if e.startswith("0.0.0.0 ")]
    assert publics == ["0.0.0.0 9119"], ecoutes
    _, statut = pile.json("/api/status")
    assert statut["gateway_platforms"]["api_server"]["listener_base"] == "http://127.0.0.1:8642"


def test_une_injection_reste_neutralisee_apres_redemarrage_du_conteneur(pile):
    empreintes = ("sha256sum /etc/hermes/config.yaml /etc/hermes/.env /opt/data/dashboard-themes/acp.yaml "
                  "/opt/data/SOUL.md")
    avant = pile.sh(empreintes, verifier=True).stdout
    docker("restart", pile.nom, delai=240)
    pile.attendre_pret()
    apres = pile.sh(empreintes, verifier=True).stdout
    afficher("empreintes avant et après redémarrage (idempotence)", f"{avant}\n{apres}")
    assert avant == apres
    _verifier_connexion_intacte(pile, "redémarrage du conteneur")
    assert pile.executer(["hermes", "config", "get", "approvals.mode"], utilisateur="hermes",
                         verifier=True).stdout.strip() == "manual"


def test_un_soul_modifie_par_le_proprietaire_est_garde_et_signale(pile):
    pile.executer(["sh", "-c", "cat > /opt/data/SOUL.md"], utilisateur="hermes",
                  entree="Persona choisie par le propriétaire.\n", verifier=True)
    docker("restart", pile.nom, delai=240)
    pile.attendre_pret()
    contenu = pile.executer(["cat", "/opt/data/SOUL.md"], verifier=True).stdout
    code, meta = pile.json("/api/plugins/acp-poste/v1/meta", jeton=jeton(pile))
    afficher("SOUL.md modifié puis redémarrage", f"contenu : {contenu.strip()}\nétat : "
             f"{_texte_json(meta['demarrage']['soul'])}\nalertes : {_texte_json(meta['alertes'])}")
    assert contenu == "Persona choisie par le propriétaire.\n"
    assert meta["demarrage"]["soul"]["etat"] == "divergent"
    assert any("SOUL.md a été modifié" in a for a in meta["alertes"])


# ===================================================== 5. évasion de la managed scope refusée


CONFIG_API_SERVER_PUBLIC = """\
platforms:
  api_server:
    enabled: true
    extra:
      host: 0.0.0.0
      port: 8642
      key: cle-intrus-tres-longue-0123456789
"""


def test_l_api_server_reste_en_boucle_locale_meme_sans_cle_dans_l_env(ressources, image):
    """Défaut P1 : l'agent retire API_SERVER_KEY de /opt/data/.env (l'enrôlement par
    l'environnement s'arrête, gateway/config_env.py:307-315) puis enrôle l'api_server sur
    0.0.0.0 via /opt/data/config.yaml. La managed scope épingle l'hôte : l'écoute reste locale."""
    conteneur = lancer(ressources, image, ENV_VALIDE)
    conteneur.executer(["sh", "-c", "sed -i '/^API_SERVER_KEY=/d' /opt/data/.env"],
                       utilisateur="hermes", verifier=True)
    conteneur.executer(["sh", "-c", "cat > /opt/data/config.yaml"], utilisateur="hermes",
                       entree=CONFIG_API_SERVER_PUBLIC, verifier=True)
    relance = conteneur.executer(["/command/s6-svc", "-r", "/run/service/gateway-default"],
                                 utilisateur="hermes")
    assert relance.returncode == 0, relance.stderr
    time.sleep(3)
    conteneur.attendre_passerelle()
    ecoutes = _ecoutes(conteneur)
    afficher("api_server après retrait de la clé et enrôlement 0.0.0.0 par config.yaml",
             "\n".join(sorted(ecoutes)))
    assert "127.0.0.1 8642" in ecoutes
    assert "0.0.0.0 8642" not in ecoutes
    assert all(e.endswith(" 9119") or e == "127.0.0.1 8642" for e in ecoutes), ecoutes


def _attendre_arret(nom: str, delai: float = 40) -> int:
    """Attend qu'un conteneur s'arrête et rend son code de sortie."""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        etat = docker("inspect", "-f", "{{.State.Running}}", nom, verifier=False).stdout.strip()
        if etat == "false":
            return int(docker("inspect", "-f", "{{.State.ExitCode}}", nom, verifier=True).stdout.strip())
        time.sleep(1)
    raise AssertionError(f"le conteneur {nom} tourne encore après {delai} s")


def test_hermes_managed_dir_injecte_dans_le_volume_est_fail_closed(ressources, image):
    """HERMES_MANAGED_DIR ne peut pas être épinglée (elle choisit la portée gérée). Posée par
    l'agent dans /opt/data/.env, elle est refusée : la relance du tableau de bord échoue fermé,
    et le redémarrage du conteneur refuse de démarrer (message français, code 1)."""
    conteneur = lancer(ressources, image, ENV_VALIDE)
    conteneur.executer(["sh", "-c", "mkdir -p /opt/data/faux-gere && "
                        "printf 'approvals:\\n  mode: \"off\"\\n' > /opt/data/faux-gere/config.yaml && "
                        "printf 'HERMES_MANAGED_DIR=/opt/data/faux-gere\\n' >> /opt/data/.env"],
                       utilisateur="hermes", verifier=True)

    # 1. Relance du tableau de bord par l'agent : la garde root (enveloppe de run) refuse. Le
    #    tableau de bord ne repart donc jamais sur la portée détournée ; il boucle sur le refus.
    relance = conteneur.executer(["/command/s6-svc", "-r", "/run/service/dashboard"], utilisateur="hermes")
    assert relance.returncode == 0, relance.stderr
    time.sleep(8)  # la garde de relance temporise 5 s sur refus, puis s6 réessaie
    journal = conteneur.journaux()
    afficher("relance du tableau de bord avec HERMES_MANAGED_DIR injectée",
             "\n".join(l for l in journal.splitlines() if "acp" in l.lower())[-2000:])
    # La garde a bien refusé la relance (au moins une fois ; s6 boucle donc jamais servi détourné).
    assert journal.count("REFUS : relance du tableau de bord refusée") >= 1

    # 2. Redémarrage du conteneur : les gardes de démarrage refusent (échec fermé, code 1).
    docker("restart", conteneur.nom, verifier=False, delai=60)
    code = _attendre_arret(conteneur.nom)
    journal = conteneur.journaux()
    afficher(f"redémarrage avec HERMES_MANAGED_DIR injectée : code {code}",
             "\n".join(l for l in journal.splitlines() if "[acp]" in l)[-2000:])
    assert code == 1
    assert "[acp] REFUS" in journal and "HERMES_MANAGED_DIR" in journal
    assert "des variables interdites ont été injectées dans le volume" in journal
