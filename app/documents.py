
import hashlib

from app.database import ROOT, connect, now
from app.style_references import STYLE_EXTENSIONS


DOCUMENT_SOURCES = [
    (
        ROOT / "config" / "00_START_HIER.md",
        "instructions"
    ),
    (
        ROOT / "config" / "00_STILKOMPASS_ANSCHREIBEN.md",
        "style_guide"
    ),
]


def source_files():
    files = list(DOCUMENT_SOURCES)

    folders = [
        (
            "lebenslauf",
            {
                ".txt": "cv_facts",
                ".pdf": "cv_pdf_layout"
            }
        ),
        (
            "stilreferenzen",
            {extension: "style_example" for extension in STYLE_EXTENSIONS}
        ),
        (
            "stilreferenzen_pdf",
            {".pdf": "style_pdf_layout"}
        ),
    ]

    for folder, extensions in folders:
        directory = ROOT / "data" / "input" / folder

        # Die öffentlichen Beispiele benötigen keine zusätzlichen Layout-PDFs.
        if folder == "stilreferenzen_pdf" and not directory.exists():
            continue

        for path in sorted(directory.iterdir()):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in extensions
            ):
                files.append((
                    path,
                    extensions[path.suffix.lower()]
                ))

    return files


def import_documents():
    new_or_changed = 0
    unchanged = 0

    with connect() as db:
        sources = source_files()
        # Gelöschte Stilvorlagen dürfen nicht als private Kopien weiterbestehen.
        current_styles = {
            path.relative_to(ROOT).as_posix()
            for path, kind in sources
            if kind in ("style_example", "style_pdf_layout")
        }
        for row in db.execute("""
            SELECT id, relative_path FROM documents
            WHERE kind IN ('style_example', 'style_pdf_layout')
        """).fetchall():
            if row["relative_path"] not in current_styles:
                db.execute("DELETE FROM documents WHERE id = ?", (row["id"],))

        for path, kind in sources:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Benötigte Datei fehlt: {path}"
                )

            content = path.read_bytes()

            digest = hashlib.sha256(
                content
            ).hexdigest()

            relative = path.relative_to(
                ROOT
            ).as_posix()

            previous = db.execute("""
                SELECT sha256 FROM documents
                WHERE relative_path = ?
            """, (relative,)).fetchone()

            if (
                previous
                and previous["sha256"] == digest
            ):
                unchanged += 1
                continue

            text = ""
            pages = 0

            if path.suffix.lower() == ".pdf":
                from pypdf import PdfReader

                # PDFs sind Layoutreferenzen.
                # Als Text-/Faktenquelle dienen TXT und MD.
                pages = len(
                    PdfReader(str(path)).pages
                )
            else:
                text = content.decode("utf-8-sig")

            db.execute("""
                INSERT INTO documents (
                    relative_path,
                    kind,
                    sha256,
                    text_content,
                    page_count,
                    import_status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'ok', ?)

                ON CONFLICT(relative_path) DO UPDATE SET
                    kind = excluded.kind,
                    sha256 = excluded.sha256,
                    text_content = excluded.text_content,
                    page_count = excluded.page_count,
                    import_status = excluded.import_status,
                    updated_at = excluded.updated_at
            """, (
                relative,
                kind,
                digest,
                text,
                pages,
                now()
            ))

            new_or_changed += 1

    return new_or_changed, unchanged
