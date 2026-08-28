"""ASGI entry point and lifecycle management."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings, parse_settings
from app.core.database import Database
from app.core.refresh import RefreshService
from app.providers.registry import select_providers


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct the application without importing mutable process-global settings."""
    active_settings = settings or parse_settings([])
    selected_providers = select_providers(active_settings.providers)
    database = Database(active_settings.database_path)
    refresh_service = RefreshService(
        database,
        selected_providers,
        active_settings.static_refresh_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        app.state.database = database
        app.state.providers = {provider.slug: provider for provider in selected_providers}
        task = asyncio.create_task(_refresh_forever(refresh_service, active_settings.refresh_seconds))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="IOT Open API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


async def _refresh_forever(service: RefreshService, seconds: int) -> None:
    await service.refresh_all()
    while True:
        await asyncio.sleep(seconds)
        await service.refresh_all()


def run() -> None:
    """Run the Uvicorn server with command-line settings."""
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(parse_settings()), host="0.0.0.0", port=8000)


app = create_app()


if __name__ == "__main__":
    run()
