
import csv
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state" / "bewerbungsagent.sqlite3"
CSV_PATH = ROOT / "data" / "input" / "bewerbungen.csv"

STATUSES = {
    "beworben", "absage", "nicht_beworben",
    "entwurf", "unklar"
}


def now():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def key(value):
    return " ".join(value.casefold().split())


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY,
                unternehmen TEXT NOT NULL,
                stelle TEXT NOT NULL DEFAULT '',
                company_key TEXT NOT NULL,
                role_key TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'beworben','absage','nicht_beworben',
                    'entwurf','unklar'
                )),
                bewerbungsdatum TEXT,
                stellen_url TEXT NOT NULL DEFAULT '',
                notiz TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(company_key, role_key)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                text_content TEXT NOT NULL DEFAULT '',
                page_count INTEGER NOT NULL DEFAULT 0,
                import_status TEXT NOT NULL DEFAULT 'ok',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                remote_model TEXT NOT NULL DEFAULT '',
                availability_status TEXT NOT NULL
                    DEFAULT 'ungeprueft',
                fit_score REAL,
                analysis_json TEXT,
                workflow_status TEXT NOT NULL
                    DEFAULT 'gefunden',
                discovered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                content TEXT NOT NULL,
                pdf_path TEXT,
                status TEXT NOT NULL DEFAULT 'pruefen',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                summary TEXT
            );
        """)


def import_applications():
    if not CSV_PATH.is_file():
        raise FileNotFoundError(
            f"CSV fehlt: {CSV_PATH}"
        )

    required = {
        "unternehmen", "stelle", "status",
        "bewerbungsdatum", "stellen_url", "notiz"
    }

    rows = []

    with CSV_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:

        reader = csv.DictReader(f)

        if not required.issubset(reader.fieldnames or []):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(
                f"CSV-Spalten fehlen: {sorted(missing)}"
            )

        for line, raw in enumerate(reader, 2):
            if None in raw:
                raise ValueError(
                    f"Zeile {line}: Zu viele CSV-Spalten. "
                    "Eventuell Kommas ohne Anführungszeichen."
                )

            r = {
                name: (raw.get(name) or "").strip()
                for name in required
            }

            if not r["unternehmen"]:
                raise ValueError(
                    f"Zeile {line}: Unternehmensname fehlt."
                )

            r["status"] = r["status"].lower()

            if r["status"] not in STATUSES:
                raise ValueError(
                    f"Zeile {line}: Unbekannter Status "
                    f"'{r['status']}'."
                )

            if r["bewerbungsdatum"]:
                try:
                    date.fromisoformat(r["bewerbungsdatum"])
                except ValueError as e:
                    raise ValueError(
                        f"Zeile {line}: Datum bitte YYYY-MM-DD."
                    ) from e

            rows.append(r)

    inserted = 0

    with connect() as db:
        for r in rows:
            result = db.execute("""
                INSERT OR IGNORE INTO applications (
                    unternehmen, stelle, company_key, role_key,
                    status, bewerbungsdatum, stellen_url, notiz,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["unternehmen"],
                r["stelle"],
                key(r["unternehmen"]),
                key(r["stelle"]),
                r["status"],
                r["bewerbungsdatum"] or None,
                r["stellen_url"],
                r["notiz"],
                now(),
                now()
            ))

            inserted += result.rowcount

    return len(rows), inserted


def mark_applied(application_id):
    with connect() as db:
        row = db.execute(
            "SELECT status FROM applications WHERE id = ?",
            (application_id,)
        ).fetchone()

        if row is None:
            raise ValueError(
                f"Unbekannte Bewerbungs-ID: {application_id}"
            )

        if row["status"] == "absage":
            raise ValueError(
                "Eine Absage darf nicht automatisch "
                "überschrieben werden."
            )

        db.execute("""
            UPDATE applications
            SET status = 'beworben',
                bewerbungsdatum =
                    COALESCE(bewerbungsdatum, ?),
                updated_at = ?
            WHERE id = ?
        """, (
            date.today().isoformat(),
            now(),
            application_id
        ))


def counts():
    with connect() as db:
        return {
            name: db.execute(
                f"SELECT COUNT(*) FROM {name}"
            ).fetchone()[0]
            for name in (
                "applications", "documents",
                "jobs", "drafts", "runs"
            )
        }
