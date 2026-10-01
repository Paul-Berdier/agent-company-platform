"""Sondes Codex du poste (cahier P5 § 9) contre un faux ``codex`` piloté par scénario (``faux_codex.py``).

Aucun accès réseau ni compte réel. Les réponses du faux et les requêtes du poste sont validées contre les schémas
publiés par Codex CLI 0.156.1 (``fixtures/codex_app_server_0_156_1``, régénérés et comparés octet pour octet :
``PROVENANCE.md``).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acp_poste import sondes_codex as sc
from acp_poste.app_server import METHODES_ADMISES, MethodeRefusee, Session
from acp_poste.politique import SectionCodex
from acp_poste.sondes_codex import (
    CONFIG_TOML,
    SURCHARGES,
    bac_a_sable,
    ecrire_config_toml,
    etat_config_toml,
    installer_bac_a_sable,
)
from acp_poste.subscription_quotas import codex_environment

ICI = Path(__file__).resolve().parent
SCHEMAS = ICI / "fixtures" / "codex_app_server_0_156_1"
PYTHON = str(Path(sys.executable).resolve())
INTERDITES = ("windowsSandbox/setupStart", "account/login/start", "account/login/cancel", "account/logout",
              "account/rateLimitResetCredit/consume", "account/sendAddCreditsNudgeEmail", "config/value/write",
              "config/batchWrite", "skills/config/write", "thread/start", "turn/start")


def _faux():
    spec = importlib.util.spec_from_file_location("faux_codex", ICI / "faux_codex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAUX = _faux()


# ------------------------------------------------------------------ sous-ensemble de JSON Schema draft-07

_TYPES = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
          "string": lambda v: isinstance(v, str), "integer": lambda v: type(v) is int,
          "number": lambda v: type(v) in (int, float), "boolean": lambda v: type(v) is bool,
          "null": lambda v: v is None}


def erreurs_schema(valeur, schema, racine=None, chemin="$") -> list[str]:
    racine = schema if racine is None else racine
    if schema is True or schema == {}:
        return []
    if "$ref" in schema:
        cible = racine
        for partie in schema["$ref"].removeprefix("#/").split("/"):
            cible = cible[partie]
        return erreurs_schema(valeur, cible, racine, chemin)
    erreurs: list[str] = []
    for branche in schema.get("allOf", []):
        erreurs += erreurs_schema(valeur, branche, racine, chemin)
    if "anyOf" in schema and all(erreurs_schema(valeur, b, racine, chemin) for b in schema["anyOf"]):
        erreurs.append(f"{chemin} : aucune branche anyOf")
    if "oneOf" in schema and sum(not erreurs_schema(valeur, b, racine, chemin) for b in schema["oneOf"]) != 1:
        erreurs.append(f"{chemin} : oneOf")
    if "type" in schema:
        attendus = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](valeur) for t in attendus):
            return erreurs + [f"{chemin} : type {attendus} attendu"]
    if "enum" in schema and valeur not in schema["enum"]:
        erreurs.append(f"{chemin} : hors énumération")
    if isinstance(valeur, dict):
        for nom in schema.get("required", []):
            if nom not in valeur:
                erreurs.append(f"{chemin}.{nom} : requis")
        for nom, element in valeur.items():
            if nom in schema.get("properties", {}):
                erreurs += erreurs_schema(element, schema["properties"][nom], racine, f"{chemin}.{nom}")
            elif "additionalProperties" in schema:
                erreurs += erreurs_schema(element, schema["additionalProperties"], racine, f"{chemin}.{nom}")
    if isinstance(valeur, list) and "items" in schema:
        for rang, element in enumerate(valeur):
            erreurs += erreurs_schema(element, schema["items"], racine, f"{chemin}[{rang}]")
    return erreurs


def schema(relatif: str) -> dict:
    return json.loads((SCHEMAS / relatif).read_text(encoding="utf-8"))


def methodes_du_client() -> set[str]:
    return {m for branche in schema("ClientRequest.json")["oneOf"]
            for m in branche["properties"]["method"].get("enum", [])}


# ------------------------------------------------------------------ outils


def section(poste, **valeurs) -> SectionCodex:
    return SectionCodex(executable=Path(PYTHON), home=poste.emplacements.acp_local / "codex-home",
                        version_testee=valeurs.pop("version_testee", "0.156.1"), modeles_permis=(),
                        bac_a_sable="elevated")


async def sonder(poste, *, delai: float = 30.0, preparer: bool = True, **scenario):
    if preparer:
        poste.preparer_profil_codex()
    poste.scenario_codex = {k: v for k, v in scenario.items() if not (k == "enregistrer" and v is None)}
    return await sc.sonder_codex(section(poste), poste.emplacements, delai_s=delai,
                                 prefixe=poste.lanceurs()["codex"])


def enregistres(fichier: Path) -> list[dict]:
    return [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]


def processus_vivant(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        noyau.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        noyau.OpenProcess.restype = ctypes.c_void_p
        noyau.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        noyau.CloseHandle.argtypes = [ctypes.c_void_p]
        poignee = noyau.OpenProcess(0x1000, False, pid)
        if not poignee:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(noyau.GetExitCodeProcess(poignee, ctypes.byref(code))) and code.value == 259
        finally:
            noyau.CloseHandle(poignee)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and ") Z " in stat.read_text(encoding="ascii", errors="ignore"))


# ------------------------------------------------------------------ fidélité du faux et des requêtes


def test_les_reponses_du_faux_suivent_les_schemas_de_codex_0_156_1():
    assert erreurs_schema({"data": FAUX.MODELES, "nextCursor": None}, schema("v2/ModelListResponse.json")) == []
    assert erreurs_schema({"config": FAUX.CONFIG, "origins": FAUX.ORIGINES}, schema("v2/ConfigReadResponse.json")) == []
    for statut in ("ready", "notConfigured", "updateRequired"):
        assert erreurs_schema({"status": statut}, schema("v2/WindowsSandboxReadinessResponse.json")) == []
    assert erreurs_schema(FAUX.limites_par_defaut(), schema("v2/GetAccountRateLimitsResponse.json")) == []
    for compte in ({"type": "chatgpt", "email": FAUX.EMAIL, "planType": "prolite"}, {"type": "apiKey"}, None):
        assert erreurs_schema({"account": compte, "requiresOpenaiAuth": True}, schema("v2/GetAccountResponse.json")) == []
    assert erreurs_schema({"mode": "elevated", "success": True, "error": None},
                          schema("v2/WindowsSandboxSetupCompletedNotification.json")) == []
    assert erreurs_schema({"started": True}, schema("v2/WindowsSandboxSetupStartResponse.json")) == []
    # Le validateur refuse ce qu'il doit refuser.
    assert erreurs_schema({"status": "peut-etre"}, schema("v2/WindowsSandboxReadinessResponse.json")) != []


def test_les_methodes_admises_et_interdites_existent_dans_codex_0_156_1():
    methodes = methodes_du_client()
    assert METHODES_ADMISES <= methodes
    for methode in INTERDITES[:9]:
        assert methode in methodes, methode
    requetes_serveur = {m for b in schema("ServerRequest.json")["oneOf"] for m in b["properties"]["method"].get("enum", [])}
    assert "account/chatgptAuthTokens/refresh" in requetes_serveur


async def test_sonde_ne_demande_que_les_methodes_admises(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    resultat = await sonder(poste, enregistrer=str(fichier))
    assert resultat.releve["etat"] == "ok" and resultat.releve["origine_liste"] == "compte"
    principal = []
    for entree in enregistres(fichier):
        if "argv" in entree:
            principal.append([])
        elif "method" in entree:
            principal[-1].append(entree)
    methodes = [m["method"] for m in principal[1]]
    assert methodes == ["initialize", "initialized", "account/read", "config/read", "windowsSandbox/readiness",
                        "model/list", "account/rateLimits/read"]
    initialize, initialized, compte, config, readiness, liste, limites = principal[1]
    assert erreurs_schema(initialize, schema("JSONRPCRequest.json")) == []
    assert erreurs_schema(initialize["params"], schema("v1/InitializeParams.json")) == []
    assert erreurs_schema(initialized, schema("ClientNotification.json")) == [] and "id" not in initialized
    assert compte["params"] == {} and erreurs_schema(compte["params"], schema("v2/GetAccountParams.json")) == []
    assert config["params"] == {"includeLayers": False}
    assert erreurs_schema(config["params"], schema("v2/ConfigReadParams.json")) == []
    assert "params" not in readiness
    assert liste["params"] == {"includeHidden": False}
    assert erreurs_schema(liste["params"], schema("v2/ModelListParams.json")) == []
    assert limites["params"] == {"excludeResetCreditDetails": True}
    assert erreurs_schema(limites["params"], schema("v2/NullableGetAccountRateLimitsParams.json")) == []
    assert all("jsonrpc" not in m for m in principal[1])
    # Le second app-server (catalogue embarqué) ne demande que initialize, account/read et model/list.
    assert [m["method"] for m in principal[2]] == ["initialize", "initialized", "account/read", "model/list"]


async def test_surcharges_imposees_dans_l_argv(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    await sonder(poste, enregistrer=str(fichier))
    argvs = [e["argv"] for e in enregistres(fichier) if "argv" in e]
    assert argvs[0] == ["--version"]
    assert argvs[1] == [*SURCHARGES, "app-server"]
    assert argvs[1] == ["-c", 'windows.sandbox="elevated"', "-c", 'cli_auth_credentials_store="keyring"', "-c",
                        'service_tier="default"', "app-server"]


async def test_environnement_sans_cle_d_api(poste, tmp_path, monkeypatch):
    fichier = tmp_path / "env.json"
    for nom in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "ACP_SECRET_DE_TEST"):
        monkeypatch.setenv(nom, "sk-proj-" + "z" * 30)
    await sonder(poste, env=str(fichier))
    vu = json.loads(fichier.read_text(encoding="utf-8"))
    assert not {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "ACP_SECRET_DE_TEST"} & set(vu["noms"])
    assert vu["codex_home"] == str(poste.emplacements.acp_local / "codex-home")
    assert codex_environment(Path("/x"), source={"OPENAI_API_KEY": "k", "PATH": "p"}) == {"PATH": "p",
                                                                                           "CODEX_HOME": str(Path("/x"))}


async def test_setup_start_refuse_hors_interactif(tmp_path):
    session = Session(["inutile"], env={}, cwd=tmp_path)
    for methode in INTERDITES:
        with pytest.raises(MethodeRefusee):
            await session.appeler(methode, {})
    assert session.methodes_envoyees == []
    with pytest.raises(MethodeRefusee):
        await session.notifier("account/logout")


async def test_setup_start_sans_cwd(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    poste.scenario_codex.update(enregistrer=str(fichier))
    argv = [*poste.lanceurs()["codex"], *SURCHARGES, "app-server"]
    issue = await installer_bac_a_sable(argv, codex_environment(tmp_path), str(tmp_path), 30)
    assert issue == {"mode": "elevated", "success": True, "error": None}
    demande = next(e for e in enregistres(fichier) if e.get("method") == "windowsSandbox/setupStart")
    assert demande["params"] == {"mode": "elevated"}
    assert erreurs_schema(demande["params"], schema("v2/WindowsSandboxSetupStartParams.json")) == []


async def test_requete_serveur_repond_32601(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    resultat = await sonder(poste, enregistrer=str(fichier), requete_serveur=True)
    assert resultat.releve["etat"] == "ok" and resultat.mesures["requetes_du_serveur"] == 1
    reponse = next(e for e in enregistres(fichier) if e.get("id") == 900)
    assert reponse == {"id": 900, "error": {"code": -32601, "message": "non pris en charge par le poste"}}


async def test_notifications_et_reponses_etrangeres_ignorees(poste):
    resultat = await sonder(poste, notifications=True)
    assert resultat.releve["etat"] == "ok"


async def test_pagination_bornee(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    modeles = [dict(FAUX.MODELES[1], id=f"factice-{n}", model=f"factice-{n}") for n in range(3)]
    resultat = await sonder(poste, enregistrer=str(fichier), modeles=modeles, page=1,
                            embarque={"modeles": modeles[:1]})
    assert [m["id"] for m in resultat.releve["modeles"]] == ["factice-0", "factice-1", "factice-2"]
    curseurs = [e["params"].get("cursor") for e in enregistres(fichier) if e.get("method") == "model/list"]
    assert curseurs[:3] == [None, "1", "2"]
    trop = [dict(FAUX.MODELES[1], id=f"factice-{n}", model=f"factice-{n}") for n in range(65)]
    refuse = await sonder(poste, modeles=trop, page=50, enregistrer=None)
    assert refuse.releve["etat"] == "indisponible" and refuse.releve["detail"] == sc.TROP_DE_MODELES
    assert refuse.releve["modeles"] == []


async def test_extraction_liste_blanche(poste):
    resultat = await sonder(poste)
    texte = json.dumps(resultat.__dict__, ensure_ascii=False, default=str)
    for jete in ("email", FAUX.EMAIL, "description", "workspaceRouting", "availabilityNux", "texte promotionnel",
                 "inputModalities", "codexHome"):
        assert jete not in texte, jete
    premier = resultat.releve["modeles"][0]
    assert premier == {"id": "factice-codex-1", "displayName": "Factice 1", "isDefault": True,
                       "supportedReasoningEfforts": ["low", "medium", "high"], "defaultReasoningEffort": "medium",
                       "serviceTiers": ["default", "priority"], "defaultServiceTier": "default",
                       "modele": "factice-codex-1", "cache": False, "remplace_par": None,
                       "retrait_le": "2026-09-21T14:13:20Z", "nature": "catalogue_compte",
                       "resolution_documentee": None, "source_efforts": "releve"}
    assert resultat.connexion == "compte_chatgpt" and resultat.plan == "prolite"
    assert [c["limit_id"] for c in resultat.releve["compteurs"]] == ["codex"]


async def test_origine_catalogue_embarque_sans_compte(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    resultat = await sonder(poste, compte=None, enregistrer=str(fichier))
    assert resultat.releve["origine_liste"] == "catalogue_embarque" and resultat.releve["etat"] == "ok"
    assert resultat.releve["detail"] == sc.SANS_COMPTE and resultat.connexion == "non_connecte"
    assert [c["status"] for c in resultat.releve["compteurs"]] == ["not_signed_in"]
    argvs = [e["argv"] for e in enregistres(fichier) if "argv" in e]
    assert not any('cli_auth_credentials_store="ephemeral"' in a for a in argvs)
    assert "account/rateLimits/read" not in [e.get("method") for e in enregistres(fichier)]


async def test_origine_identique_au_catalogue_embarque(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    resultat = await sonder(poste, embarque={"modeles": FAUX.MODELES}, enregistrer=str(fichier))
    assert resultat.releve["origine_liste"] == "identique_au_catalogue_embarque"
    assert "liste de secours probable" in resultat.releve["detail"]
    cache = poste.emplacements.catalogue_embarque("0.156.1")
    assert json.loads(cache.read_text(encoding="utf-8"))["version"] == "0.156.1"
    fichier.unlink()
    await sonder(poste, embarque={"modeles": FAUX.MODELES}, enregistrer=str(fichier))
    assert not any('cli_auth_credentials_store="ephemeral"' in e["argv"]
                   for e in enregistres(fichier) if "argv" in e), "catalogue embarqué relu du cache"


async def test_second_app_server_ephemere_et_non_connecte(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    resultat = await sonder(poste, enregistrer=str(fichier))
    argvs = [e["argv"] for e in enregistres(fichier) if "argv" in e]
    assert argvs[2] == ["-c", 'cli_auth_credentials_store="ephemeral"', "app-server"]
    assert resultat.releve["origine_liste"] == "compte"
    poste.emplacements.catalogue_embarque("0.156.1").unlink()
    connecte = await sonder(poste, embarque={"compte": {"type": "chatgpt", "email": FAUX.EMAIL, "planType": "plus"}},
                            enregistrer=None)
    assert connecte.releve["etat"] == "indisponible" and connecte.releve["detail"] == sc.EMBARQUE_ILLISIBLE
    assert connecte.releve["modeles"] == []


@pytest.mark.parametrize("compte, connexion", [({"type": "apiKey"}, "cle_api"),
                                                ({"type": "amazonBedrock", "usesCodexManagedCredentials": True},
                                                 "autre")])
async def test_compte_cle_api_refuse(poste, compte, connexion):
    resultat = await sonder(poste, compte=compte)
    assert resultat.releve["etat"] == "indisponible" and resultat.releve["origine_liste"] == "aucune"
    assert resultat.releve["modeles"] == [] and resultat.connexion == connexion
    assert resultat.releve["detail"] == sc.COMPTE_HORS_ABONNEMENT


async def test_model_catalog_json_d_une_couche_refuse(poste):
    config = dict(FAUX.CONFIG, model_catalog_json="catalogue.json")
    origines = dict(FAUX.ORIGINES, model_catalog_json={"name": {"type": "system", "file": "C:/x"}, "version": "1"})
    resultat = await sonder(poste, config=config, origines=origines)
    assert resultat.releve["etat"] == "indisponible" and resultat.releve["detail"] == sc.CATALOGUE_LOCAL
    assert "C:/x" not in json.dumps(resultat.__dict__, default=str)


LU = datetime(2026, 9, 26, 9, 14, 4, tzinfo=UTC)


def _config(mode="elevated", origine="sessionFlags", stockage="keyring"):
    return {"mode": mode, "origine_mode": origine, "palier": "default", "stockage": stockage, "catalogue_local": False}


@pytest.mark.parametrize("readiness, config, admise, raison", [
    ("ready", _config(), True, None),
    ("ready", _config(origine="system"), False, sc.RAISONS_BAC["couche"].format(type="system")),
    ("ready", _config(mode="unelevated"), False, sc.RAISONS_BAC["unelevated"]),
    ("ready", _config(mode="mxc"), False, sc.RAISONS_BAC["mxc"]),
    ("updateRequired", _config(), False, sc.RAISONS_BAC["installation"]),
    ("notConfigured", _config(), False, sc.RAISONS_BAC["non_configure"]),
    ("ready", _config(mode="absent"), False, sc.RAISONS_BAC["illisible"]),
], ids=["ready-elevated-sessionFlags", "couche-systeme", "unelevated", "mxc", "updateRequired", "notConfigured",
        "mode-absent"])
def test_matrice_bac_a_sable(readiness, config, admise, raison):
    bloc = bac_a_sable(readiness, config, LU)
    assert bloc["ecriture_admise"] is admise and bloc["raison"] == raison
    from acp_poste_contrat.inventaire import BacASableCodex

    BacASableCodex.model_validate(bloc)


def test_stockage_hors_keyring_refuse_l_ecriture():
    bloc = bac_a_sable("ready", _config(stockage="file"), LU)
    assert bloc["ecriture_admise"] is False and "attendu : keyring" in bloc["raison"]


async def test_mode_lu_par_config_read_et_non_deduit_de_la_readiness(poste):
    """Readiness « ready » mais mode absent de config/read : écriture refusée (décision D60)."""
    config = dict(FAUX.CONFIG)
    config.pop("windows")
    resultat = await sonder(poste, config=config, readiness="ready")
    assert resultat.bac_a_sable["ecriture_admise"] is False
    assert resultat.bac_a_sable["mode_lu"] == "absent"
    assert resultat.bac_a_sable["raison"] == sc.RAISONS_BAC["illisible"]
    ok = await sonder(poste)
    assert ok.bac_a_sable["ecriture_admise"] is True and ok.bac_a_sable["origine_mode"] == "sessionFlags"


async def test_config_toml_modifie_refuse(poste, tmp_path):
    fichier = tmp_path / "enregistrement.jsonl"
    absent = await sonder(poste, preparer=False, enregistrer=str(fichier))
    assert absent.releve["etat"] == "non_connecte" and absent.releve["detail"] == sc.PROFIL_ABSENT
    assert not fichier.exists(), "aucun lancement sans profil"
    home = poste.preparer_profil_codex()
    assert etat_config_toml(home) == "conforme" and ecrire_config_toml(home) == "conforme"
    (home / "config.toml").write_bytes(CONFIG_TOML + b'model_catalog_json = "x.json"\n')
    modifie = await sonder(poste, preparer=False, enregistrer=str(fichier))
    assert modifie.releve["etat"] == "indisponible" and modifie.releve["detail"] == sc.CONFIG_MODIFIEE
    with pytest.raises(ValueError, match="modifié hors du poste"):
        ecrire_config_toml(home)
    assert not fichier.exists()


async def test_agents_md_dans_le_profil_refuse(poste):
    home = poste.preparer_profil_codex()
    (home / "AGENTS.md").write_text("instructions", encoding="utf-8")
    resultat = await sonder(poste, preparer=False)
    assert resultat.releve["etat"] == "indisponible" and resultat.releve["detail"] == sc.AGENTS_DANS_LE_PROFIL


async def test_arret_d_arbre_confirme(poste, tmp_path):
    pid = tmp_path / "pid.txt"
    resultat = await sonder(poste, delai=3, bloquer="initialize", pid=str(pid))
    assert resultat.releve["etat"] == "indisponible" and "délai de 3 s" in resultat.releve["detail"]
    numero = int(pid.read_text(encoding="ascii"))
    for _ in range(50):
        if not processus_vivant(numero):
            break
        await asyncio.sleep(0.1)
    assert not processus_vivant(numero), "l'app-server bloqué doit être arrêté"


async def test_version_bloquee_arretee(poste):
    resultat = await sonder(poste, delai=2, version_bloquee=True)
    assert resultat.releve["etat"] == "indisponible" and resultat.version["lue"] is None


@pytest.mark.parametrize("version, etat", [("codex-cli 0.99.0", "cli_hors_version"), (None, "indisponible")])
async def test_version_trop_ancienne_ou_illisible(poste, version, etat):
    resultat = await sonder(poste, version=version)
    assert resultat.releve["etat"] == etat and resultat.releve["modeles"] == []


async def test_version_non_testee_publiee_non_conforme(poste):
    resultat = await sonder(poste, version="codex-cli 0.157.0")
    assert resultat.releve["etat"] == "ok"
    assert resultat.version == {"lue": "0.157.0", "testee": "0.156.1", "conforme": False}


async def test_executable_absent(poste):
    poste.preparer_profil_codex()
    absent = SectionCodex(executable=poste.racine / "absent" / "codex.exe", home=poste.emplacements.acp_local /
                          "codex-home", version_testee="0.156.1", modeles_permis=(), bac_a_sable="elevated")
    resultat = await sc.sonder_codex(absent, poste.emplacements, delai_s=5)
    assert resultat.releve["etat"] == "cli_absente" and resultat.releve["detail"] == sc.CODEX_ABSENT


@pytest.mark.parametrize("scenario, detail", [({"planter": "config/read"}, sc.FERME),
                                               ({"ligne_invalide": "account/read"}, sc.MAL_FORME)])
async def test_echanges_casses(poste, scenario, detail):
    resultat = await sonder(poste, **scenario)
    assert resultat.releve["etat"] == "indisponible" and resultat.releve["detail"] == detail


async def test_erreur_des_limites_sans_echo_du_serveur(poste):
    resultat = await sonder(poste, limites="erreur")
    assert resultat.releve["etat"] == "ok"
    compteur = resultat.releve["compteurs"][0]
    assert compteur["status"] == "unavailable" and "code -32600" in compteur["detail"]
    assert FAUX.EMAIL not in json.dumps(resultat.releve)


async def test_releve_conforme_au_contrat(poste):
    from acp_poste_contrat.inventaire import valider_releve

    resultat = await sonder(poste)
    valider_releve(dict(resultat.releve, depots=[]))
    for echec in (await sonder(poste, compte={"type": "apiKey"}), await sonder(poste, version=None)):
        valider_releve(dict(echec.releve, depots=[]))


def test_commandes_des_textes_publies_executables_et_publiables():
    """Relecture de P5 (décision D68) : les textes publiés dans l'inventaire citaient « acp-poste connexion codex »,
    qu'aucune console ne reconnaît. Ils citent la forme exécutable sans lettre de lecteur, que la garde admet."""
    from acp_poste_contrat.inventaire import raison_identifiant
    from acp_poste_contrat.machine import commande_publiee

    from acp_poste.subscription_quotas import CODEX_API_KEY_ACCOUNT

    textes = {sc.PROFIL_ABSENT: "connexion codex", sc.CONFIG_MODIFIEE: "connexion codex",
              sc.SANS_COMPTE: "connexion codex", sc.COMPTE_HORS_ABONNEMENT: "connexion codex",
              sc.RAISONS_BAC["installation"]: "connexion bac-a-sable", CODEX_API_KEY_ACCOUNT: "connexion codex"}
    for texte, arguments in textes.items():
        assert commande_publiee(arguments) in texte, texte
        assert raison_identifiant(texte) is None, texte
        assert "« acp-poste " not in texte and "(acp-poste " not in texte and ": acp-poste " not in texte, texte
        assert len(texte) <= 300, texte
