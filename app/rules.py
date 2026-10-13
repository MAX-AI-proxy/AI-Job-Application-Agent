
import re
import unicodedata
from difflib import SequenceMatcher

from app.database import ROOT, connect
from app.configuration import load_distance_settings
from app.urls import distinct_urls, urls_match


# Diese Ortslisten dienen als konservative Vorprüfung.
# Bei unbekannten Orten wird eine manuelle Prüfung verlangt.

def normalized(value: str) -> str:
    value = value.casefold()
    value = (
        value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def excluded_companies() -> list[str]:
    source = ROOT / "config" / "suchprofil.md"

    if not source.exists():
        raise FileNotFoundError(
            f"Suchprofil fehlt: {source}"
        )

    text = source.read_text(encoding="utf-8")

    match = re.search(
        r"^#{2,6}\s*Ausgeschlossene Unternehmen\s*$"
        r"([\s\S]*?)(?=^#{1,6}\s|\Z)",
        text,
        flags=re.I | re.M,
    )

    if not match:
        raise ValueError(
            "Abschnitt '## Ausgeschlossene Unternehmen' "
            "fehlt in suchprofil.md"
        )

    companies = []

    for line in match.group(1).splitlines():
        item = re.match(
            r"^\s*[-*]\s+(.+?)\s*$",
            line
        )

        if item:
            raw = item.group(1).strip()

            if (
                raw.startswith("[")
                or "ergänzen" in raw.lower()
            ):
                continue

            companies.extend(
                v.strip()
                for v in raw.split("|")
                if v.strip()
            )

    return companies


def is_excluded(company: str) -> bool:
    name = normalized(company)

    for excluded in excluded_companies():
        needle = normalized(excluded)

        if needle and re.search(
            r"(?<!\w)"
            + re.escape(needle)
            + r"(?!\w)",
            name
        ):
            return True

    return False


def location_band(location: str) -> str:
    text = normalized(location)

    if not text:
        return "unbekannt"

    try:
        settings = load_distance_settings(ROOT)
    except ValueError:
        return "unbekannt"

    far = any(
        re.search(
            r"(?<!\w)" + re.escape(c) + r"(?!\w)",
            text
        )
        for c in (normalized(city) for city in settings.far_cities)
    )

    near = any(
        re.search(
            r"(?<!\w)" + re.escape(c) + r"(?!\w)",
            text
        )
        for c in (normalized(city) for city in settings.near_cities)
    )

    if far and not near:
        return "fern"

    if near and not far:
        return "regional"

    return "unbekannt"


def suitability(
    company: str,
    location: str,
    attendance: str,
    application_format: str,
    open_for_applications: bool,
    description: str,
) -> tuple[str, str]:

    if is_excluded(company):
        return (
            "gesperrt",
            "Unternehmen ist ausgeschlossen"
        )

    if not open_for_applications:
        return (
            "pruefen",
            "Aktive Bewerbungsmöglichkeit nicht belegt"
        )

    if len(description.strip()) < 150:
        return (
            "pruefen",
            "Vollständige Stellenbeschreibung fehlt"
        )

    if application_format != "anschreiben":
        return (
            "pruefen",
            "Anschreiben nicht ausdrücklich vorgesehen "
            "oder Bewerbungsformat unklar"
        )

    valid_attendance = (
        "keine",
        "nur_einarbeitung",
        "gelegentlich",
        "woechentlich",
        "unklar",
    )

    if attendance not in valid_attendance:
        return (
            "pruefen",
            "Präsenzregelung nicht valide"
        )

    if attendance == "unklar":
        return (
            "pruefen",
            "Präsenzpflicht nicht geklärt"
        )

    if attendance == "woechentlich":
        band = location_band(location)

        if band == "fern":
            return (
                "gesperrt",
                "Wöchentliche Präsenz an eindeutig "
                "weit entferntem Standort"
            )

        if band == "unbekannt":
            return (
                "pruefen",
                "Entfernung ab konfiguriertem Ausgangsort ungeklärt"
            )

        return (
            "bereit",
            "Regionaler Standort. Tatsächliche "
            "Anreise vor Versand prüfen"
        )

    return (
        "bereit",
        "Präsenzrhythmus grundsätzlich geeignet"
    )


def applied_or_uncertain(
    company: str,
    title: str,
    url: str,
) -> str | None:

    with connect() as db:
        rows = db.execute("""
            SELECT
                unternehmen,
                stelle,
                status,
                stellen_url
            FROM applications
        """).fetchall()

    for row in rows:
        if normalized(row["unternehmen"]) != normalized(
            company
        ):
            continue

        same_url = urls_match(row["stellen_url"], url)

        similarity = SequenceMatcher(
            None,
            normalized(row["stelle"]),
            normalized(title)
        ).ratio()

        similar_title = similarity >= 0.84

        if same_url or (similar_title and not distinct_urls(row["stellen_url"], url)):
            if row["status"] in (
                "beworben", "absage"
            ):
                return "bereits_beworben"

            if row["status"] in (
                "entwurf", "unklar"
            ):
                return "status_unklar"

        if similar_title and distinct_urls(row["stellen_url"], url) and row["status"] != "nicht_beworben":
            return "status_unklar"

    return None
