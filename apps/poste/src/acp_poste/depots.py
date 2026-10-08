"""Dépôts de l'exécutant (cahier P6 § 3.3, § 6.2, § 6.6, § 6.7, § 12.2) : clone nu, récupération, worktree d'une
carte, commit local par le superviseur, diff, quarantaine, intégration et ``git bundle``. **Aucun push.**

Tout ``git`` est lancé par le superviseur (root), sans shell, avec des options imposées à chaque commande :

    -c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never -c protocol.https.allow=always
    -c submodule.recurse=false -c core.symlinks=false -c credential.helper=

et ``GIT_TERMINAL_PROMPT=0``, ``GIT_LFS_SKIP_SMUDGE=1``, ``GIT_CONFIG_GLOBAL=/dev/null`` (la configuration système
de l'image reste lue). Dans un worktree, le superviseur ne se fie **jamais** au fichier ``.git`` du dossier, que les
agents peuvent réécrire : il passe ``--git-dir`` (le dossier ``worktrees/<carte>`` du clone nu, root, 0755) et
``--work-tree`` explicitement. Sans cela, un agent remplaçant ``.git`` par un dépôt à lui ferait exécuter au
superviseur un ``core.fsmonitor`` de son choix (ajout de cette implémentation au cahier).

Dépôt privé : ``GIT_ASKPASS=/opt/acp/bin/acp-askpass`` ; le jeton **de lecture** (D92) n'est transmis qu'au seul
``git fetch`` du superviseur, dans une variable que ``acp-askpass`` relit — jamais dans l'URL, l'argv, ni
l'environnement d'un agent. Droits : clone nu root 0755 (aucun agent n'y écrit d'objet ni ne déplace de référence) ;
dossier d'une carte ``root:acp-travail`` 2770 et fichiers en ``g+w`` pendant son tour, ``0700 root:root`` hors de son
tour (§ 3.3, correction n° 21).

Étape P7 (cahier P7 § 11.2, décision P7-11) : **visibilité mesurée** d'un dépôt (:meth:`Depots.visibilite`). Un
``git ls-remote --heads`` **sans aucun identifiant** (même environnement et mêmes options que toute commande, invites
fermées, ``credential.helper`` vide, délai de 30 s) : accepté → ``public`` ; refusé par un motif d'authentification
reconnu de git (code 128) → ``prive`` ; tout le reste (délai, réseau, certificat, 403, 500, motif inconnu) →
``inconnue``. Puis la lecture que l'exécutant fera réellement : avec le jeton de lecture (``acp-askpass``) pour un
dépôt ``jeton_lecture`` → ``ok`` | ``refusee`` | ``inconnue``. La voie Codex n'est ouverte que sur ``prive`` ET ``ok``
(:mod:`acp_poste.execution`). Rien de la sortie de git (que le serveur distant peut composer) n'est repris : seuls des
messages français composés ici.

Étape P7 (correction K25) : une carte dont la branche a été mise en **quarantaine** (secret détecté) n'est jamais
reprise sur son worktree : :meth:`Depots.worktree` le retire et repart du départ de la carte ; la branche
``quarantaine/<carte>`` reste, jamais intégrée ni poussée.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from acp_poste_contrat.inventaire import ALIAS_DEPOT as ALIAS
from acp_poste_contrat.machine import BRANCHE_CARTE, BRANCHE_PROJET, branche_git_valide

GIT = "git"
GROUPE_TRAVAIL = 10100
DELAI_FETCH_S = 600.0
DELAI_GIT_S = 120.0
DIFF_MAX = 4 * 1024 * 1024
ASKPASS = "/opt/acp/bin/acp-askpass"
VARIABLE_JETON = "ACP_JETON_LECTURE"
PATH_GIT = "/usr/local/bin:/usr/bin:/bin"
_SHA = re.compile(r"[0-9a-f]{40}")
DELAI_VISIBILITE_S = 30.0
CODE_FATAL_GIT = 128
STDERR_VISIBILITE_MAX = 64 * 1024
# Messages composés par git LUI-MÊME (jamais par le serveur : les lignes du serveur sont préfixées « remote: »), relevés
# sur git 2.47.3, la version épinglée dans executant/Dockerfile, contre un faux serveur HTTPS
# (apps/poste/tests/test_visibilite.py) : invite d'identifiant refusée (aucun identifiant fourni), identifiants
# refusés par le serveur (401 après le jeton), dépôt « introuvable » (404 : GitHub répond ainsi à un dépôt privé hors
# de portée du jeton comme à un dépôt inexistant). Tout autre message → « inconnue » (échec fermé).
MOTIFS_REFUS_GIT = (
    re.compile(r"^fatal: could not read (?:Username|Password) for '[^'\n]*': terminal prompts disabled$", re.M),
    re.compile(r"^fatal: Authentication failed for '[^'\n]*'$", re.M),
    re.compile(r"^fatal: repository '[^'\n]*' not found$", re.M),
)


class ErreurDepot(RuntimeError):
    """Opération git refusée ou en échec (message français, sans URL ni jeton)."""


@dataclass(frozen=True)
class Visibilite:
    """Visibilité MESURÉE d'un dépôt (cahier P7 § 11.2) : ``visibilite`` (``public``, ``prive``, ``inconnue``),
    ``lecture`` (``ok``, ``refusee``, ``inconnue``), ``verifie_le`` et ``raison`` (phrase française composée ici, pour
    le journal ; jamais l'URL, le jeton ni une sortie de git). Publiée dans l'inventaire par :meth:`contrat`."""

    visibilite: str
    lecture: str
    verifie_le: datetime
    raison: str

    @property
    def codex_admis(self) -> bool:
        """D83 : Codex (compte ChatGPT) seulement sur un dépôt prouvé privé ET lu avec le jeton."""
        return self.visibilite == "prive" and self.lecture == "ok"

    def contrat(self) -> dict[str, str]:
        return {"visibilite": self.visibilite, "lecture": self.lecture,
                "verifie_le": self.verifie_le.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}


@dataclass(frozen=True)
class SortieLsRemote:
    """Issue d'un ``git ls-remote`` : ``code`` (``None`` : délai dépassé ou git impossible à lancer) et ``refus``
    (un motif d'authentification reconnu dans la sortie d'erreur, code 128)."""

    code: int | None
    refus: bool
    delai: bool = False


def classer_ls_remote(code: int | None, erreur: bytes) -> SortieLsRemote:
    """Code et sortie d'erreur d'un ``git ls-remote`` → :class:`SortieLsRemote` (seuls les motifs de git comptent)."""
    if code != CODE_FATAL_GIT:
        return SortieLsRemote(code=code, refus=False)
    texte = erreur[:STDERR_VISIBILITE_MAX].decode("utf-8", "replace").replace("\r\n", "\n")
    return SortieLsRemote(code=code, refus=any(motif.search(texte) for motif in MOTIFS_REFUS_GIT))


def _raison_ls_remote(objet: str, sortie: SortieLsRemote, delai_s: float, *, accepte: str, refuse: str) -> str:
    """Phrase française d'une mesure (jamais la sortie de git, que le serveur distant peut composer)."""
    if sortie.code == 0:
        return f"{objet} {accepte}"
    if sortie.refus:
        return f"{objet} {refuse}"
    if sortie.delai:
        return f"{objet} : délai de {delai_s:g} s dépassé"
    if sortie.code is None:
        return f"{objet} : git impossible à lancer"
    return f"{objet} : réponse de git non reconnue (code {sortie.code})"


def options_git(protocoles: Sequence[str] = ("https",), *, liens_symboliques: bool = False) -> list[str]:
    options = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "protocol.allow=never"]
    for protocole in protocoles:
        options += ["-c", f"protocol.{protocole}.allow=always"]
    options += ["-c", "submodule.recurse=false", "-c", f"core.symlinks={'true' if liens_symboliques else 'false'}",
                "-c", "credential.helper="]
    return options


@dataclass(frozen=True)
class Changement:
    """Une entrée de ``git diff --raw -M`` : statut (A, M, D, R…), modes et chemins (ancien et nouveau)."""

    statut: str
    mode_avant: str
    mode_apres: str
    chemins: tuple[str, ...]


def analyser_raw(sortie: bytes) -> list[Changement]:
    """Sortie de ``git diff --raw -z -M`` → changements (chemins non quotés, renommages à deux chemins)."""
    morceaux = sortie.split(b"\0")
    changements = []
    i = 0
    while i < len(morceaux):
        entete = morceaux[i]
        if not entete:
            i += 1
            continue
        if not entete.startswith(b":"):
            raise ErreurDepot("Sortie de git diff illisible.")
        champs = entete[1:].decode("ascii", "replace").split()
        if len(champs) < 5:
            raise ErreurDepot("Sortie de git diff illisible.")
        statut = champs[4]
        nombre = 2 if statut[:1] in ("R", "C") else 1
        chemins = tuple(m.decode("utf-8", "surrogateescape") for m in morceaux[i + 1:i + 1 + nombre])
        changements.append(Changement(statut=statut[:1], mode_avant=champs[0], mode_apres=champs[1],
                                      chemins=chemins))
        i += 1 + nombre
    return changements


@dataclass
class Depots:
    """Opérations git de l'exécutant sur ses emplacements (``depots`` et ``espaces`` du volume, ``bundles``).

    ``protocoles`` : ``("https",)`` en production ; les tests ajoutent ``file`` (dépôt distant local). ``droits`` :
    applique propriétaires et modes (root seulement ; ``False`` dans les tests sans root). ``jeton_lecture`` : lu au
    moment du fetch, jamais gardé."""

    racine_depots: Path
    racine_espaces: Path
    racine_bundles: Path
    jeton_lecture: Callable[[], str | None] = lambda: None
    protocoles: tuple[str, ...] = ("https",)
    askpass: str = ASKPASS
    droits: bool = field(default_factory=lambda: hasattr(os, "geteuid") and os.geteuid() == 0)
    auteur: tuple[str, str] = ("ACP exécutant", "executant@acp.invalid")

    # ------------------------------------------------------------------ exécution
    def _env(self, supplement: dict[str, str] | None = None) -> dict[str, str]:
        env = {"PATH": PATH_GIT, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": "/nonexistent",
               "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS": "/bin/false"}
        if os.name == "nt":
            env.update({k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP")})
        env.update(supplement or {})
        return env

    def git(self, *arguments: str, cwd: Path | None = None, git_dir: Path | None = None,
            work_tree: Path | None = None, delai_s: float = DELAI_GIT_S, env: dict[str, str] | None = None,
            liens_symboliques: bool = False, verifier: bool = True, sortie_max: int = DIFF_MAX) -> bytes:
        argv = [GIT, *options_git(self.protocoles, liens_symboliques=liens_symboliques)]
        if git_dir is not None:
            argv += [f"--git-dir={git_dir}"]
        if work_tree is not None:
            argv += [f"--work-tree={work_tree}"]
        argv += list(arguments)
        try:
            resultat = subprocess.run(argv, cwd=str(cwd) if cwd else None, env=self._env(env), capture_output=True,
                                      timeout=delai_s, check=False)
        except subprocess.TimeoutExpired:
            raise ErreurDepot(f"git {arguments[0]} : délai de {delai_s:g} s dépassé.") from None
        except OSError:
            raise ErreurDepot("git introuvable dans l'image : opération impossible.") from None
        if verifier and resultat.returncode != 0:
            raise ErreurDepot(f"git {arguments[0]} en échec (code {resultat.returncode}).")
        if len(resultat.stdout) > sortie_max:
            raise ErreurDepot(f"git {arguments[0]} : sortie de plus de {sortie_max // (1024 * 1024)} Mio refusée.")
        return resultat.stdout

    # ------------------------------------------------------------------ chemins
    def nu(self, alias: str) -> Path:
        return self.racine_depots / f"{alias}.git"

    def espace(self, alias: str, nom: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", nom):
            raise ErreurDepot("Nom de worktree refusé.")
        return self.racine_espaces / alias / nom

    def gitdir_du_worktree(self, alias: str, nom: str) -> Path:
        return self.nu(alias) / "worktrees" / nom

    # ------------------------------------------------------------------ clone nu et récupération (§ 6.2)
    def _droits_racine(self, chemin: Path, mode: int) -> None:
        if self.droits:
            os.chown(chemin, 0, 0)
        os.chmod(chemin, mode)

    def preparer_racines(self) -> None:
        for racine, mode in ((self.racine_depots, 0o755), (self.racine_espaces, 0o751), (self.racine_bundles, 0o700)):
            racine.mkdir(parents=True, exist_ok=True)
            if self.droits:
                os.chown(racine, 0, GROUPE_TRAVAIL if racine == self.racine_espaces else 0)
            os.chmod(racine, mode)

    def _env_fetch(self, acces: str) -> dict[str, str]:
        if acces != "jeton_lecture":
            return {}
        jeton = self.jeton_lecture()
        if not jeton:
            raise ErreurDepot("Jeton GitHub de lecture absent : déposez-le par « acp-poste connexion github --stdin » "
                              "(D92) ; dépôt non récupéré.")
        return {"GIT_ASKPASS": self.askpass, VARIABLE_JETON: jeton}

    def recuperer(self, depot: Any) -> Path:
        """Clone nu à la première carte, puis ``fetch`` de la branche de base vers ``refs/remotes/origin/<base>``."""
        self.preparer_racines()
        nu = self.nu(depot.alias)
        env = self._env_fetch(depot.acces)
        if (nu / "HEAD").is_file():
            # Étape P7 (relecture indépendante de la partie E) : la visibilité est mesurée sur l'URL de la politique ;
            # un clone nu d'une AUTRE URL (alias réaffecté par une PR) ne doit jamais être récupéré à sa place.
            origine = self.git("config", "--get", "remote.origin.url", git_dir=nu, verifier=False)
            if origine.decode("utf-8", "replace").strip() != depot.url:
                raise ErreurDepot(f"Le clone nu du dépôt « {depot.alias} » vient d'une autre URL que la politique : "
                                  "récupération refusée ; retirez ce clone (/donnees/depots, session railway ssh) "
                                  "après avoir récupéré ses branches.")
        if not (nu / "HEAD").is_file():
            if nu.exists():
                shutil.rmtree(nu)
            self.git("clone", "--bare", "--no-tags", "--", depot.url, str(nu), env=env, delai_s=DELAI_FETCH_S)
            self._droits_racine(nu, 0o755)
        self.git("fetch", "--no-tags", "origin",
                 f"+refs/heads/{depot.branche_base}:refs/remotes/origin/{depot.branche_base}",
                 git_dir=nu, env=env, delai_s=DELAI_FETCH_S)
        self.verrouiller_nu(nu)
        return nu

    # ------------------------------------------------------------------ visibilité mesurée (étape P7, § 11.2)
    def _ls_remote(self, url: str, env: dict[str, str], delai_s: float) -> SortieLsRemote:
        """``git ls-remote --heads -- <url>`` avec les options imposées ; sortie standard jetée, sortie d'erreur lue pour
        ses seuls motifs. Lancé DEPUIS la racine des clones (root, jamais un dépôt) : git ne lit la configuration
        d'aucun dépôt rencontré dans le dossier courant (un ``http.extraHeader`` ou un mandataire y détournerait le
        jeton). Délai dépassé : tout le groupe de processus est tué (``git-remote-https`` compris)."""
        argv = [GIT, *options_git(self.protocoles), "ls-remote", "--heads", "--", url]
        posix = os.name == "posix"
        try:
            self.racine_depots.mkdir(parents=True, exist_ok=True)
            processus = subprocess.Popen(argv, cwd=str(self.racine_depots), env=self._env(env),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                         start_new_session=posix)
        except OSError:
            return SortieLsRemote(code=None, refus=False)
        try:
            _sortie, erreur = processus.communicate(timeout=delai_s)
        except subprocess.TimeoutExpired:
            try:
                if posix:
                    os.killpg(processus.pid, signal.SIGKILL)
                else:
                    processus.kill()
            except OSError:
                pass
            try:
                processus.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            return SortieLsRemote(code=None, refus=False, delai=True)
        return classer_ls_remote(processus.returncode, erreur or b"")

    def visibilite(self, depot: Any, *, delai_s: float = DELAI_VISIBILITE_S,
                   horloge: Callable[[], datetime] | None = None) -> Visibilite:
        """Visibilité mesurée de ``depot`` (cahier P7 § 11.2) : accès ANONYME (``GIT_ASKPASS=/bin/false``, aucun
        jeton dans l'environnement), puis la lecture que l'exécutant fera vraiment — avec le jeton de lecture
        (``acp-askpass``, variable ``ACP_JETON_LECTURE``, jamais l'argv) pour un dépôt ``jeton_lecture``, sans
        identifiant pour un dépôt déclaré ``public``. Ne lève jamais : un échec se dit ``inconnue``."""
        anonyme = self._ls_remote(depot.url, {}, delai_s)
        visibilite = "public" if anonyme.code == 0 else "prive" if anonyme.refus else "inconnue"
        raisons = [_raison_ls_remote("accès anonyme", anonyme, delai_s, accepte="accepté (dépôt public)",
                                     refuse="refusé (authentification demandée)")]
        if getattr(depot, "acces", None) == "jeton_lecture":
            jeton = self.jeton_lecture()
            if not jeton:
                lecture = "inconnue"
                raisons.append("jeton de lecture absent : déposez-le par « acp-poste connexion github --stdin » (D92)")
            else:
                avec = self._ls_remote(depot.url, {"GIT_ASKPASS": self.askpass, VARIABLE_JETON: jeton}, delai_s)
                lecture = "ok" if avec.code == 0 else "refusee" if avec.refus else "inconnue"
                raisons.append(_raison_ls_remote("lecture avec le jeton", avec, delai_s, accepte="acceptée",
                                                 refuse="refusée"))
                if visibilite == "prive" and lecture == "ok":
                    # La mesure n'est pas atomique : un refus anonyme passager suivi d'une lecture réussie ferait
                    # passer pour privé un dépôt lisible sans identifiant. L'accès anonyme est REFAIT après la lecture :
                    # « prive » exige deux refus (relecture indépendante de la partie E).
                    second = self._ls_remote(depot.url, {}, delai_s)
                    if not second.refus:
                        visibilite = "public" if second.code == 0 else "inconnue"
                        raisons.append(_raison_ls_remote("second accès anonyme", second, delai_s,
                                                         accepte="accepté (dépôt lisible sans identifiant)",
                                                         refuse="refusé"))
        else:
            # Dépôt déclaré « public » : l'exécutant le lit sans identifiant ; sa lecture mesurée est l'accès anonyme.
            lecture = "ok" if anonyme.code == 0 else "refusee" if anonyme.refus else "inconnue"
        instant = (horloge or (lambda: datetime.now(UTC)))()
        return Visibilite(visibilite=visibilite, lecture=lecture, verifie_le=instant, raison=" ; ".join(raisons) + ".")

    def verrouiller_nu(self, nu: Path) -> None:
        """Clone nu root, aucun droit d'écriture pour le groupe ni les autres (les agents n'y écrivent rien)."""
        if not self.droits:
            return
        for racine, dossiers, fichiers in os.walk(nu):
            for nom in dossiers + fichiers:
                chemin = os.path.join(racine, nom)
                os.lchown(chemin, 0, 0)
                if not os.path.islink(chemin):
                    os.chmod(chemin, os.lstat(chemin).st_mode & ~0o022)
        os.chown(nu, 0, 0)
        os.chmod(nu, 0o755)

    def sha(self, git_dir: Path, reference: str) -> str | None:
        sortie = self.git("rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}", git_dir=git_dir,
                          verifier=False).decode("ascii", "replace").strip()
        return sortie if _SHA.fullmatch(sortie) else None

    def merge_base(self, alias: str, gauche: str, droite: str) -> str | None:
        """Ancêtre commun de deux références du clone nu (base d'une carte dont l'état local a été perdu)."""
        sortie = self.git("merge-base", gauche, droite, git_dir=self.nu(alias), verifier=False)
        texte = sortie.decode("ascii", "replace").strip()
        return texte if _SHA.fullmatch(texte) else None

    def branche_existe(self, alias: str, branche: str) -> bool:
        return self.sha(self.nu(alias), f"refs/heads/{branche}") is not None

    # ------------------------------------------------------------------ worktree d'une carte
    def worktree(self, depot: Any, nom: str, branche: str, depart: str, *, liens_symboliques: bool = False) -> Path:
        """Worktree ``espaces/<alias>/<nom>`` sur la branche ``branche``, créée depuis ``depart`` ; gardé s'il existe
        (reprise). ``depart`` : branche locale d'une carte parente (``hermes/<carte>``) ou ``origin/<base>``.

        Étape P7 (correction K25) : un worktree gardé n'est repris que s'il est posé sur ``branche`` (``HEAD`` lu dans
        son gitdir, root, jamais dans le ``.git`` du dossier). Après la mise en quarantaine d'un secret, il est posé sur
        ``quarantaine/<carte>`` : il est retiré, et la carte repart de ``depart`` sur une branche neuve, sans le commit
        fautif (la branche de quarantaine reste, jamais intégrée ni poussée)."""
        if not (BRANCHE_CARTE.fullmatch(branche) or BRANCHE_PROJET.fullmatch(branche)):
            raise ErreurDepot("Branche d'une carte refusée (hermes/<carte> ou hermes/projet-<slug> attendu).")
        if not branche_git_valide(depart.removeprefix("origin/")):
            raise ErreurDepot("Branche de départ refusée.")
        nu = self.nu(depot.alias)
        chemin = self.espace(depot.alias, nom)
        gitdir = self.gitdir_du_worktree(depot.alias, nom)
        if chemin.exists() and gitdir.is_dir():
            if self.branche_du_worktree(depot.alias, nom) == branche:
                return chemin
            self.retirer_worktree(depot.alias, nom)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        if self.droits:
            os.chown(chemin.parent, 0, GROUPE_TRAVAIL)
        os.chmod(chemin.parent, 0o751)
        reference = (f"refs/remotes/{depart}" if depart.startswith("origin/") else f"refs/heads/{depart}")
        if self.sha(nu, reference) is None:
            raise ErreurDepot(f"Branche de départ {depart} absente du clone : carte non préparée.")
        if self.branche_existe(depot.alias, branche):
            self.git("worktree", "add", "--", str(chemin), branche, git_dir=nu, liens_symboliques=liens_symboliques)
        else:
            self.git("worktree", "add", "-b", branche, "--", str(chemin), reference, git_dir=nu,
                     liens_symboliques=liens_symboliques)
        self.verrouiller_nu(nu)
        return chemin

    def branche_du_worktree(self, alias: str, nom: str) -> str | None:
        """Branche sur laquelle le worktree ``nom`` est posé, lue dans son gitdir (root) ; ``None`` si illisible ou
        détaché."""
        sortie = self.git("symbolic-ref", "-q", "HEAD", git_dir=self.gitdir_du_worktree(alias, nom), verifier=False)
        texte = sortie.decode("utf-8", "replace").strip()
        return texte.removeprefix("refs/heads/") if texte.startswith("refs/heads/") else None

    def ouvrir_tour(self, chemin: Path) -> None:
        """Pendant le tour de la carte : ``root:acp-travail``, dossiers 2770 (setgid), fichiers ``g+w``."""
        if not self.droits:
            return
        for racine, dossiers, fichiers in os.walk(chemin):
            for nom in dossiers:
                d = os.path.join(racine, nom)
                if os.path.islink(d):
                    continue
                os.chown(d, os.lstat(d).st_uid, GROUPE_TRAVAIL)
                os.chmod(d, (os.lstat(d).st_mode & 0o777) | 0o2770)
            for nom in fichiers:
                f = os.path.join(racine, nom)
                os.lchown(f, os.lstat(f).st_uid, GROUPE_TRAVAIL)
                if not os.path.islink(f):
                    os.chmod(f, (os.lstat(f).st_mode & 0o777) | 0o060)
        os.chown(chemin, 0, GROUPE_TRAVAIL)
        os.chmod(chemin, 0o2770)

    def fermer_tour(self, chemin: Path) -> None:
        """Hors du tour de la carte : dossier ``0700 root:root`` (un dossier non traversable coupe l'accès à tout ce
        qu'il contient)."""
        if not chemin.exists():
            return
        if self.droits:
            os.chown(chemin, 0, 0)
        os.chmod(chemin, 0o700)

    def _wt(self, alias: str, nom: str) -> dict[str, Path]:
        return {"git_dir": self.gitdir_du_worktree(alias, nom), "work_tree": self.espace(alias, nom),
                "cwd": self.espace(alias, nom)}

    # ------------------------------------------------------------------ commit et diff (§ 6.6)
    def indexer(self, alias: str, nom: str) -> None:
        self.git("add", "-A", "--", ".", **self._wt(alias, nom))

    def changements(self, alias: str, nom: str, base: str) -> list[Changement]:
        """Changements indexés par rapport à ``base`` (renommages compris, modes : liens 120000, gitlinks 160000)."""
        return analyser_raw(self.git("diff", "--cached", "--raw", "-z", "-M", "--no-ext-diff", "--no-textconv", base,
                                     **self._wt(alias, nom)))

    def lignes_ajoutees(self, alias: str, nom: str, base: str) -> str:
        brut = self.git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", base, "--",
                        **self._wt(alias, nom))
        lignes = [ligne[1:] for ligne in brut.decode("utf-8", "replace").splitlines()
                  if ligne.startswith("+") and not ligne.startswith("+++")]
        return "\n".join(lignes)

    def committer(self, alias: str, nom: str, message: str) -> str | None:
        """Commit local du superviseur (aucun crochet, aucune signature, aucun trailer) ; ``None`` si rien n'a changé."""
        wt = self._wt(alias, nom)
        self.indexer(alias, nom)
        if not self.git("diff", "--cached", "--name-only", **wt).strip():
            return None
        nom_auteur, courriel = self.auteur
        self.git("-c", f"user.name={nom_auteur}", "-c", f"user.email={courriel}", "-c", "commit.gpgsign=false",
                 "commit", "--no-verify", "--quiet", "-m", message, **wt)
        return self.tete(alias, nom)

    def tete(self, alias: str, nom: str) -> str | None:
        return self.sha(self.gitdir_du_worktree(alias, nom), "HEAD")

    def diffstat(self, alias: str, nom: str, base: str, tete: str) -> dict[str, int]:
        sortie = self.git("diff", "--numstat", "--no-ext-diff", "--no-textconv", base, tete,
                          **self._wt(alias, nom)).decode("utf-8", "replace")
        fichiers = ajouts = retraits = 0
        for ligne in sortie.splitlines():
            parties = ligne.split("\t")
            if len(parties) < 3:
                continue
            fichiers += 1
            ajouts += int(parties[0]) if parties[0].isdigit() else 0
            retraits += int(parties[1]) if parties[1].isdigit() else 0
        return {"fichiers": fichiers, "ajouts": ajouts, "retraits": retraits}

    def diff_texte(self, alias: str, nom: str, base: str, tete: str, *, maximum: int = 256 * 1024) -> str:
        """Diff d'une carte relue (préparé par le superviseur pour Claude, qui n'a pas de shell)."""
        brut = self.git("diff", "--no-color", "--no-ext-diff", "--no-textconv", base, tete, **self._wt(alias, nom))
        return brut[:maximum].decode("utf-8", "replace")

    def quarantaine(self, alias: str, nom: str, branche: str) -> str:
        """Renomme ``hermes/<carte>`` en ``quarantaine/<carte>`` (jamais intégrée, jamais poussée)."""
        cible = "quarantaine/" + branche.removeprefix("hermes/")
        self.git("branch", "-M", branche, cible, **self._wt(alias, nom))
        return cible

    # ------------------------------------------------------------------ intégration (§ 6.7)
    def fusionner(self, alias: str, nom: str, branches: Sequence[str]) -> list[str]:
        """Fusionne ``--no-ff`` chaque branche dans l'ordre ; au premier conflit, ``merge --abort`` et la liste des
        fichiers en conflit (vide : tout est fusionné). Une branche déjà contenue est sans effet."""
        wt = self._wt(alias, nom)
        nom_auteur, courriel = self.auteur
        for branche in branches:
            if not BRANCHE_CARTE.fullmatch(branche):
                raise ErreurDepot("Branche à intégrer refusée (hermes/<carte> attendu).")
            if self.sha(wt["git_dir"], f"refs/heads/{branche}") is None:
                raise ErreurDepot(f"Branche {branche} absente de l'exécutant : intégration impossible.")
            self.git("-c", f"user.name={nom_auteur}", "-c", f"user.email={courriel}", "-c", "commit.gpgsign=false",
                     "merge", "--no-ff", "--no-edit", "--no-verify", "-m", f"integration: {branche}",
                     f"refs/heads/{branche}", verifier=False, **wt)
            conflits = self.git("diff", "--name-only", "--diff-filter=U", **wt).decode("utf-8", "replace").split()
            if conflits:
                self.git("merge", "--abort", verifier=False, **wt)
                return sorted(conflits)
            if self.sha(wt["git_dir"], "MERGE_HEAD") is not None:
                self.git("merge", "--abort", verifier=False, **wt)
                raise ErreurDepot(f"Fusion de {branche} interrompue sans conflit lisible : intégration arrêtée.")
        return []

    # ------------------------------------------------------------------ bundle (§ 12.2)
    def bundle(self, alias: str, branche: str) -> tuple[Path, str, str]:
        """``git bundle create`` de ``branche`` (root, 0600) : (fichier, SHA-256 du fichier, tête)."""
        if not (BRANCHE_PROJET.fullmatch(branche) or BRANCHE_CARTE.fullmatch(branche)):
            raise ErreurDepot("Branche refusée : seules hermes/projet-<slug> et hermes/<carte> se récupèrent.")
        nu = self.nu(alias)
        tete = self.sha(nu, f"refs/heads/{branche}")
        if tete is None:
            raise ErreurDepot(f"Branche {branche} absente du dépôt {alias} sur l'exécutant.")
        self.racine_bundles.mkdir(parents=True, exist_ok=True)
        os.chmod(self.racine_bundles, 0o700)
        fichier = self.racine_bundles / f"{alias}-{branche.split('/', 1)[1]}-{tete[:12]}.bundle"
        self.git("bundle", "create", str(fichier), f"refs/heads/{branche}", git_dir=nu, delai_s=DELAI_FETCH_S)
        os.chmod(fichier, 0o600)
        empreinte = hashlib.sha256(fichier.read_bytes()).hexdigest()
        return fichier, empreinte, tete

    # ------------------------------------------------------------------ purge et espace
    def _activite(self, alias: str, nom: str, chemin: Path) -> float | None:
        """Dernière activité d'un worktree : le plus récent des mtime du dossier et de son gitdir (index, HEAD : chaque
        commit du superviseur les touche) ; ``None`` si illisible (jamais purgé alors)."""
        instants = []
        for candidat in (chemin, self.gitdir_du_worktree(alias, nom) / "index",
                         self.gitdir_du_worktree(alias, nom) / "HEAD"):
            try:
                instants.append(os.lstat(candidat).st_mtime)
            except OSError:
                continue
        return max(instants) if instants else None

    def purger(self, *, age_s: float, garder: Iterable[str] = (), maintenant: float | None = None) -> dict[str, int]:
        """Purge de ``[disque] purge_apres_jours`` (relecture de P6 : lu, jamais appliqué ; sur un volume de 5 Go,
        l'exécutant aurait fini par refuser toute carte sous le seuil d'espace libre). Retire les WORKTREES sans activité
        depuis ``age_s`` (leurs BRANCHES sont gardées : une carte reprise recrée son worktree depuis sa branche, où son
        travail est committé) et les bundles plus anciens. Jamais le worktree d'une carte en main (``garder``) ; aucun
        lien n'est suivi (entrées racine, ``lstat``). Rend les nombres retirés."""
        limite = (time.time() if maintenant is None else maintenant) - age_s
        garder = set(garder)
        retires = {"worktrees": 0, "bundles": 0}
        try:
            alias_trouves = sorted(self.racine_espaces.iterdir())
        except OSError:
            alias_trouves = []
        for dossier_alias in alias_trouves:
            if dossier_alias.is_symlink() or not dossier_alias.is_dir() or not ALIAS.fullmatch(dossier_alias.name):
                continue
            for chemin in sorted(dossier_alias.iterdir()):
                nom = chemin.name
                if nom in garder or chemin.is_symlink() or not chemin.is_dir() or \
                        not re.fullmatch(r"[a-z0-9_-]{1,80}", nom):
                    continue
                activite = self._activite(dossier_alias.name, nom, chemin)
                if activite is not None and activite < limite:
                    self.retirer_worktree(dossier_alias.name, nom)
                    retires["worktrees"] += 1
        try:
            bundles = sorted(self.racine_bundles.iterdir())
        except OSError:
            bundles = []
        for fichier in bundles:
            try:
                etat = os.lstat(fichier)
            except OSError:
                continue
            if stat.S_ISREG(etat.st_mode) and fichier.suffix == ".bundle" and etat.st_mtime < limite:
                fichier.unlink(missing_ok=True)
                retires["bundles"] += 1
        return retires

    def retirer_worktree(self, alias: str, nom: str) -> None:
        """Retire le worktree (la BRANCHE reste)."""
        chemin = self.espace(alias, nom)
        self.git("worktree", "remove", "--force", str(chemin), git_dir=self.nu(alias), verifier=False)
        if chemin.exists() and not chemin.is_symlink():
            shutil.rmtree(chemin, ignore_errors=True)
        self.git("worktree", "prune", git_dir=self.nu(alias), verifier=False)


def espace_libre_mio(chemin: Path) -> int | None:
    try:
        etat = os.statvfs(chemin)
    except (OSError, AttributeError):
        try:
            return int(shutil.disk_usage(chemin).free // (1024 * 1024))
        except OSError:
            return None
    return int(etat.f_bavail * etat.f_frsize // (1024 * 1024))


def mode_lien(changement: Changement) -> bool:
    return changement.mode_apres == "120000" and changement.statut != "D"


def mode_gitlink(changement: Changement) -> bool:
    return changement.mode_apres == "160000" and changement.statut != "D"
