
from datetime import date
from difflib import SequenceMatcher

from app.database import connect, key, now
from app.urls import canonical_url, distinct_urls, urls_match


STATUSES = (
    "beworben",
    "absage",
    "nicht_beworben",
    "entwurf",
    "unklar",
)


def application_date(old_status, old_date, new_status):
    if old_date:
        return old_date

    if (
        new_status == "beworben"
        and old_status not in ("beworben", "absage")
    ):
        return date.today().isoformat()

    return None


def validate_transition(old_status, new_status):
    if new_status not in STATUSES:
        raise ValueError(
            f"Ungültiger Status: {new_status}"
        )

    if (
        old_status in ("beworben", "absage")
        and new_status in (
            "entwurf", "nicht_beworben", "unklar"
        )
    ):
        raise ValueError(
            "Eine bereits verschickte Bewerbung "
            "darf nicht versehentlich als "
            "unverschickt markiert werden."
        )

    if old_status == "absage" and new_status == "beworben":
        raise ValueError(
            "Eine bestehende Absage wird "
            "nicht automatisch überschrieben."
        )


def job_status(status):
    return {
        "beworben": "beworben",
        "absage": "absage",
        "nicht_beworben": "gefunden",
        "entwurf": "entwurf",
        "unklar": "pruefen",
    }[status]


def update_matching_jobs(db, company, role, url, status):
    jobs = db.execute("""
        SELECT id, company, title, url
        FROM jobs
    """).fetchall()

    for job in jobs:
        same_url = urls_match(url, job["url"])

        same_role = (
            key(company) == key(job["company"])
            and key(role) == key(job["title"])
        )

        if same_url or (same_role and not distinct_urls(url, job["url"])):
            db.execute("""
                UPDATE jobs
                SET workflow_status = ?
                WHERE id = ?
            """, (
                job_status(status),
                job["id"]
            ))


def set_application_status(application_id, status):
    with connect() as db:
        app = db.execute("""
            SELECT *
            FROM applications
            WHERE id = ?
        """, (application_id,)).fetchone()

        if app is None:
            raise ValueError(
                f"Bewerbungs-ID {application_id} "
                "existiert nicht."
            )

        validate_transition(app["status"], status)

        applied_date = application_date(
            app["status"],
            app["bewerbungsdatum"],
            status
        )

        db.execute("""
            UPDATE applications
            SET status = ?,
                bewerbungsdatum = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            status,
            applied_date,
            now(),
            application_id
        ))

        update_matching_jobs(
            db,
            app["unternehmen"],
            app["stelle"],
            app["stellen_url"],
            status
        )

    return (
        f"Bewerbung {application_id}: "
        f"Status = {status}"
    )


def mark_job(job_id, status):
    if status not in STATUSES:
        raise ValueError(
            f"Ungültiger Status: {status}"
        )

    with connect() as db:
        job = db.execute("""
            SELECT id, company, title, url
            FROM jobs
            WHERE id = ?
        """, (job_id,)).fetchone()

        if job is None:
            raise ValueError(
                f"Job-ID {job_id} existiert nicht."
            )

        applications = db.execute("""
            SELECT *
            FROM applications
        """).fetchall()

        matching = []
        similar = []

        for app in applications:
            same_url = urls_match(app["stellen_url"], job["url"])

            same_company = (
                key(app["unternehmen"])
                == key(job["company"])
            )

            same_role = (
                same_company
                and key(app["stelle"])
                == key(job["title"])
            )

            if same_url or (same_role and not distinct_urls(app["stellen_url"], job["url"])):
                matching.append(app)

            elif same_company:
                similarity = SequenceMatcher(
                    None,
                    key(app["stelle"]),
                    key(job["title"])
                ).ratio()

                if similarity >= 0.84:
                    similar.append(app)

        if len(matching) > 1:
            raise ValueError(
                "Mehrere Bewerbungen passen zu "
                "dieser Stelle. Bitte manuell prüfen."
            )

        if not matching and similar:
            ids = ", ".join(
                str(app["id"])
                for app in similar
            )

            raise ValueError(
                f"Mögliche Doppelbewerbung: {ids}. "
                "Bitte zunächst prüfen."
            )

        if matching:
            app = matching[0]

            validate_transition(
                app["status"],
                status
            )

            applied_date = application_date(
                app["status"],
                app["bewerbungsdatum"],
                status
            )

            db.execute("""
                UPDATE applications
                SET status = ?,
                    bewerbungsdatum = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                status,
                applied_date,
                now(),
                app["id"]
            ))

            application_id = app["id"]

        else:
            applied_date = application_date(
                None, None, status
            )

            cursor = db.execute("""
                INSERT INTO applications (
                    unternehmen,
                    stelle,
                    company_key,
                    role_key,
                    status,
                    bewerbungsdatum,
                    stellen_url,
                    notiz,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job["company"],
                job["title"],
                key(job["company"]),
                key(job["title"]),
                status,
                applied_date,
                job["url"],
                "Über Bewerbungsagent erfasst",
                now(),
                now()
            ))

            application_id = cursor.lastrowid

        db.execute("""
            UPDATE jobs
            SET workflow_status = ?
            WHERE id = ?
        """, (
            job_status(status),
            job_id
        ))

    return (
        f"Job {job_id}: {status}. "
        f"Bewerbungs-ID: {application_id}"
    )
