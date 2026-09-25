"""Étape P3 : catalogue de skills épinglé, dans l'image de test, contre le code de Hermes à la version
épinglée.

- Les skills livrées sous /opt/acp/skills sont celles du verrou (empreintes), root 0755/0644, texte
  seul, lues par le chargeur de Hermes sous le nom du verrou, sans verdict « dangerous » de son
  analyse de sécurité, sans collision avec les skills livrées ou optionnelles RÉELLES de l'image.
- Hermes lit skills.external_dirs et skills.disabled dans le config.yaml du volume SANS la managed
  scope (constat C1, témoin ci-dessous) : 05-acp les y écrit (appliquer_reglages_skills), sans rien
  perdre du reste du fichier, et n'écrit rien d'autre.
- Avec ces réglages, le chargeur voit exactement le catalogue, et GET /api/skills liste exactement
  les skills livrées visibles sur Linux et celles d'ACP, drapeaux « enabled » conformes au verrou.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

import acp_demarrage as ad
from conftest import env_processus, executer_python, installer_home_de_test, lancer_outil

UID_HERMES = 10000
RACINE = Path("/opt/acp/skills")
VERROU = json.loads(Path("/opt/acp/catalogue/catalogue.lock.json").read_text(encoding="utf-8"))
SKILLS_HERMES = [s for s in VERROU["skills"] if s["cible"] == "hermes"]
NOMS_ACP = sorted(s["nom"] for s in SKILLS_HERMES)
DESACTIVEES = sorted(e["nom"] for e in VERROU["livrees"]["desactivees_par_acp"])
GARDEES = sorted(e["nom"] for e in VERROU["livrees"]["gardees"])
MACOS = sorted(VERROU["livrees"]["macos_seulement"])
# Skill livrée dont le frontmatter porte « environments: [kanban] » : Hermes ne l'offre que dans un
# worker kanban (agent/skill_utils.py:201-208), y compris dans GET /api/skills.
CACHEES_HORS_KANBAN = ["sdlc-review"]


def _noms_reels(racine: Path) -> dict:
    code = ("import json; from pathlib import Path; "
            "from agent.skill_utils import iter_skill_index_files, parse_frontmatter; resultat = {}\n"
            f"for p in iter_skill_index_files(Path({str(racine)!r}), 'SKILL.md'):\n"
            "    fm, _ = parse_frontmatter(p.read_text(encoding='utf-8')[:4000])\n"
            "    resultat.setdefault(fm.get('name', p.parent.name), []).append(str(p.parent))")
    return executer_python(code, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})


# =============================================================== fichiers livrés


def test_les_fichiers_livres_sont_ceux_du_verrou_root_et_texte_seul():
    attendus = {}
    for categorie, bloc in VERROU["categories"].items():
        for nom, entree in bloc["fichiers"].items():
            attendus[f"{categorie}/{nom}"] = entree["sha256"]
    for skill in SKILLS_HERMES:
        for nom, entree in skill["fichiers"].items():
            attendus[f"{skill['chemin']}/{nom}"] = entree["sha256"]
    presents = {}
    for dossier, sous, fichiers in os.walk(RACINE):
        st = os.lstat(dossier)
        assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o755, dossier
        for nom in fichiers:
            chemin = Path(dossier) / nom
            st = os.lstat(chemin)
            assert stat.S_ISREG(st.st_mode) and st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644, chemin
            assert chemin.suffix == ".md" or nom == "LICENSE", chemin
            presents[chemin.relative_to(RACINE).as_posix()] = hashlib.sha256(chemin.read_bytes()).hexdigest()
    assert presents == attendus
    for fichier in ("/opt/acp/catalogue/catalogue.lock.json", "/opt/acp/THIRD_PARTY.md"):
        st = os.lstat(fichier)
        assert st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o644, fichier
    print(f"{len(presents)} fichiers sous {RACINE}, identiques au verrou.")


def test_l_uid_hermes_ne_peut_rien_ecrire_sous_opt_acp():
    """Le curateur et la revue de Hermes refusent d'écrire dans un external_dirs, mais skill_manage
    écrirait « là où la skill se trouve » (C6) : c'est la permission root qui l'empêche."""
    def comme_hermes(*commande):
        def abandonner():
            os.setgroups([])
            os.setgid(UID_HERMES)
            os.setuid(UID_HERMES)
        return subprocess.run(list(commande), preexec_fn=abandonner, capture_output=True, text=True)

    assert comme_hermes("sh", "-c", "echo x >> /opt/acp/skills/acp/acp-redaction/SKILL.md").returncode != 0
    assert comme_hermes("mkdir", "/opt/acp/skills/acp/intrus").returncode != 0
    assert comme_hermes("sh", "-c", "echo x > /opt/acp/skills/ecc/nouveau.md").returncode != 0
    assert comme_hermes("true").returncode == 0


def test_les_noms_lus_par_hermes_sont_ceux_du_verrou():
    reels = _noms_reels(RACINE)
    assert sorted(reels) == NOMS_ACP
    for skill in SKILLS_HERMES:
        assert reels[skill["nom"]] == [str(RACINE / skill["chemin"])], skill["nom"]


def test_aucune_collision_avec_les_skills_livrees_et_optionnelles_reelles():
    livrees = _noms_reels(Path("/opt/hermes/skills"))
    optionnelles = _noms_reels(Path("/opt/hermes/optional-skills"))
    # L'instantané du verrou est celui de l'image épinglée (sinon il est périmé).
    assert sorted(livrees) == VERROU["livrees"]["noms"]
    assert sorted(optionnelles) == VERROU["livrees"]["optionnelles"]
    assert not set(NOMS_ACP) & set(livrees)
    assert not set(NOMS_ACP) & set(optionnelles)
    assert all(len(v) == 1 for v in livrees.values())
    print(f"{len(livrees)} skills livrées, {len(optionnelles)} optionnelles, {len(NOMS_ACP)} skills ACP : "
          "aucun nom commun.")


def test_analyse_de_securite_de_hermes_sur_chaque_skill_acp():
    """tools/skills_guard.py : scan_skill (source « community ») sur chaque skill livrée ; aucun
    verdict « dangerous ». Le rapport complet est imprimé (preuve)."""
    code = ("from pathlib import Path; from tools.skills_guard import scan_skill, should_allow_install; "
            "resultat = {}\n"
            f"for chemin in {[str(RACINE / s['chemin']) for s in SKILLS_HERMES]!r}:\n"
            "    r = scan_skill(Path(chemin), source='community')\n"
            "    autorise, raison = should_allow_install(r)\n"
            "    resultat[Path(chemin).name] = {'verdict': r.verdict, 'constats': [(f.severity, f.pattern_id, f.file) "
            "for f in r.findings][:12], 'installation': autorise, 'raison': str(raison)[:160]}")
    rapport = executer_python(code, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})
    print(json.dumps(rapport, ensure_ascii=False, indent=1))
    assert sorted(rapport) == NOMS_ACP
    dangereuses = {n: r for n, r in rapport.items() if r["verdict"] == "dangerous"}
    assert not dangereuses


def test_recensement_des_skills_livrees_desactivees():
    """Chaque skill désactivée par ACP existe dans l'image, hermes-agent (essentielle) n'en est
    jamais ; le tableau imprimé dit pourquoi (scripts, outils fermés cités)."""
    outils_fermes = ("terminal", "execute_code", "write_file", "read_file", "patch", "search_files", "browser_",
                     "delegate_task", "cronjob", "computer_use")
    livrees = _noms_reels(Path("/opt/hermes/skills"))
    lignes = []
    for nom in sorted(livrees):
        dossier = Path(livrees[nom][0])
        fichiers = [p for p in dossier.rglob("*") if p.is_file()]
        scripts = sum(1 for p in fichiers if "scripts" in p.parts or p.suffix in (".py", ".sh", ".js", ".mjs"))
        texte = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fichiers if p.suffix == ".md")
        cites = sorted({o.rstrip("_") for o in outils_fermes if re.search(r"\b" + re.escape(o), texte)})
        classe = ("désactivée" if nom in DESACTIVEES else "gardée" if nom in GARDEES
                  else "macOS" if nom in MACOS else "NON CLASSÉE")
        lignes.append(f"{nom:32} {classe:11} scripts={scripts:2} outils fermés cités : {', '.join(cites) or '—'}")
    print("\n".join(lignes))
    assert set(DESACTIVEES) <= set(livrees) and "hermes-agent" not in DESACTIVEES
    assert set(DESACTIVEES) | set(GARDEES) | set(MACOS) == set(livrees)
    # Une skill gardée ne cite aucun script exécuté comme flux principal : pas de scripts/ (arxiv
    # excepté : sa lecture passe par web_extract, documentée par la skill elle-même).
    for nom in GARDEES:
        dossier = Path(livrees[nom][0])
        assert nom == "arxiv" or not (dossier / "scripts").exists(), nom


# Critère du classement des skills livrées (docs/refonte/catalogue.md § 3.4), relevé dans leur texte.
# Un LIVRABLE qui exige un outil fermé sur Railway (fichier écrit sur le disque, dépôt git) fait
# désactiver la skill ; un passage fermé à la marge (recherche par curl, fichier d'état, planification…)
# la laisse gardée à condition que sa raison au verrou le dise. Relecture de P3 : claude-design
# (« a complete local HTML file », « Default to local files. ») et hermes-agent-skill-authoring
# (« Use `write_file` + `git add` ») étaient gardées pour des raisons que leur texte contredit.
ESSENTIELLES = {"hermes-agent"}
LIVRABLE_FERME = re.compile(r"local HTML file|on-disk path|Default to local files|Use `write_file`")
PASSAGES_FERMES = {  # mot que la raison au verrou doit contenir → motif relevé dans le texte
    "fichier": re.compile(r"\bwrite_file\b|\bread_file\b|state file|local files?\b"),
    "terminal": re.compile(r"\bcurl\b|\bterminal\b"),
    "planification": re.compile(r"\bcronjob\b"),
    "navigateur": re.compile(r"\bbrowser_[a-z]+"),
    "délégation": re.compile(r"\bdelegate_task\b"),
    "code": re.compile(r"\bexecute_code\b"),
}


def test_une_skill_livree_gardee_n_a_aucun_livrable_ferme_et_dit_ses_limites():
    livrees = _noms_reels(Path("/opt/hermes/skills"))
    raisons = {e["nom"]: e["raison"] for e in VERROU["livrees"]["gardees"]}
    ecarts, releve = [], []
    for nom in GARDEES:
        dossier = Path(livrees[nom][0])
        texte = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(dossier.rglob("*.md")))
        livrable = LIVRABLE_FERME.search(texte)
        if livrable and nom not in ESSENTIELLES:
            ecarts.append(f"{nom} : livrable fermé sur Railway (« {livrable.group(0)} ») : à désactiver")
        passages = {mot: motif.search(texte).group(0) for mot, motif in PASSAGES_FERMES.items() if motif.search(texte)}
        releve.append(f"{nom:32} {', '.join(f'{m} ({p})' for m, p in passages.items()) or '—'}")
        for mot, passage in passages.items():
            if mot not in raisons[nom]:
                ecarts.append(f"{nom} : son texte cite « {passage} », sa raison au verrou ne dit pas « {mot} »")
    print("\n".join(releve))
    assert ecarts == [], "\n".join(ecarts)


# =============================================================== réglages du volume (05-acp)


def _preparer(chemins, contenu: str = None, *, lien: str = None) -> Path:
    cible = chemins.config_volume
    if lien is not None:
        cible.symlink_to(lien)
    elif contenu is not None:
        cible.write_text(contenu, encoding="utf-8")
        os.chown(cible, UID_HERMES, UID_HERMES)
        os.chmod(cible, 0o640)
    return cible


def _lire(cible: Path):
    return ad.charger_yaml(cible.read_text(encoding="utf-8"))


CATALOGUE = ad.charger_catalogue(ad.Chemins())


def test_reglages_fichier_absent_cree(chemins):
    etat = ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=UID_HERMES, gid=UID_HERMES)
    assert etat["etat"] == "cree"
    cible = chemins.config_volume
    assert _lire(cible) == {"skills": {"external_dirs": ["/opt/acp/skills"], "disabled": DESACTIVEES},
                            "mcp_servers": {"context7": {}}}
    assert etat["mcp_ajoutes"] == ["context7"]
    st = os.lstat(cible)
    assert (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) == (UID_HERMES, UID_HERMES, 0o640)


def test_reglages_config_semee_par_l_image_commentaires_conserves(chemins):
    """Le config.yaml que stage2-hook sème (cli-config.yaml.example) : seules les deux listes
    changent pour le chargeur de Hermes ; les commentaires restent ; propriétaire et mode gardés ;
    second passage : rien n'est écrit."""
    exemple = Path("/opt/hermes/cli-config.yaml.example").read_text(encoding="utf-8")
    cible = _preparer(chemins, exemple)
    avant = _lire(cible)
    etat = ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)
    assert etat["etat"] == "applique" and etat["external_dirs_ajoute"] is True
    assert etat["desactivations_ajoutees"] == DESACTIVEES and etat["mcp_ajoutes"] == ["context7"]
    apres = _lire(cible)
    assert apres["skills"]["external_dirs"] == ["/opt/acp/skills"]
    assert apres["skills"]["disabled"] == DESACTIVEES
    attendu = dict(avant)
    attendu["skills"] = dict(avant["skills"], external_dirs=["/opt/acp/skills"], disabled=DESACTIVEES)
    attendu["mcp_servers"] = dict(avant.get("mcp_servers") or {}, context7={})
    assert apres == attendu
    texte = cible.read_text(encoding="utf-8")
    assert "# External skill directories" in texte and "# Nudge the agent to create skills" in texte
    st = os.lstat(cible)
    assert (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) == (UID_HERMES, UID_HERMES, 0o640)
    empreinte = hashlib.sha256(cible.read_bytes()).hexdigest()
    date = os.lstat(cible).st_mtime_ns
    assert ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)["etat"] == "conforme"
    assert hashlib.sha256(cible.read_bytes()).hexdigest() == empreinte and os.lstat(cible).st_mtime_ns == date


def test_reglages_entrees_du_proprietaire_gardees(chemins):
    cible = _preparer(chemins, "# réglages du propriétaire\nskills:\n  external_dirs:\n    - /opt/data/mes-skills\n"
                               "    - /opt/acp/skills/\n  disabled: [maps, ma-skill]\n  creation_nudge_interval: 3\n"
                               "model:\n  default: x\n")
    etat = ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)
    assert etat["etat"] == "applique"
    relu = _lire(cible)
    assert relu["skills"]["external_dirs"] == ["/opt/acp/skills", "/opt/data/mes-skills"]
    assert relu["skills"]["disabled"][:2] == ["maps", "ma-skill"]
    assert set(relu["skills"]["disabled"]) == set(DESACTIVEES) | {"ma-skill"}
    assert relu["skills"]["creation_nudge_interval"] == 3 and relu["model"] == {"default": "x"}
    assert relu["mcp_servers"] == {"context7": {}}
    assert "# réglages du propriétaire" in cible.read_text(encoding="utf-8")


def test_reglages_liste_ecrite_par_hermes_config_set(chemins):
    """``hermes config set`` écrit une liste sous forme de chaîne « [...] » : Hermes la lit comme une
    liste (parse_config_string_list) ; ACP aussi, et la réécrit en vraie liste."""
    cible = _preparer(chemins, "skills:\n  disabled: \"['ma-skill']\"\n")
    assert ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)["etat"] == "applique"
    assert _lire(cible)["skills"]["disabled"] == ["ma-skill", *DESACTIVEES]


@pytest.mark.parametrize("contenu, motif", [
    ("skills: [a, b\n", "ne se lit pas"),
    ("- une liste\n", "n'a pas de table"),
    ("skills: texte\n", "skills n'est pas une table"),
    ("skills:\n  external_dirs: {a: 1}\n", "ni une liste ni une chaîne"),
    ("mcp_servers: [context7]\n", "mcp_servers n'est pas une table"),
])
def test_reglages_illisibles_rien_n_est_ecrit(chemins, contenu, motif):
    cible = _preparer(chemins, contenu)
    avant = cible.read_bytes()
    etat = ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)
    assert etat["etat"] == "illisible" and motif in etat["detail"]
    assert cible.read_bytes() == avant


def test_reglages_entree_context7_du_proprietaire_gardee(chemins):
    """Une entrée context7 déjà présente (par exemple un en-tête ajouté plus tard pour une clé d'API)
    est gardée telle quelle ; la managed scope l'emporte sur les feuilles épinglées."""
    contenu = ("skills:\n  external_dirs: [/opt/acp/skills]\n  disabled: [" + ", ".join(DESACTIVEES) + "]\n"
               "mcp_servers:\n  context7:\n    headers:\n      X-Test: acp\n")
    cible = _preparer(chemins, contenu)
    avant = cible.read_bytes()
    assert ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)["etat"] == "conforme"
    assert cible.read_bytes() == avant


def test_reglages_lien_symbolique_refuse(chemins, tmp_path):
    autre = tmp_path / "ailleurs.yaml"
    autre.write_text("skills: {}\n", encoding="utf-8")
    _preparer(chemins, lien=str(autre))
    with pytest.raises(ad.Refus, match="n'est pas un fichier ordinaire"):
        ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=0, gid=0)
    assert autre.read_text(encoding="utf-8") == "skills: {}\n"


def test_preparer_donnees_ecrit_les_reglages_et_l_etat(chemins, valeurs):
    scope = ad.preparer_scope_geree(chemins, valeurs)
    etat = ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)
    assert etat["schema"] == 3
    bloc = etat["catalogue"]
    assert bloc["reglages_skills"]["etat"] == "cree"
    assert bloc["racine_skills"] == "/opt/acp/skills" and bloc["serveurs_mcp_admis"] == ["context7"]
    assert bloc["verrou_sha256"] == hashlib.sha256(
        Path("/opt/acp/catalogue/catalogue.lock.json").read_bytes()).hexdigest()
    assert ad.preparer_donnees(chemins, scope, uid=UID_HERMES, gid=UID_HERMES)["catalogue"]["reglages_skills"][
        "etat"] == "conforme"


def test_les_listes_de_skills_ne_sont_jamais_dans_la_managed_scope(chemins, valeurs):
    ad.installer_scope_geree(chemins, valeurs)
    gere = ad.charger_yaml((chemins.dossier_gere / "config.yaml").read_text(encoding="utf-8"))
    assert "external_dirs" not in gere["skills"] and "disabled" not in gere["skills"]


# =============================================================== le chargeur de Hermes


LIRE_CHARGEUR = """
from agent.skill_utils import get_disabled_skill_names, get_external_skills_dirs
from tools.skills_tool import _find_all_skills
resultat = {
    "externes": [str(p) for p in get_external_skills_dirs()],
    "desactivees": sorted(get_disabled_skill_names()),
    "chargees": sorted(s["name"] for s in _find_all_skills()),
}
"""


def test_temoin_c1_external_dirs_en_managed_scope_est_ignore(chemins, valeurs):
    """Constat C1 : posées SEULEMENT dans la managed scope, les deux listes ne sont pas vues par le
    chargeur de skills de Hermes. D'où leur écriture par 05-acp dans le volume."""
    installer_home_de_test(chemins, valeurs)
    fichier = chemins.dossier_gere / "config.yaml"
    fichier.write_text(fichier.read_text(encoding="utf-8").replace(
        "  inline_shell: false\n", "  inline_shell: false\n  external_dirs: [/opt/acp/skills]\n  disabled: [maps]\n"),
        encoding="utf-8")
    vu = executer_python(LIRE_CHARGEUR, env=env_processus(chemins))
    assert vu["externes"] == [] and vu["desactivees"] == []
    assert not set(NOMS_ACP) & set(vu["chargees"])
    code = "from hermes_cli.config import load_config; resultat = load_config()['skills'].get('external_dirs')"
    assert executer_python(code, env=env_processus(chemins)) == ["/opt/acp/skills"]  # la config fusionnée, elle, l'a


def _synchroniser_les_skills_livrees(chemins) -> None:
    """Ce que fait stage2-hook au démarrage (tools/skills_sync.py) : les skills livrées sont recopiées
    dans le dossier local du volume."""
    code = "from tools.skills_sync import sync_skills; sync_skills(quiet=True); resultat = True"
    executer_python(code, env=env_processus(chemins))


def test_le_chargeur_voit_exactement_le_catalogue(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    _synchroniser_les_skills_livrees(chemins)
    assert ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "cree"
    vu = executer_python(LIRE_CHARGEUR, env=env_processus(chemins))
    print(json.dumps(vu, ensure_ascii=False))
    assert vu["externes"] == ["/opt/acp/skills"]
    assert vu["desactivees"] == DESACTIVEES
    # Skills chargées = catalogue ACP + skills livrées gardées (hors macOS).
    assert vu["chargees"] == sorted(set(NOMS_ACP) | set(GARDEES))


def test_temoin_sans_les_reglages_les_skills_acp_sont_absentes(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    _synchroniser_les_skills_livrees(chemins)
    vu = executer_python(LIRE_CHARGEUR, env=env_processus(chemins))
    assert vu["externes"] == []
    assert not set(NOMS_ACP) & set(vu["chargees"])
    assert set(DESACTIVEES) - set(CACHEES_HORS_KANBAN) <= set(vu["chargees"])


def test_get_api_skills_liste_exactement_le_catalogue(chemins, valeurs):
    """GET /api/skills (hermes_cli/web_routers/skills.py) appelé tel quel : exactement les skills
    livrées visibles sur Linux (hors celles réservées aux workers kanban) et les skills d'ACP ;
    « enabled » faux pour chaque skill désactivée par le catalogue, vrai pour les autres."""
    installer_home_de_test(chemins, valeurs)
    _synchroniser_les_skills_livrees(chemins)
    ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=UID_HERMES, gid=UID_HERMES)
    code = ("import asyncio; from hermes_cli.web_routers.skills import get_skills; "
            "resultat = {s['name']: [s['enabled'], s['category'], s['provenance']] for s in asyncio.run(get_skills())}")
    vu = executer_python(code, env=env_processus(chemins))
    livrees_visibles = set(VERROU["livrees"]["noms"]) - set(MACOS) - set(CACHEES_HORS_KANBAN)
    assert set(vu) == livrees_visibles | set(NOMS_ACP)
    for nom, (active, categorie, provenance) in vu.items():
        assert active is (nom not in DESACTIVEES), nom
        if nom in NOMS_ACP:
            source = next(s for s in SKILLS_HERMES if s["nom"] == nom)
            assert categorie == VERROU["sources"][source["source"]]["categorie"], nom
        else:
            assert provenance == "bundled", nom
    print(f"GET /api/skills : {len(vu)} skills, {sum(1 for v in vu.values() if v[0])} activées, "
          f"{sum(1 for v in vu.values() if not v[0])} désactivées.")


def test_skill_view_d_une_skill_acp_et_refus_d_une_desactivee(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    _synchroniser_les_skills_livrees(chemins)
    ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=UID_HERMES, gid=UID_HERMES)
    code = ("import json; from tools.skills_tool import skill_view; "
            "resultat = [json.loads(skill_view('acp-redaction')), json.loads(skill_view('emil-design-eng')), "
            "json.loads(skill_view('codex'))]")
    redaction, emil, codex = executer_python(code, env=env_processus(chemins))
    assert redaction.get("success") is True and "Rédaction ACP" in redaction.get("content", "")
    assert emil.get("success") is True
    assert codex.get("success") is not True, codex


def test_nouvelle_session_l_index_des_skills_est_celui_du_catalogue(chemins, valeurs, modele_factice):
    """Nouvelle session (surface cli, AIAgent neuf) : l'index des skills du prompt système reçu par le
    modèle liste chaque skill d'ACP sous sa catégorie (description française de DESCRIPTION.md) et
    aucune skill désactivée par le catalogue."""
    installer_home_de_test(chemins, valeurs, modele_url=modele_factice.url)
    _synchroniser_les_skills_livrees(chemins)
    ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=UID_HERMES, gid=UID_HERMES)
    fichier = chemins.hermes_home.parent / "agent-index.json"
    sortie = lancer_outil("agent_neuf.py", "cli", modele_factice.url, "Bonjour.", str(fichier), env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    index = next(r["index_skills"] for r in modele_factice.requetes() if r.get("index_skills"))
    print(index)
    lignes = index.splitlines()
    for nom in NOMS_ACP:
        assert any(l.startswith(f"    - {nom}:") for l in lignes), nom
    for nom in DESACTIVEES:
        assert not any(l.startswith(f"    - {nom}:") or l.strip() == f"- {nom}" for l in lignes), nom
    assert any(l.startswith("  acp: Skills maison d'ACP, en français") for l in lignes)
    assert any(l.startswith("  ecc: Sélection de skills du dépôt affaan-m/ECC") for l in lignes)
