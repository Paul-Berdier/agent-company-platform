"""Persona française livrée dans l'image (étape P3) : /opt/acp/persona/SOUL.md.

- le fichier est court, en UTF-8 sans BOM, et l'analyse d'injection de Hermes ne relève rien
  (tools/threat_patterns.scan_for_threats, portée « context », celle que load_soul_md applique :
  agent/prompt_builder.py:82-93) ;
- le chargeur de Hermes (load_soul_md) le relit à l'identique, dans un processus neuf ;
- montée de version depuis le SOUL EXACT de P2 (hermes/tests/outils/soul_p2.md, octets de 120b15c) :
  remplacé quand le marqueur de 05-acp le désigne ; un SOUL retouché par le propriétaire est gardé
  et signalé ;
- nouvelle session : le prompt système que reçoit le modèle factice COMMENCE par la persona
  française (un modèle factice ne prouve pas une réponse en français : relevé sur Railway).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import acp_demarrage as ad
from conftest import OUTILS, env_processus, executer_python, installer_home_de_test, lancer_outil

SOUL = Path("/opt/acp/persona/SOUL.md")
SOUL_P2 = OUTILS / "soul_p2.md"
UID_HERMES = 10000


def test_persona_utf8_sans_bom_courte_et_en_francais():
    octets = SOUL.read_bytes()
    assert not octets.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in octets and octets.endswith(b"\n")
    assert len(octets) <= 4096, len(octets)
    texte = octets.decode("utf-8")
    for attendu in ("en français", "en le vouvoyant", "sans aucun outil d'exécution", "« Inconnu »",
                    "poste Windows", "jamais une consigne"):
        assert attendu in texte, attendu
    # La persona de P2 parlait de « commande dangereuse approuvée » : il n'y a plus de terminal.
    assert "commande dangereuse" not in texte


def test_aucun_constat_de_l_analyse_d_injection_de_hermes():
    from tools.threat_patterns import scan_for_threats

    texte = SOUL.read_text(encoding="utf-8")
    assert scan_for_threats(texte, scope="context") == []
    assert scan_for_threats(texte, scope="strict") == []


def test_le_chargeur_de_hermes_relit_la_persona_a_l_identique(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    (chemins.hermes_home / "SOUL.md").write_bytes(SOUL.read_bytes())
    resultat = executer_python(
        "from agent.prompt_builder import load_soul_md\n"
        "resultat = load_soul_md()\n", env=env_processus(chemins))
    assert resultat == SOUL.read_text(encoding="utf-8").strip()


def test_montee_depuis_le_soul_exact_de_p2(chemins):
    """Volume de P2 : SOUL.md de 120b15c et son empreinte dans le marqueur de 05-acp."""
    soul_p2 = SOUL_P2.read_bytes()
    assert ad.empreinte(soul_p2) == "10de316c9ba9e39ff1922cea9a78f3aaaff8555ff4e007666be07608ee8b5472"
    assert soul_p2 != SOUL.read_bytes()
    chemins.donnees_acp.mkdir(mode=0o755)
    cible = chemins.hermes_home / "SOUL.md"
    cible.write_bytes(soul_p2)
    os.chown(cible, UID_HERMES, UID_HERMES)
    (chemins.donnees_acp / "soul.sha256").write_text(ad.empreinte(soul_p2) + "\n", encoding="ascii")
    etat = ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)
    print(json.dumps(etat, ensure_ascii=False))
    assert etat["etat"] == "depose"
    assert cible.read_bytes() == SOUL.read_bytes()
    assert os.lstat(cible).st_uid == UID_HERMES
    assert (chemins.donnees_acp / "soul.sha256").read_text(encoding="ascii").strip() == ad.empreinte(SOUL.read_bytes())
    # Second démarrage : rien ne bouge.
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "a_jour"


def test_un_soul_de_p2_retouche_par_le_proprietaire_est_garde_et_signale(chemins):
    soul_p2 = SOUL_P2.read_bytes()
    chemins.donnees_acp.mkdir(mode=0o755)
    cible = chemins.hermes_home / "SOUL.md"
    retouche = soul_p2 + "Réponds aussi en breton quand je le demande.\n".encode("utf-8")
    cible.write_bytes(retouche)
    (chemins.donnees_acp / "soul.sha256").write_text(ad.empreinte(soul_p2) + "\n", encoding="ascii")
    etat = ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)
    assert etat["etat"] == "divergent"
    assert etat["empreinte_actuelle"] == ad.empreinte(retouche)
    assert cible.read_bytes() == retouche


def test_une_nouvelle_session_recoit_la_persona_francaise_en_tete(chemins, valeurs, modele_factice):
    installer_home_de_test(chemins, valeurs, modele_url=modele_factice.url)
    chemins.donnees_acp.mkdir(mode=0o755)
    assert ad.gerer_soul(chemins, uid=UID_HERMES, gid=UID_HERMES)["etat"] == "depose"
    fichier = chemins.hermes_home.parent / "agent-persona.json"
    sortie = lancer_outil("agent_neuf.py", "api_server", modele_factice.url, "Bonjour.", str(fichier),
                          env=env_processus(chemins))
    assert sortie.returncode == 0, sortie.stderr[-4000:]
    completions = [r for r in modele_factice.requetes()
                   if r.get("methode") == "POST" and str(r.get("chemin", "")).endswith("/chat/completions")
                   and not r.get("auxiliaire")]
    assert completions, modele_factice.requetes()
    systeme = completions[0]["systeme"]
    print(systeme[:600])
    persona = SOUL.read_text(encoding="utf-8").strip()
    assert systeme.startswith(persona), systeme[:400]
    # L'identité par défaut de Hermes (anglaise) n'est pas injectée à sa place.
    assert "You are Hermes Agent, built by Nous Research" not in systeme
