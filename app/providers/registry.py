"""Registered provider adapters."""

from app.providers.base import TransitProvider
from app.providers.gdansk import GdanskProvider
from app.providers.mkuran import mkuran_providers


def registered_providers() -> dict[str, TransitProvider]:
    """Return all installed providers keyed by their stable URL slug."""
    providers = (*mkuran_providers(), GdanskProvider())
    return {provider.slug: provider for provider in providers}


def select_providers(requested: tuple[str, ...]) -> list[TransitProvider]:
    """Select requested enabled providers; an empty request selects all enabled providers."""
    registry = registered_providers()
    selected_slugs = requested or tuple(registry)
    unknown = sorted(set(selected_slugs).difference(registry))
    if unknown:
        unknown_text = ", ".join(unknown)
        raise ValueError(f"Unknown provider(s): {unknown_text}")
    return [registry[slug] for slug in selected_slugs if registry[slug].enabled]
