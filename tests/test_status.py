"""Provider refresh status API tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fastapi import FastAPI, Request

from app.api.routes import provider_status, router
from app.core.database import Database
from app.core.refresh import RefreshService
from app.providers.base import TransitProvider


class _ExampleProvider(TransitProvider):
    slug = "example"
    city = "Example City"
    static_url = "https://example.invalid/feed.zip"


def test_status_lists_every_configured_provider_before_first_refresh(tmp_path: Path) -> None:
    database = Database(tmp_path / "transit.sqlite3")
    database.initialize()
    provider = _ExampleProvider()
    application = FastAPI()
    application.state.database = database
    application.state.providers = {provider.slug: provider}
    application.state.refresh_service = RefreshService(database, [provider], 86_400)
    application.include_router(router)

    response = provider_status(cast(Request, SimpleNamespace(app=application)))

    assert "/status" in application.openapi()["paths"]
    assert [item.model_dump(mode="json") for item in response] == [
        {"slug": "example", "city": "Example City", "status": "pending", "progress": 0.0}
    ]
