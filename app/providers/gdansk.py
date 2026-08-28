"""Public ZTM Gdańsk feeds."""

from app.providers.base import TransitProvider


class GdanskProvider(TransitProvider):
    """ZTM Gdańsk: static GTFS, public GTFS-RT, and ticket machines."""

    slug = "gdansk"
    city = "Gdańsk"
    static_url = (
        "https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/"
        "resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip"
    )
    trip_updates_url = "http://ckan2.multimediagdansk.pl/gtfs-rt?feed=tripUpdates"
    ticket_machines_url = "https://files.cloudgdansk.pl/d/otwarte-dane/ztm/biletomaty.json"
