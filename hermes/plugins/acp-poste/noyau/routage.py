"""Routage d'une étape : exécutant (voie), modèle, effort et palier, résolus de façon DÉTERMINISTE
contre le relevé du poste (étape P4, plan d'autonomie § 3 ; cahier P4 § 7).

Ordre de résolution :

1. surcharge du propriétaire (carte, puis projet, puis globale ; table ``surcharges``) ;
2. choix explicite (étape du plan ou triplet ``exploration``), s'il est au relevé et admis par la
   classe ;
3. première entrée de la table ``routage`` admissible (modèle au relevé, effort pris en charge et non
   interdit, palier admis, quota connu sous le seuil ou inconnu — mentionné —, voie admise) ;
4. sinon refus « Aucun modèle disponible… ». Aucun repli silencieux.

Voie ``hermes`` : aucun ``model_override`` par défaut (modèle du profil) ; un modèle n'est admis que
s'il figure dans le dernier relevé ``poste-codex`` (abonnement ChatGPT du cerveau). Jamais de
``provider_override``.

L'effort exact demandé est gardé dans ``demandes.effort`` ; il n'est posé sur la carte
(``reasoning_effort``) que s'il appartient à l'énumération de Hermes (kanban_db.py:115-127).

Étape P6 (cahier P6 § 4.3, § 6.7, § 9.2) :

- classe ``integration`` OUVERTE : voie ``poste-integration``, sans modèle, effort ni palier, toujours hors de la
  table de routage (rien à y valider) ;
- **voies fermées** d'après le DERNIER inventaire (:func:`voies_fermees` : isolement de l'exécutant, bac à sable du
  poste, conditions d'usage non décidées, exécutant absent de la politique) : refus ``voie_fermee`` ;
- **repli de la relecture** (D91, appliqué ; réglage ``relecture_repli_meme_voie``) : si l'AUTRE voie est fermée, la
  relecture va à la même voie avec un modèle de la classe « relecture » DIFFÉRENT de celui de l'implémentation, et la
  mention le dit ; sinon, ou si le réglage est levé, D27 s'applique (refus ``relecture_impossible``) ;
- résolutions d'alias **observées** à l'exécution (:func:`resolutions_observees`), pour la page Routage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import base, contrat_partage  # noqa: F401 — contrat_partage met le contrat sur sys.path
from . import kanban_adapter as ka
from . import textes as T
from .textes import RefusACP, refus

from acp_poste_contrat.inventaire import Releve, valider_releve  # noqa: E402

HERMES = "hermes"
VOIES_PAR_CLASSE: Dict[str, Tuple[str, ...]] = {
    "exploration": ("poste-claude", "poste-codex"),
    "planification": (HERMES,),
    "synthese": (HERMES,),
    "repondre": (HERMES,),
    "recherche_web": (HERMES,),
    "architecture": ("poste-codex", "poste-claude", HERMES),
    "implementation": ("poste-codex", "poste-claude"),
    "debogage_tests": ("poste-codex", "poste-claude"),
    "petite_tache": ("poste-codex", "poste-claude"),
    "documentation": ("poste-codex", "poste-claude", HERMES),
    "relecture": ("poste-codex", "poste-claude"),
    # Étape P6 (cahier P6 § 6.7) : voie dédiée, déterministe, sans modèle ; hors de la table (CLASSES_TABLE).
    "integration": (ka.VOIE_INTEGRATION,),
}
CLASSES_ETAPE = ("architecture", "implementation", "debogage_tests", "documentation", "petite_tache",
                 "recherche_web", "integration")
PALIER_PAR_DEFAUT = "default"


@dataclass(frozen=True)
class Resolution:
    voie: str
    modele: Optional[str]          # None : modèle du profil de Hermes
    effort: Optional[str]          # effort exact demandé (même hors énumération de Hermes)
    effort_carte: Optional[str]    # effort posé sur la carte (énumération de Hermes), sinon None
    palier: str
    source_routage: str
    releve_id: Optional[int] = None
    mention: Optional[str] = None

    def en_dict(self) -> Dict[str, Any]:
        return {"voie": self.voie, "modele": self.modele, "effort": self.effort, "effort_carte": self.effort_carte,
                "palier": self.palier, "source_routage": self.source_routage, "mention": self.mention}


def autre_voie(voie: str) -> str:
    return "poste-claude" if voie == "poste-codex" else "poste-codex"


def date_lisible(epoch: Optional[int], forme: str = "%d/%m/%Y %H:%M") -> str:
    """« 26/09/2026 10:00 » en heure de Paris (UTC dit tel quel si la base des fuseaux manque)."""
    if not epoch:
        return T.INCONNU
    instant = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return instant.astimezone(ZoneInfo("Europe/Paris")).strftime(forme)
    except Exception:  # noqa: BLE001 — base des fuseaux absente : on le dit
        return instant.strftime(forme) + " UTC"


# ------------------------------------------------------------------ relevés (catalogue du poste)


def enregistrer_releve_dans(conn, donnees: Any, *, machine_id: Optional[str] = None,
                            recu_le: Optional[int] = None) -> int:
    """Valide le relevé (contrat partagé) puis l'enregistre SOUS la transaction de l'appelant (route machine
    ``/machine/v1/inventaire``, étape P5) ; rend son identifiant. ``machine_id`` : poste qui l'a publié (NULL pour
    un relevé factice)."""
    releve = valider_releve(donnees)
    contenu = releve.model_dump(mode="json")
    curseur = conn.execute(
        "INSERT INTO releves (voie, source, version_cli, releve_le, recu_le, contenu, machine_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (releve.voie, releve.source, releve.version_cli, int(releve.releve_le.timestamp()),
         int(recu_le if recu_le is not None else base.maintenant()), json.dumps(contenu, ensure_ascii=False),
         machine_id))
    base.journaliser(conn, f"releve:{releve.source}", "releve", cible=releve.voie,
                     detail={"modeles": len(releve.modeles), "depots": len(releve.depots), "etat": releve.etat,
                             "origine_liste": releve.origine_liste, "machine": machine_id})
    return int(curseur.lastrowid)


def enregistrer_releve(conn, donnees: Any, *, recu_le: Optional[int] = None) -> int:
    """Comme :func:`enregistrer_releve_dans`, sous sa propre transaction ``IMMEDIATE`` (P4 : tests et poste
    simulé, ``source: "releve_factice"``)."""
    with base.transaction(conn):
        return enregistrer_releve_dans(conn, donnees, recu_le=recu_le)


# Rétention des relevés (cahier P5 § 4.3) : les 50 derniers par voie, sauf les relevés cités par une demande
# (``demandes.releve_id``, base en foreign_keys=ON : une purge naïve lèverait « FOREIGN KEY constraint failed » et
# annulerait la réception) ou acceptés par le propriétaire.
RELEVES_GARDES_PAR_VOIE = 50


def purger_releves_dans(conn, voie: str, garder: int = RELEVES_GARDES_PAR_VOIE) -> int:
    return conn.execute(
        "DELETE FROM releves WHERE voie = ? AND accepte_le IS NULL "
        "AND id NOT IN (SELECT id FROM releves WHERE voie = ? ORDER BY recu_le DESC, id DESC LIMIT ?) "
        "AND id NOT IN (SELECT releve_id FROM demandes WHERE releve_id IS NOT NULL)",
        (voie, voie, int(garder))).rowcount


def dernier_releve(conn, voie: str) -> Optional[Tuple[int, Releve, int]]:
    """(identifiant, relevé, date de relevé) du dernier relevé reçu pour ``voie``, ou None."""
    ligne = conn.execute("SELECT id, contenu, releve_le FROM releves WHERE voie = ? ORDER BY recu_le DESC, id DESC "
                         "LIMIT 1", (voie,)).fetchone()
    if ligne is None:
        return None
    try:
        return int(ligne["id"]), Releve.model_validate(json.loads(ligne["contenu"])), int(ligne["releve_le"])
    except (ValueError, TypeError):
        return None


def releve_factice_present(conn) -> bool:
    return conn.execute("SELECT 1 FROM releves WHERE source = 'releve_factice' LIMIT 1").fetchone() is not None


def depots_autorises(conn) -> Optional[List[str]]:
    """Alias des dépôts autorisés, lus dans le dernier relevé de chaque voie ; None si le poste n'a
    publié AUCUN relevé (inventaire inconnu)."""
    alias: List[str] = []
    vu = False
    for voie in ka.VOIES_POSTE:
        dernier = dernier_releve(conn, voie)
        if dernier is None:
            continue
        vu = True
        alias.extend(d.alias for d in dernier[1].depots if d.alias not in alias)
    return sorted(alias) if vu else None


# ------------------------------------------------------------------ table de routage et surcharges


def enregistrer_routage(conn, classe: str, entrees: Sequence[Dict[str, Any]], *, source: str, valide_par: str) -> None:
    """Table de routage d'une classe (P5 : validée par le propriétaire ; P4 : tests seulement,
    ``source="releve_factice"``). Chaque entrée : ``{voie, modele, effort?, palier?}``."""
    if classe not in VOIES_PAR_CLASSE:
        raise ValueError(f"classe inconnue : {classe}")
    propres = []
    for entree in entrees:
        if not isinstance(entree, dict) or entree.get("voie") not in (*ka.VOIES_POSTE, HERMES):
            raise ValueError("entrée de routage invalide : voie attendue")
        propres.append({"voie": entree["voie"], "modele": entree.get("modele"), "effort": entree.get("effort"),
                        "palier": entree.get("palier")})
    with base.transaction(conn):
        conn.execute("INSERT INTO routage (classe, entrees, valide_le, valide_par, source) VALUES (?, ?, ?, ?, ?) "
                     "ON CONFLICT(classe) DO UPDATE SET entrees = excluded.entrees, valide_le = excluded.valide_le, "
                     "valide_par = excluded.valide_par, source = excluded.source",
                     (classe, json.dumps(propres), base.maintenant(), valide_par, source))
        base.journaliser(conn, valide_par, "routage", cible=classe, detail=propres)


def entrees_routage(conn, classe: str) -> List[Dict[str, Any]]:
    ligne = conn.execute("SELECT entrees FROM routage WHERE classe = ?", (classe,)).fetchone()
    if ligne is None:
        return []
    try:
        entrees = json.loads(ligne[0])
    except ValueError:
        return []
    return [e for e in entrees if isinstance(e, dict)] if isinstance(entrees, list) else []


def surcharge_applicable(conn, classe: str, projet_id: Optional[str], carte: Optional[str]) -> Optional[Dict[str, Any]]:
    """Surcharge active la plus précise : carte, puis projet, puis globale (la plus récente d'abord)."""
    for portee, cible in (("carte", carte), ("projet", projet_id), ("globale", None)):
        if portee != "globale" and not cible:
            continue
        sql = ("SELECT * FROM surcharges WHERE active = 1 AND classe = ? AND portee = ? AND "
               + ("cible IS NULL" if cible is None else "cible = ?") + " ORDER BY id DESC LIMIT 1")
        ligne = conn.execute(sql, (classe, portee) if cible is None else (classe, portee, cible)).fetchone()
        if ligne is not None:
            return base.ligne_en_dict(ligne)
    return None


# ------------------------------------------------------------------ conditions de l'étape P5 (cahier P5 § 12.4)

LIBELLES_VOIE = {"poste-codex": "Codex", "poste-claude": "Claude Code"}
CLE_VERSION = {"poste-codex": "codex", "poste-claude": "claude"}
CONNEXIONS_ADMISES = {"poste-codex": ("compte_chatgpt",),
                      "poste-claude": ("jeton_reconnu", "jeton_present_non_verifie")}
LISTES_DE_SECOURS = ("catalogue_embarque", "identique_au_catalogue_embarque")


def contexte_poste(conn, releve_id: int) -> Optional[Dict[str, Any]]:
    """Ce que l'inventaire le plus récent du poste qui a publié ce relevé dit de lui (connexions, versions,
    politique de poste.toml), et si le propriétaire a accepté ce relevé. None pour un relevé factice (P4) :
    aucune de ces conditions ne s'applique alors."""
    ligne = conn.execute("SELECT machine_id, accepte_le, accepte_par FROM releves WHERE id = ?", (releve_id,)).fetchone()
    if ligne is None or ligne["machine_id"] is None:
        return None
    inventaire = conn.execute("SELECT contenu, recu_le FROM inventaires WHERE machine_id = ? ORDER BY id DESC LIMIT 1",
                              (ligne["machine_id"],)).fetchone()
    try:
        contenu = json.loads(inventaire["contenu"]) if inventaire is not None else {}
    except ValueError:
        contenu = {}
    return {"machine_id": ligne["machine_id"], "accepte_le": ligne["accepte_le"], "accepte_par": ligne["accepte_par"],
            "connexions": contenu.get("connexions") or {}, "versions": contenu.get("versions") or {},
            "politique": contenu.get("politique"), "poste": contenu.get("poste") or {}}


def raison_liste_de_secours(releve: Releve) -> str:
    if releve.origine_liste == "identique_au_catalogue_embarque":
        return T.RAISON_IDENTIQUE_EMBARQUE.format(v=releve.version_cli or T.INCONNU)
    return T.RAISON_SANS_COMPTE


def verifier_voie(conn, voie: str, releve_id: int, releve: Releve, releve_le: int) -> Optional[Dict[str, Any]]:
    """Conditions d'une VOIE du poste, dans l'ordre du cahier : relevé en état ok (un relevé en échec remplace le
    précédent, qui ne reste donc jamais routable), connexion au compte de l'abonnement, liste qui n'est pas de
    secours (sauf relevé accepté par le propriétaire), version de la CLI conforme. Rend le contexte du poste."""
    if releve.etat not in (None, "ok"):
        raise refus("voie_indisponible", T.VOIE_INDISPONIBLE.format(
            v=voie, date=date_lisible(releve_le), detail=releve.detail or releve.etat))
    contexte = contexte_poste(conn, releve_id)
    if contexte is None:
        return None
    etat_connexion = (contexte["connexions"] or {}).get(CLE_VERSION[voie])
    if etat_connexion not in CONNEXIONS_ADMISES[voie]:
        raise refus("voie_non_connectee", T.VOIE_NON_CONNECTEE.format(cli=LIBELLES_VOIE[voie],
                                                                      etat=etat_connexion or T.INCONNU))
    if voie == "poste-codex" and releve.origine_liste in LISTES_DE_SECOURS and not (
            releve.origine_liste == "identique_au_catalogue_embarque" and contexte["accepte_le"]):
        raise refus("liste_de_secours", T.LISTE_DE_SECOURS.format(date=date_lisible(releve_le),
                                                                  raison=raison_liste_de_secours(releve)))
    version = (contexte["versions"] or {}).get(CLE_VERSION[voie]) or {}
    if not version.get("conforme"):
        raise refus("cli_hors_version", T.CLI_HORS_VERSION.format(
            cli=LIBELLES_VOIE[voie], lue=version.get("lue") or T.INCONNU, testee=version.get("testee") or T.INCONNU))
    return contexte


def verifier_politique_du_poste(contexte: Optional[Dict[str, Any]], voie: str, modele: str, effort: Optional[str],
                                palier: str) -> None:
    """Ce que poste.toml refuse, Hermes ne peut pas le lever : exécutant, modèle ou alias permis, effort interdit,
    palier admis (cahier P5 § 12.4, décision D52). Sans contexte (relevé factice de P4) : rien à vérifier."""
    if contexte is None:
        return
    politique = contexte.get("politique")
    if not isinstance(politique, dict):
        raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(objet="tout routage (politique inconnue)",
                                                                             cle="executants"))
    executant = CLE_VERSION[voie]
    if executant not in (politique.get("executants") or []):
        raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(
            objet=f"l'exécutant {LIBELLES_VOIE[voie]}", cle="executants"))
    if voie == "poste-codex":
        permis = politique.get("modeles_codex_permis") or []
        if permis and modele not in permis:
            raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(
                objet=f"le modèle « {modele} »", cle="modeles_codex_permis"))
    elif modele not in (politique.get("alias_claude_permis") or []):
        raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(
            objet=f"l'alias « {modele} »", cle="alias_claude_permis"))
    if effort and effort in (politique.get("efforts_interdits") or []):
        raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(
            objet=f"l'effort « {effort} »", cle="efforts_interdits"))
    if palier not in (politique.get("paliers_admis") or []):
        raise refus("interdit_par_le_poste", T.INTERDIT_PAR_LE_POSTE.format(
            objet=f"le palier « {palier} »", cle="paliers_admis"))


# ------------------------------------------------------------------ voies fermées (étape P6, cahier P6 § 4.3, § 6.1)


def dernier_inventaire(conn, machine_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Contenu du dernier inventaire de la machine active (ou de ``machine_id``), ``None`` s'il n'y en a aucun."""
    if machine_id is None:
        actif = conn.execute("SELECT id FROM machines WHERE etat = 'actif'").fetchone()
        if actif is None:
            return None
        machine_id = actif[0]
    ligne = conn.execute("SELECT contenu FROM inventaires WHERE machine_id = ? ORDER BY id DESC LIMIT 1",
                         (machine_id,)).fetchone()
    if ligne is None:
        return None
    try:
        contenu = json.loads(ligne[0])
    except ValueError:
        return None
    return contenu if isinstance(contenu, dict) else None


def voies_fermees(conn, inventaire: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Voies du poste fermées d'après le dernier inventaire du poste ACTIF (jamais devinées) : ``{voie: raison}``.

    - exécutant Linux : écriture non admise par le verdict de la sonde (régime, identifiants séparés, D79) ;
    - poste Windows : écriture Codex non admise par le bac à sable (P5) ;
    - conditions d'usage publiées sans date de décision (D83, D84).

    Un exécutant absent de la politique reste refusé par :func:`verifier_politique_du_poste` (code
    ``interdit_par_le_poste``, P5). Sans inventaire, aucune voie n'est dite fermée ici : le routage refuse déjà faute de relevé."""
    inventaire = dernier_inventaire(conn) if inventaire is None else inventaire
    if not inventaire:
        return {}
    fermees: Dict[str, str] = {}
    isolement = inventaire.get("isolement_linux")
    bac = inventaire.get("bac_a_sable_codex")
    politique = inventaire.get("politique") or {}
    conditions = politique.get("conditions") or {}
    for voie, cle in (("poste-codex", "codex"), ("poste-claude", "claude")):
        if isinstance(isolement, dict):
            if not (isolement.get("ecriture_admise") or {}).get(cle):
                fermees[voie] = T.VOIE_FERMEE_ISOLEMENT.format(
                    regime=isolement.get("regime") or T.INCONNU, raison=isolement.get("raison") or T.INCONNU)
                continue
        elif cle == "codex" and isinstance(bac, dict) and not bac.get("ecriture_admise"):
            fermees[voie] = T.VOIE_FERMEE_BAC_A_SABLE.format(raison=bac.get("raison") or T.INCONNU)
            continue
        if conditions and conditions.get(cle) is None:
            fermees[voie] = T.VOIE_FERMEE_CONDITIONS.format(cli=LIBELLES_VOIE[voie])
    return fermees


def resolutions_observees(conn, limite: int = 20) -> List[Dict[str, Any]]:
    """Résolutions d'alias OBSERVÉES à l'exécution (modèle servi rapporté par ``terminer``), les plus récentes
    d'abord, une par couple (voie, alias) : D59, « résolution observée en P6 »."""
    vues: Dict[tuple, Dict[str, Any]] = {}
    for ligne in conn.execute("SELECT voie, modele, modele_servi, observe_le FROM demandes WHERE modele_servi IS NOT "
                              "NULL AND observe_le IS NOT NULL ORDER BY observe_le DESC LIMIT 500").fetchall():
        cle = (ligne["voie"], ligne["modele"])
        if cle not in vues:
            vues[cle] = {"voie": ligne["voie"], "alias": ligne["modele"], "modele_servi": ligne["modele_servi"],
                         "observe_le": ligne["observe_le"], "observe_le_lisible": date_lisible(ligne["observe_le"])}
    return list(vues.values())[:limite]


# ------------------------------------------------------------------ résolution


def _politique(conn) -> Tuple[List[str], List[str]]:
    return list(base.reglage(conn, "efforts_interdits") or []), list(base.reglage(conn, "paliers_admis") or [])


def valider_choix(conn, *, classe: str, projet: Dict[str, Any], voie: str, modele: Optional[str],
                  effort: Optional[str], palier: Optional[str], source: str, ref: Optional[str] = None) -> Resolution:
    """Vérifie un triplet (voie, modèle, effort) et son palier contre la classe, le projet, la politique
    et le relevé ; rend la résolution ou lève le refus exact."""
    admises = VOIES_PAR_CLASSE.get(classe, ())
    if voie not in admises:
        raise refus("classe_voie", T.CLASSE_VOIE.format(c=classe, v=voie, admises=T.liste(admises)))
    if voie != HERMES and not projet.get("depot_alias"):
        raise refus("sans_depot", T.SANS_DEPOT.format(titre=projet.get("titre"), ref=ref or classe))
    interdits, paliers = _politique(conn)
    palier = palier or PALIER_PAR_DEFAUT
    if effort and effort in interdits:
        raise refus("effort_interdit", T.EFFORT_INTERDIT.format(e=effort))
    if palier not in paliers:
        raise refus("palier_interdit", T.PALIER_INTERDIT.format(p=palier))
    if voie == ka.VOIE_INTEGRATION:
        if modele or effort:
            raise refus("integration_sans_modele", T.INTEGRATION_SANS_MODELE_ROUTAGE)
        return Resolution(voie=voie, modele=None, effort=None, effort_carte=None, palier=palier,
                          source_routage="sans_objet")
    fermee = voies_fermees(conn).get(voie) if voie in ka.VOIES_POSTE else None
    if fermee:
        raise refus("voie_fermee", T.VOIE_FERMEE.format(v=voie, raison=fermee))
    if voie == HERMES:
        releve_id = None
        if modele:
            codex = dernier_releve(conn, "poste-codex")
            if codex is None or codex[1].modele(modele) is None:
                raise refus("modele_absent", T.MODELE_HERMES_ABSENT.format(
                    m=modele, date=date_lisible(codex[2]) if codex else T.INCONNU))
            # Étape P5 : le relevé Codex qui fonde ce modèle doit être celui du compte (ni en échec, ni de secours).
            verifier_voie(conn, "poste-codex", *codex)
            releve_id = codex[0]
        if effort and ka.effort_hermes(effort) is None:
            raise refus("effort_non_pris_en_charge", T.EFFORT_NON_PRIS.format(
                e=effort, m=modele or T.MODELE_DU_PROFIL, efforts=T.liste(("none", *ka.VALID_REASONING_EFFORTS))))
        src = source if (modele or effort or source.startswith("surcharge")) else "profil"
        return Resolution(voie=HERMES, modele=modele or None, effort=effort or None, effort_carte=ka.effort_hermes(effort),
                          palier=palier, source_routage=src, releve_id=releve_id)
    dernier = dernier_releve(conn, voie)
    if dernier is None:
        raise RefusACP("aucun_modele", T.AUCUN_MODELE.format(c=classe, raison=T.RAISON_AUCUN_RELEVE))
    releve_id, releve, releve_le = dernier
    contexte = verifier_voie(conn, voie, releve_id, releve, releve_le)
    if not modele:
        defaut = releve.modele_par_defaut()
        if defaut is None:
            raise RefusACP("aucun_modele", T.AUCUN_MODELE.format(
                c=classe, raison=f"le relevé de {voie} ne désigne aucun modèle par défaut"))
        modele = defaut.id
    fiche = releve.modele(modele)
    if fiche is None:
        raise refus("modele_absent", T.MODELE_ABSENT.format(m=modele, v=voie, date=date_lisible(releve_le)))
    effort = effort or fiche.defaultReasoningEffort
    verifier_politique_du_poste(contexte, voie, modele, effort, palier)
    if fiche.supportedReasoningEfforts is None:
        # Étape P5 : efforts inconnus (alias Claude hors de la plage documentée) : refusé AVANT tout usage de la
        # liste (None), jamais une TypeError.
        raise refus("efforts_inconnus", T.EFFORTS_INCONNUS.format(
            alias=modele, version=releve.version_cli or T.INCONNU,
            date=releve.documentation_lue_le.strftime("%d/%m/%Y") if releve.documentation_lue_le else T.INCONNU))
    if effort and effort in interdits:
        raise refus("effort_interdit", T.EFFORT_INTERDIT.format(e=effort))
    if effort and effort not in fiche.supportedReasoningEfforts:
        raise refus("effort_non_pris_en_charge", T.EFFORT_NON_PRIS.format(
            e=effort, m=modele, efforts=T.liste(fiche.supportedReasoningEfforts)))
    mentions = []
    quota = releve.quotas.pourcentage_utilise if releve.quotas is not None else None
    if quota is None:
        mentions.append(T.QUOTA_INCONNU)
    elif quota >= float(base.reglage(conn, "seuil_quota_pct") or 90):
        raise RefusACP("aucun_modele", T.AUCUN_MODELE.format(c=classe, raison=T.RAISON_QUOTA.format(x=f"{quota:g}")))
    if base.maintenant() - releve_le > int(base.reglage(conn, "releve_perime_s") or 7200):
        mentions.append("relevé périmé")
    return Resolution(voie=voie, modele=modele, effort=effort or None, effort_carte=ka.effort_hermes(effort),
                      palier=palier, source_routage=source, releve_id=releve_id,
                      mention=", ".join(mentions) or None)


def resoudre(conn, *, classe: str, projet: Dict[str, Any], voie: Optional[str] = None, modele: Optional[str] = None,
             effort: Optional[str] = None, carte: Optional[str] = None, ref: Optional[str] = None) -> Resolution:
    """Résolution déterministe d'une étape de ``classe`` (voir l'en-tête du module)."""
    if classe == "integration":
        # Étape P6 : déterministe, sans modèle ; aucune surcharge ni table ne s'y applique.
        return valider_choix(conn, classe=classe, projet=projet, voie=ka.VOIE_INTEGRATION, modele=modele,
                             effort=effort, palier=None, source="sans_objet", ref=ref)
    admises = VOIES_PAR_CLASSE.get(classe)
    if admises is None:
        raise refus("plan_invalide", f"classe « {classe} » inconnue.")
    surcharge = surcharge_applicable(conn, classe, projet.get("id"), carte)
    if surcharge is not None:
        return valider_choix(conn, classe=classe, projet=projet, voie=surcharge["voie"], modele=surcharge["modele"],
                             effort=surcharge["effort"], palier=surcharge["palier"],
                             source="surcharge_" + surcharge["portee"], ref=ref)
    hermes_par_defaut = admises == (HERMES,) or (HERMES in admises and not projet.get("depot_alias"))
    if voie or modele or effort:
        if not voie and modele:
            candidates = [v for v in admises if v != HERMES and (d := dernier_releve(conn, v)) and d[1].modele(modele)]
            if candidates:
                voie = candidates[0]
            elif HERMES in admises and not projet.get("depot_alias"):
                voie = HERMES
            else:
                raise refus("modele_absent", T.MODELE_ABSENT.format(m=modele, v=T.liste(
                    v for v in admises if v != HERMES), date=T.INCONNU))
        elif not voie:
            # Effort seul : la voie par défaut de la classe (Hermes, ou la première voie du poste relevée).
            relevees = [v for v in admises if v != HERMES and dernier_releve(conn, v)]
            voie = HERMES if hermes_par_defaut else (relevees[0] if relevees else next(
                (v for v in admises if v != HERMES), HERMES))
        return valider_choix(conn, classe=classe, projet=projet, voie=voie, modele=modele, effort=effort, palier=None,
                             source="choix_explicite", ref=ref)
    if hermes_par_defaut:
        return valider_choix(conn, classe=classe, projet=projet, voie=HERMES, modele=None, effort=None, palier=None,
                             source="profil", ref=ref)
    entrees = entrees_routage(conn, classe)
    raisons: List[RefusACP] = []
    for entree in entrees:
        try:
            return valider_choix(conn, classe=classe, projet=projet, voie=entree.get("voie"), modele=entree.get("modele"),
                                 effort=entree.get("effort"), palier=entree.get("palier"), source="table", ref=ref)
        except RefusACP as exc:
            raisons.append(exc)
    postes = [v for v in admises if v != HERMES]
    if postes and not projet.get("depot_alias"):
        raise refus("sans_depot", T.SANS_DEPOT.format(titre=projet.get("titre"), ref=ref or classe))
    if not any(dernier_releve(conn, v) for v in postes):
        raise RefusACP("aucun_modele", T.AUCUN_MODELE.format(c=classe, raison=T.RAISON_AUCUN_RELEVE))
    if not entrees:
        raise RefusACP("aucun_modele", T.AUCUN_MODELE.format(c=classe, raison=T.RAISON_TABLE))
    quota = next((r for r in raisons if "quota à" in r.message), None)
    raise quota or raisons[0]


def _relecture_de_repli(conn, *, projet: Dict[str, Any], voie_relue: str, modele_relu: Optional[str], ref: str,
                        modele: Optional[str], raison_fermeture: str) -> Resolution:
    """D91 (appliqué) : l'autre voie est fermée ; la relecture va à la MÊME voie avec un modèle de la classe
    « relecture » différent de celui de l'implémentation (choix explicite, puis table pour cette voie), jamais le même.
    Sinon, refus ``relecture_impossible`` (la planification le dit ; carte de décision par le plafond du projet)."""
    candidats: List[Tuple[Optional[str], Optional[str], Optional[str], str]] = []
    if modele:
        candidats.append((modele, None, None, "choix_explicite"))
    candidats += [(e.get("modele"), e.get("effort"), e.get("palier"), "table")
                  for e in entrees_routage(conn, "relecture") if e.get("voie") == voie_relue]
    raisons: List[str] = []
    for modele_rel, effort_rel, palier_rel, source in candidats:
        if not modele_rel or modele_rel == modele_relu:
            raisons.append(T.REPLI_MEME_MODELE.format(m=modele_rel or T.INCONNU))
            continue
        try:
            r = valider_choix(conn, classe="relecture", projet=projet, voie=voie_relue, modele=modele_rel,
                              effort=effort_rel, palier=palier_rel, source=source, ref=ref)
        except RefusACP as exc:
            raisons.append(exc.message.removeprefix(T.PREFIXE_REFUS).rstrip("."))
            continue
        mention = T.MENTION_REPLI_MEME_VOIE.format(raison=raison_fermeture)
        return Resolution(voie=r.voie, modele=r.modele, effort=r.effort, effort_carte=r.effort_carte, palier=r.palier,
                          source_routage=r.source_routage, releve_id=r.releve_id,
                          mention=", ".join(m for m in (r.mention, mention) if m))
    raison = T.REPLI_IMPOSSIBLE.format(v=autre_voie(voie_relue), fermeture=raison_fermeture,
                                       detail="; ".join(raisons[:3]) or T.REPLI_SANS_ENTREE.format(v=voie_relue))
    raise refus("relecture_impossible", T.RELECTURE_IMPOSSIBLE.format(ref=ref, raison=raison))


def resoudre_relecture(conn, *, projet: Dict[str, Any], voie_relue: str, ref: str, modele: Optional[str] = None,
                       carte: Optional[str] = None, modele_relu: Optional[str] = None) -> Resolution:
    """Relecture CROISÉE : toujours l'autre voie du poste (décision D27 : refus plutôt qu'une relecture
    par la même voie). Modèle : surcharge, choix explicite (``relecture_modele``), table, sinon le modèle
    par défaut du relevé de l'autre voie et son effort par défaut (lus, jamais inventés).

    Étape P6 (D91, appliqué) : l'autre voie FERMÉE d'après le dernier inventaire, et le réglage
    ``relecture_repli_meme_voie`` levé : :func:`_relecture_de_repli`, jamais silencieux (mention)."""
    autre = autre_voie(voie_relue)
    fermee = voies_fermees(conn).get(autre)
    if fermee and base.reglage(conn, "relecture_repli_meme_voie"):
        return _relecture_de_repli(conn, projet=projet, voie_relue=voie_relue, modele_relu=modele_relu, ref=ref,
                                   modele=modele, raison_fermeture=fermee)
    try:
        if dernier_releve(conn, autre) is None:
            raise RefusACP("aucun_modele", f"aucun relevé pour {autre}")
        surcharge = surcharge_applicable(conn, "relecture", projet.get("id"), carte)
        if surcharge is not None and surcharge["voie"] == autre:
            return valider_choix(conn, classe="relecture", projet=projet, voie=autre, modele=surcharge["modele"],
                                 effort=surcharge["effort"], palier=surcharge["palier"],
                                 source="surcharge_" + surcharge["portee"], ref=ref)
        if modele:
            return valider_choix(conn, classe="relecture", projet=projet, voie=autre, modele=modele, effort=None,
                                 palier=None, source="choix_explicite", ref=ref)
        for entree in entrees_routage(conn, "relecture"):
            if entree.get("voie") != autre:
                continue
            try:
                return valider_choix(conn, classe="relecture", projet=projet, voie=autre, modele=entree.get("modele"),
                                     effort=entree.get("effort"), palier=entree.get("palier"), source="table", ref=ref)
            except RefusACP:
                continue
        return valider_choix(conn, classe="relecture", projet=projet, voie=autre, modele=None, effort=None,
                             palier=None, source="table", ref=ref)
    except RefusACP as exc:
        raison = exc.message
        for prefixe in (T.PREFIXE_REFUS,):
            if raison.startswith(prefixe):
                raison = raison[len(prefixe):]
        raise refus("relecture_impossible", T.RELECTURE_IMPOSSIBLE.format(ref=ref, raison=raison.rstrip("."))) from None


# ------------------------------------------------------------------ catalogue (outil poste_catalogue, route)


def badge(conn, voie: str, dernier: Optional[Tuple[int, Releve, int]] = None) -> str:
    """Badge de la page Routage pour la liste d'une voie : lu dans le relevé, jamais une appréciation."""
    dernier = dernier if dernier is not None else dernier_releve(conn, voie)
    if dernier is None:
        return "inconnu"
    releve_id, releve, releve_le = dernier
    if releve.source == "releve_factice":
        return "releve_factice"
    if releve.etat not in (None, "ok"):
        return "indisponible"
    if releve.origine_liste == "catalogue_embarque":
        return "liste_de_secours"
    if releve.origine_liste == "identique_au_catalogue_embarque":
        contexte = contexte_poste(conn, releve_id) or {}
        return "liste_acceptee" if contexte.get("accepte_le") else "liste_de_secours_probable"
    if base.maintenant() - releve_le > int(base.reglage(conn, "releve_perime_s") or 7200):
        return "perime"
    if releve.origine_liste == "alias_documentes":
        return "alias_documentes"
    return "releve_du_compte"


def catalogue(conn) -> Dict[str, Any]:
    """Ce que le greffon sait du poste : relevés par voie (datés, périmés ou non ; étape P5 : origine de la liste,
    état, compteurs de quotas, badge), modèle de Hermes, table de routage et politique. Sans relevé :
    ``etat: "inconnu"`` et le message."""
    maintenant = base.maintenant()
    perime_s = int(base.reglage(conn, "releve_perime_s") or 7200)
    voies: Dict[str, Any] = {}
    for voie in ka.VOIES_POSTE:
        dernier = dernier_releve(conn, voie)
        if dernier is None:
            voies[voie] = {"etat": "inconnu", "releve_le": None, "badge": "inconnu",
                           "badge_libelle": T.BADGES["inconnu"]}
            continue
        releve_id, releve, releve_le = dernier
        age = maintenant - releve_le
        genre = badge(conn, voie, dernier)
        voies[voie] = {
            "etat": "perime" if age > perime_s else "a_jour",
            "releve_id": releve_id,
            "releve_le": releve_le,
            "releve_le_lisible": date_lisible(releve_le),
            "age_s": age,
            "perime": age > perime_s,
            "source": releve.source,
            "version_cli": releve.version_cli,
            "modeles": [m.model_dump(mode="json") for m in releve.modeles],
            "quotas": releve.quotas.model_dump(mode="json") if releve.quotas else None,
            "depots": [d.alias for d in releve.depots],
            # Étape P5.
            "etat_releve": releve.etat,
            "origine_liste": releve.origine_liste,
            "detail": releve.detail,
            "documentation_lue_le": releve.documentation_lue_le.isoformat() if releve.documentation_lue_le else None,
            "compteurs": [c.model_dump(mode="json") for c in releve.compteurs],
            "badge": genre,
            "badge_libelle": T.BADGES[genre],
        }
    interdits, paliers = _politique(conn)
    routage = {l["classe"]: {"entrees": json.loads(l["entrees"]), "source": l["source"], "valide_le": l["valide_le"]}
               for l in conn.execute("SELECT * FROM routage ORDER BY classe")}
    connu = any(v.get("etat") != "inconnu" for v in voies.values())
    resultat: Dict[str, Any] = {
        "etat": "connu" if connu else "inconnu",
        "voies": voies,
        "hermes": {"modele": T.MODELE_DU_PROFIL},
        "routage": {"valide": bool(routage), "classes": routage},
        "politique": {"efforts_interdits": interdits, "paliers_admis": paliers,
                      "voies_par_classe": {c: list(v) for c, v in VOIES_PAR_CLASSE.items()}},
        "releve_factice": releve_factice_present(conn),
    }
    if not connu:
        resultat["message"] = T.CATALOGUE_INCONNU
    return resultat


# ------------------------------------------------------------------ page Routage (étape P5, cahier P5 § 12.3, § 13.2)

CLASSES_TABLE = tuple(c for c in VOIES_PAR_CLASSE if c != "integration")
PROJET_DE_VALIDATION = {"id": None, "titre": "table de routage", "depot_alias": "table"}
_VALEUR = re.compile(r"[a-z0-9][a-z0-9._\[\]-]{0,63}")
EFFORTS_HORS_ENVELOPPE = ("max", "ultra", "ultracode")


def admission(conn, classe: str, entree: Dict[str, Any]) -> Dict[str, Any]:
    """Une entrée de la table est-elle admise par le dernier relevé ? ``{"admise", "code", "message"}``."""
    try:
        resolution = valider_choix(conn, classe=classe, projet=PROJET_DE_VALIDATION, voie=entree.get("voie"),
                                   modele=entree.get("modele"), effort=entree.get("effort"),
                                   palier=entree.get("palier"), source="table")
    except RefusACP as exc:
        return {"admise": False, "code": exc.code, "message": exc.message}
    return {"admise": True, "code": None, "message": resolution.mention}


def suggestion(conn, classe: str) -> Dict[str, Any]:
    """Suggestion calculée sur les SEULS champs lus : pour chaque voie admise par la classe, le modèle
    ``isDefault`` du relevé, son effort par défaut et le palier ``default`` ; jamais une appréciation de qualité."""
    entrees, remarques = [], []
    dates = []
    for voie in VOIES_PAR_CLASSE.get(classe, ()):
        if voie == HERMES:
            entree = {"voie": HERMES, "modele": None, "effort": None, "palier": PALIER_PAR_DEFAUT}
            if admission(conn, classe, entree)["admise"]:
                entrees.append(entree)
            continue
        dernier = dernier_releve(conn, voie)
        if dernier is None:
            continue
        defaut = dernier[1].modele_par_defaut()
        if defaut is None:
            remarques.append(T.SUGGESTION_SANS_DEFAUT_CLAUDE if voie == "poste-claude"
                             else T.SUGGESTION_SANS_DEFAUT.format(v=voie))
            continue
        entree = {"voie": voie, "modele": defaut.id, "effort": defaut.defaultReasoningEffort,
                  "palier": PALIER_PAR_DEFAUT}
        verdict = admission(conn, classe, entree)
        if verdict["admise"]:
            entrees.append(entree)
            dates.append(dernier[2])
        else:
            remarques.append(verdict["message"])
    return {"entrees": entrees, "remarques": remarques,
            "libelle": T.SUGGESTION_DATEE.format(date=date_lisible(max(dates))) if dates else None}


def etat_de_la_table(conn, classe: str) -> Dict[str, Any]:
    ligne = conn.execute("SELECT * FROM routage WHERE classe = ?", (classe,)).fetchone()
    entrees = entrees_routage(conn, classe)
    verdicts = [dict(e, **admission(conn, classe, e)) for e in entrees]
    if ligne is None or ligne["source"] != "proprietaire":
        etat = "non_validee"
    elif any(not v["admise"] for v in verdicts):
        etat = "a_revalider"
    else:
        etat = "validee"
    return {"etat": etat, "entrees": verdicts, "source": ligne["source"] if ligne else None,
            "valide_le": ligne["valide_le"] if ligne else None, "valide_par": ligne["valide_par"] if ligne else None}


def surcharges_globales(conn) -> List[Dict[str, Any]]:
    return [base.ligne_en_dict(l) for l in conn.execute(
        "SELECT id, classe, voie, modele, effort, palier, motif, auteur, cree_le FROM surcharges WHERE active = 1 AND "
        "portee = 'globale' ORDER BY id DESC").fetchall()]


def vue_routage(conn) -> Dict[str, Any]:
    """Contenu de GET /v1/routage : listes lues par voie (badges), table par classe (état, verdict de chaque entrée,
    suggestion), politique de Hermes et politique du poste (lecture seule), surcharges globales actives."""
    cat = catalogue(conn)
    politique_poste = None
    for voie in ka.VOIES_POSTE:
        dernier = dernier_releve(conn, voie)
        contexte = contexte_poste(conn, dernier[0]) if dernier else None
        if contexte and contexte.get("politique"):
            politique_poste = contexte["politique"]
            break
    interdits, paliers = _politique(conn)
    return {
        "voies": cat["voies"],
        "releves": {v: cat["voies"][v].get("releve_id") for v in ka.VOIES_POSTE},
        "classes": {c: dict(etat_de_la_table(conn, c), voies=list(VOIES_PAR_CLASSE[c]), suggestion=suggestion(conn, c))
                    for c in CLASSES_TABLE},
        "politique_hermes": {"efforts_interdits": interdits, "paliers_admis": paliers,
                             "efforts_hors_enveloppe": list(EFFORTS_HORS_ENVELOPPE),
                             "confirmation": T.CONFIRMATION_DEPENSE},
        "politique_poste": politique_poste,
        "surcharges": surcharges_globales(conn),
        "releve_factice": cat["releve_factice"],
    }


def _entree_propre(entree: Any) -> Dict[str, Any]:
    if not isinstance(entree, dict) or set(entree) - {"voie", "modele", "effort", "palier"}:
        raise refus("table_invalide", T.TABLE_INVALIDE.format(detail="entrée {voie, modele, effort, palier} attendue"))
    propre = {"voie": entree.get("voie"), "modele": entree.get("modele") or None, "effort": entree.get("effort") or None,
              "palier": entree.get("palier") or None}
    for cle in ("voie", "modele", "effort", "palier"):
        if propre[cle] is not None and (not isinstance(propre[cle], str) or len(propre[cle]) > 128):
            raise refus("table_invalide", T.TABLE_INVALIDE.format(detail=f"« {cle} » doit être une chaîne courte"))
    return propre


def valider_table(conn, *, releves: Any, classes: Any, auteur: str) -> Dict[str, Any]:
    """Validation complète ou rien (POST /v1/routage) : les relevés vus par la page doivent être encore les derniers
    (409 sinon), chaque entrée doit être admise ; alors chaque classe est enregistrée ``source = proprietaire``."""
    if not isinstance(releves, dict) or not isinstance(classes, dict) or not classes:
        raise refus("table_invalide", T.TABLE_INVALIDE.format(detail="« releves » et « classes » attendus"))
    actuels = {v: (dernier_releve(conn, v) or (None,))[0] for v in ka.VOIES_POSTE}
    if {v: releves.get(v) for v in ka.VOIES_POSTE} != actuels:
        raise RefusACP("releve_change", T.RELEVE_CHANGE)
    propres: Dict[str, List[Dict[str, Any]]] = {}
    refus_par_entree: List[Dict[str, Any]] = []
    for classe, entrees in classes.items():
        if classe not in CLASSES_TABLE:
            raise refus("table_invalide", T.CLASSE_INCONNUE.format(c=str(classe)[:40]))
        if not isinstance(entrees, list) or not 1 <= len(entrees) <= 8:
            raise refus("table_invalide", T.TABLE_INVALIDE.format(detail=f"de 1 à 8 entrées pour « {classe} »"))
        propres[classe] = [_entree_propre(e) for e in entrees]
        for rang, entree in enumerate(propres[classe]):
            verdict = admission(conn, classe, entree)
            if not verdict["admise"]:
                refus_par_entree.append({"classe": classe, "rang": rang, "code": verdict["code"],
                                         "message": verdict["message"]})
    if refus_par_entree:
        exc = RefusACP("table_refusee", T.TABLE_REFUSEE.format(n=len(refus_par_entree)))
        exc.refus = refus_par_entree  # type: ignore[attr-defined]
        raise exc
    for classe, entrees in propres.items():
        enregistrer_routage(conn, classe, entrees, source="proprietaire", valide_par=auteur)
    return vue_routage(conn)


def _liste_de_valeurs(valeur: Any, cle: str) -> List[str]:
    if not isinstance(valeur, list) or len(valeur) > 32 or any(not isinstance(v, str) or not _VALEUR.fullmatch(v)
                                                               for v in valeur):
        raise refus("politique_invalide", T.POLITIQUE_INVALIDE.format(detail=f"« {cle} » : liste de valeurs courtes"))
    if len(set(valeur)) != len(valeur):
        raise refus("politique_invalide", T.POLITIQUE_INVALIDE.format(detail=f"« {cle} » contient un doublon"))
    return list(valeur)


def _motif(motif: Any) -> str:
    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 200:
        raise refus("motif", T.MOTIF_REQUIS)
    from .motifs_secrets import motif_trouve

    trouve = motif_trouve(motif)
    if trouve:
        raise refus("secret", T.SECRET_TEXTE.format(motif=trouve))
    return motif.strip()


def poser_politique(conn, *, efforts_interdits: Any, paliers_admis: Any, motif: Any, confirmation: Any,
                    auteur: str) -> Dict[str, Any]:
    """Interdits CÔTÉ HERMES (POST /v1/routage/politique). Lever un effort hors enveloppe (max, ultra, ultracode) ou
    admettre un palier autre que ``default`` exige la phrase de confirmation exacte. Ce que poste.toml interdit
    reste interdit (verifier_politique_du_poste)."""
    efforts = _liste_de_valeurs(efforts_interdits, "efforts_interdits")
    paliers = _liste_de_valeurs(paliers_admis, "paliers_admis")
    if not paliers:
        raise refus("politique_invalide", T.POLITIQUE_INVALIDE.format(detail="au moins un palier admis"))
    raison = _motif(motif)
    anciens_efforts, anciens_paliers = _politique(conn)
    leves = [e for e in EFFORTS_HORS_ENVELOPPE if e in anciens_efforts and e not in efforts]
    nouveaux_paliers = [p for p in paliers if p != PALIER_PAR_DEFAUT and p not in anciens_paliers]
    if (leves or nouveaux_paliers) and confirmation != T.CONFIRMATION_DEPENSE:
        objet = ", ".join([f"effort « {e} » levé" for e in leves] + [f"palier « {p} » admis" for p in nouveaux_paliers])
        raise refus("confirmation_requise", T.CONFIRMATION_REQUISE.format(objet=objet))
    base.poser_reglage(conn, "efforts_interdits", efforts, auteur)
    base.poser_reglage(conn, "paliers_admis", paliers, auteur)
    with base.transaction(conn):
        base.journaliser(conn, auteur, "politique_hermes", detail={"efforts_interdits": efforts, "paliers_admis": paliers,
                                                                   "motif": raison, "leves": leves,
                                                                   "paliers_ajoutes": nouveaux_paliers})
    return vue_routage(conn)


def creer_surcharge_globale(conn, *, classe: Any, voie: Any, modele: Any = None, effort: Any = None,
                            palier: Any = None, motif: Any, auteur: str) -> Dict[str, Any]:
    """Surcharge GLOBALE (POST /v1/routage/surcharges), vérifiée comme une entrée de table, puis enregistrée."""
    if classe not in CLASSES_TABLE:
        raise refus("table_invalide", T.CLASSE_INCONNUE.format(c=str(classe)[:40]))
    entree = _entree_propre({"voie": voie, "modele": modele, "effort": effort, "palier": palier})
    raison = _motif(motif)
    resolution = valider_choix(conn, classe=classe, projet=PROJET_DE_VALIDATION, voie=entree["voie"],
                               modele=entree["modele"], effort=entree["effort"], palier=entree["palier"],
                               source="surcharge_globale")
    with base.transaction(conn):
        curseur = conn.execute(
            "INSERT INTO surcharges (portee, cible, classe, voie, modele, effort, palier, motif, auteur, cree_le) "
            "VALUES ('globale', NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (classe, resolution.voie, entree["modele"], entree["effort"], entree["palier"], raison, auteur,
             base.maintenant()))
        base.journaliser(conn, auteur, "surcharge_globale", cible=classe,
                         detail={"voie": resolution.voie, "modele": resolution.modele, "effort": resolution.effort,
                                 "palier": resolution.palier, "motif": raison})
    return {"surcharge": int(curseur.lastrowid), "resolution": resolution.en_dict()}


def desactiver_surcharge(conn, identifiant: Any, auteur: str) -> Dict[str, Any]:
    try:
        numero = int(identifiant)
    except (TypeError, ValueError):
        raise refus("surcharge_inconnue", T.SURCHARGE_INCONNUE.format(i=str(identifiant)[:20])) from None
    with base.transaction(conn):
        if conn.execute("UPDATE surcharges SET active = 0 WHERE id = ? AND active = 1 AND portee = 'globale'",
                        (numero,)).rowcount != 1:
            raise refus("surcharge_inconnue", T.SURCHARGE_INCONNUE.format(i=numero))
        base.journaliser(conn, auteur, "surcharge_desactivee", cible=str(numero))
    return {"surcharges": surcharges_globales(conn)}


def accepter_releve(conn, releve_id: Any, auteur: str) -> Dict[str, Any]:
    """« Accepter ce relevé comme celui de mon compte » : un relevé Codex ``identique_au_catalogue_embarque``, encore
    le dernier de sa voie ; vaut pour CE relevé seulement (le suivant devra l'être à son tour)."""
    try:
        numero = int(releve_id)
    except (TypeError, ValueError):
        raise refus("releve_inconnu", T.RELEVE_INCONNU.format(i=str(releve_id)[:20])) from None
    with base.transaction(conn):
        ligne = conn.execute("SELECT id, voie, contenu FROM releves WHERE id = ?", (numero,)).fetchone()
        if ligne is None:
            raise refus("releve_inconnu", T.RELEVE_INCONNU.format(i=numero))
        try:
            origine = json.loads(ligne["contenu"]).get("origine_liste")
        except ValueError:
            origine = None
        if ligne["voie"] != "poste-codex" or origine != "identique_au_catalogue_embarque":
            raise refus("releve_non_acceptable", T.RELEVE_NON_ACCEPTABLE.format(origine=origine or T.INCONNU))
        dernier = conn.execute("SELECT id FROM releves WHERE voie = ? ORDER BY recu_le DESC, id DESC LIMIT 1",
                               (ligne["voie"],)).fetchone()
        if dernier is None or int(dernier[0]) != numero:
            raise refus("releve_plus_le_dernier", T.RELEVE_PLUS_LE_DERNIER.format(i=numero))
        conn.execute("UPDATE releves SET accepte_le = ?, accepte_par = ? WHERE id = ?",
                     (base.maintenant(), auteur, numero))
        base.journaliser(conn, auteur, "releve_accepte", cible=str(numero))
    return vue_routage(conn)
