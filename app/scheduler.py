"""Optionale Zeitsteuerung für macOS, ohne zusätzliche Python-Pakete."""
import os
import plistlib
import sys
from pathlib import Path

from app.database import ROOT

LABEL = 'de.bewerbungsagent.local'
PLIST = Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'


def install_mac_schedule():
    if sys.platform != 'darwin':
        raise RuntimeError('macOS-Zeitsteuerung kann nur auf einem Mac eingerichtet werden.')
    logs = ROOT / 'output' / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    program = str(ROOT / '.venv' / 'bin' / 'python')
    if not Path(program).exists():
        raise FileNotFoundError(f'Python-Umgebung fehlt: {program}')
    cfg = {
        'Label': LABEL,
        'ProgramArguments': [program, '-u', str(ROOT / 'main.py'), 'run'],
        'WorkingDirectory': str(ROOT),
        'StartCalendarInterval': [
            {'Hour': 8, 'Minute': 0},
            {'Hour': 18, 'Minute': 0},
        ],
        'StandardOutPath': str(logs / 'agent_stdout.log'),
        'StandardErrorPath': str(logs / 'agent_stderr.log'),
        'RunAtLoad': False,
    }
    PLIST.write_bytes(plistlib.dumps(cfg))
    print(f'Zeitplan angelegt: {PLIST}')
    print('Zum AKTIVIEREN im macOS-Terminal:')
    print(f'launchctl bootstrap gui/$(id -u) "{PLIST}"')
    print('Zum DEAKTIVIEREN:')
    print(f'launchctl bootout gui/$(id -u) "{PLIST}"')
    print('Nur bei angemeldetem Mac und laufendem System zuverlässig ausführbar.')
