"""Plateforme Linux : l'exécutant Railway (cahier P6 § 3.3, § 7.4, § 7.5, § 8.3, § 8.4 et § 11).

**Identités.** Le superviseur tourne en root ; chaque agent sous **son** UID, sans capacité ni nouveau privilège :

| Identité | UID/GID | Groupes | Rôle |
|---|---|---|---|
| ``acp-codex`` | 10001 | 10100 (``acp-travail``) | Codex CLI, propriétaire de ``/donnees/codex`` |
| ``acp-claude`` | 10002 | 10100 | Claude Code, propriétaire de ``/donnees/claude`` |
| ``acp-verif`` | 10003 | 10100 | commandes de vérification, sans aucun identifiant |

Lancement : ``/usr/bin/setpriv --reuid=<uid> --regid=<gid> --groups=10100 --inh-caps=-all --bounding-set=-all
--no-new-privs -- <argv>``, avec un environnement **calculé** passé tel quel (correction du cahier § 3.3 :
``--reset-env`` remplacerait cet environnement par celui du compte et perdrait ``CODEX_HOME``,
``CLAUDE_CONFIG_DIR`` et le jeton de Claude ; sans lui, setpriv transmet exactement l'environnement reçu).

**Secrets** (D92) : fichiers ``/donnees/acp/secrets/{jeton-machine,claude-oauth,github-lecture}``, root, 0600,
écriture atomique ; un fichier d'un autre propriétaire, aux droits plus larges, ou un lien symbolique est refusé.

**Arrêt** (§ 7.5) : SIGTERM au groupe, SIGKILL au groupe après le délai de grâce, puis parcours de
``/proc/*/status`` : tout processus dont un UID vaut celui de l'agent reçoit SIGKILL (au plus 5 passes). Un processus
peut quitter son groupe par ``setsid``, jamais son UID. Vérification finale : plus aucun processus de cet UID ; sinon
l'exécution est suspendue (échec fermé).

Aucune de ces valeurs ne se règle par l'environnement ni par la politique ; les tests construisent des emplacements
sur une racine jetable (:meth:`EmplacementsLinux.de_test`).
"""

from __future__ import annotations

import asyncio
import errno
import os
import platform
import signal
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, ClassVar, Iterable

from ..coffre import CoffreErreur, ecrire_atomiquement

SETPRIV = "/usr/bin/setpriv"
GROUPE_TRAVAIL = 10100
PATH_AGENTS = "/usr/local/bin:/usr/bin:/bin"
TAILLE_SECRET_MAX = 64 * 1024
GRACE_AGENT_S = 20.0
PASSES_UID = 5
SIGKILL = getattr(signal, "SIGKILL", 9)


@dataclass(frozen=True)
class Identite:
    """Compte d'un agent dans le conteneur de l'exécutant."""

    nom: str
    uid: int
    gid: int
    home: PurePosixPath
    groupes: tuple[int, ...] = (GROUPE_TRAVAIL,)


IDENTITES = {
    "acp-codex": Identite("acp-codex", 10001, 10001, PurePosixPath("/home/acp-codex")),
    "acp-claude": Identite("acp-claude", 10002, 10002, PurePosixPath("/home/acp-claude")),
    "acp-verif": Identite("acp-verif", 10003, 10003, PurePosixPath("/home/acp-verif")),
}
UID_AGENTS = tuple(sorted(i.uid for i in IDENTITES.values()))


def identite(nom: str) -> Identite:
    try:
        return IDENTITES[nom]
    except KeyError:
        raise ValueError(f"Identité d'agent inconnue : {nom}.") from None


def prefixe_setpriv(ident: Identite) -> list[str]:
    """argv à placer devant la commande d'un agent (jamais un shell, jamais ``--reset-env``)."""
    return [SETPRIV, f"--reuid={ident.uid}", f"--regid={ident.gid}",
            "--groups=" + ",".join(str(g) for g in ident.groupes), "--inh-caps=-all", "--bounding-set=-all",
            "--no-new-privs", "--"]


class DossierPiege(OSError):
    """Chemin préparé par le superviseur root déjà occupé par un lien, un non-dossier ou un autre propriétaire."""


def preparer_dossier(chemin: Path, *, uid: int, gid: int, mode: int, droits: bool) -> Path:
    """Crée (ou reprend) un dossier pour le superviseur root SANS suivre de lien (relecture de P6) : ``/tmp/acp`` est
    inscriptible par le groupe ``acp-travail``, donc par les trois UID d'agents ; ``mkdir(exist_ok=True)`` puis
    ``chown``/``chmod`` auraient suivi un lien posé par un agent. Le dossier existant doit être un VRAI dossier, à root
    ou à ``uid`` (reprise) ; propriétaire et mode sont posés sur un descripteur ouvert sans suivre de lien.
    ``droits`` faux (tests sans root) : ni propriétaire exigé, ni ``chown``."""
    if not chemin.parent.exists():  # parent absent (tests, premier usage) : rien n'a pu y être posé
        chemin.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(chemin, 0o700)
    except FileExistsError:
        pass
    etat = os.lstat(chemin)
    if stat.S_ISLNK(etat.st_mode) or not stat.S_ISDIR(etat.st_mode):
        raise DossierPiege(errno.ELOOP, f"{chemin.name} n'est pas un dossier ordinaire (lien ou fichier)")
    if droits and etat.st_uid not in (0, uid):
        raise DossierPiege(errno.EPERM, f"{chemin.name} appartient à un autre compte (UID {etat.st_uid})")
    drapeaux = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if not hasattr(os, "fchown"):  # Windows (tests seulement)
        os.chmod(chemin, mode)
        return chemin
    descripteur = os.open(chemin, drapeaux)
    try:
        if not stat.S_ISDIR(os.fstat(descripteur).st_mode):
            raise DossierPiege(errno.ENOTDIR, f"{chemin.name} n'est pas un dossier")
        if droits:
            os.fchown(descripteur, uid, gid)
        os.fchmod(descripteur, mode)
    finally:
        os.close(descripteur)
    return chemin


def lire_fichier_agent(chemin: Path, *, uid: int | None, maximum: int) -> bytes | None:
    """Lit AU PLUS ``maximum`` octets d'un fichier écrit par un agent (``reponse.json`` de Codex), sans suivre de lien :
    fichier ordinaire exigé, appartenant à ``uid`` (si donné) ; ``None`` sinon (absent, lien, tube, autre
    propriétaire). Ouvert en non bloquant (un tube nommé posé à sa place ne bloque pas le superviseur)."""
    drapeaux = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descripteur = os.open(chemin, drapeaux)
    except OSError:
        return None
    try:
        etat = os.fstat(descripteur)
        if not stat.S_ISREG(etat.st_mode) or (uid is not None and etat.st_uid != uid):
            return None
        morceaux, total = [], 0
        while total < maximum:
            morceau = os.read(descripteur, min(65536, maximum - total))
            if not morceau:
                break
            morceaux.append(morceau)
            total += len(morceau)
        return b"".join(morceaux)
    finally:
        os.close(descripteur)


def environnement_agent(ident: Identite, *, tmpdir: Path | None = None, **variables: str) -> dict[str, str]:
    """Environnement calculé d'un agent : ``HOME``, ``PATH`` minimal, ``LANG``, ``TMPDIR``, puis les seules
    variables de l'outil (``variables``). Rien n'est hérité du superviseur."""
    env = {"HOME": str(ident.home), "PATH": PATH_AGENTS, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if tmpdir is not None:
        env["TMPDIR"] = Path(tmpdir).as_posix()
    env.update({cle: str(valeur) for cle, valeur in variables.items()})
    return env


# ============================================================ emplacements


@dataclass(frozen=True)
class EmplacementsLinux:
    """Emplacements de l'exécutant (cahier P6 § 8.4). Mêmes noms de propriétés que les emplacements Windows quand le
    rôle est le même (``politique``, ``secrets``, ``etat``, ``journal``, verrous…), plus ceux de l'exécution."""

    plateforme: ClassVar[str] = "linux"
    donnees: Path = Path("/donnees")
    fichier_politique: Path = Path("/etc/acp/executant.toml")
    outils: Path = Path("/opt/acp/outils")
    tmp: Path = Path("/tmp/acp")

    # ---------------------------------------------------------------- politique et outils (image)
    @property
    def politique(self) -> Path:
        return self.fichier_politique

    @property
    def codex_par_defaut(self) -> Path:
        return self.outils / "codex" / "codex"

    @property
    def claude_par_defaut(self) -> Path:
        return self.outils / "claude" / "claude"

    # ---------------------------------------------------------------- /donnees/acp (root, 0700)
    @property
    def acp(self) -> Path:
        return self.donnees / "acp"

    @property
    def acp_local(self) -> Path:
        """Dossier propre au poste (même rôle que ``%LOCALAPPDATA%\\ACP`` sous Windows)."""
        return self.acp

    @property
    def secrets(self) -> Path:
        return self.acp / "secrets"

    @property
    def etat(self) -> Path:
        return self.acp / "etat"

    @property
    def journal(self) -> Path:
        return self.acp / "journal"

    @property
    def preuves(self) -> Path:
        return self.acp / "preuves"

    @property
    def sortie(self) -> Path:
        return self.acp / "sortie"

    @property
    def sortie_refusees(self) -> Path:
        return self.sortie / "refusees"

    @property
    def verrous(self) -> Path:
        return self.acp / "verrous"

    @property
    def bundles(self) -> Path:
        return self.acp / "bundles"

    @property
    def verrou_instance(self) -> Path:
        return self.verrous / "poste.verrou"

    @property
    def verrou_sondes(self) -> Path:
        return self.verrous / "sondes.verrou"

    @property
    def verrou_codex(self) -> Path:
        """Partagé par les sondes Codex et ``codex exec`` : un seul processus Codex à la fois (cahier P6 § 2.1)."""
        return self.verrous / "codex.lock"

    @property
    def verrou_claude(self) -> Path:
        return self.verrous / "claude.lock"

    @property
    def machine(self) -> Path:
        return self.etat / "machine.json"

    @property
    def etat_service(self) -> Path:
        return self.etat / "service.json"

    @property
    def dernier_inventaire(self) -> Path:
        return self.etat / "dernier-inventaire.json"

    @property
    def carte(self) -> Path:
        """Carte en main (reprise après un redémarrage ou un OOM, § 6.4)."""
        return self.etat / "carte.json"

    @property
    def pause_locale(self) -> Path:
        return self.etat / "pause-locale"

    @property
    def sonde_isolement(self) -> Path:
        return self.etat / "isolement.json"

    @property
    def quotas_claude(self) -> Path:
        """Dernier ``rate_limit_event`` observé (source ``claude_code_rate_limit_event``)."""
        return self.etat / "quotas-claude.json"

    @property
    def compteurs(self) -> Path:
        """Cartes et heures d'agent du jour (garde de budget, D85)."""
        return self.etat / "compteurs.json"

    @property
    def sessions(self) -> Path:
        """Identifiants de session locaux par carte (reprise du fil)."""
        return self.etat / "sessions"

    def catalogue_embarque(self, version: str) -> Path:
        return self.etat / f"catalogue-embarque-{version}.json"

    # ---------------------------------------------------------------- agents et dépôts
    @property
    def codex_home(self) -> Path:
        return self.donnees / "codex"

    @property
    def claude_config(self) -> Path:
        return self.donnees / "claude"

    @property
    def depots(self) -> Path:
        return self.donnees / "depots"

    @property
    def espaces(self) -> Path:
        return self.donnees / "espaces"

    # ---------------------------------------------------------------- construction
    @classmethod
    def de_test(cls, racine: Path) -> "EmplacementsLinux":
        """Racine jetable (tests) : jamais les vrais dossiers de l'exécutant."""
        racine = Path(racine)
        return cls(donnees=racine / "donnees", fichier_politique=racine / "etc" / "acp" / "executant.toml",
                   outils=racine / "opt" / "acp" / "outils", tmp=racine / "tmp" / "acp")

    def sous(self, racine: Path) -> bool:
        base = Path(os.path.realpath(racine))
        for chemin in (self.donnees, self.fichier_politique, self.outils, self.tmp):
            reel = Path(os.path.realpath(chemin))
            if reel != base and base not in reel.parents:
                return False
        return True


# ============================================================ coffre en fichiers 0600


USAGES_FICHIERS = {
    "jeton-machine": "jeton-machine",
    "jeton-claude": "claude-oauth",
    "jeton-github": "github-lecture",
}


class CoffreFichiers:
    """Secrets de l'exécutant en fichiers 0600 du compte courant (root en production), un fichier par usage.

    Écriture atomique (temporaire du même dossier, ``fsync``, ``os.replace``) ; lecture sans suivre de lien
    symbolique, refusée si le fichier n'appartient pas au compte courant ou s'il est lisible par d'autres."""

    def __init__(self, dossier: Path, *, proprietaire: int | None = None) -> None:
        self.dossier = Path(dossier)
        self.proprietaire = os.geteuid() if proprietaire is None else proprietaire

    def _fichier(self, usage: str) -> Path:
        try:
            return self.dossier / USAGES_FICHIERS[usage]
        except KeyError:
            raise CoffreErreur(f"Usage du coffre inconnu : {usage}.") from None

    def _dossier_pret(self) -> None:
        self.dossier.mkdir(mode=0o700, parents=True, exist_ok=True)
        etat = os.lstat(self.dossier)
        if not stat.S_ISDIR(etat.st_mode) or etat.st_uid != self.proprietaire or etat.st_mode & 0o077:
            raise CoffreErreur("Dossier des secrets de l'exécutant aux droits trop larges ou d'un autre propriétaire "
                               "(attendu : root, 0700) : aucun secret n'est écrit ni lu.")

    def ecrire(self, usage: str, valeur: str) -> None:
        fichier = self._fichier(usage)
        if not isinstance(valeur, str) or not valeur or len(valeur.encode("utf-8")) > TAILLE_SECRET_MAX:
            raise CoffreErreur("Secret vide ou démesuré refusé par le coffre.")
        self._dossier_pret()
        ecrire_atomiquement(fichier, valeur.encode("utf-8"))
        os.chmod(fichier, 0o600)

    def lire(self, usage: str) -> str | None:
        fichier = self._fichier(usage)
        try:
            descripteur = os.open(fichier, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise CoffreErreur(f"Secret « {fichier.name} » : lien symbolique refusé.") from None
            raise CoffreErreur(f"Secret « {fichier.name} » illisible par le superviseur.") from None
        with os.fdopen(descripteur, "rb") as flux:
            etat = os.fstat(flux.fileno())
            if not stat.S_ISREG(etat.st_mode):
                raise CoffreErreur(f"Secret « {fichier.name} » : fichier ordinaire attendu.")
            if etat.st_uid != self.proprietaire or etat.st_mode & 0o077:
                raise CoffreErreur(f"Secret « {fichier.name} » d'un autre propriétaire ou lisible par d'autres "
                                   "(attendu : root, 0600) : refusé ; redéposez-le par « acp-poste connexion ».")
            contenu = flux.read(TAILLE_SECRET_MAX + 1)
        if len(contenu) > TAILLE_SECRET_MAX:
            raise CoffreErreur(f"Secret « {fichier.name} » démesuré : refusé.")
        try:
            texte = contenu.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise CoffreErreur(f"Secret « {fichier.name} » illisible (UTF-8 attendu).") from None
        return texte or None

    def effacer(self, usage: str) -> bool:
        try:
            self._fichier(usage).unlink()
            return True
        except FileNotFoundError:
            return False

    def present(self, usage: str) -> bool:
        return self._fichier(usage).is_file()

    def premiere_vue(self, usage: str) -> float | None:
        """Instant de dernière écriture (mtime) du secret, pour l'alerte d'expiration du jeton Claude (J-30)."""
        try:
            return os.lstat(self._fichier(usage)).st_mtime
        except OSError:
            return None


# ============================================================ processus d'un UID


def _uids_du_statut(texte: str) -> set[int]:
    """UID d'un processus VIVANT d'après ``/proc/<pid>/status`` ; un zombie (``Z``) ou un mort (``X``) n'exécute plus
    rien et n'attend que d'être recueilli (par ``tini`` dans l'image) : il ne compte pas."""
    uids: set[int] = set()
    for ligne in texte.splitlines():
        if ligne.startswith("State:") and ligne.split()[1:2] in (["Z"], ["X"]):
            return set()
        if ligne.startswith("Uid:"):
            try:
                uids = {int(x) for x in ligne.split()[1:5]}
            except ValueError:
                return set()
    return uids


def processus_de_l_uid(uid: int, *, proc: Path = Path("/proc")) -> list[int]:
    """PID de tous les processus dont un UID (réel, effectif, sauvé ou système de fichiers) vaut ``uid``."""
    trouves = []
    try:
        entrees = list(os.scandir(proc))
    except OSError:
        return trouves
    for entree in entrees:
        if not entree.name.isdigit():
            continue
        try:
            texte = (Path(entree.path) / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if uid in _uids_du_statut(texte):
            trouves.append(int(entree.name))
    return trouves


@dataclass
class ArretUid:
    """Balayage par UID (§ 7.5, points 3 et 4). ``lister`` et ``tuer`` sont injectables pour les tests."""

    uid: int
    lister: Callable[[int], Iterable[int]] = processus_de_l_uid
    tuer: Callable[[int, int], None] = os.kill
    passes: int = PASSES_UID
    pause_s: float = 0.1
    tues: list[int] = field(default_factory=list)

    def executer(self) -> bool:
        """``True`` si plus aucun processus de l'UID ne reste après au plus ``passes`` passes."""
        if self.uid < 10000:
            raise ValueError("Balayage refusé : seul l'UID dédié d'un agent (10000 ou plus) peut être balayé.")
        for _ in range(self.passes):
            restants = [p for p in self.lister(self.uid) if p != os.getpid()]
            if not restants:
                return True
            for pid in restants:
                try:
                    self.tuer(pid, SIGKILL)
                    self.tues.append(pid)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    pass
            time.sleep(self.pause_s)
        return not [p for p in self.lister(self.uid) if p != os.getpid()]


SURVIVANT = ("Processus de l'agent impossibles à arrêter : exécution suspendue jusqu'au redémarrage de l'exécutant.")


async def arreter_agent(processus: Any, uid: int, *, grace_s: float = GRACE_AGENT_S,
                        balayage: ArretUid | None = None) -> bool:
    """Arrêt complet d'un agent lancé par ``spawn_fenced_process`` sous ``uid`` : groupe (SIGTERM, grâce, SIGKILL),
    puis balayage par UID. ``True`` seulement si plus rien de cet UID ne tourne."""
    from ..local_runner import terminate_process_tree

    # Le verdict du groupe seul ne suffit pas (un descendant a pu quitter le groupe par setsid) : seul le balayage
    # par UID conclut.
    await terminate_process_tree(processus, grace_s)
    arret = balayage or ArretUid(uid)
    return bool(await asyncio.to_thread(arret.executer))


# ============================================================ plateforme


def _os_release(chemin: Path = Path("/etc/os-release")) -> str | None:
    try:
        for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
            if ligne.startswith("PRETTY_NAME="):
                return ligne.split("=", 1)[1].strip().strip('"')[:80] or None
    except OSError:
        return None
    return None


class PlateformeLinux:
    nom = "linux"

    def __init__(self, environnement: dict[str, str] | None = None) -> None:
        self._environnement = os.environ if environnement is None else environnement

    def emplacements(self) -> EmplacementsLinux:
        return EmplacementsLinux()

    def coffre(self, emplacements: EmplacementsLinux) -> CoffreFichiers:
        return CoffreFichiers(emplacements.secrets)

    def hote(self) -> str:
        """« railway » si Railway a posé ``RAILWAY_SERVICE_ID`` (sa VALEUR n'est jamais lue ni publiée), sinon « pc »."""
        return "railway" if "RAILWAY_SERVICE_ID" in self._environnement else "pc"

    def infos(self) -> dict[str, Any]:
        noyau = platform.release().split()[0] if platform.release() else None
        return {"plateforme": "linux", "hote": self.hote(), "noyau": noyau, "windows": None}

    def distribution(self) -> str | None:
        return _os_release()
