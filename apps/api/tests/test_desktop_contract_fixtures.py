"""Les documents d'API versionnés pour les tests du client desktop suivent l'API réelle.

Les fichiers de ``apps/desktop/tests/fixtures/`` sont lus par les tests Qt Test
(``tst_compatibility``, ``tst_session_state``, ``tst_readiness``) : ce sont les formes sur lesquelles la
station éprouve sa lecture du contrat. Si le serveur ajoute, retire ou renomme un champ,
ces tests échouent ici, côté Python, avant que le client natif ne lise une forme qui
n'existe plus.

C'est exactement ce qui s'est produit avant leur existence, découvert à la première
connexion réelle du client, le 18 septembre 2026 : la station lisait
``api_contract_version`` à plat quand ``GET /meta`` publiait ``versions.api_contract``,
envoyait ``email`` quand ``POST /auth/login`` exige ``login``, lisait
``platform_role`` quand la session publie ``role``, et lisait ``status`` et ``detail``
quand ``/ready`` publie ``ok`` et ``reason``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from acp_api.deps import get_db
from acp_api.main import app
from acp_contracts.auth import AuthSessionResponse, LoginRequest
from acp_contracts.compatibility import CompatibilityDocument
from acp_database.testing import make_test_engine

FIXTURES = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "tests" / "fixtures"

BOOTSTRAP_TOKEN = "jeton-d-amorcage-de-test-suffisamment-long"
PASSWORD = "mot de passe de test suffisamment long"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _shape(value):
    """Arbre des clés et des types JSON, sans les valeurs."""

    if isinstance(value, dict):
        return {key: _shape(child) for key, child in value.items()}
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


#: Variables conservées : la base de test posée par conftest.py. La retirer ferait
#: retomber l'API sur ``./acp.db``, la base de développement du poste.
PRESERVED_ENV = frozenset({"ACP_DATABASE_URL"})


@pytest.fixture
def clean_environ(monkeypatch):
    """Serveur sans aucune bascule, sur la base de test de la session."""

    for name in list(os.environ):
        if name.startswith("ACP_") and name not in PRESERVED_ENV:
            monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_meta_fixture_is_a_valid_compatibility_document():
    CompatibilityDocument.model_validate(_fixture("meta-document.json"))


def test_meta_fixture_has_exactly_the_shape_served_by_the_api(clean_environ):
    with TestClient(app) as client:
        response = client.get("/meta")
    assert response.status_code == 200, response.text
    assert _shape(_fixture("meta-document.json")) == _shape(response.json()), (
        "La forme de GET /meta a changé : régénérez "
        "apps/desktop/tests/fixtures/meta-document.json et adaptez "
        "CompatibilityService::evaluate côté desktop."
    )


def test_login_request_fixture_is_accepted_by_the_login_contract():
    LoginRequest.model_validate(_fixture("auth-login-request.json"))


def test_session_fixture_is_a_valid_session_response():
    AuthSessionResponse.model_validate(_fixture("auth-session.json"))


def test_login_and_session_fixtures_match_a_real_login(clean_environ, tmp_path):
    clean_environ.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    database = make_test_engine(tmp_path)
    session_factory = sessionmaker(bind=database.engine, expire_on_commit=False)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={"login": "owner", "display_name": "Propriétaire", "password": PASSWORD},
            )
            assert created.status_code == 201, created.text

            request = _fixture("auth-login-request.json")
            request["login"] = "owner"
            request["password"] = PASSWORD
            logged_in = client.post("/auth/login", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close()

    assert logged_in.status_code == 200, logged_in.text
    assert _shape(_fixture("auth-session.json")) == _shape(logged_in.json()), (
        "La forme de la réponse de session a changé : régénérez "
        "apps/desktop/tests/fixtures/auth-session.json et adaptez "
        "AuthManager::applySessionPayload côté desktop."
    )


def _assert_readiness_contract(document: dict) -> None:
    checks = document["checks"]
    assert checks, "/ready doit détailler ses contrôles"
    for name, check in checks.items():
        assert isinstance(check.get("ok"), bool), f"{name} : « ok » booléen attendu"
        assert isinstance(check.get("reason"), str) and check["reason"], (
            f"{name} : « reason » attendue"
        )


def test_ready_fixture_and_live_ready_follow_the_readiness_contract(clean_environ):
    fixture = _fixture("ready-document.json")
    _assert_readiness_contract(fixture)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code in (200, 503), response.text
    served = response.json()
    _assert_readiness_contract(served)
    assert set(served["checks"]) == set(fixture["checks"]), (
        "Les contrôles de /ready ont changé : régénérez "
        "apps/desktop/tests/fixtures/ready-document.json et vérifiez "
        "ReadinessModel::parseChecks côté desktop."
    )
