"""Vérificateur du catalogue (scripts/verifier_catalogue.py) : le dépôt est conforme, et chaque
règle rougit sur une copie altérée (un témoin par règle). Bibliothèque standard seulement, comme le
script ; la lecture des skills par le chargeur de Hermes est vérifiée dans l'image
(hermes/tests/image/test_catalogue.py)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pytest

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("verifier_catalogue", RACINE / "scripts" / "verifier_catalogue.py")
assert _SPEC is not None and _SPEC.loader is not None
vc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vc)


@pytest.fixture
def copie(tmp_path: Path) -> Path:
    """Copie des fichiers lus par le vérificateur (hors dépôt git : les modes de l'index sont ignorés)."""
    for relatif in ("hermes/skills", "hermes/catalogue"):
        shutil.copytree(RACINE / relatif, tmp_path / relatif)
    for relatif in ("hermes/THIRD_PARTY.md", "hermes/plugins/acp-poste/garde_execution.py",
                    "hermes/image/acp_demarrage.py"):
        (tmp_path / relatif).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RACINE / relatif, tmp_path / relatif)
    return tmp_path


def _verifier(racine: Path, **options) -> List[str]:
    return vc.Verification(vc.Chemins(racine)).tout(**options)


def _verrou(racine: Path) -> Dict:
    return json.loads((racine / "hermes/catalogue/catalogue.lock.json").read_text(encoding="utf-8"))


def _ecrire_verrou(racine: Path, verrou: Dict) -> None:
    (racine / "hermes/catalogue/catalogue.lock.json").write_text(
        json.dumps(verrou, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _modifier_verrou(racine: Path, modification: Callable[[Dict], None]) -> None:
    verrou = _verrou(racine)
    modification(verrou)
    _ecrire_verrou(racine, verrou)


def _skill(verrou: Dict, nom: str) -> Dict:
    return next(s for s in verrou["skills"] if s["nom"] == nom)


def _reecrire_skill(racine: Path, nom: str, fichier: str, contenu: bytes) -> None:
    """Réécrit un fichier d'une skill ET son empreinte au verrou : isole la règle visée de la règle 1."""
    verrou = _verrou(racine)
    skill = _skill(verrou, nom)
    (racine / "hermes/skills" / skill["chemin"] / fichier).write_bytes(contenu)
    entree = skill["fichiers"].setdefault(fichier, {})
    entree["sha256"] = vc.sha256(contenu)
    if "blob_git" in entree:
        entree["blob_git"] = vc.blob_git(contenu)
    _ecrire_verrou(racine, verrou)


def _un_ecart(erreurs: List[str], fragment: str) -> None:
    assert any(fragment in e for e in erreurs), f"« {fragment} » attendu parmi : {erreurs}"


# ------------------------------------------------------------------------------------ dépôt réel


def test_le_depot_est_conforme():
    verification = vc.Verification(vc.Chemins(RACINE))
    assert verification.tout() == []
    verrou = verification.verrou
    hermes = [s for s in verrou["skills"] if s["cible"] == "hermes"]
    # 16 en P3 ; l'étape P4 ajoute cinq skills maison des projets (acp-exploration, acp-orchestration, acp-routage,
    # acp-synthese, acp-questions), chargées par les cartes et rattachées à aucun profil.
    assert len(hermes) == 21 and sum(1 for s in hermes if s["source"] == "acp") == 7
    projets = {s["nom"]: s for s in hermes if s["nom"] in {"acp-exploration", "acp-orchestration", "acp-routage",
                                                            "acp-synthese", "acp-questions"}}
    assert len(projets) == 5 and all(s["profils"] == [] and s["execution"] == "aucune" for s in projets.values())
    assert len(verrou["livrees"]["noms"]) == 58 and len(verrou["livrees"]["optionnelles"]) == 150
    assert [m["nom"] for m in verrou["mcp"] if m["cible"] == "hermes"] == ["context7"]


def test_la_copie_est_conforme(copie):
    assert _verifier(copie) == []


def test_main_code_et_message(capsys):
    assert vc.main([]) == 0
    assert "Catalogue conforme : 21 skills livrées dans l'image" in capsys.readouterr().out


# ------------------------------------------------------------------------------------ règle 1


def test_fichier_modifie(copie):
    fichier = copie / "hermes/skills/ecc/accessibility/SKILL.md"
    fichier.write_bytes(fichier.read_bytes() + b"\nligne ajoutee\n")
    _un_ecart(_verifier(copie), "hermes/skills/ecc/accessibility/SKILL.md a été modifié")


def test_fichier_ajoute_hors_catalogue(copie):
    (copie / "hermes/skills/ecc/intrus").mkdir()
    (copie / "hermes/skills/ecc/intrus/SKILL.md").write_text("---\nname: intrus\n---\n", encoding="utf-8")
    _un_ecart(_verifier(copie), "hermes/skills/ecc/intrus/SKILL.md n'est pas au verrou")


def test_fichier_du_verrou_absent(copie):
    (copie / "hermes/skills/emil-kowalski/animate/RECIPES.md").unlink()
    _un_ecart(_verifier(copie), "hermes/skills/emil-kowalski/animate/RECIPES.md est au verrou mais absent")


def test_blob_git_different_du_depot_amont(copie):
    """Même contenu, SHA-256 recalculé au verrou, mais blob git d'origine : le fichier n'est plus
    celui du dépôt amont."""
    verrou = _verrou(copie)
    skill = _skill(verrou, "minimalist-ui")
    fichier = copie / "hermes/skills" / skill["chemin"] / "SKILL.md"
    contenu = fichier.read_bytes().replace(b"\n", b"\r\n")
    fichier.write_bytes(contenu)
    skill["fichiers"]["SKILL.md"]["sha256"] = vc.sha256(contenu)
    _ecrire_verrou(copie, verrou)
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "le fichier n'est plus celui du dépôt amont")
    assert not any("a été modifié" in e for e in erreurs)


# ------------------------------------------------------------------------------------ règle 2


def test_licence_retiree(copie):
    (copie / "hermes/skills/taste-skill/LICENSE").unlink()
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "hermes/skills/taste-skill/LICENSE est au verrou mais absent")
    _un_ecart(erreurs, "(licence non livrée)")


def test_licence_non_libre(copie):
    _modifier_verrou(copie, lambda v: v["sources"]["affaan-m/ECC"].update(licence="GPL-3.0"))
    _un_ecart(_verifier(copie), "licence « GPL-3.0 » hors de la liste admise")


def test_provenance_sans_commit(copie):
    fichier = copie / "hermes/skills/emil-kowalski/PROVENANCE.md"
    texte = fichier.read_text(encoding="utf-8").replace("d16ebe60d09a5ba2afcb7054ede9d0a10c9f6128", "d16ebe60")
    fichier.write_text(texte, encoding="utf-8")
    _modifier_verrou(copie, lambda v: v["categories"]["emil-kowalski"]["fichiers"]["PROVENANCE.md"].update(
        sha256=vc.sha256(fichier.read_bytes())))
    _un_ecart(_verifier(copie), "PROVENANCE.md ne cite pas « d16ebe60d09a5ba2afcb7054ede9d0a10c9f6128 »")


def test_third_party_sans_texte_de_licence(copie):
    fichier = copie / "hermes/THIRD_PARTY.md"
    fichier.write_text(fichier.read_text(encoding="utf-8").replace("Copyright (c) 2026 Leonxlnx", "Copyright"),
                       encoding="utf-8")
    _un_ecart(_verifier(copie), "leonxlnx/taste-skill : THIRD_PARTY.md ne reprend pas le texte exact de LICENSE")


# ------------------------------------------------------------------------------------ règles 3 à 6


def test_nom_du_frontmatter_different(copie):
    fichier = copie / "hermes/skills/ecc/python-patterns/SKILL.md"
    _reecrire_skill(copie, "python-patterns", "SKILL.md",
                    fichier.read_bytes().replace(b"name: python-patterns", b"name: autre-nom", 1))
    _un_ecart(_verifier(copie), "skill python-patterns : le frontmatter déclare « autre-nom »")


def test_collision_avec_une_skill_livree(copie):
    def ajouter(v):
        v["skills"].append({"nom": "systematic-debugging", "source": "affaan-m/ECC", "chemin_amont": "skills/x",
                            "cible": "poste", "etat": "candidate-poste", "profils": [], "description_fr": "x",
                            "raison": "x"})
    _modifier_verrou(copie, ajouter)
    _un_ecart(_verifier(copie), "collision : « systematic-debugging » est aussi une skill livrée par Hermes")


def test_collision_avec_une_skill_optionnelle(copie):
    optionnelle = _verrou(copie)["livrees"]["optionnelles"][0]

    def ajouter(v):
        v["skills"].append({"nom": optionnelle, "source": "affaan-m/ECC", "chemin_amont": "skills/x",
                            "cible": "poste", "etat": "candidate-poste", "profils": [], "description_fr": "x",
                            "raison": "x"})
    _modifier_verrou(copie, ajouter)
    _un_ecart(_verifier(copie), f"collision : « {optionnelle} » est aussi une skill optionnelle de Hermes")


def test_collision_interne(copie):
    def doubler(v):
        v["skills"].append(dict(_skill(v, "benchmark")))
    _modifier_verrou(copie, doubler)
    _un_ecart(_verifier(copie), "collision : la skill « benchmark » apparaît 2 fois")


def test_skill_exclue_au_catalogue(copie):
    def ajouter(v):
        v["skills"].append({"nom": "agent-reach", "source": "affaan-m/ECC", "chemin_amont": "skills/x",
                            "cible": "poste", "etat": "candidate-poste", "profils": [], "description_fr": "x",
                            "raison": "x"})
    _modifier_verrou(copie, ajouter)
    _un_ecart(_verifier(copie), "« agent-reach » est au catalogue ET dans les exclus")


def test_skill_anthropic_proprietaire_refusee(copie):
    def ajouter(v):
        v["sources"]["anthropics/skills"] = {"url": "https://github.com/anthropics/skills", "commit": "0" * 40,
                                             "licence": "MIT", "auteur": "Anthropic", "categorie": "anthropic",
                                             "vendorisee": True}
        v["skills"].append({"nom": "pptx", "source": "anthropics/skills", "chemin_amont": "skills/pptx",
                            "cible": "poste", "etat": "candidate-poste", "profils": [], "description_fr": "x",
                            "raison": "x"})
    _modifier_verrou(copie, ajouter)
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "anthropics/skills ne peut pas être vendorisé")
    _un_ecart(erreurs, "la skill pptx d'anthropics/skills est refusée")


def test_exclusion_anthropic_retiree(copie):
    _modifier_verrou(copie, lambda v: v.update(exclus=[e for e in v["exclus"] if e["nom"] != "xlsx"]))
    _un_ecart(_verifier(copie), "l'exclusion de « xlsx » (anthropics/skills, licence propriétaire) manque")


@pytest.mark.parametrize("source, nom", [("anthropics/skills", "frontend-design"), ("obra/superpowers", "superpowers"),
                                         ("emilkowalski/skills", "write-swift")])
def test_skill_recommandee_par_le_plan_non_classee(copie, source, nom):
    """Relecture de P3 : une skill recommandée par le plan doit être au catalogue ou aux exclus."""
    _modifier_verrou(copie, lambda v: v.update(exclus=[e for e in v["exclus"] if e["nom"] != nom]))
    _un_ecart(_verifier(copie), f"« {nom} » ({source}), recommandée par le plan de la refonte")


def test_exclusion_d_une_autre_source_ne_classe_pas_la_skill(copie):
    def deplacer(v):
        next(e for e in v["exclus"] if e["nom"] == "mcp-builder")["source"] = "affaan-m/ECC"
    _modifier_verrou(copie, deplacer)
    _un_ecart(_verifier(copie), "« mcp-builder » (anthropics/skills), recommandée par le plan de la refonte")


def test_scripts_dans_une_skill_hermes(copie):
    dossier = copie / "hermes/skills/ecc/security-review/scripts"
    dossier.mkdir()
    (dossier / "audit.py").write_text("print('x')\n", encoding="utf-8")
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "hermes/skills/ecc/security-review/scripts : sous-dossier refusé")
    _un_ecart(erreurs, "seul le Markdown est admis")


def test_fichier_non_markdown_au_verrou(copie):
    _reecrire_skill(copie, "animate", "outil.sh", b"#!/bin/sh\necho x\n")
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "« outil.sh » n'est pas un texte Markdown")
    _un_ecart(erreurs, "hermes/skills/emil-kowalski/animate/outil.sh : seul le Markdown est admis")


def test_shell_en_ligne_refuse(copie):
    fichier = copie / "hermes/skills/acp/acp-redaction/SKILL.md"
    _reecrire_skill(copie, "acp-redaction", "SKILL.md", fichier.read_bytes() + "\nÉtat : !`id`\n".encode("utf-8"))
    _un_ecart(_verifier(copie), "commande « !`…` » refusée")


def test_metadata_hermes_config_refusee(copie):
    fichier = copie / "hermes/skills/acp/acp-profils/SKILL.md"
    contenu = fichier.read_bytes().replace(b"\n---\n", b"\nmetadata:\n  hermes:\n    config:\n      - cle: x\n---\n", 1)
    _reecrire_skill(copie, "acp-profils", "SKILL.md", contenu)
    _un_ecart(_verifier(copie), "clé metadata.hermes.config refusée")


def test_skill_poste_livree_dans_l_image(copie):
    (copie / "hermes/skills/emil-kowalski/prototype").mkdir()
    (copie / "hermes/skills/emil-kowalski/prototype/SKILL.md").write_text("---\nname: prototype\n---\n", encoding="utf-8")
    _modifier_verrou(copie, lambda v: _skill(v, "prototype").update(chemin="emil-kowalski/prototype"))
    _un_ecart(_verifier(copie), "skill prototype : cible poste, elle ne doit pas être livrée dans l'image")


# ------------------------------------------------------------------------------------ règle 10


def test_skill_poste_promise_en_p8_refusee(copie):
    """Relecture de P3 : le plan d'autonomie ne prévoit aucune skill au poste en P8."""
    _modifier_verrou(copie, lambda v: _skill(v, "benchmark").update(etat="reportee-p8"))
    _un_ecart(_verifier(copie), "skill benchmark : état « reportee-p8 » invalide pour la cible poste")


def test_mcp_poste_promis_en_p8_hors_du_plan_refuse(copie):
    """Relecture de P3 : Figma est « hors v1 » au plan, pas une livraison de P8."""
    def promettre(v):
        next(m for m in v["mcp"] if m["nom"] == "figma")["etat"] = "reporte-p8"
    _modifier_verrou(copie, promettre)
    _un_ecart(_verifier(copie), "MCP figma : « reporte-p8 » promet une livraison que le plan d'autonomie (P8)")


def test_mcp_poste_etat_inconnu_refuse(copie):
    def inventer(v):
        next(m for m in v["mcp"] if m["nom"] == "playwright")["etat"] = "livre"
    _modifier_verrou(copie, inventer)
    _un_ecart(_verifier(copie), "MCP playwright : cible poste, état « livre » invalide")


# ------------------------------------------------------------------------------------ règle 7


def test_outil_mcp_absent_de_la_garde(copie):
    garde = copie / "hermes/plugins/acp-poste/garde_execution.py"
    garde.write_text(garde.read_text(encoding="utf-8").replace('"mcp__context7__query_docs",', ""), encoding="utf-8")
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "l'outil mcp__context7__query_docs n'est pas dans OUTILS_ADMIS")


def test_outil_mcp_en_trop_dans_la_garde(copie):
    garde = copie / "hermes/plugins/acp-poste/garde_execution.py"
    garde.write_text(garde.read_text(encoding="utf-8").replace(
        '"mcp__context7__query_docs",', '"mcp__context7__query_docs", "mcp__intrus__outil",'), encoding="utf-8")
    _un_ecart(_verifier(copie), "OUTILS_ADMIS admet les outils MCP")


def test_nom_hermes_d_un_outil_mcp(copie):
    _modifier_verrou(copie, lambda v: v["mcp"][0].update(outils_hermes=["mcp__context7__resolve-library-id",
                                                                        "mcp__context7__query_docs"]))
    _un_ecart(_verifier(copie), "Hermes les nomme ['mcp__context7__resolve_library_id'")


@pytest.mark.parametrize("avant, apres, fragment", [
    ('("mcp_servers.context7.sampling.enabled", False)', '("mcp_servers.context7.sampling.enabled", True)',
     "mcp_servers.context7.sampling.enabled vaut True"),
    ('("mcp_servers.context7.url", "https://mcp.context7.com/mcp"),', "",
     "l'épingle mcp_servers.context7.url manque"),
    ('"clarify",\n                               "context7"]', '"clarify",\n                               "no_mcp"]',
     "absent de platform_toolsets.cli"),
    ('("platform_toolsets.cron", ["web", "vision", "skills", "todo", "memory", "session_search", "no_mcp"])',
     '("platform_toolsets.cron", ["web", "vision", "skills", "todo", "memory", "session_search", "context7"])',
     "platform_toolsets.cron doit garder no_mcp"),
    ('    ("skills.inline_shell", False),', '    ("skills.inline_shell", False),\n    ("skills.external_dirs", []),',
     "skills.external_dirs ne doit PAS être épinglé"),
])
def test_epingles_mcp_et_skills(copie, avant, apres, fragment):
    fichier = copie / "hermes/image/acp_demarrage.py"
    texte = fichier.read_text(encoding="utf-8")
    assert avant in texte, avant
    fichier.write_text(texte.replace(avant, apres), encoding="utf-8")
    _un_ecart(_verifier(copie), fragment)


def test_mcp_local_refuse_cote_hermes(copie):
    _modifier_verrou(copie, lambda v: v["mcp"][0].update(transport="stdio", url="npx"))
    _un_ecart(_verifier(copie), "seul un serveur distant en https est admis côté Hermes")


# ------------------------------------------------------------------------------------ règles 8 et 9


def test_hermes_agent_jamais_desactivee(copie):
    def desactiver(v):
        v["livrees"]["gardees"] = [e for e in v["livrees"]["gardees"] if e["nom"] != "hermes-agent"]
        v["livrees"]["desactivees_par_acp"].append({"nom": "hermes-agent", "raison": "x"})
    _modifier_verrou(copie, desactiver)
    _un_ecart(_verifier(copie), "« hermes-agent » est essentielle")


def test_skill_livree_non_classee(copie):
    _modifier_verrou(copie, lambda v: v["livrees"].update(
        gardees=[e for e in v["livrees"]["gardees"] if e["nom"] != "arxiv"]))
    erreurs = _verifier(copie)
    _un_ecart(erreurs, "« arxiv » doit être classée exactement une fois")
    _un_ecart(erreurs, "profil recherche : arxiv n'est ni au catalogue ni une skill livrée gardée")


def test_profil_cite_une_skill_desactivee(copie):
    _modifier_verrou(copie, lambda v: v["profils"]["web"]["skills_hermes"].append("dogfood"))
    _un_ecart(_verifier(copie), "profil web : dogfood n'est ni au catalogue ni une skill livrée gardée")


def test_profils_d_une_skill_incoherents(copie):
    _modifier_verrou(copie, lambda v: _skill(v, "accessibility").update(profils=["web", "donnees"]))
    _un_ecart(_verifier(copie), "accessibility : profils déclarés ['donnees', 'web'] ; cité par ['web']")


def test_acp_profils_doit_citer_chaque_skill(copie):
    fichier = copie / "hermes/skills/acp/acp-profils/SKILL.md"
    _reecrire_skill(copie, "acp-profils", "SKILL.md",
                    fichier.read_bytes().replace(b"`mle-workflow`", b"mle-workflow"))
    _un_ecart(_verifier(copie), "la skill acp-profils ne cite pas `mle-workflow`")


# ------------------------------------------------------------------------------------ --amont


def _faux_amont(racine: Path, *, changer: Optional[str] = None, absent: Optional[str] = None,
                notice: bool = False, panne: bool = False):
    """Réponses « amont » tirées de la copie locale (via le verrou), éventuellement altérées."""
    verrou = _verrou(racine)
    table = {}
    for id_source, source in verrou["sources"].items():
        if not source.get("vendorisee"):
            continue
        base = f"https://raw.githubusercontent.com/{id_source}/{source['commit']}/"
        table[base + "LICENSE"] = (racine / "hermes/skills" / source["categorie"] / "LICENSE").read_bytes()
        for skill in verrou["skills"]:
            if skill.get("source") == id_source and skill["cible"] == "hermes":
                for f in skill["fichiers"]:
                    table[base + f"{skill['chemin_amont']}/{f}"] = (racine / "hermes/skills" / skill["chemin"] / f).read_bytes()
    appels = []

    def telecharger(url: str):
        appels.append(url)
        if panne:
            raise OSError("réseau coupé")
        if notice and url.endswith("/NOTICE"):
            return b"notice"
        if absent and url.endswith(absent):
            return None
        contenu = table.get(url)
        if contenu is not None and changer and url.endswith(changer):
            return contenu + b"\nmodifie en amont\n"
        return contenu
    return telecharger, appels


def test_amont_conforme(copie):
    telecharger, appels = _faux_amont(copie)
    assert _verifier(copie, amont=True, telecharger=telecharger) == []
    # 3 LICENSE + 17 fichiers de skills + 3×3 recherches de NOTICE.
    assert len(appels) == 3 + 17 + 9


def test_amont_different(copie):
    telecharger, _ = _faux_amont(copie, changer="skills/soft-skill/SKILL.md")
    _un_ecart(_verifier(copie, amont=True, telecharger=telecharger),
              "amont : hermes/skills/taste-skill/high-end-visual-design/SKILL.md diffère")


def test_amont_absent(copie):
    telecharger, _ = _faux_amont(copie, absent="skills/mle-workflow/SKILL.md")
    _un_ecart(_verifier(copie, amont=True, telecharger=telecharger), "n'existe pas (404) au commit épinglé")


def test_amont_notice_non_livre(copie):
    telecharger, _ = _faux_amont(copie, notice=True)
    _un_ecart(_verifier(copie, amont=True, telecharger=telecharger), "publie un fichier NOTICE")


def test_amont_injoignable_echoue_ferme(copie):
    telecharger, _ = _faux_amont(copie, panne=True)
    _un_ecart(_verifier(copie, amont=True, telecharger=telecharger), "injoignable (OSError : réseau coupé)")


def test_telechargement_limite_a_github():
    with pytest.raises(ValueError):
        vc.telecharger_https("https://exemple.test/LICENSE")


# ------------------------------------------------------------------------------------ outils


def test_nom_mcp_hermes():
    assert vc.nom_mcp_hermes("context7", "resolve-library-id") == "mcp__context7__resolve_library_id"
    assert vc.nom_mcp_hermes("mon.serveur", "a b") == "mcp__mon_serveur__a_b"


def test_frontmatter():
    texte = ("---\nname: \"exemple\"\ndescription: x\nmetadata:\n  hermes:\n    tags: [a]\n  origin: ECC\n---\n"
             "name: corps\n")
    nom, cles = vc.frontmatter(texte)
    assert nom == "exemple"
    assert {"name", "description", "metadata", "metadata.hermes", "metadata.hermes.tags", "metadata.origin"} == cles
    assert vc.frontmatter("# pas de frontmatter\n") == (None, set())
