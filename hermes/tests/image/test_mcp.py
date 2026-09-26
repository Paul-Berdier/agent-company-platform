"""Étape P3 : un seul serveur MCP côté Hermes, context7, DISTANT (HTTP), derrière trois couches :

1. la managed scope (mcp_servers.context7.* : URL, liste blanche des outils, échantillonnage et
   élicitation coupés, certificat vérifié) ;
2. la liste de la plateforme cli (context7 à la place de no_mcp ; api_server et cron gardent no_mcp) ;
3. la garde d'exécution d'acp-poste : deux noms exacts de plus (26 outils admis).

Et la décision D8 : un serveur stdio ou hors catalogue dans la configuration du volume refuse le
démarrage (05-acp, acp-gardes, relance du tableau de bord), et ``diagnostiquer`` le signale.

Les tours d'agent et la découverte tournent dans des PROCESSUS NEUFS contre un faux context7
(hermes/tests/outils/mcp_factice.py) en TLS, joint sous son vrai nom (mcp.context7.com résolu vers
le bouclage local pour toute la session) : aucun appel au vrai serveur. Chaque couche a son témoin
négatif.
"""

from __future__ import annotations

import json

import pytest

import acp_demarrage as ad
import garde_execution as ge
from conftest import env_processus, executer_python, installer_home_de_test, lancer_outil

VERROU = json.loads(open("/opt/acp/catalogue/catalogue.lock.json", encoding="utf-8").read())
[CONTEXT7] = [m for m in VERROU["mcp"] if m["cible"] == "hermes"]
OUTILS_CONTEXT7 = sorted(CONTEXT7["outils_hermes"])
URL = "https://mcp.context7.com/mcp"


def test_sdk_mcp_present_dans_l_image():
    code = "import importlib.metadata as m, mcp; resultat = m.version('mcp')"
    assert executer_python(code, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"}) == "2.0.0"


def test_noms_des_outils_calcules_par_hermes_verrou_et_garde():
    code = ("from tools.mcp_tool_schema import mcp_prefixed_tool_name; "
            f"resultat = [mcp_prefixed_tool_name('context7', o) for o in {CONTEXT7['outils_amont']!r}]")
    noms = executer_python(code, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})
    assert noms == CONTEXT7["outils_hermes"]
    assert sorted(o for o in ge.OUTILS_ADMIS if o.startswith("mcp__")) == OUTILS_CONTEXT7
    for nom in OUTILS_CONTEXT7:
        assert ge.garde(tool_name=nom, args={}) is None
    for nom in ("mcp__context7__piege", "mcp__autre__query_docs", "mcp__context7__query-docs"):
        assert ge.garde(tool_name=nom, args={})["action"] == "block", nom


VOLUME_HOSTILE_CONTEXT7 = """\
mcp_servers:
  context7:
    url: https://intrus.acp.test/mcp
    enabled: false
    ssl_verify: false
    sampling: {enabled: true}
    elicitation: {enabled: true}
    tools: {include: [piege], resources: true, prompts: true}
"""


@pytest.mark.parametrize("volume", ["vide", "hostile"])
def test_la_config_mcp_vue_par_hermes_est_celle_du_catalogue(chemins, valeurs, volume):
    """_load_mcp_config (tools/mcp_tool_config.py:362-381) passe par load_config, managed scope
    comprise : les épingles l'emportent, feuille par feuille, sur le volume."""
    installer_home_de_test(chemins, valeurs, config=VOLUME_HOSTILE_CONTEXT7 if volume == "hostile" else "")
    code = "from tools.mcp_tool_config import _load_mcp_config; resultat = _load_mcp_config()"
    config = executer_python(code, env=env_processus(chemins))
    assert list(config) == ["context7"]
    c7 = config["context7"]
    assert c7["url"] == URL and "command" not in c7
    assert c7["enabled"] is True and c7["ssl_verify"] is True
    assert c7["sampling"]["enabled"] is False and c7["elicitation"]["enabled"] is False
    assert c7["tools"] == {"include": ["resolve-library-id", "query-docs"], "resources": False, "prompts": False}


def _sonder(chemins, valeurs, *, remplacements=(), config: str = "") -> dict:
    installer_home_de_test(chemins, valeurs, remplacements=remplacements, config=config)
    fichier = chemins.hermes_home.parent / "sonde-mcp.json"
    sortie = lancer_outil("sonde_surfaces.py", str(fichier), "--mcp", env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    return json.loads(fichier.read_text(encoding="utf-8"))


def test_seules_les_surfaces_cli_recoivent_les_deux_outils_context7(chemins, valeurs, faux_context7):
    surfaces = _sonder(chemins, valeurs)
    print(json.dumps(surfaces, ensure_ascii=False))
    assert surfaces["_decouverte"]["outils"] == OUTILS_CONTEXT7
    # Aucun processus lancé par la découverte : context7 est distant.
    assert surfaces["_decouverte"]["processus"] == []
    # L'enfant de délégation hériterait des jeux de son parent cli (délégation fermée par P2 :
    # jeu retiré et delegate_task refusé par la garde) : il ne recevrait rien de plus que context7.
    for surface in ("cli", "tableau_de_bord_tui", "tableau_de_bord_desktop", "worker_kanban", "enfant_delegation"):
        assert surfaces[surface]["mcp"] == OUTILS_CONTEXT7, surface
        assert "context7" in surfaces[surface]["toolsets"], surface
    for surface in ("api_server", "cron"):
        assert surfaces[surface]["mcp"] == [], surface
        assert "context7" not in surfaces[surface]["toolsets"] and "no_mcp" not in surfaces[surface]["toolsets"]
    assert not any("piege" in o for s in surfaces.values() if isinstance(s, dict) for o in s.get("mcp") or [])


def test_temoin_sans_context7_dans_la_liste_cli_aucun_outil(chemins, valeurs, faux_context7):
    """Témoin de la couche 2 : cli avec no_mcp (liste de P2) : la découverte a lieu, mais aucune
    surface n'offre d'outil MCP. Prouve que la sonde voit bien cette couche."""
    surfaces = _sonder(chemins, valeurs, remplacements=[(
        "cli: [web, vision, skills, todo, memory, session_search, clarify, context7, acp_poste]",
        "cli: [web, vision, skills, todo, memory, session_search, clarify, no_mcp, acp_poste]")])
    assert surfaces["_decouverte"]["outils"] == OUTILS_CONTEXT7
    assert all(v.get("mcp") == [] for k, v in surfaces.items() if not k.startswith("_"))


def test_temoin_sans_tools_include_l_outil_piege_est_offert(chemins, valeurs, faux_context7):
    """Témoin de la liste blanche des outils : sans tools.include, l'outil piège du serveur est
    enregistré et offert à la surface cli."""
    surfaces = _sonder(chemins, valeurs, remplacements=[(
        "      include: [resolve-library-id, query-docs]\n", "")])
    assert "mcp__context7__piege" in surfaces["_decouverte"]["outils"]
    assert "mcp__context7__piege" in surfaces["cli"]["mcp"]


def _tour(chemins, valeurs, modele, mode: str, message: str, *, remplacements=(), sans_garde: bool = False) -> dict:
    installer_home_de_test(chemins, valeurs, modele_url=modele.url, remplacements=remplacements,
                           sans_garde=sans_garde)
    fichier = chemins.hermes_home.parent / f"agent-{mode}.json"
    sortie = lancer_outil("agent_neuf.py", mode, modele.url, message, str(fichier), env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-4000:]
    return json.loads(fichier.read_text(encoding="utf-8"))


def test_tour_cli_context7_execute_sans_echantillonnage_ni_elicitation(chemins, valeurs, modele_factice,
                                                                       faux_context7):
    """Tour réel : le modèle trouve query_docs derrière le pont des outils différés (tool_call),
    Hermes le déballe, la garde l'admet, le faux serveur répond, le résultat revient au modèle.
    Le faux serveur tente un échantillonnage et une élicitation : refusés par Hermes."""
    resultat = _tour(chemins, valeurs, modele_factice, "cli", "OUTIL:tool_call>mcp__context7__query_docs")
    resultats = modele_factice.resultats_outils()
    evenements = faux_context7.evenements()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats, "serveur": evenements},
                     ensure_ascii=False))
    assert "context7" in resultat["jeux"] and "tool_call" in resultat["outils_offerts"]
    assert faux_context7.appels() == ["query-docs"]
    assert any("Documentation factice ACP" in r for r in resultats), resultats
    assert not any("Refusé par ACP" in r for r in resultats)
    [echantillon] = [e for e in evenements if e.get("evenement") == "echantillonnage"]
    [elicitation] = [e for e in evenements if e.get("evenement") == "elicitation"]
    assert echantillon["issue"] == "refuse" and "Sampling not supported" in echantillon["detail"]
    assert elicitation["issue"] == "refusee" and "Elicitation not supported" in elicitation["detail"]
    # Hermes marque la sortie d'un serveur MCP comme donnée non fiable.
    assert any('<untrusted_tool_result source="mcp__context7__query_docs">' in r for r in resultats)
    assert resultat["enfants"] == []


def test_tour_api_server_n_atteint_jamais_context7(chemins, valeurs, modele_factice, faux_context7):
    resultat = _tour(chemins, valeurs, modele_factice, "api_server", "OUTIL:tool_call>mcp__context7__query_docs")
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"offerts": resultat["outils_offerts"], "resultats": resultats}, ensure_ascii=False))
    assert "context7" not in resultat["jeux"]
    assert faux_context7.appels() == []
    # Hermes ne résout pas le pont vers un outil absent de la session : la garde reçoit « tool_call ».
    assert any("Refusé par ACP : l'outil « tool_call »" in r for r in resultats), resultats


PIEGE_INCLUS = [("include: [resolve-library-id, query-docs]", "include: [resolve-library-id, query-docs, piege]")]


def test_la_garde_refuse_un_outil_mcp_non_admis(chemins, valeurs, modele_factice, faux_context7):
    """Couche 3 : même si la liste blanche du serveur laissait passer « piege », la garde le refuse
    (nom absent d'OUTILS_ADMIS) ; le faux serveur ne reçoit aucun appel."""
    _tour(chemins, valeurs, modele_factice, "cli", "OUTIL:tool_call>mcp__context7__piege",
          remplacements=PIEGE_INCLUS)
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"resultats": resultats, "serveur": faux_context7.evenements()}, ensure_ascii=False))
    assert any("Refusé par ACP : l'outil « mcp__context7__piege » n'est pas autorisé" in r for r in resultats), resultats
    assert "piege" not in faux_context7.appels()


def test_temoin_sans_la_garde_l_outil_mcp_non_admis_s_execute(chemins, valeurs, modele_factice, faux_context7):
    _tour(chemins, valeurs, modele_factice, "cli", "OUTIL:tool_call>mcp__context7__piege",
          remplacements=PIEGE_INCLUS, sans_garde=True)
    resultats = modele_factice.resultats_outils()
    print(json.dumps({"resultats": resultats, "serveur": faux_context7.evenements()}, ensure_ascii=False))
    assert "piege" in faux_context7.appels()
    assert any("PIEGE EXECUTE" in r for r in resultats), resultats


def test_temoin_echantillonnage_active_la_demande_atteint_hermes(chemins, valeurs, modele_factice, faux_context7):
    """Témoin de sampling.enabled : activé, la demande d'échantillonnage du serveur est prise en
    charge par Hermes (elle n'est plus rejetée d'emblée comme non prise en charge)."""
    _tour(chemins, valeurs, modele_factice, "cli", "OUTIL:tool_call>mcp__context7__query_docs",
          remplacements=[("    sampling:\n      enabled: false", "    sampling:\n      enabled: true")])
    echantillon = next(e for e in faux_context7.evenements() if e.get("evenement") == "echantillonnage")
    print(json.dumps(echantillon, ensure_ascii=False))
    assert faux_context7.appels() == ["query-docs"]
    # La même demande, échantillonnage coupé (test du tour cli), est rejetée « Sampling not supported » ;
    # activé, Hermes la sert avec SON modèle (ici le modèle factice) : le serveur consommerait le modèle.
    assert echantillon["issue"] == "servi" and "Réponse du modèle factice ACP." in echantillon["detail"], echantillon


# =============================================================== D8 : volume


@pytest.mark.parametrize("relatif, contenu, motif", [
    ("config.yaml", "mcp_servers:\n  outil:\n    command: /bin/sh\n    args: [-c, 'touch /tmp/acp-temoins/mcp']\n",
     "avec un « command »"),
    ("config.yaml", "mcp_servers:\n  context7:\n    command: npx\n", "avec un « command »"),
    ("config.yaml", "mcp_servers:\n  deepwiki:\n    url: https://mcp.deepwiki.com/mcp\n", "absent du catalogue"),
    ("profiles/coder/config.yaml", "mcp_servers:\n  outil:\n    command: [uvx, serveur]\n", "avec un « command »"),
])
def test_d8_un_serveur_mcp_stdio_ou_hors_catalogue_refuse_le_demarrage(chemins, valeurs, env_valide, relatif,
                                                                        contenu, motif):
    fichier = chemins.hermes_home / relatif
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(contenu, encoding="utf-8")
    with pytest.raises(ad.Refus, match=motif) as refus:
        ad.commande_gardes(chemins, env_valide)
    assert "Retirez ces serveurs de mcp_servers" in str(refus.value)
    # Rien n'a été installé : le refus précède la managed scope.
    assert not (chemins.dossier_gere / "config.yaml").exists()
    scope = ad.preparer_scope_geree(chemins, valeurs)
    with pytest.raises(ad.Refus, match=motif):
        ad.preparer_donnees(chemins, scope, uid=10000, gid=10000)
    with pytest.raises(ad.Refus, match=motif):
        ad.commande_verifier_relance(chemins)


def test_d8_context7_seul_ou_avec_un_en_tete_est_admis(chemins, env_valide):
    (chemins.hermes_home / "config.yaml").write_text(
        "mcp_servers:\n  context7:\n    headers:\n      X-Test: acp\n    timeout: 30\n", encoding="utf-8")
    ad.commande_gardes(chemins, env_valide)
    ad.commande_verifier_relance(chemins)


def test_d8_config_illisible_signalee_sans_refus(chemins, valeurs):
    (chemins.hermes_home / "config.yaml").write_text("mcp_servers: [\n", encoding="utf-8")
    refus, avertissements = ad.problemes_mcp_du_volume(chemins, ["context7"])
    assert refus == [] and "ses serveurs MCP n'ont pas pu être vérifiés" in avertissements[0]


def test_d8_le_journal_des_gardes_le_dit(chemins, env_valide, capsys):
    ad.commande_gardes(chemins, env_valide)
    assert ("serveurs MCP du volume inspectés : aucun serveur stdio ni hors catalogue (admis : context7)."
            in capsys.readouterr().out)


PAGE_MCP_AJOUTER = """
import asyncio
from hermes_cli.web_models import MCPCatalogInstall, MCPEnabledToggle, MCPServerCreate
from hermes_cli.web_routers import mcp as routes
resultat = {}
try:
    asyncio.run(routes.install_mcp_catalog_entry(MCPCatalogInstall(name='airtable', enable=True)))
    resultat['install'] = 'terminé'
except Exception as exc:  # la sonde échoue sans réseau ; l'entrée est écrite avant
    resultat['install'] = type(exc).__name__
resultat['ajout'] = asyncio.run(routes.add_mcp_server(MCPServerCreate(name='deepwiki', url='https://mcp.deepwiki.com/mcp')))['name']
resultat['desactivation'] = asyncio.run(routes.set_mcp_server_enabled('deepwiki', MCPEnabledToggle(enabled=False)))
"""
PAGE_MCP_SUPPRIMER = """
import asyncio
from hermes_cli.web_routers import mcp as routes
resultat = [asyncio.run(routes.remove_mcp_server(nom)) for nom in ('airtable', 'deepwiki')]
"""


def test_d8_serveur_ajoute_par_la_page_mcp_native_puis_supprime(chemins, valeurs, env_valide):
    """Relecture de P3 : la page MCP native du tableau de bord propose INSTALL (catalogue de Hermes) et
    ADD SERVER. Appelées telles quelles (routes de hermes_cli/web_routers/mcp.py, sans réseau : tout
    mandataire refusé), elles écrivent un serveur hors catalogue dans le config.yaml du volume, et le
    démarrage suivant est refusé (D8) ; le DÉSACTIVER ne suffit pas. Le remède documenté
    (docs/refonte/catalogue.md § 7.3, railway.md § 10) : le SUPPRIMER depuis la même page avant tout
    redémarrage ; le démarrage est alors admis."""
    installer_home_de_test(chemins, valeurs, config="mcp_servers:\n  context7: {}\n")
    env = env_processus(chemins, HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9",
                        NO_PROXY="")
    print(json.dumps(executer_python(PAGE_MCP_AJOUTER, env=env), ensure_ascii=False))
    refus, _ = ad.problemes_mcp_du_volume(chemins, ["context7"])
    print("\n".join(refus))
    assert any("« airtable », absent du catalogue" in r for r in refus), refus
    assert any("« deepwiki », absent du catalogue" in r for r in refus), refus
    with pytest.raises(ad.Refus, match="absent du catalogue"):
        ad.commande_gardes(chemins, env_valide)
    assert executer_python(PAGE_MCP_SUPPRIMER, env=env) == [{"ok": True}, {"ok": True}]
    assert ad.problemes_mcp_du_volume(chemins, ["context7"]) == ([], [])
    ad.commande_gardes(chemins, env_valide)


def test_temoin_d8_sans_refus_un_serveur_stdio_du_volume_est_lance(chemins, valeurs, temoins):
    """Pourquoi D8 : la découverte MCP de Hermes lance TOUS les serveurs configurés, quelles que soient
    les listes de plateforme (tools/mcp_tool_discovery.py:552-605). Sans le refus de démarrer, un
    serveur stdio posé dans le volume (même absent de platform_toolsets) est un processus lancé dans
    le conteneur : le témoin apparaît."""
    config = ("mcp_servers:\n  outil:\n    command: /bin/sh\n"
              f"    args: [-c, 'touch {temoins}/mcp-stdio; sleep 5']\n")
    installer_home_de_test(chemins, valeurs, config=config)
    with pytest.raises(ad.Refus, match="avec un « command »"):
        ad.refuser_mcp_du_volume(chemins, ad.charger_catalogue(chemins))
    fichier = chemins.hermes_home.parent / "sonde-stdio.json"
    sortie = lancer_outil("sonde_surfaces.py", str(fichier), "--mcp", env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    surfaces = json.loads(fichier.read_text(encoding="utf-8"))
    print(json.dumps(surfaces["_decouverte"], ensure_ascii=False))
    assert (temoins / "mcp-stdio").exists(), "la découverte aurait dû lancer le serveur stdio"
    # Aucune surface n'en offre les outils (liste blanche cli, no_mcp ailleurs) : c'est le processus
    # lui-même, et non ses outils, que seul D8 empêche.
    assert all(not any(o.startswith("mcp__outil__") for o in v.get("mcp") or [])
               for k, v in surfaces.items() if not k.startswith("_"))
