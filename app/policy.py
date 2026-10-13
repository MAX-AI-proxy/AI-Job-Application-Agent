"""Sicherheitsregeln und Entfernungskontrolle des Bewerbungsagenten."""
import json
import re
import time
from difflib import SequenceMatcher
from math import isfinite
from app.database import ROOT, connect, key
from app.configuration import load_distance_settings
from app.rules import is_excluded
from app.urls import canonical_url, distinct_urls, urls_match

CACHE_FILE = ROOT / 'data' / 'state' / 'routen_cache.json'


def duplicate_application(company, title, url):
    with connect() as db:
        apps = db.execute('SELECT unternehmen, stelle, status, stellen_url FROM applications').fetchall()
    for row in apps:
        same_url = urls_match(row['stellen_url'], url)
        same_company = key(row['unternehmen']) == key(company)
        same_title = key(row['stelle']) == key(title)
        ratio = SequenceMatcher(None, key(row['stelle']), key(title)).ratio() if same_company else 0
        if same_url or (same_company and same_title and not distinct_urls(row['stellen_url'], url)):
            if row['status'] in ('beworben', 'absage'):
                return 'gesperrt', f"Schon beworben ({row['status']})"
            if row['status'] in ('entwurf', 'unklar'):
                return 'pruefen', f"Vorhandener Status: {row['status']}"
        if same_company and ratio >= 0.78 and row['status'] != 'nicht_beworben':
            return 'pruefen', 'Mögliche Doppelbewerbung bei gleichem Unternehmen'
    return 'bereit', ''


def _location_query(location):
    loc = location.strip()
    # Mehrere Standorte oder unklare Freitexte nicht durch Raten ersetzen.
    if not loc or '/' in loc or ' oder ' in loc.lower() or ',' in loc:
        return None
    if re.search(r'\b(remote|homeoffice|deutschlandweit|bundesweit)\b', loc, re.I):
        return None
    return loc


def distance_km(location, settings=None):
    """Straßenentfernung (OSM/OSRM), bei Unklarheit None. Kein Georaten."""
    place = _location_query(location)
    if not place:
        return None
    if settings is None:
        try:
            settings = load_distance_settings(ROOT)
        except ValueError:
            return None
    if place.casefold() == settings.origin_city.casefold():
        return 0.0
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = json.loads(CACHE_FILE.read_text(encoding='utf-8')) if CACHE_FILE.exists() else {}
    except (ValueError, OSError):
        cache = {}
    # Alte Zielort-Schlüssel werden nicht für einen anderen Ausgangspunkt genutzt.
    cache_key = 'v2:' + json.dumps([
        settings.origin_longitude, settings.origin_latitude,
        settings.origin_city.casefold(), place.casefold(),
    ], ensure_ascii=False, separators=(',', ':'))
    if cache_key in cache:
        value = cache[cache_key]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value >= 0:
            return value
    import httpx
    headers = {'User-Agent': 'BewerbungsagentLocal/1.0 (private personal project)'}
    try:
        with httpx.Client(timeout=12, headers=headers, follow_redirects=True) as client:
            geo = client.get('https://nominatim.openstreetmap.org/search', params={
                'q': f'{place}, Deutschland', 'countrycodes': 'de', 'format': 'json', 'limit': 1
            })
            geo.raise_for_status()
            results = geo.json()
            if not results:
                return None
            lon, lat = float(results[0]['lon']), float(results[0]['lat'])
            # Public-Dienste nur für geringe manuelle Nutzung, keine Massenabfragen.
            time.sleep(1.1)
            route = client.get(
                f'https://router.project-osrm.org/route/v1/driving/{settings.origin_longitude},{settings.origin_latitude};{lon},{lat}',
                params={'overview': 'false'}
            )
            route.raise_for_status()
            routes = route.json().get('routes') or []
            if not routes:
                return None
            km = round(float(routes[0]['distance']) / 1000, 1)
            cache[cache_key] = km
            CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
            return km
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def assess(company, title, url, location, attendance, fmt, original_open, description):
    """Status und Begründung. Kein ungeprüfter Treffer erzeugt Entwürfe."""
    if is_excluded(company):
        return 'gesperrt', 'Unternehmen ausgeschlossen'
    dup_status, dup_reason = duplicate_application(company, title, url)
    if dup_status != 'bereit':
        return dup_status, dup_reason
    if not canonical_url(url):
        return 'pruefen', 'Ungültige Stellen-URL'
    if not original_open or len(description.strip()) < 150:
        return 'pruefen', 'Originalanzeige/Bewerbungsoption nicht ausreichend bestätigt'
    if fmt not in ('anschreiben', 'kurze_email', 'nur_cv'):
        return 'pruefen', 'Bewerbungsformat noch nicht bestätigt'
    if attendance not in ('keine', 'nur_einarbeitung', 'gelegentlich', 'woechentlich'):
        return 'pruefen', 'Präsenzrhythmus ungeklärt'
    if attendance == 'woechentlich':
        try:
            settings = load_distance_settings(ROOT)
        except ValueError as exc:
            return 'pruefen', f'Entfernungseinstellungen fehlen oder sind ungültig: {exc}'
        km = distance_km(location, settings)
        if km is None:
            return 'pruefen', 'Straßenentfernung ab konfiguriertem Ausgangsort nicht verlässlich bestimmbar'
        if km > settings.max_weekly_distance_km:
            return 'gesperrt', f'Wöchentliche Präsenz: {km} km Straßenentfernung'
        return 'bereit', f'Wöchentliche Präsenz: {km} km Straßenentfernung'
    return 'bereit', 'Arbeitsmodell grundsätzlich vereinbar'


def assess_saved_job(row):
    info = json.loads(row['analysis_json'] or '{}')
    return assess(row['company'], row['title'], row['url'], row['location'],
                  info.get('praesenzrhythmus', 'unklar'),
                  info.get('bewerbungsformat', 'unbekannt'),
                  bool(info.get('originalseite_bewerbung')), row['description'])
