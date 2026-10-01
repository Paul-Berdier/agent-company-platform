"""Une carte dans l'exécutant (cahier P6 § 6) : ``preparer → lancer → verifier → committer → controler → emettre``.

1. **Contrôle** de la carte contre la politique de l'IMAGE (jamais contre Hermes) : dépôt connu, voie ouverte
   (régime, conditions D83/D84, garde de quota), modèle, effort et palier permis, Codex sur dépôt privé seulement
   (D83). Écart : ``bloquer`` (``politique`` ou ``capacite``), rien n'est lancé.
2. **Préparation** (superviseur, root) : clone nu et ``fetch`` en lecture seule, worktree et branche
   ``hermes/<carte>`` depuis la branche de la carte parente ou ``origin/<base>`` (gardé à la reprise), dossiers de la
   tentative sous ``/tmp/acp/<carte>`` à l'UID de chaque agent, diff de la carte relue pour Claude (qui n'a pas de
   shell), puis l'étape ``preparation`` du dépôt sous ``acp-verif`` (réseau ouvert, hors bac à sable), seulement si la
   vérification pourra tourner.
3. **Agent** sous son UID (``codex exec`` ou ``claude -p``, options imposées, consigne par l'entrée standard),
   ``battement`` toutes les 60 s avec une note composée ici (jamais une sortie brute), chien de garde de la durée,
   verrou de l'outil (un seul processus Codex à la fois). ``valide: false`` → arrêt, commit « wip », ``reprendre`` ;
   ``annuler: true`` ou arrêt du service → arrêt, commit « wip », ``arret``. Claude : modèle servi contrôlé contre la
   résolution documentée de l'alias (sinon arrêt et ``bloquer(capacite)``), outils d'exécution refusés, chaque
   ``rate_limit_event`` noté (garde de quota) ; limite atteinte → ``bloquer(quota)``. Deux arrêts mémoire (137) →
   ``bloquer(memoire)``.
4. **Vérification** (implémentation, correction, intégration) sous ``acp-verif`` : régime A dans
   ``codex sandbox -P acp_verif`` (réseau coupé) ; régime B seulement si le dépôt porte
   ``verification_sans_bac_a_sable = true`` (réseau ouvert), sinon « non exécutée » (la CI reste juge). Échec : reprise
   du fil avec la fin de la sortie, au plus ``reprises_verification`` fois ; au-delà, ``terminer`` avec
   ``verification.etat = "echouee"`` et un résumé qui le dit. Aucun succès simulé.
5. **Commit** local par le superviseur (aucun crochet, aucun trailer) ; **contrôles** : fichiers de pilotage (→ revue),
   balayage des secrets (→ branche ``quarantaine/<carte>`` et ``bloquer(secret)``, rien du contenu n'est envoyé).
6. **Issue** par la file de sortie : ``terminer``, ``question`` ou ``bloquer``. Le dossier de la carte repasse en
   ``0700 root:root`` hors de son tour. **Aucun push.**

L'état de la carte en main est gardé dans ``/donnees/acp/etat/carte.json`` (reprise après un redémarrage ou un arrêt
mémoire) ; la session locale de chaque carte (reprise du fil) et sa base dans ``etat/sessions/<carte>.json``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from acp_poste_contrat.machine import DemandeCarte

from . import pilotage
from .balayage import RAISON_SECRET, secret_dans, valeurs_exactes
from .catalogue_claude import TABLE as TABLE_CLAUDE
from .coffre import ecrire_atomiquement
from .commandes_agents import ROLES_LECTURE, commande_claude, commande_codex, schema_json
from .depots import Depots, ErreurDepot
from .evenements import SortieInvalide, lire_flux_claude, lire_flux_codex, sortie_claude, valider_sortie
from .garde_quota import Budget, QuotasClaude, codex_ouverte
from .journal import masquer
from .local_runner import FencedSpawnError, spawn_fenced_process, terminate_process_tree
from .protocole import HermesIndisponible, HorsContrat, JetonRefuse, Refus, TropFrequent
from .sonde_plateforme import PROFIL, profil_codex_toml
from .sortie import FileSortie, nouvel_id_envoi
from .verrou import Verrou, VerrouOccupe

INTERVALLE_BATTEMENT_S = 60.0
GRACE_S = 20.0
SORTIE_VERIF_MAX = 8 * 1024
STDERR_MAX = 64 * 1024
CODE_OOM = 137
QUOTA_SANS_REMISE = timedelta(hours=1)
VOIE_OUTIL = {"poste-codex": "codex", "poste-claude": "claude"}
IDENTITE_OUTIL = {"codex": "acp-codex", "claude": "acp-claude"}
VERIF_NON_EXECUTEE = ("Vérification non exécutée : bac à sable indisponible sur l'exécutant ; la CI du dépôt reste "
                      "juge.")
CONSIGNE = """Tu es l'agent « {role} » d'ACP pour la carte {carte} (projet {projet}), dans le dépôt « {alias} », sur la \
branche {branche}.
Règles de l'exécutant : travaille seulement dans ce dossier ; ne fais ni commit ni push (l'exécutant committe pour \
toi) ; ne modifie aucun fichier de pilotage des agents (CLAUDE.md, AGENTS.md, .claude/, .codex/, .github/, \
.gitattributes…) sans le dire dans ton résumé : la carte passerait en revue ; n'écris aucun secret.
Termine par l'objet JSON imposé : « issue » vaut « termine » (travail fini : « resume » dit ce qui a été fait), \
« question » (il te manque une décision : pose-la dans « question ») ou « echec » (impossible : dis pourquoi)."""
CONSIGNE_RELECTURE = ("Tu RELIS la carte {relue} : son diff est dans {lecture}/diff.patch (lecture seule). Rends le "
                      "verdict « accepte » ou « corrections » ; avec « corrections », la consigne de correction va "
                      "dans « corrections ».")
CONSIGNE_EXPLORATION = "Lecture seule : explore et décris le dépôt pour la planification ; ne modifie rien."
SUITE_VERIF = ("La vérification a échoué (code {code}). Fin de la sortie :\n{fin}\nCorrige puis termine par l'objet "
               "JSON imposé.")
SUITE_REPRISE = "Reprise de la carte {carte}.{reponses}\nTermine par l'objet JSON imposé."


class CarteRefusee(Exception):
    """Carte non exécutable : ``genre`` et ``raison`` du blocage (français, composé ici)."""

    def __init__(self, genre: str, raison: str, *, reprise_le: datetime | None = None) -> None:
        super().__init__(raison)
        self.genre = genre
        self.raison = raison[:500]
        self.reprise_le = reprise_le


class AgentSurvivant(RuntimeError):
    """Des processus de l'agent restent après l'arrêt : l'exécution est suspendue jusqu'au redémarrage (§ 7.5)."""


class Interruption(Exception):
    """Agent arrêté en cours de route : ``route`` (``reprendre`` ou ``arret``) et son ``motif``."""

    def __init__(self, route: str, motif: str) -> None:
        super().__init__(motif)
        self.route = route
        self.motif = motif


@dataclass
class IssueCarte:
    route: str
    corps: dict[str, Any]
    reponse: Any = None
    envoyee: bool = False


@dataclass
class ResultatAgent:
    code: int | None
    sortie: Any = None
    session: str | None = None
    modele_servi: str | None = None
    jetons: dict[str, int | None] | None = None
    erreur: str | None = None
    limite_atteinte: bool = False
    remise: datetime | None = None
    duree_s: float = 0.0


@dataclass
class LanceurAgents:
    """Lancement et arrêt des processus d'agents. Production Linux : ``setpriv`` vers l'UID de l'identité et arrêt
    par groupe puis par UID (:func:`acp_poste.plateforme.linux.arreter_agent`) ; ``identites`` vide (tests sans
    root) : les faux CLI tournent sous le compte du test, arrêt de l'arbre seulement."""

    identites: dict[str, Any] = field(default_factory=dict)
    droits: bool = False

    def prefixe(self, nom: str) -> list[str]:
        if nom not in self.identites:
            return []
        from .plateforme.linux import prefixe_setpriv

        return prefixe_setpriv(self.identites[nom])

    def home(self, nom: str) -> str:
        identite = self.identites.get(nom)
        return str(identite.home) if identite is not None else "/nonexistent"

    async def arreter(self, processus: Any, nom: str, grace_s: float) -> bool:
        if nom in self.identites:
            from .plateforme.linux import arreter_agent

            return await arreter_agent(processus, self.identites[nom].uid, grace_s=grace_s)
        return await terminate_process_tree(processus, grace_s)

    def dossier(self, chemin: Path, nom: str | None, mode: int) -> Path:
        """Dossier de la tentative, à l'UID de l'identité ``nom`` (root si ``None``), groupe ``acp-travail``."""
        chemin.mkdir(parents=True, exist_ok=True)
        if self.droits:
            identite = self.identites.get(nom) if nom else None
            os.chown(chemin, identite.uid if identite else 0, 10100)
        os.chmod(chemin, mode)
        return chemin


@dataclass
class Execution:
    politique: Any
    emplacements: Any
    depots: Depots
    coffre: Any
    journal: Any
    sortie: FileSortie
    envoyer: Callable[[str, dict[str, Any]], Any]
    lanceur: LanceurAgents
    isolement: dict[str, Any]
    quotas_claude: QuotasClaude
    budget: Budget
    executables: dict[str, list[str]] = field(default_factory=dict)
    intervalle_battement_s: float = INTERVALLE_BATTEMENT_S
    grace_s: float = GRACE_S
    horloge: Callable[[], datetime] = lambda: datetime.now(UTC)
    compteurs_codex: Callable[[], list[dict[str, Any]] | None] = lambda: None

    # ================================================================== état persistant
    def _ecrire_json(self, chemin: Path, donnees: dict[str, Any]) -> None:
        ecrire_atomiquement(chemin, json.dumps(donnees, ensure_ascii=False).encode("utf-8"))

    def _lire_json(self, chemin: Path) -> dict[str, Any] | None:
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return donnees if isinstance(donnees, dict) else None

    def session(self, carte: str) -> dict[str, Any]:
        return self._lire_json(self.emplacements.sessions / f"{carte}.json") or {}

    def _noter_session(self, carte: str, **valeurs: Any) -> None:
        donnees = self.session(carte)
        donnees.update({k: v for k, v in valeurs.items() if v is not None})
        self._ecrire_json(self.emplacements.sessions / f"{carte}.json", donnees)

    def carte_en_main(self) -> dict[str, Any] | None:
        return self._lire_json(self.emplacements.carte)

    def _noter_carte(self, demande: DemandeCarte, etape: str, **valeurs: Any) -> None:
        etat = self.carte_en_main() or {}
        if etat.get("carte") != demande.carte or etat.get("run_id") != demande.run_id:
            etat = {"tableau": demande.tableau, "carte": demande.carte, "run_id": demande.run_id,
                    "voie": demande.voie, "role": demande.role, "depot_alias": demande.depot_alias,
                    "oom": self.session(demande.carte).get("oom", 0), "debut": self.horloge().isoformat()}
        etat.update(etape=etape, **valeurs)
        self._ecrire_json(self.emplacements.carte, etat)

    def oublier_carte(self) -> None:
        try:
            self.emplacements.carte.unlink()
        except FileNotFoundError:
            pass

    # ================================================================== issues
    def _base(self, demande: DemandeCarte) -> dict[str, Any]:
        return {"id_envoi": nouvel_id_envoi(), "tableau": demande.tableau, "carte": demande.carte,
                "run_id": demande.run_id}

    def emettre(self, route: str, corps: dict[str, Any]) -> IssueCarte:
        """Dépôt dans la file de sortie, PUIS envoi ; un refus transitoire laisse la requête en file (le service la
        rejoue avant toute réclamation)."""
        fichier = self.sortie.deposer(route, corps)
        try:
            resultat = self.sortie.envoyer(fichier, self.envoyer)
        except (HermesIndisponible, TropFrequent, JetonRefuse, HorsContrat) as exc:
            self.journal.ecrire("avertissement", "issue_en_file", f"Issue « {route} » gardée dans la file de sortie : "
                                f"{exc.message}", carte=corps.get("carte"))
            return IssueCarte(route, corps)
        except Refus as exc:
            self.journal.ecrire("avertissement", "issue_en_file", f"Issue « {route} » gardée dans la file de sortie : "
                                f"{exc.message}", carte=corps.get("carte"))
            return IssueCarte(route, corps)
        if resultat is None:
            return IssueCarte(route, corps)
        if resultat.refus is not None:
            self.journal.ecrire("erreur", "issue_refusee", f"Issue « {route} » refusée par Hermes : "
                                f"{resultat.refus.message}", carte=corps.get("carte"), code=resultat.refus.code)
            return IssueCarte(route, corps, envoyee=True)
        self.journal.ecrire("info", "issue", f"Issue « {route} » reçue par Hermes.", carte=corps.get("carte"))
        return IssueCarte(route, corps, reponse=resultat.reponse, envoyee=True)

    def bloquer(self, demande: DemandeCarte, genre: str, raison: str, reprise_le: datetime | None = None) -> IssueCarte:
        corps = dict(self._base(demande), genre=genre, raison=raison[:500])
        if reprise_le is not None and genre == "quota":
            corps["reprise_le"] = reprise_le.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.emettre("bloquer", corps)

    # ================================================================== contrôle de la carte (§ 6.1)
    def voies_ouvertes(self) -> dict[str, str | None]:
        """Voie → ``None`` si ouverte, sinon la raison (française) de sa fermeture."""
        fermetures: dict[str, str | None] = {}
        ecriture = self.isolement.get("ecriture_admise") or {}
        for voie, outil in VOIE_OUTIL.items():
            raison = None
            section = getattr(self.politique, outil)
            if outil not in self.politique.politique.executants or section is None:
                raison = f"{outil} absent de la politique de l'exécutant."
            elif self.politique.conditions.get(outil) is None:
                raison = f"Conditions d'usage de {outil} non décidées (D83/D84) : voie fermée."
            elif not ecriture.get(outil):
                raison = self.isolement.get("raison") or f"Écriture de {outil} non admise par l'isolement mesuré."
            elif outil == "codex":
                ouverte, raison_quota = codex_ouverte(self.compteurs_codex())
                raison = None if ouverte else raison_quota
            else:
                ouverte, raison_quota, _remise = self.quotas_claude.ouverte(self.horloge())
                raison = None if ouverte else raison_quota
            fermetures[voie] = raison
        fermetures["poste-integration"] = None if (self.isolement.get("uid_separes") is True) else \
            "Identifiants séparés par UID non prouvés : aucune écriture."
        return fermetures

    def controler(self, demande: DemandeCarte) -> Any:
        """Dépôt de la politique, ou :class:`CarteRefusee`."""
        depot = self.politique.depot(demande.depot_alias)
        if depot is None:
            raise CarteRefusee("politique", f"Dépôt « {demande.depot_alias} » absent de la politique de l'exécutant "
                                            "(executant.toml) : carte refusée.")
        raison = self.voies_ouvertes().get(demande.voie)
        if raison:
            raise CarteRefusee("capacite", f"Voie {demande.voie} fermée sur l'exécutant : {raison}")
        if demande.role == "integration":
            return depot
        outil = VOIE_OUTIL[demande.voie]
        regles = self.politique.politique
        if outil == "codex":
            if depot.acces == "public":
                raise CarteRefusee("politique", "Voie Codex fermée pour un dépôt public (D83 : dépôts privés "
                                                "seulement avec le compte ChatGPT).")
            permis = self.politique.codex.modeles_permis
            if permis and demande.modele not in permis:
                raise CarteRefusee("capacite", f"Modèle Codex {demande.modele} hors de la politique de l'exécutant.")
        elif demande.modele not in self.politique.claude.alias_permis and demande.modele not in {
                r for _a, r, _e, _d in TABLE_CLAUDE if r and _a in self.politique.claude.alias_permis}:
            raise CarteRefusee("capacite", f"Modèle Claude {demande.modele} hors de la politique de l'exécutant.")
        if demande.effort and demande.effort in regles.efforts_interdits:
            raise CarteRefusee("capacite", f"Effort {demande.effort} interdit par la politique de l'exécutant.")
        if (demande.palier or "default") not in regles.paliers_admis:
            raise CarteRefusee("capacite", f"Palier {demande.palier} refusé par la politique de l'exécutant.")
        return depot

    # ================================================================== exécution d'une carte
    async def executer(self, demande: DemandeCarte, arret: asyncio.Event | None = None) -> IssueCarte:
        arret = arret or asyncio.Event()
        debut = time.monotonic()
        try:
            depot = self.controler(demande)
        except CarteRefusee as exc:
            self.journal.ecrire("avertissement", "carte_refusee", exc.raison, carte=demande.carte)
            return self.bloquer(demande, exc.genre, exc.raison)
        self._noter_carte(demande, "preparation")
        nom = demande.branche.removeprefix("hermes/")
        try:
            issue = await self._executer(demande, depot, nom, arret)
        except CarteRefusee as exc:
            self._commit_wip(demande, depot, nom, "wip: blocage")
            issue = self.bloquer(demande, exc.genre, exc.raison, exc.reprise_le)
        except Interruption as exc:
            self._commit_wip(demande, depot, nom, f"wip: {exc.motif}")
            corps = dict(self._base(demande), motif=exc.motif)
            issue = self.emettre(exc.route, corps)
        except ErreurDepot as exc:
            issue = self.bloquer(demande, "capacite", f"Opération git en échec sur l'exécutant : {exc}")
        finally:
            try:
                self.depots.fermer_tour(self.depots.espace(demande.depot_alias, nom))
            except (OSError, ErreurDepot):
                pass
            shutil.rmtree(self._tmp(demande), ignore_errors=True)
        if issue.route in ("terminer", "question", "bloquer"):
            self.budget.compter(carte=True, maintenant=self.horloge())
            self.oublier_carte()
        self.journal.ecrire("info", "carte_finie", f"Carte finie localement : {issue.route}.", carte=demande.carte,
                            duree_s=round(time.monotonic() - debut))
        return issue

    def _tmp(self, demande: DemandeCarte) -> Path:
        return Path(self.emplacements.tmp) / demande.carte

    def _commit_wip(self, demande: DemandeCarte, depot: Any, nom: str, message: str) -> str | None:
        try:
            if not self.depots.gitdir_du_worktree(depot.alias, nom).is_dir():
                return None
            return self.depots.committer(depot.alias, nom, f"{message} ({demande.carte})")
        except ErreurDepot as exc:
            self.journal.ecrire("erreur", "wip_impossible", f"Commit « wip » impossible : {exc}", carte=demande.carte)
            return None

    def _verification_possible(self, depot: Any) -> str | None:
        """``None`` si la vérification peut tourner, sinon la raison de « non exécutée »."""
        if self.isolement.get("regime") == "A":
            return None
        if depot.verification_sans_bac_a_sable:
            return None
        return VERIF_NON_EXECUTEE

    async def _executer(self, demande: DemandeCarte, depot: Any, nom: str, arret: asyncio.Event) -> IssueCarte:
        await asyncio.to_thread(self.depots.recuperer, depot)
        base_ref = f"origin/{depot.branche_base}"
        depart = demande.branche_depart or base_ref
        if demande.branche_depart and not self.depots.branche_existe(depot.alias, demande.branche_depart):
            raise CarteRefusee("politique", f"Branche de départ {demande.branche_depart} absente de l'exécutant : "
                                            "carte non préparée.")
        connue = self.session(demande.carte)
        liens = depot.liens_symboliques and self.isolement.get("regime") == "A"
        chemin = await asyncio.to_thread(self.depots.worktree, depot, nom, demande.branche, depart,
                                         liens_symboliques=liens)
        base = connue.get("base") or self.depots.sha(self.depots.nu(depot.alias),
                                                     f"refs/remotes/{depart}" if depart.startswith("origin/")
                                                     else f"refs/heads/{depart}")
        self._noter_session(demande.carte, base=base)
        self.depots.ouvrir_tour(chemin)
        tmp = self.lanceur.dossier(self._tmp(demande), None, 0o751)

        if demande.role == "integration":
            return await self._integrer(demande, depot, nom, chemin, base, tmp, arret)

        outil = VOIE_OUTIL[demande.voie]
        verification_raison = None if demande.role not in ROLES_LECTURE else "Lecture seule : aucune vérification."
        if verification_raison is None:
            verification_raison = self._verification_possible(depot)
        if verification_raison is None and depot.preparation and not connue.get("prepare"):
            self._noter_carte(demande, "preparation_dependances")
            code, _fin = await self._commande_verif(demande, depot, chemin, tmp, depot.preparation, bac=False,
                                                    reseau=True)
            self._noter_session(demande.carte, prepare=True)
            self.journal.ecrire("info", "preparation", f"Préparation des dépendances : code {code}.",
                                carte=demande.carte)
        lecture = self.lanceur.dossier(tmp / "lecture", None, 0o750)
        if demande.role == "relecture" and demande.carte_relue:
            relue = self.session(demande.carte_relue)
            branche_relue = f"hermes/{demande.carte_relue}"
            tete_relue = self.depots.sha(self.depots.nu(depot.alias), f"refs/heads/{branche_relue}")
            base_relue = relue.get("base") or self.depots.sha(self.depots.nu(depot.alias), f"refs/remotes/{base_ref}")
            if tete_relue and base_relue:
                diff = self.depots.diff_texte(depot.alias, nom, base_relue, tete_relue)
                (lecture / "diff.patch").write_text(diff, encoding="utf-8")
                os.chmod(lecture / "diff.patch", 0o640)

        consigne = self._consigne(demande, lecture)
        session = connue.get("session") if demande.reprise else None
        if session:
            consigne = SUITE_REPRISE.format(carte=demande.carte, reponses=self._texte_reponses(demande) or "")
        tentatives = 0
        verification: dict[str, Any] = {"etat": "non_executee", "raison": verification_raison or "Non lancée.",
                                        "tentatives": 0}
        jetons_total: dict[str, int | None] = {"entree": None, "sortie": None, "cache": None}
        modele_servi = None
        while True:
            self._noter_carte(demande, "agent", tentative=tentatives)
            resultat = await self._lancer_agent(demande, outil, chemin, tmp, lecture, consigne, session, arret)
            session = resultat.session or session
            modele_servi = resultat.modele_servi or modele_servi
            self._noter_session(demande.carte, session=session)
            for cle, valeur in (resultat.jetons or {}).items():
                if valeur is not None:
                    jetons_total[cle] = (jetons_total.get(cle) or 0) + valeur
            self.budget.compter(secondes=resultat.duree_s, maintenant=self.horloge())
            if resultat.code == CODE_OOM:
                oom = int(self.session(demande.carte).get("oom", 0)) + 1
                self._noter_session(demande.carte, oom=oom)
                if oom >= 2:
                    raise CarteRefusee("memoire", "Mémoire insuffisante (limite 4 Gio) : deux arrêts de l'agent sur "
                                                  "cette carte.")
                raise Interruption("reprendre", "redemarrage")
            if resultat.limite_atteinte:
                remise = resultat.remise or (self.horloge() + QUOTA_SANS_REMISE)
                raise CarteRefusee("quota", f"Limite de l'abonnement {outil} atteinte : reprise prévue après la "
                                            "remise à zéro.", reprise_le=remise)
            try:
                sortie = valider_sortie(resultat.sortie, relecture=demande.role == "relecture")
            except SortieInvalide as exc:
                raise CarteRefusee("capacite", f"{exc} (code de sortie {resultat.code}) : carte bloquée.") from None
            if sortie.issue != "termine" or demande.role in ROLES_LECTURE or verification_raison is not None:
                break
            tentatives += 1
            self._noter_carte(demande, "verification", tentative=tentatives)
            code, fin, duree = await self._verifier(demande, depot, chemin, tmp)
            verification = {"etat": "reussie" if code == 0 else "echouee", "code": code, "duree_s": duree,
                            "tentatives": tentatives, "raison": None if code == 0 else
                            ("Délai de vérification dépassé." if code is None else None)}
            if code == 0 or tentatives > depot.reprises_verification:
                break
            consigne = SUITE_VERIF.format(code=code, fin=fin or "(aucune sortie)")
        if verification["etat"] == "non_executee":
            raison = verification_raison or ("Non exécutée : échec déclaré par l'agent." if sortie.issue == "echec"
                                             else "Non exécutée : question posée par l'agent.")
            verification = {"etat": "non_executee", "raison": raison, "tentatives": 0}
        if sortie.issue == "echec":
            resume = f"Échec déclaré par l'agent : {sortie.resume}"
        elif verification["etat"] == "echouee":
            resume = f"Vérification en échec : {sortie.resume}"
        else:
            resume = sortie.resume
        return await self._conclure(demande, depot, nom, base, outil, sortie, resume, verification,
                                    {"modele_servi": modele_servi, "jetons": jetons_total, "session": session})

    async def _conclure(self, demande: DemandeCarte, depot: Any, nom: str, base: str | None, outil: str | None,
                        sortie: Any, resume: str, verification: dict[str, Any], observe: dict[str, Any]) -> IssueCarte:
        self._noter_carte(demande, "commit")
        titre = " ".join(resume.split())[:60]
        message = (f"wip: question ({demande.carte})" if getattr(sortie, "issue", None) == "question"
                   else f"{demande.role}({demande.carte}): {titre}")
        tete = await asyncio.to_thread(self.depots.committer, depot.alias, nom, message)
        tete = tete or self.depots.tete(depot.alias, nom)
        self._noter_carte(demande, "controles")
        await asyncio.to_thread(self.depots.indexer, depot.alias, nom)
        changements = self.depots.changements(depot.alias, nom, base) if base else []
        chemins = pilotage.chemins_de_pilotage(changements, depot.pilotage_supplementaire)
        ajoutees = self.depots.lignes_ajoutees(depot.alias, nom, base) if base else ""
        textes = [ajoutees, resume, getattr(sortie, "question", None), getattr(sortie, "corrections", None)]
        trouve = secret_dans(textes, valeurs_exactes(self.coffre, getattr(self.politique.codex, "home", None)))
        if trouve:
            self.depots.quarantaine(depot.alias, nom, demande.branche)
            self.journal.ecrire("erreur", "secret_detecte", f"Secret détecté ({trouve}) : branche en quarantaine, rien "
                                "n'est envoyé.", carte=demande.carte)
            return self.bloquer(demande, "secret", RAISON_SECRET)
        if sortie is not None and sortie.issue == "question":
            corps = dict(self._base(demande), texte=sortie.question, contexte=sortie.resume[:4000])
            return self.emettre("question", corps)
        diffstat = self.depots.diffstat(depot.alias, nom, base, tete) if base and tete else None
        palier = None if demande.role == "integration" else (demande.palier or "default")
        metadonnees = {
            "modele_demande": demande.modele, "modele_servi": observe.get("modele_servi"), "effort": demande.effort,
            "palier_demande": palier, "palier_servi": None, "jetons": observe.get("jetons"),
            "branche": demande.branche, "base": base, "tete": tete, "diffstat": diffstat,
            "verification": verification, "pilotage": {"touche": bool(chemins), "chemins": chemins},
            "regime": self.isolement.get("regime", "inconnu"), "session_locale": bool(observe.get("session")),
        }
        verdict = getattr(sortie, "verdict", None) if demande.role == "relecture" else None
        corps = dict(self._base(demande), issue="termine", resume=resume[:4000], verdict=verdict,
                     corrections=getattr(sortie, "corrections", None) if verdict == "corrections" else None,
                     metadonnees=metadonnees)
        return self.emettre("terminer", corps)

    # ================================================================== intégration (§ 6.7)
    async def _integrer(self, demande: DemandeCarte, depot: Any, nom: str, chemin: Path, base: str | None,
                        tmp: Path, arret: asyncio.Event) -> IssueCarte:
        self._noter_carte(demande, "integration")
        conflits = await asyncio.to_thread(self.depots.fusionner, depot.alias, nom, demande.branches_a_integrer)
        if conflits:
            raise CarteRefusee("capacite", "Conflit d'intégration : " + ", ".join(conflits[:20]) + " : aucune "
                                           "résolution automatique ; tranchez, ou demandez une correction.")
        raison = self._verification_possible(depot)
        if raison is None:
            code, _fin, duree = await self._verifier(demande, depot, chemin, tmp)
            verification = {"etat": "reussie" if code == 0 else "echouee", "code": code, "duree_s": duree,
                            "tentatives": 1, "raison": None if code is not None else "Délai de vérification dépassé."}
        else:
            verification = {"etat": "non_executee", "raison": raison, "tentatives": 0}
        branches = ", ".join(demande.branches_a_integrer)
        resume = f"Intégration de {len(demande.branches_a_integrer)} branche(s) ({branches[:3000]})."
        if verification["etat"] == "echouee":
            resume = f"Vérification en échec : {resume}"
        return await self._conclure(demande, depot, nom, base, None, None, resume, verification, {})

    # ================================================================== consigne
    def _texte_reponses(self, demande: DemandeCarte) -> str:
        if not demande.reponses:
            return ""
        lignes = []
        for reponse in demande.reponses:
            if reponse.genre == "refus_revue":
                lignes.append(f"\n- Refus du propriétaire : {reponse.texte}")
            else:
                lignes.append(f"\n- Réponse ({reponse.repondu_par}) à ta question : {reponse.texte}")
        return "\nRéponses reçues :" + "".join(lignes)

    def _consigne(self, demande: DemandeCarte, lecture: Path) -> str:
        texte = CONSIGNE.format(role=demande.role, carte=demande.carte, projet=demande.projet_id,
                                alias=demande.depot_alias, branche=demande.branche)
        if demande.role == "relecture" and demande.carte_relue:
            texte += "\n" + CONSIGNE_RELECTURE.format(relue=demande.carte_relue, lecture=lecture.as_posix())
        elif demande.role == "exploration":
            texte += "\n" + CONSIGNE_EXPLORATION
        texte += "\n\nConsigne de Hermes :\n" + demande.consigne
        if demande.parents:
            texte += "\n\nRésumés des cartes parentes :"
            for parent in demande.parents:
                texte += f"\n- {parent.carte} ({parent.role}) : {parent.resume or '(aucun résumé)'}"
        texte += self._texte_reponses(demande)
        return texte

    # ================================================================== agent
    def _executable(self, outil: str) -> list[str]:
        if outil in self.executables:
            return list(self.executables[outil])
        section = getattr(self.politique, outil)
        return [Path(section.executable).as_posix()]

    async def _lancer_agent(self, demande: DemandeCarte, outil: str, chemin: Path, tmp: Path, lecture: Path,
                            consigne: str, session: str | None, arret: asyncio.Event) -> ResultatAgent:
        identite = IDENTITE_OUTIL[outil]
        dossier = self.lanceur.dossier(tmp / outil, identite, 0o700)
        executable = self._executable(outil)
        prefixe = self.lanceur.prefixe(identite) + executable[:-1]
        if outil == "codex":
            schema = tmp / "schema.json"
            schema.write_text(schema_json(), encoding="utf-8")
            os.chmod(schema, 0o644)
            reponse = dossier / "reponse.json"
            reponse.unlink(missing_ok=True)
            commande = commande_codex(prefixe=prefixe, executable=executable[-1], worktree=chemin,
                                      modele=demande.modele, effort=demande.effort, role=demande.role, schema=schema,
                                      reponse=reponse, codex_home=self.politique.codex.home,
                                      home=self.lanceur.home(identite), tmpdir=dossier, session=session)
            verrou_chemin = self.emplacements.verrou_codex
        else:
            jeton = self.coffre.lire("jeton-claude")
            if not jeton:
                raise CarteRefusee("capacite", "Jeton Claude absent de l'exécutant : déposez-le par « acp-poste "
                                               "connexion claude --stdin » (D92).")
            commande = commande_claude(prefixe=prefixe, executable=executable[-1], modele=demande.modele,
                                       effort=demande.effort, role=demande.role, lecture=lecture,
                                       config_dir=self.politique.claude.config_dir, jeton=jeton,
                                       home=self.lanceur.home(identite), tmpdir=dossier, session=session)
            verrou_chemin = self.emplacements.verrou_claude
        verrou_chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            verrou = Verrou(verrou_chemin).prendre(attendre_s=120.0)
        except VerrouOccupe:
            raise CarteRefusee("capacite", f"Une sonde {outil} occupe l'outil depuis plus de 2 min : carte remise "
                                           "à plus tard.") from None
        try:
            return await self._processus(demande, outil, identite, commande, chemin, consigne, arret,
                                         reponse if outil == "codex" else None)
        finally:
            verrou.rendre()

    async def _processus(self, demande: DemandeCarte, outil: str, identite: str, commande: Any, chemin: Path,
                         consigne: str, arret: asyncio.Event, reponse: Path | None) -> ResultatAgent:
        debut = time.monotonic()
        duree_max = min(demande.duree_max_s, self.politique.politique.duree_max_carte_s)
        try:
            processus = await spawn_fenced_process(commande.argv, cwd=str(chemin), env=commande.env,
                                                   stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE, limit=1024 * 1024)
        except FencedSpawnError:
            raise CarteRefusee("capacite", f"{outil} introuvable ou impossible à lancer sur l'exécutant.") from None
        lignes: list[bytes] = []
        verdict_init: list[str] = []

        async def ecrire() -> None:
            try:
                processus.stdin.write(consigne.encode("utf-8"))
                await processus.stdin.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                try:
                    processus.stdin.close()
                except (OSError, RuntimeError):
                    pass

        async def lire() -> None:
            while True:
                try:
                    ligne = await processus.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    continue
                if not ligne:
                    return
                if len(lignes) < 50_000:
                    lignes.append(ligne)
                if outil == "claude" and b'"init"' in ligne and not verdict_init:
                    flux = lire_flux_claude([ligne])
                    probleme = self._controle_init(demande, flux)
                    if probleme:
                        verdict_init.append(probleme)
                        return

        async def vider() -> None:
            total = 0
            while True:
                morceau = await processus.stderr.read(4096)
                if not morceau:
                    return
                total += len(morceau)

        taches = [asyncio.create_task(ecrire()), asyncio.create_task(lire()), asyncio.create_task(vider())]
        attente = asyncio.create_task(self._attendre_fin(processus))
        interruption: Interruption | None = None
        depasse = False
        # Premier battement aussitôt : il confirme la réclamation et acquitte les réponses livrées avec la carte.
        prochain = time.monotonic()
        try:
            while not attente.done():
                if verdict_init:
                    break
                if arret.is_set():
                    interruption = Interruption("arret", "sigterm")
                    break
                if time.monotonic() - debut > duree_max:
                    depasse = True
                    break
                if time.monotonic() >= prochain:
                    prochain = time.monotonic() + self.intervalle_battement_s
                    minutes = int((time.monotonic() - debut) // 60)
                    note = (f"Agent {outil} en cours depuis {minutes} min." if minutes else
                            f"Agent {outil} démarré ({demande.role}).")
                    reponse_b = await self._battement(demande, note)
                    if reponse_b is not None and not reponse_b.valide:
                        interruption = Interruption("reprendre", "reclamation_perdue")
                        break
                    if reponse_b is not None and reponse_b.annuler:
                        interruption = Interruption("arret", "annulee")
                        break
                await asyncio.wait({attente}, timeout=0.2)
        finally:
            if not attente.done():
                arrete = await self.lanceur.arreter(processus.process, identite, self.grace_s)
                if not arrete:
                    self.journal.ecrire("erreur", "agent_survivant", "Processus de l'agent impossibles à arrêter : "
                                        "exécution suspendue.", carte=demande.carte)
                    raise AgentSurvivant("agent_survivant")
            else:
                await self.lanceur.arreter(processus.process, identite, 0)
            for tache in taches:
                if not tache.done():
                    tache.cancel()
            await asyncio.gather(*taches, return_exceptions=True)
            attente.cancel()
            await asyncio.gather(attente, return_exceptions=True)
            processus.close_fence()
        duree = time.monotonic() - debut
        if interruption is not None:
            raise interruption
        if verdict_init:
            raise CarteRefusee("capacite", verdict_init[0])
        if depasse:
            raise CarteRefusee("duree", f"Durée maximale de la carte dépassée ({duree_max} s) : le travail est "
                                        "committé.")
        code = processus.returncode
        if outil == "codex":
            flux = lire_flux_codex(lignes)
            sortie = None
            if reponse is not None and reponse.is_file():
                sortie = reponse.read_text(encoding="utf-8", errors="replace")[: 64 * 1024]
            elif flux.dernier_message:
                sortie = flux.dernier_message
            return ResultatAgent(code=code, sortie=sortie, session=flux.session, jetons=flux.jetons,
                                 erreur=flux.erreur, limite_atteinte=flux.limite_atteinte, duree_s=duree)
        flux = lire_flux_claude(lignes, maintenant=self.horloge())
        self.quotas_claude.noter(flux.limite)
        return ResultatAgent(code=code, sortie=sortie_claude(flux), session=flux.session,
                             modele_servi=flux.modele_servi, jetons=flux.jetons, erreur=flux.erreur,
                             limite_atteinte=flux.limite_atteinte,
                             remise=flux.limite.remise if flux.limite else None, duree_s=duree)

    @staticmethod
    async def _attendre_fin(processus: Any) -> int | None:
        while processus.returncode is None:
            await asyncio.sleep(0.05)
        return processus.returncode

    def _controle_init(self, demande: DemandeCarte, flux: Any) -> str | None:
        """Claude : outils d'exécution présents, ou modèle servi différent de la résolution documentée de l'alias."""
        if flux.outils_interdits:
            return ("Outils d'exécution présents dans la session Claude (" + ", ".join(flux.outils_interdits[:5]) +
                    ") : exécution arrêtée.")
        documentee = next((r for a, r, _e, _d in TABLE_CLAUDE if a == demande.modele), None)
        servi = flux.modele_servi
        if documentee and servi and servi != documentee and not (
                servi.startswith(documentee + "-") and servi[len(documentee) + 1:].isdigit()):
            return (f"Modèle servi {servi} différent de la résolution documentée {documentee} pour l'alias "
                    f"{demande.modele} : exécution arrêtée.")
        return None

    async def _battement(self, demande: DemandeCarte, note: str) -> Any:
        corps = dict(self._base(demande), note=note[:500])
        try:
            return await asyncio.to_thread(self.envoyer, "battement", corps)
        except Refus as exc:
            self.journal.ecrire_au_plus("battement", 600, "avertissement", "battement_refuse", exc.message,
                                        carte=demande.carte)
            return None

    # ================================================================== vérification
    async def _verifier(self, demande: DemandeCarte, depot: Any, chemin: Path, tmp: Path) -> tuple[int | None, str,
                                                                                                    int]:
        debut = time.monotonic()
        code, fin = await self._commande_verif(demande, depot, chemin, tmp, depot.verification,
                                               bac=self.isolement.get("regime") == "A", reseau=False)
        return code, fin, int(time.monotonic() - debut)

    async def _commande_verif(self, demande: DemandeCarte, depot: Any, chemin: Path, tmp: Path,
                              argv: tuple[str, ...], *, bac: bool, reseau: bool) -> tuple[int | None, str]:
        dossier = self.lanceur.dossier(tmp / "verif", "acp-verif", 0o700)
        caches = Path(self.emplacements.tmp) / "caches" / depot.alias
        self.lanceur.dossier(caches.parent, None, 0o751)
        self.lanceur.dossier(caches, "acp-verif", 0o700)
        env = {"HOME": self.lanceur.home("acp-verif"), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
               "LC_ALL": "C.UTF-8", "TMPDIR": dossier.as_posix(), "XDG_CACHE_HOME": caches.as_posix(),
               "UV_CACHE_DIR": (caches / "uv").as_posix(), "PIP_CACHE_DIR": (caches / "pip").as_posix(),
               "npm_config_cache": (caches / "npm").as_posix(), "npm_config_ignore_scripts": "true", "CI": "1"}
        if os.name == "nt":
            env.update({k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP")})
        commande = list(argv)
        if bac and not reseau:
            home_verif = self.lanceur.dossier(tmp / "codex-home-verif", None, 0o755)
            (home_verif / "config.toml").write_text(profil_codex_toml(), encoding="utf-8")
            os.chmod(home_verif / "config.toml", 0o444)
            env["CODEX_HOME"] = home_verif.as_posix()
            commande = [*self._executable("codex"), "sandbox", "-P", PROFIL, "-C", chemin.as_posix(), "--", *argv]
        commande = [*self.lanceur.prefixe("acp-verif"), *commande]
        try:
            processus = await spawn_fenced_process(commande, cwd=str(chemin), env=env,
                                                   stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.STDOUT)
        except FencedSpawnError:
            return 127, "Commande de vérification introuvable."
        tampon = bytearray()

        async def lire() -> None:
            while True:
                morceau = await processus.stdout.read(65536)
                if not morceau:
                    return
                tampon.extend(morceau)
                if len(tampon) > SORTIE_VERIF_MAX * 4:
                    del tampon[:-SORTIE_VERIF_MAX]

        lecture = asyncio.create_task(lire())
        try:
            await asyncio.wait_for(self._attendre_fin(processus), timeout=depot.verification_max_s)
            code: int | None = processus.returncode
        except TimeoutError:
            code = None
        finally:
            await self.lanceur.arreter(processus.process, "acp-verif", 2.0 if code is None else 0)
            try:
                await asyncio.wait_for(lecture, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                lecture.cancel()
            processus.close_fence()
        fin = masquer(bytes(tampon[-SORTIE_VERIF_MAX:]).decode("utf-8", "replace"))
        return code, fin
