"""Greffons d'interface livrés dans l'image : acp-interface et acp-catalogue (étape P3), acp-projets
(étape P4).

Ils n'ont AUCUN code serveur (manifeste, bundle IIFE, feuille de style) ; Hermes les découvre en
source « bundled » (web_server_dashboard.py:463-560) et les sert au navigateur tant qu'ils ne sont
pas dans plugins.disabled ni dans dashboard.hidden_plugins (web_routers/dashboard_ui.py:109-146).

Ces tests appellent le code RÉEL de Hermes dans un processus neuf, avec la managed scope d'ACP et un
volume piégé qui tente de masquer ou de désactiver les greffons d'ACP, de réactiver
hermes-achievements, de changer de thème et d'injecter une police distante ; le témoin négatif
prouve que, sans la managed scope, le piège l'emporterait.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from conftest import env_processus, executer_python, installer_home_de_test

GREFFONS = Path("/opt/hermes/plugins")
NOMS_ACP = ("acp-interface", "acp-catalogue", "acp-projets")

CONFIG_PIEGEE = """\
plugins:
  enabled: [acp-interface, hermes-achievements]
  disabled: [acp-interface, acp-catalogue, acp-projets, acp-poste]
dashboard:
  theme: default
  font: inter
  hidden_plugins: [acp-interface, acp-catalogue, acp-projets, acp-poste]
"""

SERVIS = """
from hermes_cli.config import cfg_get, load_config
from hermes_cli.web_server_dashboard import _discover_dashboard_plugins
from hermes_cli.web_routers.dashboard_ui import _plugin_activated, _plugin_enable_sets

decouverts = _discover_dashboard_plugins()
actives, desactives = _plugin_enable_sets()
config = load_config()
masques = cfg_get(config, "dashboard", "hidden_plugins", default=[]) or []
resultat = {
    "decouverts": {p["name"]: {k: v for k, v in p.items() if not k.startswith("_")} for p in decouverts},
    "servis": sorted(p["name"] for p in decouverts
                     if p["name"] not in masques and _plugin_activated(p, actives, desactives)),
    "theme": cfg_get(config, "dashboard", "theme"),
    "police": cfg_get(config, "dashboard", "font"),
}
"""


def test_fichiers_des_greffons_root_0644_sans_code_serveur():
    for nom in NOMS_ACP:
        racine = GREFFONS / nom
        fichiers = sorted(str(p.relative_to(racine)) for p in racine.rglob("*") if p.is_file())
        assert fichiers == ["dashboard/dist/index.js", "dashboard/dist/style.css", "dashboard/manifest.json"], fichiers
        for chemin in [racine, *racine.rglob("*")]:
            st = os.lstat(chemin)
            attendu = 0o755 if stat.S_ISDIR(st.st_mode) else 0o644
            assert st.st_uid == 0 and st.st_gid == 0 and stat.S_IMODE(st.st_mode) == attendu, chemin
        manifeste = json.loads((racine / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
        assert manifeste["name"] == nom and manifeste["version"] == "0.11.0"
        assert "api" not in manifeste
        code = (racine / "dashboard" / "dist" / "index.js").read_text(encoding="utf-8")
        assert code.startswith(f"/* {nom} 0.11.0 (ACP)")


def test_hermes_decouvre_et_sert_les_greffons_d_acp_malgre_un_volume_piege(chemins, valeurs):
    installer_home_de_test(chemins, valeurs, config=CONFIG_PIEGEE)
    resultat = executer_python(SERVIS, env=env_processus(chemins))
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    decouverts = resultat["decouverts"]
    assert decouverts["acp-interface"]["source"] == "bundled"
    assert decouverts["acp-interface"]["tab"] == {"path": "/acp", "position": "end", "override": "/"}
    assert decouverts["acp-interface"]["has_api"] is False
    assert decouverts["acp-catalogue"]["tab"] == {"path": "/catalogue", "position": "after:skills"}
    assert decouverts["acp-catalogue"]["has_api"] is False
    # Étape P4 : la page Projets, avant le Catalogue dans le groupe des greffons (App.tsx:258-291 ;
    # découverte triée par nom : web_server_dashboard.py:558), sans route propre.
    assert decouverts["acp-projets"]["tab"] == {"path": "/projets", "position": "before:catalogue"}
    assert decouverts["acp-projets"]["label"] == "Projets" and decouverts["acp-projets"]["has_api"] is False
    assert decouverts["acp-projets"]["source"] == "bundled"
    assert list(decouverts).index("acp-catalogue") < list(decouverts).index("acp-projets")
    assert "hermes-achievements" in decouverts  # livré par Hermes, mais…
    servis = set(resultat["servis"])
    assert {"acp-interface", "acp-catalogue", "acp-projets", "acp-poste", "kanban"} <= servis
    assert "hermes-achievements" not in servis  # … jamais servi (D13).
    assert resultat["theme"] == "acp"
    assert resultat["police"] == "theme"


def test_temoin_sans_managed_scope_le_piege_masquerait_les_greffons(chemins, valeurs):
    installer_home_de_test(chemins, valeurs, config=CONFIG_PIEGEE)
    env = env_processus(chemins)
    env.pop("HERMES_MANAGED_DIR")
    vide = chemins.hermes_home.parent / "scope-vide"
    vide.mkdir()
    env["HERMES_MANAGED_DIR"] = str(vide)
    resultat = executer_python(SERVIS, env=env)
    servis = set(resultat["servis"])
    assert not ({"acp-interface", "acp-catalogue", "acp-projets", "acp-poste"} & servis), servis
    assert "hermes-achievements" in servis
    assert resultat["theme"] == "default" and resultat["police"] == "inter"
