"""Public Polish GTFS feeds curated by mkuran.pl."""

from dataclasses import dataclass

from app.providers.base import TransitProvider


@dataclass(frozen=True, slots=True)
class MkuranProvider(TransitProvider):
    """One city feed published by the mkuran.pl service."""

    slug: str
    city: str
    static_url: str
    trip_updates_url: str | None = None
    ticket_machines_url: str | None = None


def mkuran_providers() -> tuple[TransitProvider, ...]:
    """Return every Polish municipal feed currently exposed by mkuran.pl."""
    base_url = "https://mkuran.pl/gtfs/"
    return (
        MkuranProvider("warsaw", "Warszawa", f"{base_url}warsaw.zip"),
        MkuranProvider("wkd", "Warszawska Kolej Dojazdowa", f"{base_url}wkd.zip", f"{base_url}wkd.pb"),
        MkuranProvider(
            "polish-trains",
            "Polskie koleje",
            f"{base_url}polish_trains.zip",
            f"{base_url}polish_trains/updates.pb",
        ),
        MkuranProvider("bydgoszcz", "Bydgoszcz", f"{base_url}bydgoszcz.zip"),
        MkuranProvider("radom", "Radom", f"{base_url}radom.zip"),
        MkuranProvider("gzm", "Górnośląsko-Zagłębiowska Metropolia", f"{base_url}gzm.zip"),
        MkuranProvider("rzeszow", "Rzeszów", f"{base_url}rzeszow.zip"),
        MkuranProvider("lublin", "Lublin", f"{base_url}lublin.zip"),
        MkuranProvider("kielce", "Kielce", f"{base_url}kielce.zip"),
        MkuranProvider("torun", "Toruń", f"{base_url}torun.zip"),
        MkuranProvider("wejherowo", "Wejherowo", f"{base_url}wejherowo.zip"),
        MkuranProvider("lomza", "Łomża", f"{base_url}lomza.zip"),
        MkuranProvider("swinoujscie", "Świnoujście", f"{base_url}swinoujscie.zip"),
        MkuranProvider("gizycko", "Giżycko", f"{base_url}gizycko.zip"),
        MkuranProvider("elk", "Ełk", f"{base_url}elk.zip", f"{base_url}elk.pb"),
        MkuranProvider("elblag", "Elbląg", f"{base_url}elblag.zip"),
        MkuranProvider("gorzow-wlkp", "Gorzów Wielkopolski", f"{base_url}gorzow_wlkp.zip"),
    )
