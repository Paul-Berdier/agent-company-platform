"""Tests de l'image CONSTRUITE de l'exécutant (cahier P6 § 14.1), pilotés depuis l'hôte par docker (voir conftest.py).

Ce qui est prouvé ici, sur l'image réellement construite (cible finale, binaires réels, AUCUN compte) :
- linux/amd64 ; Codex 0.156.1 et Claude Code 2.1.283, empreintes rejouées contre binaires.toml ;
- aucun secret dans l'historique ni la configuration de l'image ; contexte minimal (ni .git, ni docs, ni tests) ;
- tout ce que lit ou exécute le superviseur root est non inscriptible par les UID des agents (transposition de D67,
  contrôle du superviseur rejoué dans l'image) ; comptes 10001-10003, groupe 10100, shell nologin ;
- entrée : refus hors tini, sans volume, sur un fichier d'identifiant étranger ; modes du volume ; politique au gabarit
  refusée (échec fermé) ;
- options imposées admises par les VRAIES CLI (sans compte, réseau coupé) et nom inconnu refusé ; fonctions Codex
  actives = liste blanche versionnée ; mises à jour de Claude coupées ;
- bubblewrap de Debian seul, avec --as-pid-1 et --perms ; safe.directory « chemin/* » ;
- sonde R0 telle que lancée sur Railway (Start Command) sous le seccomp Docker par défaut, et témoin du régime A
  (seccomp et AppArmor levés). Ni l'un ni l'autre n'est une preuve pour Railway : seule R0 sur Railway tranche.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from outils_image import EXECUTANT, afficher, docker, lancer  # noqa: E402

BINAIRES = tomllib.loads((EXECUTANT / "binaires.toml").read_text(encoding="utf-8"))
SONDE_R0 = ("/usr/local/bin/acp-poste", "sonde-plateforme", "--json")
NOMS_SENSIBLES = re.compile(r"JETON|TOKEN|SECRET|PASSWORD|_KEY$|^KEY|CLE_|OAUTH", re.IGNORECASE)
# Variable héritée de l'image officielle python:3.12-slim : identifiant PUBLIC de la clé de publication de CPython.
HERITEES_PUBLIQUES = {"GPG_KEY"}
# Fonctions de Codex 0.156.1 ACTIVES sous les surcharges du superviseur (relevé « codex features list » du
# 01/10/2026 dans l'image) : toute fonction active hors de cette liste fait échouer le test (une montée de version ne
# peut pas en ajouter une en silence). Les fonctions coupées par --disable (cahier § 6.3) n'y figurent pas.
FONCTIONS_CODEX_ACTIVES = {
    "auth_elicitation", "browser_use_external", "browser_use_full_cdp_access", "code_mode_host", "collaboration_modes",
    "compaction_image_budget", "content_item_kinds", "enable_request_compression", "fast_mode", "guardian_approval",
    "guardian_reuse_parent_compaction", "in_app_browser", "in_app_chat", "in_app_dictation", "in_app_local_automation",
    "in_app_updates", "item_ids", "mentions_v2", "plugin_sharing", "realtime_conversation", "remote_plugin",
    "resize_all_images", "shell_snapshot", "shell_tool", "skill_search", "sleep_tool", "sqlite", "steer",
    "system_proxy_fallback", "terminal_resize_reflow", "tool_call_mcp_elicitation", "tool_search_always_defer_mcp_tools",
    "tool_suggest", "tui_app_server", "unbounded_connection_retries", "unified_exec", "unified_exec_tty",
    "unified_exec_zsh_fork", "view_image",
}
PY = "/usr/local/bin/python3.12"


def _python(image: str, code: str, *options: str) -> str:
    resultat = lancer(image, "-I", "-c", "import sys; sys.path.insert(0, '/opt/acp/lib')\n" + code,
                      point_d_entree=PY, options=options)
    assert resultat.returncode == 0, resultat.stderr[-3000:]
    return resultat.stdout


# ============================================================ binaires et contenu


def test_image_amd64(image):
    inspecte = json.loads(docker("image", "inspect", image, verifier=True).stdout)[0]
    assert inspecte["Architecture"] == "amd64" and inspecte["Os"] == "linux"
    assert inspecte["Config"]["Entrypoint"] == ["/usr/bin/tini", "--", "/opt/acp/bin/acp-entree-executant"]
    assert not inspecte["Config"].get("ExposedPorts") and not inspecte["Config"].get("Healthcheck")


def test_versions_epinglees(image):
    codex = lancer(image, "--version", point_d_entree="/opt/acp/outils/codex/codex")
    claude = lancer(image, "--version", point_d_entree="/opt/acp/outils/claude/claude")
    assert codex.stdout.strip() == f"codex-cli {BINAIRES['codex']['version']}"
    assert claude.stdout.strip() == f"{BINAIRES['claude']['version']} (Claude Code)"


def test_empreintes_binaires(image):
    controle = lancer(image, "-I", "/opt/acp/bin/verifier-binaires", "--controler", "/opt/acp/outils",
                      point_d_entree=PY)
    assert controle.returncode == 0, controle.stderr
    afficher("verifier-binaires --controler (dans l'image)", controle.stdout)
    sortie = lancer(image, "-c", "sha256sum /opt/acp/outils/claude/claude; cat /opt/acp/outils/PROVENANCE.json")
    assert sortie.stdout.split()[0] == BINAIRES["claude"]["sha256"]
    provenance = json.loads(sortie.stdout.split("\n", 1)[1])
    assert provenance["codex"]["sha256_archive"] == BINAIRES["codex"]["sha256"]
    assert provenance["claude"]["manifeste_signe_par"] == BINAIRES["claude"]["empreinte_cle"]
    assert provenance["codex"]["cosign"] == "identite_non_etablie"


def test_aucun_secret_dans_l_image(image):
    from acp_poste_contrat.machine import secret_trouve

    historique = docker("history", "--no-trunc", "--format", "{{.CreatedBy}}", image, verifier=True).stdout
    config = json.loads(docker("image", "inspect", image, verifier=True).stdout)[0]["Config"]
    assert secret_trouve(historique) is None and secret_trouve(json.dumps(config)) is None
    for variable in config.get("Env") or []:
        nom = variable.split("=", 1)[0]
        assert nom in HERITEES_PUBLIQUES or not NOMS_SENSIBLES.search(nom), f"variable sensible dans l'image : {nom}"
    assert not re.search(r"\bARG\b[^\n]*(JETON|TOKEN|SECRET|PASSWORD)", historique, re.IGNORECASE)
    # Fichiers texte d'ACP dans l'image : aucun motif de secret (clé publique et empreintes ne sont pas des secrets).
    textes = lancer(image, "-c", "find /opt/acp /etc/acp /etc/gitconfig -type f \\( -name '*.toml' -o -name '*.json' "
                    "-o -name '*.py' -o -name gitconfig -o -path '*/bin/*' \\) ! -path '/opt/acp/outils/*/*' "
                    "! -path '/opt/acp/lib/pydantic*' -exec cat {} +")
    assert textes.returncode == 0 and len(textes.stdout) > 10_000
    assert secret_trouve(textes.stdout) is None


def test_contexte_minimal(image):
    trouve = lancer(image, "-c", "find / -xdev \\( -name .git -o -name .claude -o -name '.env*' -o -path '*/docs' "
                    "-o -path '/opt/acp/*/tests' -o -name conftest.py -o -name 'faux-*' -o -name 'scenarios-factices*' "
                    "\\) -print 2>/dev/null | grep -v '^/proc' | grep -v '^/usr/share/doc' || true")
    assert trouve.stdout.strip() == "", trouve.stdout


# ============================================================ comptes, propriétaires et modes


def test_utilisateurs(image):
    sortie = lancer(image, "-c", "getent passwd acp-codex acp-claude acp-verif; getent group acp-travail").stdout
    assert "acp-codex:x:10001:10001::/home/acp-codex:/usr/sbin/nologin" in sortie
    assert "acp-claude:x:10002:10002::/home/acp-claude:/usr/sbin/nologin" in sortie
    assert "acp-verif:x:10003:10003::/home/acp-verif:/usr/sbin/nologin" in sortie
    assert re.search(r"^acp-travail:x:10100:acp-codex,acp-claude,acp-verif$", sortie, re.MULTILINE)


def test_proprietaires_et_modes(image):
    """Rien de ce que lit ou exécute le superviseur n'est inscriptible par 10001-10003 : vérifié par stat ET par un
    essai d'écriture réel sous chaque UID ; puis le contrôle D67 du superviseur rejoué dans l'image."""
    rapport = _python(image, """
import os, stat, json, sysconfig
racines = ['/opt/acp', '/etc/acp', '/etc/gitconfig', '/usr/local/bin/python3.12', '/usr/local/bin/acp-poste',
           sysconfig.get_paths()['stdlib'], sysconfig.get_paths()['purelib']]
ecarts = []
for racine in racines:
    for base, dossiers, fichiers in os.walk(racine) if os.path.isdir(racine) else [(os.path.dirname(racine), [], [os.path.basename(racine)])]:
        for nom in [base] + [os.path.join(base, f) for f in fichiers]:
            e = os.lstat(nom)
            if stat.S_ISLNK(e.st_mode):
                continue
            if e.st_mode & 0o022 or (e.st_uid != 0):
                ecarts.append(nom)
modes = {f: oct(os.stat('/etc/acp/' + f).st_mode & 0o777) for f in os.listdir('/etc/acp')}
from acp_poste.politique import _verifier_interpreteur_linux, cibles_de_l_interpreteur_linux
_verifier_interpreteur_linux(cibles_de_l_interpreteur_linux())
print(json.dumps({'ecarts': ecarts[:20], 'modes': modes}))
""")
    resultat = json.loads(rapport.strip().splitlines()[-1])
    assert resultat["ecarts"] == []
    assert set(resultat["modes"].values()) == {"0o444"} and set(resultat["modes"]) == {"executant.toml",
                                                                                         "claude-settings.json"}
    for uid in (10001, 10002, 10003):
        essai = lancer(image, f"--reuid={uid}", f"--regid={uid}", "--groups=10100", "--", "sh", "-c",
                       "for c in /opt/acp/outils /opt/acp/lib /opt/acp/lib/acp_poste /opt/acp/bin /etc/acp "
                       "/usr/local/lib/python3.12 /usr/local/lib/python3.12/site-packages; do "
                       "touch $c/essai-agent 2>/dev/null && echo ECRIT:$c; done; "
                       "echo x >> /etc/acp/executant.toml 2>/dev/null && echo ECRIT:politique; "
                       "echo x >> /usr/local/bin/python3.12 2>/dev/null && echo ECRIT:python; true",
                       point_d_entree="/usr/bin/setpriv")
        assert essai.returncode == 0 and "ECRIT" not in essai.stdout, (uid, essai.stdout, essai.stderr)


# ============================================================ entrée et volume


def test_entree_refuse_hors_tini(image):
    resultat = lancer(image, point_d_entree="/opt/acp/bin/acp-entree-executant")
    assert resultat.returncode == 2 and "tini n'est pas le PID 1" in resultat.stderr


def test_entree_refuse_sans_volume(image):
    resultat = docker("run", "--rm", image)
    assert resultat.returncode == 2
    assert "Volume absent : l'exécutant refuse de démarrer sans /donnees." in resultat.stderr


def test_politique_gabarit_refusee_et_modes_du_volume(image, ressources):
    """Image de production telle quelle : le volume est préparé, puis le superviseur REFUSE de démarrer tant que
    l'origine de Hermes vaut le gabarit (règle P2, échec fermé ; code 2, relancé ON_FAILURE par Railway)."""
    volume = ressources.volume()
    resultat = docker("run", "--rm", "-v", f"{volume}:/donnees", "-e", "RAILWAY_GIT_COMMIT_SHA=" + "a" * 40, image)
    assert resultat.returncode == 2, resultat.stderr
    assert f"[acp] commit déployé : {'a' * 40}" in resultat.stdout
    assert "origine vaut encore le gabarit" in resultat.stderr and "refus de démarrer" in resultat.stderr
    modes = lancer(image, "-c", "stat -c '%n %U:%G %a' /donnees/acp /donnees/acp/secrets /donnees/acp/etat "
                   "/donnees/codex /donnees/claude /donnees/depots /donnees/espaces",
                   options=("-v", f"{volume}:/donnees")).stdout.splitlines()
    assert modes == ["/donnees/acp root:root 700", "/donnees/acp/secrets root:root 700",
                     "/donnees/acp/etat root:root 700", "/donnees/codex acp-codex:acp-codex 700",
                     "/donnees/claude acp-claude:acp-claude 700", "/donnees/depots root:root 755",
                     "/donnees/espaces root:acp-travail 751"]
    afficher("volume préparé par l'entrée", "\n".join(modes) + "\n" + resultat.stderr.strip())


def test_entree_refuse_un_identifiant_etranger(image, ressources):
    volume = ressources.volume()
    lancer(image, "-c", "mkdir -p /donnees/codex && touch /donnees/codex/auth.json && chown 0:0 /donnees/codex/auth.json",
           options=("-v", f"{volume}:/donnees"))
    resultat = docker("run", "--rm", "-v", f"{volume}:/donnees", image)
    assert resultat.returncode == 2
    assert "Fichier d'un autre propriétaire ou lien symbolique dans /donnees/codex" in resultat.stderr
    lancer(image, "-c", "rm /donnees/codex/auth.json && ln -s /donnees/acp/secrets/jeton-machine /donnees/claude/x",
           options=("-v", f"{volume}:/donnees"))
    resultat = docker("run", "--rm", "-v", f"{volume}:/donnees", image)
    assert resultat.returncode == 2 and "dans /donnees/claude" in resultat.stderr


def _attendre_journal(nom: str, marque: str, fois: int, delai: float = 90) -> str:
    import time

    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        journaux = docker("logs", nom)
        texte = journaux.stdout + journaux.stderr
        etat = docker("inspect", "-f", "{{.State.Running}}", nom).stdout.strip()
        if texte.count(marque) >= fois or etat == "false":
            return texte
        time.sleep(1)
    raise AssertionError(f"« {marque} » jamais vu {fois} fois dans les journaux de {nom}")


def test_commandes_root_du_proprietaire_puis_redemarrage_accepte(image, ressources):
    """Relecture de P6 (critique) : ``diagnostic``, ``quotas``, ``releve`` et ``preuve model-list``, lancés en ROOT comme
    dans « railway ssh » (§ 13.5 et 13.9 de railway.md), lançaient Codex et Claude en root : fichiers et liens de root
    sous /donnees/codex, puis REFUS de démarrer au redémarrage suivant (code 2, dix relances, « Crashed »). Ils passent
    désormais par le lanceur du service (UID de l'outil). Codex laisse en outre, même sous son UID, des liens sous
    $CODEX_HOME/tmp/arg0 (alias de son propre binaire) : l'entrée les retire avant son contrôle. Le redémarrage est
    accepté. Vrais binaires, aucun compte, réseau coupé."""
    image_test = ressources.image_politique_de_test(image)
    volume = ressources.volume()
    nom = ressources.nom()
    ressources.conteneurs.append(nom)
    docker("run", "-d", "--name", nom, "--network", "none", "-v", f"{volume}:/donnees", image_test, verifier=True)
    _attendre_journal(nom, "[acp] volume prêt", 1)
    codes = {}
    for commande in (("diagnostic",), ("quotas",), ("releve",), ("preuve", "model-list")):
        resultat = docker("exec", nom, "acp-poste", *commande, delai=240)
        codes[" ".join(commande)] = resultat.returncode
        assert "Traceback" not in resultat.stderr, resultat.stderr[-2000:]
    # Dernière commande : « codex --version » sous l'UID de l'outil, qui sort sans retirer ses alias.
    diagnostic = json.loads(docker("exec", nom, "acp-poste", "diagnostic", delai=120).stdout)
    etrangers = docker("exec", nom, "sh", "-c", "find /donnees/codex ! -uid 10001 -printf '%u %p\\n'; "
                       "find /donnees/claude ! -uid 10002 -printf '%u %p\\n'").stdout
    alias = docker("exec", nom, "sh", "-c", "find /donnees/codex/tmp/arg0 -type l -uid 10001 | wc -l").stdout
    afficher("commandes du propriétaire en root", json.dumps({"codes": codes, "etrangers": etrangers,
                                                             "liens_de_codex": alias.strip(),
                                                             "versions": [diagnostic["codex"]["version"],
                                                                          diagnostic["claude"]["version"]]},
                                                            ensure_ascii=False, indent=1))
    assert codes["diagnostic"] == 0 and codes["quotas"] == 0 and codes["releve"] == 0
    assert etrangers == "", etrangers
    # Versions lues sous l'UID de l'outil (le lanceur du service), pas « absent » ni une lecture en root.
    assert diagnostic["codex"]["version"] == "0.156.1" and diagnostic["claude"]["version"] == "2.1.283"
    # Codex a bien laissé ses alias (sans eux, ce test ne prouverait rien du nettoyage par l'entrée).
    assert int(alias.strip()) > 0
    docker("restart", "-t", "30", nom, delai=120, verifier=True)
    journaux = _attendre_journal(nom, "[acp] volume prêt", 2)
    etat = docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", nom).stdout.split()
    assert etat == ["true", "0"], journaux[-2000:]
    assert "REFUS" not in journaux, journaux[-2000:]
    restants = docker("exec", nom, "sh", "-c", "find /donnees/codex -type l | wc -l").stdout.strip()
    assert restants == "0"


def test_entree_refuse_un_lien_a_la_place_des_alias_de_codex(image, ressources):
    volume = ressources.volume()
    lancer(image, "-c", "mkdir -p /donnees/codex/tmp && ln -s / /donnees/codex/tmp/arg0 && chown -R -h 10001:10001 "
           "/donnees/codex", options=("-v", f"{volume}:/donnees"))
    resultat = docker("run", "--rm", "-v", f"{volume}:/donnees", image)
    assert resultat.returncode == 2
    assert "/donnees/codex/tmp/arg0 est un lien symbolique : refus de démarrer." in resultat.stderr
    # Rien n'a été suivi ni retiré : le lien est encore là, tel quel (diagnostic du propriétaire).
    lien = lancer(image, "-c", "readlink /donnees/codex/tmp/arg0", options=("-v", f"{volume}:/donnees"))
    assert lien.stdout.strip() == "/"


# ============================================================ CLI réelles, sans compte


def test_codex_fonctions_coupees(image):
    from acp_poste.commandes_agents import FONCTIONS_CODEX_COUPEES

    surcharges = ["-c", 'cli_auth_credentials_store="file"', "-c", 'service_tier="default"', "-c",
                  'web_search="disabled"', "-c", "sandbox_workspace_write.network_access=false"]
    for fonction in FONCTIONS_CODEX_COUPEES:
        surcharges += ["--disable", fonction]
    resultat = lancer(image, "-c", "mkdir -p /tmp/h && CODEX_HOME=/tmp/h HOME=/tmp/h /opt/acp/outils/codex/codex "
                      + " ".join(f"'{a}'" for a in surcharges) + " features list", options=("--network", "none"))
    assert resultat.returncode == 0, resultat.stderr
    etats = {l.split()[0]: l.split()[-1] for l in resultat.stdout.splitlines() if len(l.split()) >= 3}
    actives = {nom for nom, etat in etats.items() if etat == "true"}
    assert all(etats[f] == "false" for f in FONCTIONS_CODEX_COUPEES)
    assert actives == FONCTIONS_CODEX_ACTIVES, {"nouvelles": sorted(actives - FONCTIONS_CODEX_ACTIVES),
                                                 "disparues": sorted(FONCTIONS_CODEX_ACTIVES - actives)}
    inconnue = lancer(image, "-c", "mkdir -p /tmp/h && echo x | CODEX_HOME=/tmp/h /opt/acp/outils/codex/codex exec "
                      "--disable fonction_inconnue -", options=("--network", "none"))
    assert inconnue.returncode != 0 and "Unknown feature flag: fonction_inconnue" in inconnue.stderr + inconnue.stdout


def test_codex_options_imposees_admises(image):
    """La commande EXACTE du superviseur (acp_poste.commandes_agents.commande_codex) est acceptée par Codex 0.156.1 :
    il ouvre son fil (« thread.started ») puis échoue faute de réseau et de compte ; une option inconnue est refusée."""
    sortie = _python(image, """
import json, subprocess, os
from pathlib import Path
from acp_poste.commandes_agents import commande_codex, schema_json
os.makedirs('/tmp/w', exist_ok=True); os.makedirs('/tmp/h', exist_ok=True)
subprocess.run(['git', 'init', '-q', '/tmp/w'], check=True)
Path('/tmp/schema.json').write_text(schema_json())
c = commande_codex(prefixe=[], executable='/opt/acp/outils/codex/codex', worktree=Path('/tmp/w'), modele='gpt-5.5',
                   effort='low', role='implementation', schema=Path('/tmp/schema.json'), reponse=Path('/tmp/r.json'),
                   codex_home=Path('/tmp/h'), home='/tmp/h', tmpdir=Path('/tmp'))
try:
    r = subprocess.run(c.argv, input=b'consigne', capture_output=True, env=c.env, timeout=12)
    sortie, erreur = r.stdout, r.stderr
except subprocess.TimeoutExpired as exc:
    sortie, erreur = exc.stdout or b'', exc.stderr or b''
print(json.dumps({'sortie': sortie.decode()[:2000], 'erreur': erreur.decode()[-2000:]}))
""", "--network", "none")
    resultat = json.loads(sortie.strip().splitlines()[-1])
    assert '"type":"thread.started"' in resultat["sortie"], resultat
    assert "unexpected argument" not in resultat["erreur"] and "Unknown feature" not in resultat["erreur"]


def test_claude_options_imposees_admises(image):
    """La commande EXACTE du superviseur (commande_claude) est acceptée par Claude Code 2.1.283, ``--add-dir`` avec
    ``--restricted`` compris (supposé par le cahier, § 6.3) : « system/init » annonce les seuls outils demandés et
    aucun serveur MCP ; sans jeton ni réseau, rien d'autre ne se passe. Une option inconnue est refusée."""
    sortie = _python(image, """
import json, subprocess, os
from pathlib import Path
from acp_poste.commandes_agents import commande_claude
for d in ('/tmp/c', '/tmp/l', '/tmp/w'):
    os.makedirs(d, exist_ok=True)
resultats = {}
for role in ('implementation', 'relecture'):
    c = commande_claude(prefixe=[], executable='/opt/acp/outils/claude/claude', modele='opus', effort='low', role=role,
                        lecture=Path('/tmp/l'), config_dir=Path('/tmp/c'), jeton='', home='/tmp/c', tmpdir=Path('/tmp'))
    env = dict(c.env); env.pop('CLAUDE_CODE_OAUTH_TOKEN')
    try:
        r = subprocess.run(c.argv, input=b'consigne', capture_output=True, env=env, cwd='/tmp/w', timeout=60)
        sortie = r.stdout.decode()
    except subprocess.TimeoutExpired as exc:
        sortie = (exc.stdout or b'').decode()
    init = next((json.loads(l) for l in sortie.splitlines() if '"subtype":"init"' in l), None)
    resultats[role] = {'outils': init and init['tools'], 'mcp': init and init['mcp_servers'],
                       'version': init and init['claude_code_version'], 'modele': init and init['model']}
inconnue = subprocess.run(['/opt/acp/outils/claude/claude', '-p', '--restricted', '--option-inconnue'],
                          input=b'x', capture_output=True, env={'HOME': '/tmp/c', 'PATH': '/usr/bin:/bin'}, timeout=60)
resultats['inconnue'] = inconnue.stderr.decode()[:300]
print(json.dumps(resultats))
""", "--network", "none")
    resultat = json.loads(sortie.strip().splitlines()[-1])
    afficher("system/init de Claude Code sans compte", json.dumps(resultat, ensure_ascii=False, indent=1))
    # --json-schema ajoute l'outil « StructuredOutput » (sortie structurée de la carte) ; aucun autre outil, ni Bash.
    assert sorted(resultat["implementation"]["outils"]) == ["Edit", "Glob", "Grep", "Read", "StructuredOutput", "Write"]
    assert sorted(resultat["relecture"]["outils"]) == ["Glob", "Grep", "Read", "StructuredOutput"]
    assert resultat["implementation"]["mcp"] == [] and resultat["implementation"]["version"] == "2.1.283"
    assert "unknown option '--option-inconnue'" in resultat["inconnue"]


def test_mises_a_jour_coupees(image):
    resultat = lancer(image, "-c", "mkdir -p /tmp/c && HOME=/tmp/c CLAUDE_CONFIG_DIR=/tmp/c "
                      "/opt/acp/outils/claude/claude update; echo code=$?", options=("--network", "none"))
    assert "Updates are disabled by your administrator" in resultat.stdout + resultat.stderr
    assert "DISABLE_UPDATES=1" in lancer(image, "-c", "env").stdout


def test_bwrap_systeme_retenu(image):
    resultat = lancer(image, "-c", "command -v bwrap; bwrap --help; find / -xdev -name 'bwrap*' -type f "
                      "! -path '/usr/share/*' 2>/dev/null")
    lignes = resultat.stdout
    assert lignes.splitlines()[0] == "/usr/bin/bwrap"
    assert "--as-pid-1" in lignes and "--perms" in lignes
    assert [l for l in lignes.splitlines() if l.startswith("/") and "bwrap" in l] == ["/usr/bin/bwrap", "/usr/bin/bwrap"]


def test_git_proprietaires_mixtes(image):
    """safe.directory en forme « chemin/* » (git 2.47.3) : un agent lit un worktree de root sous /donnees/espaces,
    pas un dépôt de root ailleurs ; crochets coupés par /etc/gitconfig."""
    script = (
        "set -e; mkdir -p /donnees/espaces/jetable /tmp/ailleurs; "
        "git init -q /donnees/espaces/jetable/t_1 && git init -q /tmp/ailleurs/depot; "
        "chown root:acp-travail /donnees/espaces /donnees/espaces/jetable/t_1; chmod 751 /donnees/espaces; "
        "chmod 755 /donnees/espaces/jetable; chmod 2770 /donnees/espaces/jetable/t_1; "
        "chmod -R g+rwX /donnees/espaces/jetable/t_1; "
        "S='setpriv --reuid=10003 --regid=10003 --groups=10100 --'; "
        "$S git -C /donnees/espaces/jetable/t_1 status --short >/dev/null && echo ESPACE_OK; "
        "$S git -C /tmp/ailleurs/depot status 2>&1 | grep -q 'dubious ownership' && echo AILLEURS_REFUSE; "
        "git config --system core.hooksPath")
    resultat = lancer(image, "-c", script)
    assert resultat.stdout.split() == ["ESPACE_OK", "AILLEURS_REFUSE", "/dev/null"], resultat.stderr


# ============================================================ sonde de plateforme (R0)


def _sonde(image: str, *options: str) -> dict:
    resultat = docker("run", "--rm", *options, "--entrypoint", SONDE_R0[0], image, *SONDE_R0[1:], delai=300)
    assert resultat.returncode == 0, resultat.stderr[-2000:]
    releve = json.loads(resultat.stdout)
    from acp_poste_contrat.machine import secret_trouve

    assert releve["protocole"] == "acp-sonde-plateforme/1" and secret_trouve(releve) is None
    return releve


def test_sonde_regime_docker_defaut(image):
    """Répétition locale de R0 : la Start Command de Railway (« /usr/local/bin/acp-poste sonde-plateforme --json »),
    sans volume ni identifiant, sous le seccomp par défaut de Docker. Régime B attendu (bwrap refusé), UID séparés."""
    releve = _sonde(image)
    afficher("sonde R0, seccomp Docker par défaut", json.dumps(releve["verdict"], ensure_ascii=False, indent=1))
    v = releve["verdict"]
    assert v["regime"] == "B" and v["bwrap"] == "refuse" and v["uid_separes"] is True
    assert v["raison"].startswith("Régime B : bubblewrap refusé par la plateforme")
    assert releve["plateforme"]["libre_donnees_mio"] == "sans objet"
    codes = {r["point"]: r["code"] for r in releve["releves"]}
    assert codes["7.id"] == 0 and codes["9.codex_version"] == 0 and codes["9.claude_version"] == 0


# Témoin du régime A : seccomp et AppArmor levés, et chemins système de /proc démasqués (sans cela, le lanceur
# ubuntu-24.04 de GitHub refuse le /proc neuf de bubblewrap, et Codex ne lance plus rien : relevé en CI le 01/10/2026).
TEMOIN_A = ("--security-opt", "seccomp=unconfined", "--security-opt", "apparmor=unconfined", "--security-opt",
            "systempaths=unconfined")


def test_sonde_regime_a_temoin(image):
    """Même sonde, protections du conteneur levées (TEMOIN_A) : chemin A exercé avec le VRAI « codex sandbox -P » et le
    profil du superviseur (forme supposée par le cahier, § 4.1 point 6). Sur un lanceur Ubuntu 24.04, la CI passe
    d'abord kernel.apparmor_restrict_unprivileged_userns à 0 et le dit. CE N'EST PAS UNE PREUVE POUR RAILWAY."""
    releve = _sonde(image, *TEMOIN_A)
    restriction = releve["plateforme"]["sysctl"].get("apparmor_restrict_unprivileged_userns")
    afficher("sonde, témoin du régime A", json.dumps({"verdict": releve["verdict"], "apparmor_restrict": restriction,
                                                      "releves": [(r["point"], r["code"], r["sortie"])
                                                                  for r in releve["releves"]]},
                                                     ensure_ascii=False, indent=1))
    if restriction == "1":
        pytest.fail("kernel.apparmor_restrict_unprivileged_userns vaut 1 sur cet hôte : le témoin du régime A n'est pas "
                    "exercé (la CI le passe à 0 avant ce test, voir executant.yml).")
    v = releve["verdict"]
    assert (v["regime"], v["bwrap"], v["reseau_coupe"], v["uid_separes"]) == ("A", "fonctionne", True, True), v
    codes = {r["point"]: r["code"] for r in releve["releves"]}
    assert codes["6a.true"] == 0 and all(codes[p] not in (0, None) for p in ("6b.ecriture_hors", "6c.reseau",
                                                                               "6d.auth"))


def test_sonde_sans_volume_ni_politique_ni_reseau(image):
    """La sonde n'exige ni volume, ni politique valide, ni jeton, ni réseau : elle tourne sur l'image telle quelle
    (politique au gabarit), ce qui permet de la lancer dans le projet jetable « acp-sonde »."""
    releve = _sonde(image, "--network", "none")
    assert releve["verdict"]["regime"] == "B" and releve["verdict"]["uid_separes"] is True
