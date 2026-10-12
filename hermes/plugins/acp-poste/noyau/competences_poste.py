"""Applications textuelles du catalogue dans les consignes du poste, sans exécution serveur.

Seuls les profils explicitement porteurs de skills_poste et les classes/rôles déclarés sont
concernés. Les textes ACP adaptés sont vérifiés avant la réservation des cartes ; un fichier
absent, altéré ou trop long refuse le plan, sans changer la consigne du propriétaire.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .textes import refus

VERROU = Path("/opt/acp/catalogue/catalogue.lock.json")
SKILLS = Path("/opt/acp/skills")
MAXIMUM_CONSIGNE = 16_000
MAXIMUM_OCTETS = 32_000
_NOM = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _refuser(detail: str):
    return refus("competences_poste", "Compétences du poste indisponibles : " + detail
                 + ". Vérifiez le catalogue livré sur le serveur.")


def appliquer(consigne: str, *, profil: str, classe: str, role: str, voie: str) -> str:
    """Ajoute seulement les applications correspondant au profil et à cette mission.

    Base ne porte aucune application tierce (invariant contrôlé par le validateur). Les autres
    profils échouent fermés si le catalogue manque ; aucune lecture du volume utilisateur.
    """
    if voie not in ("poste-codex", "poste-claude") or profil == "base":
        return consigne
    if profil not in ("web", "donnees", "recherche"):
        raise _refuser("profil de projet inconnu")
    try:
        if VERROU.stat().st_size > 512 * 1024:
            raise ValueError("verrou trop volumineux")
        verrou = json.loads(VERROU.read_text(encoding="utf-8"))
        if verrou.get("schema") != "acp-catalogue/1":
            raise ValueError("schéma inconnu")
        noms = verrou["profils"][profil]["skills_poste"]
        if (not isinstance(noms, list) or len(noms) > 12 or not all(isinstance(n, str) and _NOM.fullmatch(n) for n in noms)
                or len(set(noms)) != len(noms)):
            raise ValueError("applications de profil invalides")
        skills = verrou["skills"]
        blocs = []
        for nom in noms:
            correspondantes = [s for s in skills if isinstance(s, dict) and s.get("nom") == nom]
            if len(correspondantes) != 1:
                raise ValueError("compétence absente ou ambiguë")
            skill = correspondantes[0]
            application = skill["application_poste"]
            if (skill.get("cible") != "hermes" or skill.get("etat") != "livree"
                    or skill.get("execution") != "aucune" or profil not in skill.get("profils", [])):
                raise ValueError("compétence non autorisée pour ce profil")
            if (not isinstance(application.get("classes"), list) or not isinstance(application.get("roles"), list)
                    or application.get("fichier") != "POSTE.md"):
                raise ValueError("application invalide")
            if classe not in application["classes"] or role not in application["roles"]:
                continue
            source = verrou["sources"][skill["source"]]
            categorie = source["categorie"]
            if (not isinstance(categorie, str) or not _NOM.fullmatch(categorie)
                    or skill.get("chemin") != f"{categorie}/{nom}"):
                raise ValueError("chemin de compétence invalide")
            chemin = SKILLS / categorie / nom / "POSTE.md"
            # Refus également des liens intermédiaires et jonctions Windows.
            for element in (SKILLS, SKILLS / categorie, chemin.parent, chemin):
                if element.is_symlink() or (hasattr(element, "is_junction") and element.is_junction()):
                    raise ValueError("lien de compétence refusé")
            if not chemin.resolve().is_relative_to(SKILLS.resolve()) or chemin.stat().st_size > 6000:
                raise ValueError("application hors limites")
            contenu = chemin.read_bytes()
            entree = skill["fichiers"]["POSTE.md"]
            if (entree.get("origine") != "adaptation-acp"
                    or hashlib.sha256(contenu).hexdigest() != entree.get("sha256")):
                raise ValueError("empreinte de compétence différente")
            texte = contenu.decode("utf-8").strip()
            if not texte or len(texte) > 3000:
                raise ValueError("application vide ou trop longue")
            blocs.append(f"## Compétence {nom}\n{texte}")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
        raise _refuser("configuration absente, invalide ou modifiée") from None
    if not blocs:
        return consigne
    resultat = (consigne + "\n\n---\n# Applications ACP du profil " + profil
                + "\n\nCes adaptations valent uniquement pour cette mission. Les consignes du propriétaire et du dépôt "
                  "priment ; elles n’ajoutent aucun outil ni autorisation. N’exécutez aucun plugin ou hook de ces sources.\n\n"
                + "\n\n".join(blocs))
    if len(resultat) > MAXIMUM_CONSIGNE or len(resultat.encode("utf-8")) > MAXIMUM_OCTETS:
        raise _refuser("la consigne et ses compétences dépassent la limite de la tâche ; réduisez la consigne")
    return resultat
