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
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

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


class ErreurDepot(RuntimeError):
    """Opération git refusée ou en échec (message français, sans URL ni jeton)."""


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

    def branche_existe(self, alias: str, branche: str) -> bool:
        return self.sha(self.nu(alias), f"refs/heads/{branche}") is not None

    # ------------------------------------------------------------------ worktree d'une carte
    def worktree(self, depot: Any, nom: str, branche: str, depart: str, *, liens_symboliques: bool = False) -> Path:
        """Worktree ``espaces/<alias>/<nom>`` sur la branche ``branche``, créée depuis ``depart`` ; gardé s'il existe
        (reprise). ``depart`` : branche locale d'une carte parente (``hermes/<carte>``) ou ``origin/<base>``."""
        if not (BRANCHE_CARTE.fullmatch(branche) or BRANCHE_PROJET.fullmatch(branche)):
            raise ErreurDepot("Branche d'une carte refusée (hermes/<carte> ou hermes/projet-<slug> attendu).")
        if not branche_git_valide(depart.removeprefix("origin/")):
            raise ErreurDepot("Branche de départ refusée.")
        nu = self.nu(depot.alias)
        chemin = self.espace(depot.alias, nom)
        gitdir = self.gitdir_du_worktree(depot.alias, nom)
        if chemin.exists() and gitdir.is_dir():
            return chemin
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
