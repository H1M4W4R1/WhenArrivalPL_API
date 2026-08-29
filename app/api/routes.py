"""FastAPI routes for reduced transit data."""

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.core.database import Database
from app.core.refresh import RefreshService
from app.models.departure_model import DepartureModel
from app.models.health_model import HealthModel
from app.models.provider_model import ProviderModel
from app.models.provider_status_model import ProviderStatusModel
from app.models.stop_model import StopModel
from app.models.ticket_machine_model import TicketMachineModel
from app.providers.base import TransitProvider
from app.repositories.transit_queries import schedule, stops, ticket_machines

router = APIRouter()


def _database(request: Request) -> Database:
    database = getattr(request.app.state, "database", None)
    if not isinstance(database, Database):
        raise RuntimeError("Application database is unavailable")
    return database


def _providers(request: Request) -> dict[str, TransitProvider]:
    providers = getattr(request.app.state, "providers", None)
    if not isinstance(providers, dict):
        raise RuntimeError("Application providers are unavailable")
    return providers


def _refresh_service(request: Request) -> RefreshService:
    refresh_service = getattr(request.app.state, "refresh_service", None)
    if not isinstance(refresh_service, RefreshService):
        raise RuntimeError("Application refresh status is unavailable")
    return refresh_service


def _provider_or_404(provider_slug: str, request: Request) -> TransitProvider:
    provider = _providers(request).get(provider_slug)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown transit provider")
    return provider


@router.get("/health", response_model=HealthModel)
def health(request: Request) -> HealthModel:
    """Report readiness without exposing source URLs or secrets."""
    return HealthModel(status="ok", providers=len(_providers(request)))


@router.get("/status", response_model=list[ProviderStatusModel])
def provider_status(request: Request) -> list[ProviderStatusModel]:
    """Report current refresh state and progress for every configured provider."""
    providers_by_slug = _providers(request)
    statuses: list[ProviderStatusModel] = []
    for item in _refresh_service(request).statuses():
        provider = providers_by_slug.get(item.slug)
        if provider is None:
            raise RuntimeError(f"Provider metadata is unavailable for status: {item.slug}")
        statuses.append(
            ProviderStatusModel(
                slug=item.slug,
                city=provider.city,
                status=item.state,
                progress=item.progress,
            )
        )
    return statuses


@router.get("/transit", response_model=list[ProviderModel])
def providers(request: Request) -> list[ProviderModel]:
    """List active provider slugs and their cities."""
    return [
        ProviderModel(
            slug=provider.slug,
            city=provider.city,
            enabled=provider.enabled,
            has_realtime=bool(provider.trip_update_urls()),
        )
        for provider in _providers(request).values()
    ]


@router.get("/transit/{transit_provider}/stops", response_model=list[StopModel])
def list_stops(
    request: Request,
    transit_provider: str,
    query: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[StopModel]:
    """List stops, optionally filtering a bounded text fragment."""
    _provider_or_404(transit_provider, request)
    with _database(request).connection() as connection:
        return stops(connection, transit_provider, query)


@router.get("/transit/{transit_provider}/stops/{stop_name}", response_model=list[StopModel])
def search_stops(
    request: Request,
    transit_provider: str,
    stop_name: str = Path(min_length=1, max_length=100),
) -> list[StopModel]:
    """Return only stops whose names fuzzy-match the supplied text."""
    _provider_or_404(transit_provider, request)
    with _database(request).connection() as connection:
        return stops(connection, transit_provider, stop_name)


@router.get(
    "/transit/{transit_provider}/ticketing/machines",
    response_model=list[TicketMachineModel],
)
def list_ticket_machines(request: Request, transit_provider: str) -> list[TicketMachineModel]:
    """List ticket machines with their position and available type."""
    _provider_or_404(transit_provider, request)
    with _database(request).connection() as connection:
        return ticket_machines(connection, transit_provider)


@router.get(
    "/transit/{transit_provider}/schedule/{stop_name}/{count}",
    response_model=list[DepartureModel],
)
def list_stop_schedule(
    request: Request,
    transit_provider: str,
    stop_name: str = Path(min_length=1, max_length=150),
    count: int = Path(ge=1, le=100),
) -> list[DepartureModel]:
    """List departures for an exact stop name, falling back to a fuzzy match."""
    _provider_or_404(transit_provider, request)
    with _database(request).connection() as connection:
        return schedule(connection, transit_provider, stop_name, count)


@router.get(
    "/transit/{transit_provider}/schedule/{count}",
    response_model=list[DepartureModel],
)
def list_provider_schedule(
    request: Request,
    transit_provider: str,
    count: int = Path(ge=1, le=100),
) -> list[DepartureModel]:
    """List the next departures across all stops for one transit provider."""
    _provider_or_404(transit_provider, request)
    with _database(request).connection() as connection:
        return schedule(connection, transit_provider, None, count)
