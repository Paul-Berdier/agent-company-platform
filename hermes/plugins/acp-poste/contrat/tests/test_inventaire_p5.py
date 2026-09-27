"""Contrat D21 étendu à l'étape P5 (cahier P5 § 11) : élargi sans rien restreindre, inventaire complet du poste,
résumé des quotas calculé par le greffon et garde « aucun identifiant »."""

from __future__ import annotations

import copy
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from acp_poste_contrat.inventaire import (
    InventairePoste,
    Releve,
    identifiant_trouve,
    resume_quotas,
    valider_inventaire,
    valider_releve,
)
from acp_poste_contrat.quotas import SubscriptionQuotaReport

ICI = Path(__file__).resolve().parent
FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "outils" / "fixtures_machine"


def _module_p4():
    spec = importlib.util.spec_from_file_location("acp_test_inventaire_p4", ICI / "test_inventaire.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inventaire() -> dict:
    return json.loads((FIXTURES / "inventaire_requete.json").read_text(encoding="utf-8"))


def _releve_poste(**modifs) -> dict:
    releve = copy.deepcopy(_inventaire()["releves"][0])
    releve.update(modifs)
    return releve


# Relevé factice des tests d'image de P4 (hermes/tests/image/conftest.py, releve_factice), recopié tel quel.
RELEVE_FACTICE_IMAGE_P4 = {
    "voie": "poste-codex", "source": "releve_factice", "version_cli": "0.0.0-factice",
    "releve_le": "2026-09-26T08:00:00+00:00",
    "modeles": [
        {"id": "factice-codex-1", "displayName": "Factice codex 1", "isDefault": True,
         "supportedReasoningEfforts": ["low", "medium", "high", "xhigh", "max", "extreme"],
         "defaultReasoningEffort": "medium", "serviceTiers": ["default", "priority"], "defaultServiceTier": "default"},
        {"id": "factice-codex-2", "isDefault": False, "supportedReasoningEfforts": ["low"]},
    ],
    "quotas": {"pourcentage_utilise": 42},
    "depots": [{"alias": "jetable"}],
}


def test_releve_factice_p4_toujours_valide():
    """Tout relevé que P4 acceptait reste accepté, et relu à l'identique (lignes déjà en base)."""
    p4 = _module_p4()
    for donnees in (p4.RELEVE, RELEVE_FACTICE_IMAGE_P4):
        releve = valider_releve(copy.deepcopy(donnees))
        assert releve.origine_liste is None and releve.etat is None and releve.compteurs == []
        assert releve.modele_par_defaut().id == "factice-codex-1"
        # Une ligne de P4 en base (contenu JSON de model_dump) se relit sans erreur après l'extension.
        ancien = {k: v for k, v in releve.model_dump(mode="json").items()
                  if k in ("voie", "source", "version_cli", "releve_le", "modeles", "quotas", "depots")}
        for modele in ancien["modeles"]:
            for cle in ("modele", "cache", "remplace_par", "retrait_le", "nature", "resolution_documentee",
                        "source_efforts"):
                modele.pop(cle)
        assert Releve.model_validate(ancien).model_dump() == releve.model_dump()


def test_alias_a_crochets_admis():
    releve = valider_releve(_inventaire()["releves"][1])
    assert releve.modele("opus[1m]").resolution_documentee == "claude-opus-5-5"
    assert releve.modele_par_defaut() is None  # isDefault nul partout : la doc ne désigne aucun alias
    assert releve.modele("haiku").supportedReasoningEfforts == []


def test_releve_poste_sans_origine_refuse():
    for champ in ("origine_liste", "etat"):
        donnees = _releve_poste()
        del donnees[champ]
        with pytest.raises(ValueError, match="un relevé du poste exige « origine_liste » et « etat »"):
            valider_releve(donnees)


def test_modeles_vides_seulement_en_echec():
    with pytest.raises(ValueError, match="« modeles » doit être une liste non vide"):
        valider_releve(_releve_poste(modeles=[]))
    with pytest.raises(ValueError, match="« detail » : un relevé à l'état cli_absente doit expliquer pourquoi"):
        valider_releve(_releve_poste(modeles=[], etat="cli_absente", origine_liste="aucune", compteurs=[]))
    releve = valider_releve(_releve_poste(modeles=[], etat="cli_absente", origine_liste="aucune", compteurs=[],
                                          detail="Codex CLI absent du poste."))
    assert releve.modeles == [] and releve.etat == "cli_absente"


def test_efforts_inconnus_et_coherence():
    donnees = _releve_poste()
    donnees["modeles"][0]["supportedReasoningEfforts"] = None
    with pytest.raises(ValueError, match="un effort par défaut exige des efforts connus"):
        valider_releve(donnees)
    donnees["modeles"][0]["defaultReasoningEffort"] = None
    assert valider_releve(donnees).modeles[0].supportedReasoningEfforts is None


def test_quotas_du_poste_refuses():
    donnees = _inventaire()
    donnees["releves"][0]["quotas"] = {"pourcentage_utilise": 10}
    with pytest.raises(ValueError, match="résumé calculé par le greffon depuis « compteurs »"):
        valider_inventaire(donnees)


def test_releve_factice_refuse_dans_un_inventaire():
    donnees = _inventaire()
    donnees["releves"][0]["source"] = "releve_factice"
    with pytest.raises(ValueError, match="le poste ne publie que des relevés « poste »"):
        valider_inventaire(donnees)


def test_depots_recopies():
    donnees = _inventaire()
    donnees["releves"][1]["depots"] = []
    with pytest.raises(ValueError, match="chaque relevé recopie les dépôts de l'inventaire"):
        valider_inventaire(donnees)


def test_inventaire_exemple_valide():
    inventaire = valider_inventaire(_inventaire())
    assert isinstance(inventaire, InventairePoste)
    assert [r.voie for r in inventaire.releves] == ["poste-codex", "poste-claude"]
    assert inventaire.bac_a_sable_codex.ecriture_admise is True
    assert inventaire.versions["codex"].conforme is True
    assert inventaire.politique.alias_claude_permis[1] == "opus[1m]"


def test_une_voie_par_releve():
    donnees = _inventaire()
    donnees["releves"][1] = copy.deepcopy(donnees["releves"][0])
    with pytest.raises(ValueError, match="une seule entrée par voie"):
        valider_inventaire(donnees)


def test_compteurs_de_la_bonne_voie():
    donnees = _releve_poste()
    donnees["compteurs"][0]["provider"] = "claude_code"
    donnees["compteurs"][0]["source"] = "claude_code_statusline"
    with pytest.raises(ValueError, match="ne porte que des quotas codex"):
        valider_releve(donnees)


def test_compteur_dans_le_futur_refuse():
    donnees = _releve_poste()
    donnees["compteurs"][0]["observed_at"] = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    with pytest.raises(ValueError, match="plus de cinq minutes dans le futur"):
        valider_releve(donnees)


@pytest.mark.parametrize("modifs, motif", [
    ({"ecriture_admise": True, "mode_lu": "unelevated"}, "« ecriture_admise » vrai exige"),
    ({"ecriture_admise": True, "origine_mode": "system"}, "« ecriture_admise » vrai exige"),
    ({"ecriture_admise": True, "stockage_identifiants_lu": "file"}, "« ecriture_admise » vrai exige"),
    ({"ecriture_admise": True, "readiness": "updateRequired"}, "« ecriture_admise » vrai exige"),
    ({"ecriture_admise": False, "raison": None}, "une écriture refusée doit dire pourquoi"),
    ({"readiness": "prete"}, "« readiness » : valeurs admises"),
])
def test_matrice_du_bac_a_sable(modifs, motif):
    donnees = _inventaire()
    donnees["bac_a_sable_codex"].update(modifs)
    with pytest.raises(ValueError, match=motif):
        valider_inventaire(donnees)


def test_version_conforme_coherente():
    donnees = _inventaire()
    donnees["versions"]["claude"] = {"lue": "2.1.281", "testee": "2.1.280", "conforme": True}
    with pytest.raises(ValueError, match="« conforme » doit valoir vrai exactement"):
        valider_inventaire(donnees)
    donnees["versions"]["claude"] = {"lue": None, "testee": "2.1.280", "conforme": False}
    assert valider_inventaire(donnees).versions["claude"].lue is None


def test_resolutions_observees_reservees_a_p6():
    donnees = _releve_poste(resolutions_observees=[{"alias": "opus", "modele": "claude-opus-5-5",
                                                   "observe_le": "2026-09-26T09:00:00Z"}])
    with pytest.raises(ValueError, match="réservé à l'étape P6"):
        valider_releve(donnees)


def test_messages_en_francais_meme_pour_les_types():
    donnees = _inventaire()
    donnees["poste"]["hermes_meme_enveloppe_que_codex"] = "non"
    donnees["versions"] = {"codex": 3}
    with pytest.raises(ValueError) as exc:
        valider_inventaire(donnees)
    message = str(exc.value)
    assert message.startswith("Inventaire refusé : ")
    assert "Input should" not in message and "should be" not in message
    assert "doit être un booléen" in message


def _rapport(pct, resets, status="ok", limit_id="codex"):
    return SubscriptionQuotaReport.model_validate({
        "provider": "codex", "status": status, "source": "codex_app_server", "limit_id": limit_id,
        "windows": [] if status != "ok" else [
            {"key": "primary", "used_percent": pct, "window_minutes": 300, "resets_at": resets},
            {"key": "secondary", "used_percent": 5, "window_minutes": 10080, "resets_at": "2026-10-01T00:00:00Z"}],
        "observed_at": "2026-09-26T09:00:00Z", "detail": None if status == "ok" else "Codex non connecté."})


def test_resume_quotas_max_des_fenetres():
    resume = resume_quotas([_rapport(41, "2026-09-26T12:00:00Z"), _rapport(87.5, "2026-09-26T13:00:00Z",
                                                                            limit_id="autre")])
    assert resume.pourcentage_utilise == 87.5
    assert resume.remise_a_zero == datetime(2026, 9, 26, 13, tzinfo=UTC)
    assert resume_quotas([]) is None
    assert resume_quotas([_rapport(None, None, status="not_signed_in", limit_id="probe")]) is None
    sans_part = _rapport(None, "2026-09-26T12:00:00Z")
    sans_part.windows[1].used_percent = None
    assert resume_quotas([sans_part]) is None  # aucune part lue : jamais estimée


@pytest.mark.parametrize("valeur, raison", [
    ("paul" + "@" + "exemple.invalid", "adresse électronique (« @ »)"),
    ("C:\\Users\\paul\\depot", "chemin de lecteur"),
    ("voir D:/depots/jetable", "chemin de lecteur"),
    ("\\\\serveur\\partage", "chemin réseau (UNC)"),
    ("/home/x/USERS/y", "chemin de profil utilisateur"),
    ("jeton acpm_ tronqué", "jeton machine ou code d'enrôlement d'ACP"),
    ("clé " + "sk-" + "ant-" + "a" * 24, "ce qui ressemble à un secret (clé d'API Anthropic)"),
])
def test_identifiant_trouve(valeur, raison):
    donnees = _inventaire()
    donnees["releves"][0]["detail"] = valeur
    trouve = identifiant_trouve(donnees)
    assert trouve == f"releves[0].detail : {raison}"


def test_identifiant_sur_valeurs_decodees_et_valeurs_exactes():
    """La garde lit les valeurs DÉCODÉES : « C:\\\\x » du texte JSON est « C:\\x » une fois décodé."""
    texte = json.dumps({"detail": "C:\\x"})
    assert "\\\\" in texte and identifiant_trouve(json.loads(texte)) == "detail : chemin de lecteur"
    assert identifiant_trouve(_inventaire()) is None
    assert identifiant_trouve({"a": ["rien", {"b": "Factice 1"}]}, valeurs_exactes=("Factice",)) == (
        "a[1].b : valeur du coffre du poste")
    assert identifiant_trouve({"https://hermes.acp.test": 1}) is None  # une URL n'est pas un chemin de lecteur
    assert identifiant_trouve({"C:\\": 1}) == "C:\\ : clé refusée (chemin de lecteur)"


def test_identifiant_trouve_sans_recursion_sur_un_objet_tres_imbrique():
    """Relecture de P5 : le balayage récursif levait RecursionError sur un corps très imbriqué (500 sur la route
    d'inventaire au lieu d'un 422) ; itératif, il rend le premier identifiant trouvé ou None, à toute profondeur."""
    profond: object = "rien"
    for _ in range(20_000):
        profond = [profond]
    assert identifiant_trouve(profond) is None
    profond = "C:/x"
    for _ in range(20_000):
        profond = {"a": profond}
    trouve = identifiant_trouve(profond)
    assert trouve is not None and trouve.endswith(".a : chemin de lecteur") and trouve.startswith("a.a.a")


def test_identifiant_trouve_garde_l_ordre_cle_puis_valeur():
    assert identifiant_trouve({"a": "rien", "b": {"C:/": "x@y"}, "c": "D:/z"}) == "b.C:/ : clé refusée (chemin de lecteur)"
    assert identifiant_trouve({"a": ["x", "y@z"], "b": "C:/"}) == "a[1] : adresse électronique (« @ »)"


def test_profondeur_depasse():
    from acp_poste_contrat.inventaire import profondeur_depasse

    assert not profondeur_depasse(_inventaire(), 10)
    assert not profondeur_depasse({"a": [{"b": []}]}, 4) and profondeur_depasse({"a": [{"b": []}]}, 3)
    profond: object = {}
    for _ in range(20_000):
        profond = [profond]
    assert profondeur_depasse(profond, 32) and not profondeur_depasse("texte", 0)
