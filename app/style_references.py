"""Lokale TXT-/Markdown-Stilvorlagen, unabhängig vom KI-SDK lesbar."""
import json
from pathlib import Path

from app.database import ROOT


STYLE_EXTENSIONS = {'.txt', '.md'}
EMPTY_REFERENCE_NOTICE = (
    'HINWEIS: Diese Stilreferenz ist leer. Verwende die Stilbeschreibung im '
    'Stilkompass und bestätigte Nutzerfakten. Erfinde keinen Referenzinhalt.'
)


def available_style_references(root: Path = ROOT) -> list[str]:
    directory = root / 'data' / 'input' / 'stilreferenzen'
    if not directory.is_dir():
        return []
    return sorted(
        path.name for path in directory.iterdir()
        if path.is_file() and not path.is_symlink()
        and path.suffix.lower() in STYLE_EXTENSIONS
    )


def read_style_references(dateinamen: list[str], root: Path = ROOT) -> str:
    """Lies höchstens drei Vorlagen innerhalb des Referenzordners."""
    if not 1 <= len(dateinamen) <= 3:
        return 'FEHLER: Bitte 1 bis 3 Beispiele auswählen'
    directory = root / 'data' / 'input' / 'stilreferenzen'
    result = {}
    for name in dateinamen:
        path = directory / name
        if (path.name != name or path.suffix.lower() not in STYLE_EXTENSIONS
                or path.is_symlink() or not path.is_file()):
            return f'FEHLER: Nicht erlaubter Dateiname: {name}'
        text = path.read_text(encoding='utf-8-sig')[:12000]
        result[name] = text if text.strip() else EMPTY_REFERENCE_NOTICE
    return json.dumps(result, ensure_ascii=False)
