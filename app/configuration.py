"""Validierte lokale Entfernungseinstellungen, ohne Netzwerkzugriff."""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.database import ROOT


@dataclass(frozen=True)
class DistanceSettings:
    origin_city: str
    origin_longitude: float
    origin_latitude: float
    max_weekly_distance_km: float
    near_cities: tuple[str, ...] = ()
    far_cities: tuple[str, ...] = ()


def load_distance_settings(root: Path = ROOT) -> DistanceSettings:
    path = root / 'config' / 'entfernung.json'
    try:
        values = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('config/entfernung.json fehlt oder enthält ungültiges JSON.') from exc
    if not isinstance(values, dict):
        raise ValueError('config/entfernung.json muss ein JSON-Objekt enthalten.')
    city = values.get('origin_city')
    if not isinstance(city, str) or not city.strip():
        raise ValueError('origin_city muss ausgefüllt sein.')

    def number(name, minimum, maximum=None):
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name} muss eine Zahl sein.')
        if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f'{name} liegt außerhalb des erlaubten Bereichs.')
        return float(value)

    def cities(name):
        items = values.get(name, [])
        if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
            raise ValueError(f'{name} muss eine Liste nichtleerer Ortsnamen sein.')
        return tuple(item.strip() for item in items)

    return DistanceSettings(
        origin_city=city.strip(),
        origin_longitude=number('origin_longitude', -180, 180),
        origin_latitude=number('origin_latitude', -90, 90),
        max_weekly_distance_km=number('max_weekly_distance_km', 0),
        near_cities=cities('near_cities'),
        far_cities=cities('far_cities'),
    )


def distance_policy_text(root: Path = ROOT) -> str:
    try:
        settings = load_distance_settings(root)
    except ValueError:
        return ('Entfernungseinstellungen fehlen oder sind ungültig. '
                'Wöchentliche Präsenz erfordert manuelle Klärung.')
    return (f'Ausgangspunkt: {settings.origin_city}. Bei wöchentlicher Präsenz sind '
            f'maximal {settings.max_weekly_distance_km:g} km Straßenentfernung erlaubt. '
            'Maßgeblich ist config/entfernung.json, nicht ein abweichender Freitext.')
