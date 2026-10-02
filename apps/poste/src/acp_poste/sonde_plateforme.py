"""Sonde de plateforme de l'exécutant Linux (cahier P6 § 4.1, livrable 0 ; sonde R0, décision D88).

Elle tranche ce que personne n'a mesuré sur Railway : les espaces de noms utilisateur, donc bubblewrap, dont dépendent
les bacs à sable de Codex et de Claude, et la séparation des identifiants par UID. **Aucun identifiant** : elle
n'appelle ni OpenAI, ni Anthropic, ni Hermes, ne lit aucun secret et ne charge pas la politique (lancée seule par
``acp-poste sonde-plateforme --json`` dans le projet jetable ``acp-sonde``, sans volume ni origine de Hermes).

Chaque relevé est une commande (ou une lecture de ``/proc``), son code de sortie et au plus 200 caractères de sortie
filtrée (masquée : ni adresse, ni chemin de profil). Points du cahier :

1. plateforme : architecture, noyau, distribution, processeurs, ``memory.max`` et ``cpu.max`` du cgroup, ``/dev/shm``,
   espace libre de ``/`` et de ``/donnees`` (« sans objet » sans volume), ``codex doctor`` (sans identifiant) ;
2. ``/proc/self/status`` : ``Seccomp``, ``Seccomp_filters``, ``NoNewPrivs``, ``CapEff``, ``CapBnd`` ;
3. ``max_user_namespaces``, ``unprivileged_userns_clone``, ``apparmor_restrict_unprivileged_userns`` ;
4. ``unshare -Ur true`` en root puis sous l'UID 10003 ;
5. la sonde exacte de Codex, ``bwrap --unshare-user --unshare-net --ro-bind / / /bin/true``, sous l'UID 10001, puis
   la même avec ``--unshare-pid --proc /proc`` ;
6. ``codex sandbox -P <profil> -C <dossier> -- <argv>`` sous l'UID 10001 : (a) ``/bin/true`` → 0, (b) écriture hors
   du dossier refusée, (c) résolution DNS refusée (réseau coupé), (d) lecture d'un faux ``auth.json`` interdite par
   le profil refusée ;
7. ``setpriv`` vers 10003 : ``id -u`` = 10003, puis ``/proc/1/environ``, un fichier 0600 de root et ``kill -0 1``
   refusés ;
9. ``codex --version`` et ``claude --version`` (point 8, keyring du noyau : sans objet, retiré par le cahier).

Verdict (contrat ``IsolementLinux``) : régime **A** si les points 4 et 5 rendent 0, si les quatre essais du point 6
tiennent et si le point 7 est conforme ; **B** sinon. ``uid_separes`` faux : aucune écriture, quel que soit le régime.
La disponibilité se prouve par CODE DE SORTIE, jamais par l'absence d'un avertissement (la sonde interne de Codex rend
« OK » quand bwrap ne se lance pas). Forme exacte du profil ``deny`` de Codex 0.156.1 : **supposée** (cahier § 4.1,
point 6, relevée dans ``permissions_toml.rs``) ; seul le binaire réel la confirme (image de l'exécutant, puis R0).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .journal import masquer

PROTOCOLE_SONDE = "acp-sonde-plateforme/1"
SORTIE_MAX = 200
DELAI_COMMANDE_S = 20.0
UID_CODEX = 10001
UID_VERIF = 10003
GROUPE_TRAVAIL = 10100
SETPRIV = "/usr/bin/setpriv"
CHAMPS_STATUT = ("Seccomp", "Seccomp_filters", "NoNewPrivs", "CapEff", "CapBnd")
NOYAU_SYSCTL = {
    "max_user_namespaces": "/proc/sys/user/max_user_namespaces",
    "unprivileged_userns_clone": "/proc/sys/kernel/unprivileged_userns_clone",
    "apparmor_restrict_unprivileged_userns": "/proc/sys/kernel/apparmor_restrict_unprivileged_userns",
}
CHEMINS_INTERDITS = ("/donnees/codex", "/donnees/claude", "/donnees/acp", "/etc/acp")
PROFIL = "acp_verif"


def profil_codex_toml(interdits: Sequence[str] = CHEMINS_INTERDITS, *, nom: str = PROFIL) -> str:
    """``config.toml`` d'un ``CODEX_HOME`` jetable qui définit le profil de permissions de la vérification (régime A) :
    écriture dans le dossier de travail et ``$TMPDIR`` seulement, lecture interdite des identifiants, réseau coupé.
    Forme SUPPOSÉE pour Codex 0.156.1 (``permissions_toml.rs`` : ``[permissions.<nom>.filesystem]`` et
    ``[permissions.<nom>.network]``, chemins spéciaux ``:root``, ``:project_roots``, ``:tmpdir``) : le binaire réel la
    confirme ou la refuse (échec fermé, la vérification n'est alors pas exécutée)."""
    lignes = [
        "# Écrit par le superviseur de l'exécutant ACP pour une seule vérification ; lecture seule.",
        f'default_permissions = "{nom}"',
        "",
        f"[permissions.{nom}.filesystem]",
        '":root" = "read"',
        '":project_roots" = "write"',
        '":tmpdir" = "write"',
    ]
    lignes += [f'"{chemin}" = "deny"' for chemin in interdits]
    lignes += ["", f"[permissions.{nom}.network]", "enabled = false", ""]
    return "\n".join(lignes)


@dataclass
class Releve:
    point: str
    commande: str
    code: int | None
    sortie: str = ""

    def json(self) -> dict[str, Any]:
        return {"point": self.point, "commande": self.commande, "code": self.code, "sortie": self.sortie}


@dataclass
class Mesures:
    """Ce que la sonde a mesuré ; ``None`` : non mesuré (outil absent, délai dépassé)."""

    unshare_root: int | None = None
    unshare_uid: int | None = None
    bwrap_present: bool = False
    bwrap_base: int | None = None
    bwrap_proc: int | None = None
    codex_present: bool = False
    essai_true: int | None = None
    essai_ecriture_hors: int | None = None
    essai_reseau: int | None = None
    essai_auth: int | None = None
    setpriv_id: str | None = None
    environ_pid1_refuse: bool | None = None
    fichier_root_refuse: bool | None = None
    kill_pid1_refuse: bool | None = None
    releves: list[Releve] = field(default_factory=list)


# Avertissement de Codex 0.156.1 quand son CODEX_HOME est sous /tmp (cas de la sonde, sans volume) : sans objet pour
# le verdict, il occupait les 200 caractères gardés et masquait la vraie cause d'un refus (relevé en CI, 01/10/2026).
_BRUIT = ("WARNING: proceeding, even though we could not create PATH aliases",)


def _filtrer(texte: str) -> str:
    lignes = [l for l in (texte or "").splitlines() if not l.strip().startswith(_BRUIT)]
    propre = " ".join(masquer("\n".join(lignes)).split())
    return propre[:SORTIE_MAX]


Executeur = Callable[[Sequence[str]], tuple[int | None, str]]


def executer_commande(argv: Sequence[str], *, env: dict[str, str] | None = None, cwd: str | None = None,
                      delai_s: float = DELAI_COMMANDE_S) -> tuple[int | None, str]:
    """(code, sortie d'erreur et standard brutes) ; ``(None, …)`` si la commande est introuvable ou dépasse le délai."""
    try:
        resultat = subprocess.run(list(argv), capture_output=True, timeout=delai_s, env=env or {
            "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}, cwd=cwd, check=False)
    except FileNotFoundError:
        return None, "commande introuvable"
    except subprocess.TimeoutExpired:
        return None, f"délai de {delai_s:g} s dépassé"
    except OSError as exc:
        return None, f"lancement impossible ({type(exc).__name__})"
    texte = (resultat.stderr or b"").decode("utf-8", "replace") + " " + (resultat.stdout or b"").decode(
        "utf-8", "replace")
    return resultat.returncode, texte


def _sous_uid(uid: int, argv: Sequence[str]) -> list[str]:
    return [SETPRIV, f"--reuid={uid}", f"--regid={uid}", f"--groups={GROUPE_TRAVAIL}", "--inh-caps=-all",
            "--bounding-set=-all", "--no-new-privs", "--", *argv]


def _lire(chemin: str) -> str | None:
    try:
        return Path(chemin).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _statut_processus() -> dict[str, str]:
    statut = _lire("/proc/self/status") or ""
    valeurs = {}
    for ligne in statut.splitlines():
        cle, _, valeur = ligne.partition(":")
        if cle in CHAMPS_STATUT:
            valeurs[cle] = valeur.strip()
    return valeurs


def _espace_libre_mio(chemin: str) -> int | None:
    try:
        etat = os.statvfs(chemin)
    except (OSError, AttributeError):
        return None
    return int(etat.f_bavail * etat.f_frsize // (1024 * 1024))


def _point_de_montage(chemin: str) -> bool:
    try:
        return os.path.ismount(chemin)
    except OSError:
        return False


def mesurer(*, executer: Executeur | None = None, codex: str | None = "/opt/acp/outils/codex/codex",
            claude: str | None = "/opt/acp/outils/claude/claude", bwrap: str | None = None,
            racine_temporaire: str | None = None) -> tuple[dict[str, Any], Mesures]:
    """Relevés des points 1 à 9 (sauf 8) ; ``executer`` est injectable pour les tests (aucun lancement réel)."""

    lancer = executer or (lambda argv: executer_commande(argv))
    m = Mesures()
    plateforme: dict[str, Any] = {}

    def noter(point: str, argv: Sequence[str], code: int | None, sortie: str) -> None:
        m.releves.append(Releve(point, " ".join(str(a) for a in argv)[:200], code, _filtrer(sortie)))

    def essai(point: str, argv: Sequence[str]) -> int | None:
        code, sortie = lancer(list(argv))
        noter(point, argv, code, sortie)
        return code

    # 1. plateforme (lectures sans commande quand la bibliothèque standard suffit)
    plateforme["architecture"] = platform.machine() or None
    plateforme["noyau"] = platform.release() or None
    os_release = _lire("/etc/os-release") or ""
    trouve = re.search(r'^PRETTY_NAME="?([^"\n]*)"?$', os_release, re.MULTILINE)
    plateforme["distribution"] = trouve.group(1)[:80] if trouve else None
    try:
        plateforme["processeurs"] = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        plateforme["processeurs"] = os.cpu_count()
    plateforme["memoire_max"] = _lire("/sys/fs/cgroup/memory.max")
    plateforme["cpu_max"] = _lire("/sys/fs/cgroup/cpu.max")
    try:
        shm = os.statvfs("/dev/shm")
        plateforme["shm_mio"] = int(shm.f_blocks * shm.f_frsize // (1024 * 1024))
    except (OSError, AttributeError):
        plateforme["shm_mio"] = None
    plateforme["libre_racine_mio"] = _espace_libre_mio("/")
    plateforme["libre_donnees_mio"] = _espace_libre_mio("/donnees") if _point_de_montage("/donnees") else "sans objet"
    m.codex_present = bool(codex) and os.path.isfile(codex)
    if m.codex_present:
        with tempfile.TemporaryDirectory(prefix="acp-sonde-doctor-", dir=racine_temporaire) as vide:
            os.chmod(vide, 0o777)
            code, sortie = lancer(_sous_uid(UID_CODEX, ["/usr/bin/env", f"CODEX_HOME={vide}", f"HOME={vide}",
                                                        codex, "doctor"]))
        lignes = [ligne for ligne in sortie.splitlines() if re.search(r"(?i)sandbox|denied|network|bwrap", ligne)]
        noter("1.codex_doctor", [codex, "doctor"], code, " | ".join(lignes))
    else:
        noter("1.codex_doctor", ["codex", "doctor"], None, "Codex absent de l'image")

    # 2 et 3. /proc
    plateforme["statut"] = _statut_processus()
    plateforme["sysctl"] = {nom: _lire(chemin) for nom, chemin in NOYAU_SYSCTL.items()}

    # 4. espaces de noms utilisateur
    m.unshare_root = essai("4.unshare_root", ["unshare", "-Ur", "true"])
    m.unshare_uid = essai("4.unshare_10003", _sous_uid(UID_VERIF, ["unshare", "-Ur", "true"]))

    # 5. sonde exacte de Codex, puis /proc neuf
    chemin_bwrap = bwrap or shutil.which("bwrap", path="/usr/bin:/bin:/usr/local/bin")
    m.bwrap_present = bool(chemin_bwrap)
    if chemin_bwrap:
        base = [chemin_bwrap, "--unshare-user", "--unshare-net", "--ro-bind", "/", "/", "/bin/true"]
        m.bwrap_base = essai("5.bwrap", _sous_uid(UID_CODEX, base))
        m.bwrap_proc = essai("5.bwrap_proc", _sous_uid(UID_CODEX, [*base[:-1], "--unshare-pid", "--proc", "/proc",
                                                                    "/bin/true"]))
    else:
        noter("5.bwrap", ["bwrap"], None, "bubblewrap absent")

    # 6. codex sandbox sous le profil de la vérification
    if m.codex_present:
        with tempfile.TemporaryDirectory(prefix="acp-sonde-essai-", dir=racine_temporaire) as racine:
            os.chmod(racine, 0o755)
            travail = Path(racine) / "travail"
            home = Path(racine) / "codex-home"
            faux = Path(racine) / "faux-codex-home"
            # Dossier inscriptible par tous HORS du dossier de travail : seule la clôture de Codex peut y refuser
            # l'écriture (un dossier de root la refuserait sans elle, et l'essai ne prouverait rien).
            ecrivable = Path(racine) / "hors-du-dossier"
            for dossier in (travail, home, faux, ecrivable):
                dossier.mkdir()
            os.chown(travail, UID_CODEX, UID_CODEX)
            os.chmod(ecrivable, 0o777)
            (faux / "auth.json").write_text('{"faux": "jeton factice de la sonde"}', encoding="utf-8")
            os.chmod(faux / "auth.json", 0o644)
            (home / "config.toml").write_text(profil_codex_toml([str(faux)]), encoding="utf-8")
            os.chmod(home / "config.toml", 0o644)
            prefixe = _sous_uid(UID_CODEX, ["/usr/bin/env", f"CODEX_HOME={home}", f"HOME={travail}", codex,
                                            "sandbox", "-P", PROFIL, "-C", str(travail), "--"])
            m.essai_true = essai("6a.true", [*prefixe, "/bin/true"])
            m.essai_ecriture_hors = essai("6b.ecriture_hors", [*prefixe, "/usr/bin/touch",
                                                              str(ecrivable / "ecrit-par-codex")])
            m.essai_reseau = essai("6c.reseau", [*prefixe, "getent", "hosts", "example.com"])
            m.essai_auth = essai("6d.auth", [*prefixe, "cat", str(faux / "auth.json")])
    else:
        noter("6.codex_sandbox", ["codex", "sandbox"], None, "Codex absent de l'image")

    # 7. séparation par UID
    code, sortie = lancer(_sous_uid(UID_VERIF, ["id", "-u"]))
    noter("7.id", ["setpriv", "id", "-u"], code, sortie)
    m.setpriv_id = sortie.strip().split()[-1] if code == 0 and sortie.strip() else None
    m.environ_pid1_refuse = essai("7.environ_pid1", _sous_uid(UID_VERIF, ["cat", "/proc/1/environ"])) not in (0, None)
    with tempfile.TemporaryDirectory(prefix="acp-sonde-root-", dir=racine_temporaire) as dossier:
        os.chmod(dossier, 0o755)
        secret = Path(dossier) / "fichier-root"
        secret.write_text("contenu de root", encoding="utf-8")
        os.chmod(secret, 0o600)
        m.fichier_root_refuse = essai("7.fichier_root", _sous_uid(UID_VERIF, ["cat", str(secret)])) not in (0, None)
    m.kill_pid1_refuse = essai("7.kill_pid1", _sous_uid(UID_VERIF, ["kill", "-0", "1"])) not in (0, None)

    # 9. versions (sans connexion)
    for nom, chemin in (("codex", codex), ("claude", claude)):
        if chemin and os.path.isfile(chemin):
            code, sortie = lancer([chemin, "--version"])
            noter(f"9.{nom}_version", [nom, "--version"], code, sortie)
        else:
            noter(f"9.{nom}_version", [nom, "--version"], None, f"{nom} absent de l'image")
    return plateforme, m


def verdict(m: Mesures) -> dict[str, Any]:
    """Régime, état de bubblewrap, /proc neuf, réseau coupé, UID séparés et raison (française) : ce qui a été MESURÉ."""
    uid_separes = (m.setpriv_id == str(UID_VERIF) and m.environ_pid1_refuse is True
                   and m.fichier_root_refuse is True and m.kill_pid1_refuse is True)
    if not m.bwrap_present:
        bwrap = "absent"
    elif m.bwrap_base == 0:
        bwrap = "fonctionne"
    elif m.bwrap_base is None:
        bwrap = "inconnu"
    else:
        bwrap = "refuse"
    proc_neuf = None if bwrap in ("absent", "inconnu") else m.bwrap_proc == 0
    essais = (m.essai_true, m.essai_ecriture_hors, m.essai_reseau, m.essai_auth)
    essais_tenus = m.codex_present and m.essai_true == 0 and all(c not in (0, None) for c in essais[1:])
    reseau_coupe = None if not m.codex_present or m.essai_reseau is None else m.essai_reseau != 0
    a = m.unshare_root == 0 and m.unshare_uid == 0 and bwrap == "fonctionne" and essais_tenus and uid_separes
    if a:
        raison = "Régime A : espaces de noms utilisateur, bubblewrap et réseau coupé mesurés ; UID séparés."
    elif not uid_separes:
        raison = ("Identifiants séparés par UID non prouvés (setpriv, /proc/1/environ, fichier de root ou kill -0 1) : "
                  "aucune écriture.")
    elif bwrap == "absent":
        raison = "Régime B : bubblewrap absent de l'image."
    elif bwrap != "fonctionne":
        raison = "Régime B : bubblewrap refusé par la plateforme (espaces de noms utilisateur indisponibles)."
    elif m.unshare_root != 0 or m.unshare_uid != 0:
        raison = "Régime B : unshare -Ur refusé."
    elif not m.codex_present:
        raison = "Régime B : Codex absent, essais de codex sandbox non faits."
    else:
        raison = "Régime B : un essai de codex sandbox n'a pas tenu (écriture, réseau ou lecture interdite)."
    return {"regime": "A" if a else "B", "bwrap": bwrap, "proc_neuf": proc_neuf,
            "reseau_coupe": reseau_coupe if a else (False if reseau_coupe is None else reseau_coupe),
            "uid_separes": uid_separes, "raison": raison}


def sonder(*, maintenant: datetime | None = None, **options: Any) -> dict[str, Any]:
    """Relevé complet publiable (aucun identifiant) : plateforme, relevés et verdict."""
    instant = maintenant or datetime.now(UTC)
    plateforme, m = mesurer(**options)
    return {"protocole": PROTOCOLE_SONDE, "sonde_le": instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "plateforme": plateforme, "releves": [r.json() for r in m.releves], "verdict": verdict(m)}


def isolement(resultat: dict[str, Any] | None, *, sans_bac_a_sable: str = "refuse",
              maintenant: datetime | None = None) -> dict[str, Any]:
    """Bloc ``isolement_linux`` de l'inventaire (contrat ``IsolementLinux``) depuis le relevé de la sonde ; sans relevé :
    « inconnu », aucune écriture. Codex n'écrit qu'en régime A (D79 : « refuse » sinon) ; Claude (``--restricted``,
    sans commande) n'écrit que si les UID sont séparés."""
    if not resultat or not isinstance(resultat.get("verdict"), dict):
        instant = (maintenant or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"regime": "inconnu", "bwrap": "inconnu", "proc_neuf": None, "reseau_coupe": None, "uid_separes": None,
                "codex_sans_bac_a_sable": sans_bac_a_sable, "ecriture_admise": {"codex": False, "claude": False},
                "raison": "Sonde de plateforme non faite : régime inconnu, aucune écriture.", "sonde_le": instant}
    v = resultat["verdict"]
    uid = v.get("uid_separes") is True
    codex = uid and v.get("regime") == "A"
    raison = v.get("raison")
    if uid and not codex:
        raison = (f"{raison} Voie Codex fermée : bac à sable Linux refusé par la plateforme (D79)."
                  if v.get("regime") == "B" else raison)
    return {"regime": v.get("regime", "inconnu"), "bwrap": v.get("bwrap", "inconnu"), "proc_neuf": v.get("proc_neuf"),
            "reseau_coupe": v.get("reseau_coupe"), "uid_separes": v.get("uid_separes"),
            "codex_sans_bac_a_sable": sans_bac_a_sable, "ecriture_admise": {"codex": codex, "claude": uid},
            "raison": (raison or None) if not (codex and uid) else None, "sonde_le": resultat["sonde_le"]}


def imprimer(resultat: dict[str, Any]) -> str:
    return json.dumps(resultat, ensure_ascii=False, indent=2)
