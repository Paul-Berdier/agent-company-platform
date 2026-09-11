"""Adaptations de tests legacy qui ne doivent pas rouvrir l'API en production."""

from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def authenticate_legacy_office_test(request):
    """Injecte un owner uniquement dans l'ancien test Pixel déjà présent.

    Les suites auth/RBAC utilisent les vraies sessions. Cette adaptation isolée
    évite de modifier le fichier Pixel localement enrichi par l'utilisateur.
    """

    if request.node.path.name != "test_office_config.py":
        yield
        return

    from acp_api.deps import get_principal
    from acp_api.main import app
    from acp_api.security import hash_password
    from acp_database import get_session_factory, init_db
    from acp_database.models import UserModel

    init_db()
    with get_session_factory()() as db:
        owner = UserModel(
            login_normalized=f"legacy-office-{uuid4().hex}",
            display_name="Test office legacy",
            password_hash=hash_password("legacy office test password"),
            platform_role="owner",
        )
        db.add(owner)
        db.commit()
        owner_id = owner.id

    app.dependency_overrides[get_principal] = lambda: owner_id
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_principal, None)
