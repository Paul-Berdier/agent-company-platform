"""Contrat du fournisseur d'identité (étape P2) : image identite/ (Authelia 4.39.28 épinglé, garde
root acp-identite-entree, administration acp-identite-admin) et compatibilité OIDC avec le vrai
tableau de bord de Hermes, À TRAVERS un bord TLS factice qui imite celui de Railway
(outils/bord_factice.py ; pile décrite dans pile_identite.py).

Lancement : comme les autres tests de contrat (conftest.py), avec en plus
  ACP_IMAGE_IDENTITE=acp-identite:ci

Ce qu'ils prouvent, sur les images réellement construites :
1. image épinglée par condensat, sans secret, configuration figée en lecture seule ;
2. refus en français de la garde (variables, volume, secrets, arguments, utilisateur), erreurs
   rassemblées, empreinte jamais affichée ;
3. démarrage nominal « comme sur Railway », configuration validée par `authelia config validate` ;
4. secrets et clé RS256 générés UNE fois, conservés au redémarrage ;
5. un seul utilisateur, réécrit à chaque démarrage hors du volume ; tout autre sujet refusé par la
   politique OIDC du client (défense en profondeur, prouvée avec un second compte de TEST posé en
   contournant la garde) ;
6. maintenance « /bin/sh -c "exec sleep infinity" » et acp-identite-admin depuis une session sans
   environnement ;
7. découverte acceptée par Hermes à travers le bord, redirect_uri altérée refusée, en-têtes du bord
   mesurés ;
8. mémoire d'Authelia sous 10 puis 20 premiers facteurs simultanés : valeur mesurée et consignée,
   limite retenue pour railway.ts.
Le parcours complet en navigateur (passkey, consentement, rafraîchissement, révocation) est dans
hermes/tests/e2e.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from pile_identite import (
    CLIENT,
    EMETTEUR,
    HOTE_HERMES,
    HOTE_IDENTITE,
    MOT_DE_PASSE,
    PORTEES,
    RACINE_DEPOT,
    URL_HERMES,
    UTILISATEUR,
    Pile,
    attendre_identite,
    docker,
    env_identite,
    journal,
    lignes_du_bord,
    monter_pile,
    options_env,
)

IMAGE_AMONT = ("docker.io/authelia/authelia:4.39.28"
               "@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54")
GIO = 1024 ** 3
# Limite mémoire RETENUE pour le service identite (railway.ts : limitOverride.containers.memoryBytes),
# fixée d'après test_memoire_premier_facteur_concurrent : le pic mesuré sous 20 premiers facteurs
# simultanés (~1,35 Gio localement) doit rester sous les deux tiers de la limite.
LIMITE_MEMOIRE_OCTETS = int(2.5 * GIO)
ENV_RAILWAY = {"RAILWAY_ENVIRONMENT_ID": "env-contrat", "RAILWAY_SERVICE_ID": "svc-contrat",
               "RAILWAY_DEPLOYMENT_ID": "dep-contrat", "RAILWAY_VOLUME_MOUNT_PATH": "/config",
               "RAILWAY_RUN_UID": "0"}
SECRETS = ("session", "stockage", "jwt-reinitialisation", "oidc-hmac")


def afficher(titre: str, texte: str) -> None:
    print(f"\n===== {titre} =====\n{texte.rstrip()}\n", flush=True)


def _texte(valeur: object) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=2)


def _lignes_garde(journal_complet: str) -> str:
    return "\n".join(l for l in journal_complet.splitlines() if "[acp-identite" in l or "level=" in l)


def _wget(conteneur: str, chemin: str, *, corps: Optional[str] = None, hote: str = HOTE_IDENTITE,
          utilisateur: Optional[str] = None) -> Tuple[int, str]:
    """Requête DIRECTE à Authelia (sans bord), en-têtes de bord posés à la main : (code, corps)."""
    commande = ["exec"] + (["-u", utilisateur] if utilisateur else []) + [
        conteneur, "wget", "-S", "-q", "-O", "-", "--header", "X-Forwarded-Proto: https",
        "--header", f"X-Forwarded-Host: {hote}"]
    if corps is not None:
        commande += ["--header", "Content-Type: application/json", "--post-data", corps]
    resultat = docker(*commande, f"http://127.0.0.1:9091{chemin}", verifier=False)
    codes = re.findall(r"HTTP/1\.1 (\d{3})", resultat.stderr)
    return (int(codes[-1]) if codes else 0), resultat.stdout


@pytest.fixture(scope="module")
def pile():
    p = Pile()
    yield p
    p.nettoyer()


# ============================================================ 1. image épinglée, sans secret


def test_image_identite_epinglee_sans_secret(image_identite):
    dockerfile = (RACINE_DEPOT / "identite" / "Dockerfile").read_text(encoding="utf-8")
    assert f"FROM {IMAGE_AMONT}\n" in dockerfile
    assert len(re.findall(r"^FROM ", dockerfile, re.M)) == 1
    config = json.loads(docker("image", "inspect", image_identite, "--format", "{{json .Config}}").stdout)
    env = dict(v.split("=", 1) for v in config["Env"])
    afficher("configuration de l'image identite", _texte({k: config.get(k) for k in
                                                           ("Env", "Entrypoint", "Cmd", "User", "Healthcheck")}))
    assert {k: v for k, v in env.items() if k != "PATH"} == {
        "PUID": "1000", "PGID": "1000", "X_AUTHELIA_CONFIG": "/etc/authelia/configuration.yml",
        "X_AUTHELIA_CONFIG_FILTERS": "template"}
    assert config["Entrypoint"] == ["/opt/acp-identite/acp-identite-entree"]
    assert not config.get("Cmd")
    assert not config.get("User")
    assert config["Healthcheck"]["Test"] == ["NONE"]
    # L'image dérive bien de l'image amont épinglée : ses couches en sont le préfixe exact.
    docker("pull", "-q", IMAGE_AMONT, delai=600)
    amont = json.loads(docker("image", "inspect", IMAGE_AMONT, "--format", "{{json .RootFS.Layers}}").stdout)
    nous = json.loads(docker("image", "inspect", image_identite, "--format", "{{json .RootFS.Layers}}").stdout)
    assert nous[:len(amont)] == amont and len(nous) > len(amont)
    # Fichiers d'ACP : root, lecture seule pour Authelia ; ni /config ni secret dans l'image ; le
    # fichier d'environnement du HEALTHCHECK amont (0666, sourcé en root) est retiré.
    etat = docker("run", "--rm", "--entrypoint", "/bin/sh", image_identite, "-c",
                  "stat -c '%U:%G %a %n' /etc/authelia /etc/authelia/configuration.yml /opt/acp-identite "
                  "/opt/acp-identite/acp-identite-entree /opt/acp-identite/acp-identite-admin; "
                  "ls -A /config 2>&1; ls -A /app; sha256sum /etc/authelia/configuration.yml; "
                  "/app/authelia --version; find /etc/authelia /opt/acp-identite /app -name '*.pem' -o -name '*.key'"
                  ).stdout
    afficher("fichiers de l'image identite", etat)
    for ligne in ("root:root 755 /etc/authelia", "root:root 644 /etc/authelia/configuration.yml",
                  "root:root 755 /opt/acp-identite", "root:root 755 /opt/acp-identite/acp-identite-entree",
                  "root:root 755 /opt/acp-identite/acp-identite-admin"):
        assert ligne in etat
    assert "/config: No such file or directory" in etat
    assert ".healthcheck.env" not in etat
    assert "authelia version v4.39.28" in etat
    assert ".pem" not in etat.split("authelia version v4.39.28", 1)[1]
    locale = hashlib.sha256((RACINE_DEPOT / "identite" / "configuration.yml").read_bytes()).hexdigest()
    assert f"{locale}  /etc/authelia/configuration.yml" in etat


def test_gabarit_sans_secret_et_client_unique():
    """Lecture statique du gabarit : aucun secret en clair, un seul client, public, PKCE S256,
    réponse en query, politique « deny » par défaut, retour vers ACP_HERMES_URL seulement."""
    texte = (RACINE_DEPOT / "identite" / "configuration.yml").read_text(encoding="utf-8")
    for cle in ("secret", "encryption_key", "jwt_secret", "hmac_secret"):
        for valeur in re.findall(rf"^\s*{cle}:\s*(.+)$", texte, re.M):
            assert valeur.startswith("'{{ secret \"/config/secrets/"), (cle, valeur)
    assert re.findall(r"^\s*key:\s*(.+)$", texte, re.M) == [
        '{{ secret "/config/secrets/oidc-rs256.pem" | mindent 10 "|" | msquote }}']
    assert "password:" not in texte.split("authentication_backend:", 1)[1].split("access_control:", 1)[0].replace(
        "password_reset:", "").replace("password_change:", "")
    assert len(re.findall(r"^\s*- client_id:", texte, re.M)) == 1
    client = texte.split("- client_id: 'hermes-acp'", 1)[1]
    for attendu in ("public: true", "require_pkce: true", "pkce_challenge_method: 'S256'",
                    "response_modes: ['query']", "token_endpoint_auth_method: 'none'",
                    "id_token_signed_response_alg: 'RS256'", "authorization_policy: 'proprietaire'",
                    "- '{{ mustEnv \"ACP_HERMES_URL\" }}/auth/callback'"):
        assert attendu in client, attendu
    assert len(re.findall(r"/auth/callback", texte)) == 1
    politique = texte.split("authorization_policies:", 1)[1].split("lifespans:", 1)[0]
    assert "default_policy: 'deny'" in politique
    assert politique.count("- policy:") == 1 and "subject: 'user:{{ mustEnv \"ACP_IDP_UTILISATEUR\" }}'" in politique
    assert "enforce_pkce: 'always'" in texte and "enable_pkce_plain_challenge: false" in texte
    assert "refresh_token: '7 days'" in texte
    assert "path: '/run/acp-identite/utilisateurs.yml'" in texte and "watch: false" in texte


# ============================================================ 2. refus de la garde


def _preparer_volume(pile: Pile, image: str, script: str) -> str:
    volume = pile.volume()
    if script:
        docker("run", "--rm", "-v", f"{volume}:/config", "--entrypoint", "/bin/sh", image, "-c", script)
    return volume


EMPREINTE_FACTICE = "$argon2id$v=19$m={m},t={t},p=4$qikzxx9S29XEfNXmVcowsw$JyiSNAgpo6IdOilMw6Fjgghg/tKi+j5kWA2XxMjKuos"

CAS_REFUS = {
    # identifiant : (modifications d'environnement, options docker, arguments, script de volume ou None
    #                (= aucun volume), motifs attendus)
    "variables_absentes": ({k: None for k in ("ACP_IDP_DOMAINE", "ACP_HERMES_URL", "ACP_IDP_UTILISATEUR", "ACP_IDP_NOM",
                                              "ACP_IDP_EMAIL", "ACP_IDP_MOT_DE_PASSE_ARGON2")}, [], [], "",
                           [f"la variable {k} est obligatoire et absente" for k in (
                               "ACP_IDP_DOMAINE", "ACP_HERMES_URL", "ACP_IDP_UTILISATEUR", "ACP_IDP_NOM", "ACP_IDP_EMAIL",
                               "ACP_IDP_MOT_DE_PASSE_ARGON2")]),
    "gabarit_non_remplace": ({"ACP_IDP_DOMAINE": "<libellé-identite>.up.railway.app",
                              "ACP_HERMES_URL": "https://<libellé-hermes>.up.railway.app"}, [], [], "",
                             ["ACP_IDP_DOMAINE porte encore la valeur de gabarit",
                              "ACP_HERMES_URL porte encore la valeur de gabarit"]),
    "domaine_prive": ({"ACP_IDP_DOMAINE": "identite.railway.internal"}, [], [], "",
                      ["ACP_IDP_DOMAINE doit être le domaine PUBLIC du service"]),
    "domaine_avec_port": ({"ACP_IDP_DOMAINE": "identite-acp.test:443"}, [], [], "",
                          ["ACP_IDP_DOMAINE doit être un nom d'hôte public en minuscules"]),
    "url_http": ({"ACP_HERMES_URL": "http://hermes-acp.test"}, [], [], "",
                 ["ACP_HERMES_URL doit être https://<hôte public>, sans port, chemin ni barre finale"]),
    "url_barre_finale": ({"ACP_HERMES_URL": "https://hermes-acp.test/"}, [], [], "",
                         ["ACP_HERMES_URL doit être https://<hôte public>"]),
    "url_meme_hote": ({"ACP_HERMES_URL": "https://identite-acp.test"}, [], [], "",
                      ["ACP_HERMES_URL et ACP_IDP_DOMAINE désignent le même hôte"]),
    "utilisateur": ({"ACP_IDP_UTILISATEUR": "Propriétaire"}, [], [], "",
                    ["ACP_IDP_UTILISATEUR doit compter de 1 à 32 caractères"]),
    "nom_guillemet": ({"ACP_IDP_NOM": 'Nom "piégé"'}, [], [], "",
                      ["ACP_IDP_NOM doit compter au plus 64 caractères, sans guillemet double"]),
    "nom_saut_de_ligne": ({"ACP_IDP_NOM": "Nom\nusers:"}, [], [], "",
                          ["ACP_IDP_NOM doit compter au plus 64 caractères"]),
    "email": ({"ACP_IDP_EMAIL": "pas-une-adresse"}, [], [], "", ["ACP_IDP_EMAIL n'est pas une adresse électronique valide"]),
    "empreinte_bcrypt": ({"ACP_IDP_MOT_DE_PASSE_ARGON2": "$2y$10$abcdefghijklmnopqrstuuYv5bHnQnoDgp2bBqJxKkJ5rQ9bY5Zy2"},
                         [], [], "", ["ACP_IDP_MOT_DE_PASSE_ARGON2 doit être une empreinte argon2id"]),
    "empreinte_memoire_excessive": ({"ACP_IDP_MOT_DE_PASSE_ARGON2": EMPREINTE_FACTICE.format(m=131072, t=3)}, [], [], "",
                                    ["demande m=131072 Kio par vérification : au plus 65536"]),
    "empreinte_trop_faible": ({"ACP_IDP_MOT_DE_PASSE_ARGON2": EMPREINTE_FACTICE.format(m=4096, t=3)}, [], [], "",
                              ["demande m=4096 Kio : au moins 19456"]),
    "variable_authelia": ({"AUTHELIA_IDENTITY_PROVIDERS_OIDC_CLIENTS_0_REDIRECT_URIS": "https://intrus.test/auth/callback"},
                          [], [], "", ["la variable AUTHELIA_IDENTITY_PROVIDERS_OIDC_CLIENTS_0_REDIRECT_URIS est interdite"]),
    "x_authelia_autre": ({"X_AUTHELIA_HEALTHCHECK": "1"}, [], [], "",
                         ["la variable X_AUTHELIA_HEALTHCHECK est interdite"]),
    "configuration_deplacee": ({"X_AUTHELIA_CONFIG": "/config/autre.yml", "X_AUTHELIA_CONFIG_FILTERS": "expand-env"},
                               [], [], "", ["X_AUTHELIA_CONFIG doit valoir /etc/authelia/configuration.yml",
                                            "X_AUTHELIA_CONFIG_FILTERS doit valoir « template »"]),
    "cumul_puid_umask_uid": ({"PUID": "0", "PGID": "0", "UMASK": "0022", "RAILWAY_RUN_UID": "1000"}, [], [], "",
                             ["PUID doit valoir 1000", "PGID doit valoir 1000", "la variable UMASK est interdite",
                              "la variable RAILWAY_RUN_UID vaut « 1000 »"]),
    "railway_sans_volume": (dict(ENV_RAILWAY, RAILWAY_VOLUME_MOUNT_PATH=None), [], [], "",
                            ["sur Railway, le volume du service doit être monté sur /config (reçu « aucun volume »)"]),
    "railway_sans_montage": (dict(ENV_RAILWAY), [], [], None,
                             ["sur Railway, /config n'est pas un point de montage"]),
    "sans_volume": ({}, [], [], None, ["le volume /config est absent"]),
    "argument": ({}, [], ["authelia", "--version"], "", ["aucun argument n'est admis (reçu 2)"]),
    "utilisateur_non_root": ({}, ["-u", "1000:1000"], [], "", ["la garde doit s'exécuter en root (uid 1000)"]),
    "lien_symbolique": ({}, [], [], "ln -s /etc/shadow /config/lien",
                        ["/config contient un lien symbolique ou un fichier spécial (« /config/lien »)"]),
    "secret_vide": ({}, [], [], "mkdir -m 0700 /config/secrets && : > /config/secrets/session",
                    ["/config/secrets/session est vide : un secret n'est jamais régénéré en silence"]),
    "stockage_perdu": ({}, [], [], "touch /config/db.sqlite3",
                       ["la clé de chiffrement du stockage (/config/secrets/stockage) est absente alors que la base"]),
    "cle_non_pem": ({}, [], [], "mkdir -m 0700 /config/secrets && cd /config/secrets && "
                                "for n in session stockage jwt-reinitialisation oidc-hmac; do echo x > $n; done && "
                                "echo 'pas une clé' > oidc-rs256.pem",
                    ["/config/secrets/oidc-rs256.pem n'est pas une clé privée PEM (PKCS #8)"]),
}


@pytest.mark.parametrize("cas", sorted(CAS_REFUS))
def test_refus_identite_en_francais(pile, image_identite, empreinte_argon2, cas):
    modifications, options, arguments, script, motifs = CAS_REFUS[cas]
    env = env_identite(empreinte_argon2, **modifications)
    nom = pile.nom("refus")
    pile.conteneurs.append(nom)
    montage = [] if script is None else ["-v", f"{_preparer_volume(pile, image_identite, script)}:/config"]
    resultat = docker("run", "--name", nom, *montage, *options, *options_env(env), image_identite, *arguments,
                      verifier=False, delai=120)
    sortie = resultat.stdout + resultat.stderr
    afficher(f"garde identite, cas « {cas} » : code {resultat.returncode}", _lignes_garde(sortie))
    assert resultat.returncode == 1
    for motif in motifs:
        assert f"[acp-identite] REFUS : " in sortie and motif in sortie, motif
    assert "[acp-identite] Démarrage arrêté (échec fermé)." in sortie
    assert "Authelia v4.39.28 is starting" not in sortie
    assert empreinte_argon2 not in sortie
    if env.get("ACP_IDP_MOT_DE_PASSE_ARGON2"):
        assert env["ACP_IDP_MOT_DE_PASSE_ARGON2"] not in sortie
    assert "[acp-identite] variables validées" not in sortie


# ============================================================ 3-6. démarrage nominal, secrets, utilisateur


@pytest.fixture(scope="module")
def identite_seule(pile, image_identite, empreinte_argon2) -> str:
    """Démarrage « comme sur Railway » : marqueurs, volume déclaré et réellement monté sur /config."""
    return pile.lancer_identite(image_identite, dict(env_identite(empreinte_argon2), **ENV_RAILWAY))


def test_demarrage_nominal_et_config_valide(identite_seule, empreinte_argon2):
    sortie = journal(identite_seule)
    afficher("démarrage nominal du fournisseur d'identité", _lignes_garde(sortie))
    assert ("[acp-identite] variables validées ; utilisateur unique configuré (identifiant non journalisé) ; "
            "émetteur https://identite-acp.test ; client hermes-acp → https://hermes-acp.test/auth/callback") in sortie
    # Relecture P2 : ni l'identifiant ni l'adresse n'apparaissent dans les lignes de la garde, versées
    # au dépôt public.
    lignes_garde = "\n".join(l for l in sortie.splitlines() if "[acp-identite]" in l)
    assert "proprietaire" not in lignes_garde and "@" not in lignes_garde, lignes_garde
    assert "Authelia v4.39.28 is starting" in sortie and "Startup complete" in sortie
    assert empreinte_argon2 not in sortie
    pid1 = docker("exec", identite_seule, "sh", "-c", "tr '\\0' ' ' < /proc/1/cmdline; echo; stat -c '%u:%g' /proc/1").stdout
    # Même uid qu'Authelia : seul lui peut relire l'environnement de son PID 1.
    env_pid1 = docker("exec", "-u", "1000:1000", identite_seule, "sh", "-c",
                      "tr '\\0' '\\n' < /proc/1/environ | cut -d= -f1 | sort").stdout.split()
    validation = docker("exec", "-u", "1000:1000", identite_seule, "/app/authelia", "config", "validate",
                        verifier=False)
    modes = docker("exec", identite_seule, "sh", "-c", "stat -c '%u:%g %a %n' /config /config/db.sqlite3 "
                                                       "/config/notification.txt").stdout
    afficher("PID 1, environnement du PID 1 (noms), authelia config validate, /config",
             f"{pid1}\n{env_pid1}\ncode {validation.returncode} :\n{validation.stdout}{validation.stderr}\n{modes}")
    assert pid1.split("\n")[0].strip() == "authelia" and "1000:1000" in pid1
    assert "ACP_IDP_UTILISATEUR" in env_pid1 and "ACP_IDP_DOMAINE" in env_pid1
    assert not {"ACP_IDP_MOT_DE_PASSE_ARGON2", "ACP_IDP_NOM", "ACP_IDP_EMAIL"} & set(env_pid1)
    assert validation.returncode == 0
    assert "Configuration parsed and loaded" in validation.stdout
    avertissements = [l.strip() for l in validation.stdout.splitlines() if l.strip().startswith("- ")]
    assert avertissements == ["- access_control: no rules have been specified so the 'default_policy' of "
                              "'two_factor' is going to be applied to all requests"]
    assert "1000:1000 600 /config/db.sqlite3" in modes and "1000:1000 600 /config/notification.txt" in modes


def _jwks(conteneur: str) -> dict:
    code, corps = _wget(conteneur, "/jwks.json")
    assert code == 200, corps
    return json.loads(corps)


def _empreintes_secrets(conteneur: str) -> str:
    return docker("exec", conteneur, "sh", "-c", "cd /config/secrets && sha256sum * | sort").stdout


def test_secrets_generes_une_fois(identite_seule):
    premier = journal(identite_seule)
    assert ("[acp-identite] secrets de /config/secrets : générés : session stockage jwt-reinitialisation "
            "oidc-hmac oidc-rs256.pem ; conservés : aucun") in premier
    etat = docker("exec", identite_seule, "sh", "-c",
                  "stat -c '%u:%g %a %s %n' /config/secrets /config/secrets/*; ls -A /config/secrets").stdout
    afficher("secrets générés au premier démarrage (sans leur valeur)", etat)
    assert "1000:1000 700" in etat.splitlines()[0]
    for nom in SECRETS:
        assert f"1000:1000 600 64 /config/secrets/{nom}" in etat
    assert re.search(r"1000:1000 600 3\d{3} /config/secrets/oidc-rs256\.pem", etat)
    assert sorted(etat.split("\n", 6)[-1].split()) == sorted([*SECRETS, "oidc-rs256.pem"])
    avant, jwks_avant = _empreintes_secrets(identite_seule), _jwks(identite_seule)
    [cle] = jwks_avant["keys"]
    taille = len(base64.urlsafe_b64decode(cle["n"] + "==")) * 8
    assert (cle["kid"], cle["kty"], cle["alg"], cle["use"], taille) == ("acp-rs256-1", "RSA", "RS256", "sig", 4096)
    docker("restart", identite_seule, delai=180)
    attendre_identite(identite_seule)
    second = journal(identite_seule)
    afficher("second démarrage", _lignes_garde(second.split("Startup complete", 1)[1]))
    assert ("[acp-identite] secrets de /config/secrets : générés : aucun ; conservés : session stockage "
            "jwt-reinitialisation oidc-hmac oidc-rs256.pem") in second
    assert _empreintes_secrets(identite_seule) == avant
    assert _jwks(identite_seule) == jwks_avant


def _utilisateurs(conteneur: str) -> List[str]:
    texte = docker("exec", conteneur, "cat", "/run/acp-identite/utilisateurs.yml").stdout
    return re.findall(r"^  '([^']+)':$", texte, re.M)


def test_un_seul_utilisateur(identite_seule, empreinte_argon2):
    etat = docker("exec", identite_seule, "sh", "-c",
                  "stat -c '%u:%g %a %n' /run/acp-identite /run/acp-identite/utilisateurs.yml; ls -A /run/acp-identite"
                  ).stdout
    ecriture = docker("exec", "-u", "1000:1000", identite_seule, "sh", "-c",
                      "echo x >> /run/acp-identite/utilisateurs.yml", verifier=False)
    creation = docker("exec", "-u", "1000:1000", identite_seule, "sh", "-c", "touch /run/acp-identite/autre.yml",
                      verifier=False)
    code_intrus, _ = _wget(identite_seule, "/api/firstfactor",
                           corps=json.dumps({"username": "intrus", "password": MOT_DE_PASSE}))
    code_proprietaire, corps_proprietaire = _wget(identite_seule, "/api/firstfactor",
                                                  corps=json.dumps({"username": UTILISATEUR, "password": MOT_DE_PASSE}))
    afficher("fichier des utilisateurs (hors volume)", f"{etat}\nutilisateurs : {_utilisateurs(identite_seule)}\n"
                                                        f"écriture par l'uid 1000 : code {ecriture.returncode} ; "
                                                        f"création : code {creation.returncode}\n"
                                                        f"premier facteur « intrus » : {code_intrus} ; "
                                                        f"propriétaire : {code_proprietaire} {corps_proprietaire}")
    assert "0:1000 750 /run/acp-identite" in etat
    assert "0:1000 640 /run/acp-identite/utilisateurs.yml" in etat
    assert etat.strip().splitlines()[-1] == "utilisateurs.yml"
    assert _utilisateurs(identite_seule) == [UTILISATEUR]
    assert ecriture.returncode != 0 and creation.returncode != 0
    assert code_intrus == 401
    assert code_proprietaire == 200 and json.loads(corps_proprietaire) == {"status": "OK"}
    # Un second compte glissé en root dans le fichier ne survit pas à un redémarrage.
    docker("exec", "-i", identite_seule, "sh", "-c", "cat >> /run/acp-identite/utilisateurs.yml",
           entree=f"  'intrus':\n    disabled: false\n    displayname: \"Intrus\"\n"
                  f"    password: '{empreinte_argon2}'\n    email: 'intrus@acp.test'\n    groups: []\n")
    assert _utilisateurs(identite_seule) == [UTILISATEUR, "intrus"]
    docker("restart", identite_seule, delai=180)
    attendre_identite(identite_seule)
    assert _utilisateurs(identite_seule) == [UTILISATEUR]
    code_intrus, _ = _wget(identite_seule, "/api/firstfactor",
                           corps=json.dumps({"username": "intrus", "password": MOT_DE_PASSE}))
    assert code_intrus == 401


def test_sujet_autre_refuse_par_la_politique_oidc(pile, image_identite, image_tests, empreinte_argon2):
    """Défense en profondeur : Hermes n'a aucune liste blanche de sujets. Une variante de TEST
    contourne la garde pour poser un second compte « intrus » (même mot de passe) ; la politique
    « proprietaire » du client (deny par défaut) le refuse après son premier facteur, alors que le
    propriétaire est renvoyé vers son second facteur."""
    reseau = pile.reseau()
    volume = pile.volume()
    initial = pile.lancer_identite(image_identite, env_identite(empreinte_argon2), reseau=reseau, volume=volume,
                                   alias="identite-initiale")
    docker("rm", "-f", initial)
    utilisateurs = (f"users:\n  '{UTILISATEUR}':\n    displayname: \"Propriétaire\"\n    password: '{empreinte_argon2}'\n"
                    f"    email: 'proprietaire@acp.test'\n  'intrus':\n    displayname: \"Intrus\"\n"
                    f"    password: '{empreinte_argon2}'\n    email: 'intrus@acp.test'\n")
    variante = pile.nom("identite-deux-comptes")
    pile.conteneurs.append(variante)
    docker("run", "-d", "--name", variante, "--network", reseau, "--network-alias", "identite-interne",
           "-v", f"{volume}:/config", *options_env(env_identite(empreinte_argon2)),
           "-e", "ACP_TEST_UTILISATEURS=" + base64.b64encode(utilisateurs.encode()).decode(),
           "--entrypoint", "/bin/sh", image_identite, "-c",
           "mkdir -p /run/acp-identite && echo \"$ACP_TEST_UTILISATEURS\" | base64 -d > /run/acp-identite/utilisateurs.yml "
           "&& chmod 0644 /run/acp-identite/utilisateurs.yml && exec /app/entrypoint.sh")
    attendre_identite(variante)
    bord, _ = pile.lancer_bord(image_tests, reseau, routes={HOTE_IDENTITE: "identite-interne:9091"})
    resultats = {}
    for qui in ("intrus", UTILISATEUR):
        sortie = docker("exec", bord, "/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_identite.py",
                        "autoriser", "--utilisateur", qui, "--mot-de-passe", MOT_DE_PASSE).stdout
        resultats[qui] = json.loads(sortie)
    afficher("politique OIDC du client hermes-acp face à deux comptes", _texte(resultats))
    intrus, proprietaire = resultats["intrus"], resultats[UTILISATEUR]
    for r in (intrus, proprietaire):
        assert r["depart"]["statut"] == 303 and "flow=openid_connect" in r["depart"]["location"]
        assert r["premier_facteur"]["statut"] == 200
    assert "consent_id=" in (intrus["redirection"] or "")
    assert intrus["finale"]["statut"] in (302, 303)
    assert intrus["finale"]["location"].startswith(f"{URL_HERMES}/auth/callback?error=access_denied")
    assert "code=" not in intrus["finale"]["location"]
    assert proprietaire["premier_facteur"]["corps"] == {"status": "OK"} and proprietaire["redirection"] is None
    assert "the user 'intrus' is not authorized to use this client" in journal(variante)


# ============================================================ maintenance


@pytest.fixture(scope="module")
def volume_initialise(pile, image_identite, empreinte_argon2) -> str:
    """Volume d'un service identite qui a déjà démarré une fois (secrets, base)."""
    volume = pile.volume()
    premier = pile.lancer_identite(image_identite, env_identite(empreinte_argon2), volume=volume)
    docker("rm", "-f", premier)
    return volume


@pytest.mark.parametrize("arguments_en_trop", [False, True], ids=["sans_argument", "avec_arguments_herites"])
def test_maintenance_sleep_infinity_identite(pile, image_identite, empreinte_argon2, volume_initialise,
                                             arguments_en_trop):
    """Start Command de maintenance « /bin/sh -c "exec sleep infinity" » : elle remplace
    l'ENTRYPOINT (la garde ne tourne pas), le conteneur tient, docker exec donne un shell root, et
    acp-identite-admin relit l'environnement du PID 1 depuis une session SANS environnement."""
    nom = pile.nom("maintenance")
    pile.conteneurs.append(nom)
    env = dict(env_identite(empreinte_argon2), **ENV_RAILWAY)
    supplement = ["x", "y"] if arguments_en_trop else []
    docker("run", "-d", "--name", nom, "-v", f"{volume_initialise}:/config", *options_env(env),
           "--entrypoint", "/bin/sh", image_identite, "-c", "exec sleep infinity", *supplement)
    time.sleep(5)
    etat = docker("inspect", "-f", "{{.State.Running}}", nom).stdout.strip()
    pid1 = docker("exec", nom, "sh", "-c", "tr '\\0' ' ' < /proc/1/cmdline").stdout.strip()
    qui = docker("exec", nom, "id", "-u").stdout.strip()
    proprietaire = docker("exec", nom, "env", "-i", "/opt/acp-identite/acp-identite-admin", "user", "webauthn", "list",
                          UTILISATEUR, verifier=False)
    liste = docker("exec", nom, "env", "-i", "/opt/acp-identite/acp-identite-admin", "storage", "bans", "user", "list",
                   verifier=False)
    refus = {commande: docker("exec", nom, "env", "-i", "/opt/acp-identite/acp-identite-admin", *commande.split(),
                              verifier=False)
             for commande in ("migrate up", "encryption change-key", "cache mds3 status")}
    afficher(f"maintenance identite ({'avec' if arguments_en_trop else 'sans'} arguments) : {etat}, PID 1 « {pid1} », "
             f"uid {qui}",
             f"storage bans user list (code {liste.returncode}) :\n{liste.stderr}{liste.stdout}\n"
             f"user webauthn list {UTILISATEUR} (code {proprietaire.returncode}) : "
             f"{(proprietaire.stderr + proprietaire.stdout).splitlines()[1:2]}\n"
             + "\n".join(f"{c} (code {r.returncode}) : {r.stderr.strip()}" for c, r in refus.items()))
    assert etat == "true" and pid1 == "sleep infinity" and qui == "0"
    assert liste.returncode == 0, liste.stderr
    assert "[acp-identite-admin] environnement de référence : /proc/1/environ (PID 1 : sleep infinity)" in liste.stderr
    assert liste.stdout.strip() == "No results."
    # Authelia a ouvert la base avec la clé du volume et répond sur le compte lui-même (volume jamais
    # enrôlé : aucune passkey).
    assert f"Error: user '{UTILISATEUR}' has no WebAuthn credentials" in proprietaire.stderr + proprietaire.stdout
    for commande, r in refus.items():
        assert r.returncode == 1 and "[acp-identite-admin] REFUS : seules les sous-commandes « user … » et « bans … »" \
            in r.stderr, commande


def test_admin_refuse_hors_maintenance(identite_seule):
    """Hors maintenance, le PID 1 est Authelia (uid 1000) : le noyau refuse la lecture de son
    environnement à root sans CAP_SYS_PTRACE, et le script refuse au lieu de deviner."""
    r = docker("exec", identite_seule, "/opt/acp-identite/acp-identite-admin", "user", "webauthn", "list", UTILISATEUR,
               verifier=False)
    afficher("acp-identite-admin hors maintenance", f"code {r.returncode} : {r.stderr}")
    assert r.returncode == 1
    assert "[acp-identite-admin] REFUS : /proc/1/environ est illisible" in r.stderr


# ============================================================ 7. compatibilité Hermes ↔ Authelia


@pytest.fixture(scope="module")
def pile_complete(pile, image_identite, image_tests, empreinte_argon2) -> Dict[str, object]:
    return monter_pile(pile, image_identite, image_tests, empreinte_argon2)


def _curl(conteneur: str, url: str, *entetes: str) -> Tuple[int, Dict[str, List[str]], str]:
    """(code, en-têtes, corps) d'une requête HTTPS faite DEPUIS un conteneur du réseau, par le bord."""
    commande = ["exec", conteneur, "curl", "-s", "-i", "--max-time", "60"]
    for entete in entetes:
        commande += ["-H", entete]
    brut = docker(*commande, url).stdout
    tete, _, corps = brut.replace("\r\n", "\n").partition("\n\n")
    lignes = tete.split("\n")
    code = int(lignes[0].split()[1])
    en_tetes: Dict[str, List[str]] = {}
    for ligne in lignes[1:]:
        nom, _, valeur = ligne.partition(":")
        en_tetes.setdefault(nom.strip().lower(), []).append(valeur.strip())
    return code, en_tetes, corps


def _url_de_hermes(hermes: str) -> str:
    code, en_tetes, _ = _curl(hermes, f"{URL_HERMES}/auth/login?provider=self-hosted")
    assert code == 302, (code, en_tetes)
    return en_tetes["location"][0]


def test_decouverte_acceptee_par_hermes(pile_complete):
    hermes, bord, identite = pile_complete["hermes"], pile_complete["bord"], pile_complete["identite"]
    journaux_hermes = journal(hermes) + docker("exec", hermes, "sh", "-c", "cat /opt/data/logs/*.log 2>/dev/null",
                                                verifier=False).stdout
    enregistrement = [l for l in journaux_hermes.splitlines() if "dashboard-auth-self-hosted: registered provider" in l]
    code, _, corps = _curl(hermes, f"{URL_HERMES}/api/auth/providers")
    fournisseurs = json.loads(corps)
    code_d, _, corps_d = _curl(hermes, f"{EMETTEUR}/.well-known/openid-configuration")
    decouverte = json.loads(corps_d)
    autorisation = _url_de_hermes(hermes)
    parametres = urllib.parse.parse_qs(urllib.parse.urlsplit(autorisation).query)
    code_a, en_tetes_a, _ = _curl(hermes, autorisation)
    appels_hermes = [l for l in lignes_du_bord(bord) if l["hote"] == HOTE_IDENTITE and l["chemin"] ==
                     "/.well-known/openid-configuration"]
    afficher("découverte OIDC à travers le bord", _texte({
        "enregistrement": enregistrement, "fournisseurs": fournisseurs,
        "decouverte": {k: decouverte.get(k) for k in ("issuer", "authorization_endpoint", "token_endpoint",
                                                      "jwks_uri", "revocation_endpoint",
                                                      "code_challenge_methods_supported")},
        "autorisation": autorisation, "reponse_authelia": [code_a, en_tetes_a.get("location")],
        "journal_du_bord": appels_hermes}))
    assert enregistrement and ("issuer=https://identite-acp.test, client_id=hermes-acp, "
                               "scopes='openid profile email offline_access', confidential=False") in enregistrement[0]
    assert code == 200 and [p["name"] for p in fournisseurs["providers"]] == ["self-hosted"]
    assert code_d == 200 and decouverte["issuer"] == EMETTEUR
    for cle in ("authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint"):
        assert decouverte[cle].startswith(f"{EMETTEUR}/"), cle
    assert decouverte["code_challenge_methods_supported"] == ["S256"]
    assert "none" in decouverte["token_endpoint_auth_methods_supported"]
    assert "RS256" in decouverte["id_token_signing_alg_values_supported"]
    # Hermes a lu et ACCEPTÉ la découverte (origine et émetteur épinglés) : il a construit l'URL
    # d'autorisation à partir de l'authorization_endpoint découvert.
    assert autorisation.startswith(f"{EMETTEUR}/api/oidc/authorization?")
    assert parametres["client_id"] == [CLIENT] and parametres["redirect_uri"] == [f"{URL_HERMES}/auth/callback"]
    assert parametres["scope"] == [PORTEES] and parametres["code_challenge_method"] == ["S256"]
    assert parametres["response_type"] == ["code"] and len(parametres["code_challenge"][0]) == 43
    # Authelia accepte client, retour, portées et PKCE : renvoi vers son portail de connexion.
    assert code_a == 303 and en_tetes_a["location"][0].startswith(f"{EMETTEUR}/?flow=openid_connect&flow_id=")
    assert any(l["statut"] == 200 for l in appels_hermes)
    assert "level=error" not in journal(identite)


MODIFICATIONS_RETOUR = {
    "autre_hote": ("https%3A%2F%2Fhermes-acp.test%2Fauth%2Fcallback", "https%3A%2F%2Fintrus.test%2Fauth%2Fcallback"),
    "http": ("https%3A%2F%2Fhermes-acp.test", "http%3A%2F%2Fhermes-acp.test"),
    "remontee": ("%2Fauth%2Fcallback", "%2Fauth%2Fcallback%2F..%2F..%2Fintrus"),
    "requete_ajoutee": ("%2Fauth%2Fcallback", "%2Fauth%2Fcallback%3Fnext%3Dhttps%3A%2F%2Fintrus.test"),
    "barre_finale": ("%2Fauth%2Fcallback", "%2Fauth%2Fcallback%2F"),
    "sous_domaine": ("hermes-acp.test", "intrus.hermes-acp.test"),
}


def test_redirect_uri_alteree_refusee(pile_complete):
    hermes = pile_complete["hermes"]
    rapport = {}
    for cas, (avant, apres) in MODIFICATIONS_RETOUR.items():
        autorisation = _url_de_hermes(hermes)
        assert avant in autorisation, cas
        code, en_tetes, _ = _curl(hermes, autorisation.replace(avant, apres, 1))
        location = (en_tetes.get("location") or [""])[0]
        rapport[cas] = [code, location[:160]]
        assert code == 303, (cas, code)
        assert location.startswith(f"{EMETTEUR}/consent/completion?error=invalid_request"), (cas, location)
        assert "redirect_uri" in urllib.parse.unquote_plus(location), cas
    autorisation = _url_de_hermes(hermes)
    code, en_tetes, _ = _curl(hermes, autorisation.replace("client_id=hermes-acp", "client_id=autre-client", 1))
    rapport["client_inconnu"] = [code, en_tetes.get("location", [""])[0][:160]]
    afficher("redirect_uri et client altérés", _texte(rapport))
    assert code == 303 and en_tetes["location"][0].startswith(f"{EMETTEUR}/consent/completion?error=invalid_client")


def test_entetes_du_bord_mesures(pile_complete):
    """Ce que voient Authelia et Hermes derrière le bord. Consigné pour fixer, sur Railway, le
    comportement réel du bord (X-Forwarded-Host falsifié, trusted_proxies de Hermes)."""
    hermes, bord, identite = pile_complete["hermes"], pile_complete["bord"], pile_complete["identite"]
    # 1. Par le bord, des en-têtes falsifiés par le client sont retirés puis reposés : l'émetteur reste juste.
    code, _, corps = _curl(hermes, f"{EMETTEUR}/.well-known/openid-configuration", "X-Forwarded-Host: intrus.test",
                           "X-Forwarded-Proto: http", "X-Real-IP: 203.0.113.9", "X-Railway-Edge: faux")
    derniere = [l for l in lignes_du_bord(bord) if l["chemin"] == "/.well-known/openid-configuration"][-1]
    # 2. En DIRECT (pair du réseau privé, sans bord), Authelia croit X-Forwarded-Host et X-Forwarded-Proto.
    direct_intrus, _ = _wget(identite, "/.well-known/openid-configuration", hote="intrus.test")
    direct_juste, corps_direct = _wget(identite, "/.well-known/openid-configuration")
    # 3. Hermes (trusted_proxies vide) ne croit pas le bord : il voit http, d'où un cookie PKCE sans
    #    Secure et SameSite=Lax ; l'URL de retour vient de HERMES_DASHBOARD_PUBLIC_URL.
    code_h, en_tetes_h, _ = _curl(hermes, f"{URL_HERMES}/auth/login?provider=self-hosted")
    cookies = en_tetes_h.get("set-cookie", [])
    # 4. Hôte inconnu du bord : 404, comme « Application not found » sur Railway.
    code_inconnu, _, _ = _curl(hermes, f"https://{HOTE_HERMES}/api/status", f"Host: inconnu.test")
    afficher("en-têtes du bord mesurés", _texte({
        "par_le_bord_entetes_falsifies": {"code": code, "issuer": json.loads(corps).get("issuer"),
                                          "journal_du_bord": derniere},
        "direct_x_forwarded_host_intrus": direct_intrus,
        "direct_x_forwarded_host_juste": [direct_juste, json.loads(corps_direct).get("issuer")],
        "hermes_cookie_pkce": cookies, "hote_inconnu": code_inconnu}))
    assert code == 200 and json.loads(corps)["issuer"] == EMETTEUR
    assert derniere["entetes_client_retires"] == ["x-forwarded-host", "x-forwarded-proto", "x-railway-edge", "x-real-ip"]
    assert direct_intrus == 400
    assert direct_juste == 200 and json.loads(corps_direct)["issuer"] == EMETTEUR
    assert code_h == 302
    [pkce] = [c for c in cookies if c.startswith(("hermes_session_pkce=", "__Host-hermes_session_pkce="))]
    assert pkce.startswith("hermes_session_pkce=") and "Secure" not in pkce and "SameSite=lax" in pkce
    assert code_inconnu == 404


# ============================================================ 8. mémoire sous premiers facteurs simultanés


def _memoire(conteneur: str) -> Dict[str, int]:
    brut = docker("exec", conteneur, "sh", "-c",
                  "grep -E '^(VmHWM|VmRSS):' /proc/1/status; echo peak $(cat /sys/fs/cgroup/memory.peak 2>/dev/null)"
                  ).stdout
    valeurs: Dict[str, int] = {}
    for nom, nombre in re.findall(r"^(VmHWM|VmRSS):\s+(\d+) kB", brut, re.M):
        valeurs[nom] = int(nombre) * 1024
    pic = re.search(r"^peak (\d+)$", brut, re.M)
    valeurs["cgroup_peak"] = int(pic.group(1)) if pic else 0
    return valeurs


def _gio(octets: int) -> str:
    return f"{octets / GIO:.3f} Gio ({octets} octets)"


def test_memoire_premier_facteur_concurrent(pile, image_identite, image_tests, empreinte_argon2):
    """10 puis 20 POST /api/firstfactor SIMULTANÉS, identifiant du propriétaire et mauvais mot de
    passe, à travers le bord ; conteneur limité à 0,5 vCPU comme sur Railway, SANS limite mémoire
    (on mesure le vrai pic). Chaque rafale part d'un conteneur neuf (la régulation bannit ensuite
    le compte, ce qui court-circuiterait la rafale suivante). Relevés : VmHWM (RSS maximal
    d'Authelia, PID 1) et memory.peak (pic du cgroup, ce que compare le tueur OOM). Le plan
    demandait un échantillonnage par docker stats toutes les 200 ms : ces deux compteurs du noyau
    donnent le pic exact, sans échantillonnage. Témoin : sous 1 Go sans échange, la rafale de 20
    tue Authelia (OOM)."""
    reseau = pile.reseau()
    bord, _ = pile.lancer_bord(image_tests, reseau, routes={HOTE_IDENTITE: "identite-interne:9091"})
    mesures = {}
    for n in (10, 20):
        identite = pile.lancer_identite(image_identite, env_identite(empreinte_argon2), reseau=reseau,
                                        options=("--cpus", "0.5"))
        avant = _memoire(identite)
        sortie = docker("exec", bord, "/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_identite.py",
                        "rafale", "--n", str(n), "--utilisateur", UTILISATEUR, "--mot-de-passe", "mauvais-mot-de-passe",
                        delai=600).stdout
        rafale = json.loads(sortie)
        apres = _memoire(identite)
        vivant = docker("inspect", "-f", "{{.State.Running}} {{.State.OOMKilled}} {{.RestartCount}}", identite).stdout.strip()
        mesures[n] = {"avant": avant, "apres": apres, "etat": vivant,
                      "codes": sorted({r["statut"] for r in rafale["resultats"]}),
                      "duree_max_s": max(r["duree_s"] for r in rafale["resultats"])}
        docker("rm", "-f", identite)
    # Témoin : sous la limite de 1 Go envisagée au départ (sans échange), une rafale de 20 PEUT tuer
    # Authelia. Le pic dépend de l'entrelacement des vérifications sur 0,5 vCPU : sur la CI, le
    # témoin a survécu une fois (image.yml 36118860946, étape P3) après plusieurs morts constatées.
    # Jusqu'à trois essais, chacun sur un conteneur neuf ; une seule mort suffit à prouver que
    # 1 Go ne tient pas. Tous les essais sont rapportés.
    essais_temoin = []
    for _ in range(3):
        temoin = pile.lancer_identite(image_identite, env_identite(empreinte_argon2), reseau=reseau,
                                      options=("--cpus", "0.5", "--memory", "1g", "--memory-swap", "1g"))
        sortie = docker("exec", bord, "/opt/hermes/.venv/bin/python", "/opt/acp-tests/outils/client_identite.py",
                        "rafale", "--n", "20", "--utilisateur", UTILISATEUR, "--mot-de-passe", "mauvais-mot-de-passe",
                        delai=600).stdout
        codes_temoin = sorted({str(r["statut"]) for r in json.loads(sortie)["resultats"]})
        etat_temoin = docker("inspect", "-f", "{{.State.Running}} {{.State.OOMKilled}} {{.State.ExitCode}}",
                             temoin).stdout.strip()
        docker("rm", "-f", temoin)
        essais_temoin.append(f"« {etat_temoin} », réponses {codes_temoin}")
        if etat_temoin.startswith("false true"):
            break
    pic_20 = max(mesures[20]["apres"]["VmHWM"], mesures[20]["apres"]["cgroup_peak"])
    pic_10 = max(mesures[10]["apres"]["VmHWM"], mesures[10]["apres"]["cgroup_peak"])
    rapport = [f"rafale de {n} : RSS maximal (VmHWM) {_gio(m['apres']['VmHWM'])} ; pic du cgroup "
               f"{_gio(m['apres']['cgroup_peak'])} ; avant la rafale {_gio(m['avant']['VmHWM'])} ; codes {m['codes']} ; "
               f"réponse la plus lente {m['duree_max_s']} s ; état {m['etat']}" for n, m in mesures.items()]
    rapport.append("témoin, limite de 1 Gio sans échange, rafale de 20, état (en marche, tué par OOM, code) : "
                   + " ; ".join(f"essai {i} {e}" for i, e in enumerate(essais_temoin, 1)))
    rapport.append(f"limite RETENUE pour railway.ts (service identite) : {_gio(LIMITE_MEMOIRE_OCTETS)} ; "
                   f"pic à 20 rapporté à la limite : {pic_20 / LIMITE_MEMOIRE_OCTETS:.1%} (au plus 66,7 % exigés)")
    railway_ts = RACINE_DEPOT / ".railway" / "railway.ts"
    rapport.append(f".railway/railway.ts : {'présent' if railway_ts.exists() else 'absent de cette branche (étape suivante)'}")
    afficher("mémoire d'Authelia sous premiers facteurs simultanés (argon2id m=65536, t=3, p=4)", "\n".join(rapport))
    for n, m in mesures.items():
        assert m["codes"] == [401], (n, m)
        assert m["etat"] == "true false 0", (n, m)
    # Chaque rafale a bien consommé de la mémoire. L'ORDRE des deux pics n'est pas garanti : il dépend
    # de l'entrelacement des vérifications sur 0,5 vCPU (CI image.yml 36134351025 : 0,725 Gio à 10,
    # 0,538 Gio à 20, alors que le poste mesure 0,726 et 1,346 Gio). Le critère de la limite vaut
    # donc pour le plus haut des deux pics.
    for m in mesures.values():
        assert m["apres"]["VmHWM"] > m["avant"]["VmHWM"], m
    assert etat_temoin.startswith("false true"), essais_temoin
    assert max(pic_10, pic_20) <= LIMITE_MEMOIRE_OCTETS * 2 // 3
    assert LIMITE_MEMOIRE_OCTETS >= GIO
