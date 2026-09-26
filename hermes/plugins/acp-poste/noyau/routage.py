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
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import base
from . import kanban_adapter as ka
from . import textes as T
from .textes import RefusACP, refus

_CONTRAT = Path(__file__).resolve().parent.parent / "contrat"
if _CONTRAT.is_dir() and str(_CONTRAT) not in sys.path:
    # Contrat partagé avec le poste (décision D21) : importé par son chemin dans l'image.
    sys.path.insert(0, str(_CONTRAT))

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
    "integration": (),
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


def enregistrer_releve(conn, donnees: Any, *, recu_le: Optional[int] = None) -> int:
    """Valide le relevé (contrat partagé) puis l'enregistre ; rend son identifiant. C'est la fonction
    qu'appellera la route P5 ``/machine/v1/inventaire`` ; en P4, les tests seuls l'appellent, avec
    ``source: "releve_factice"``."""
    releve = valider_releve(donnees)
    contenu = releve.model_dump(mode="json")
    with base.transaction(conn):
        curseur = conn.execute(
            "INSERT INTO releves (voie, source, version_cli, releve_le, recu_le, contenu) VALUES (?, ?, ?, ?, ?, ?)",
            (releve.voie, releve.source, releve.version_cli, int(releve.releve_le.timestamp()),
             int(recu_le if recu_le is not None else base.maintenant()), json.dumps(contenu, ensure_ascii=False)))
        base.journaliser(conn, f"releve:{releve.source}", "releve", cible=releve.voie,
                         detail={"modeles": len(releve.modeles), "depots": len(releve.depots)})
        return int(curseur.lastrowid)


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
    if voie == HERMES:
        releve_id = None
        if modele:
            codex = dernier_releve(conn, "poste-codex")
            if codex is None or codex[1].modele(modele) is None:
                raise refus("modele_absent", T.MODELE_HERMES_ABSENT.format(
                    m=modele, date=date_lisible(codex[2]) if codex else T.INCONNU))
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
        raise refus("integration_p6", T.INTEGRATION_P6)
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


def resoudre_relecture(conn, *, projet: Dict[str, Any], voie_relue: str, ref: str, modele: Optional[str] = None,
                       carte: Optional[str] = None) -> Resolution:
    """Relecture CROISÉE : toujours l'autre voie du poste (décision D27 : refus plutôt qu'une relecture
    par la même voie). Modèle : surcharge, choix explicite (``relecture_modele``), table, sinon le modèle
    par défaut du relevé de l'autre voie et son effort par défaut (lus, jamais inventés)."""
    autre = autre_voie(voie_relue)
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


def catalogue(conn) -> Dict[str, Any]:
    """Ce que le greffon sait du poste : relevés par voie (datés, périmés ou non), modèle de Hermes,
    table de routage et politique. Sans relevé : ``etat: "inconnu"`` et le message P5."""
    maintenant = base.maintenant()
    perime_s = int(base.reglage(conn, "releve_perime_s") or 7200)
    voies: Dict[str, Any] = {}
    for voie in ka.VOIES_POSTE:
        dernier = dernier_releve(conn, voie)
        if dernier is None:
            voies[voie] = {"etat": "inconnu", "releve_le": None}
            continue
        _id, releve, releve_le = dernier
        age = maintenant - releve_le
        voies[voie] = {
            "etat": "perime" if age > perime_s else "a_jour",
            "releve_le": releve_le,
            "releve_le_lisible": date_lisible(releve_le),
            "age_s": age,
            "perime": age > perime_s,
            "source": releve.source,
            "version_cli": releve.version_cli,
            "modeles": [m.model_dump(mode="json") for m in releve.modeles],
            "quotas": releve.quotas.model_dump(mode="json") if releve.quotas else None,
            "depots": [d.alias for d in releve.depots],
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
