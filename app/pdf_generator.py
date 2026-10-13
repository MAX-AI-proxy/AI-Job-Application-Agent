
import re
import unicodedata
import uuid
from datetime import date
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.database import ROOT


PAGE_W, PAGE_H = A4

LEFT = 57.0
RIGHT = 57.0
TEXT_WIDTH = PAGE_W - LEFT - RIGHT

INK = colors.HexColor("#202020")


# --------------------------------------------------
# SCHRIFTARTEN
# --------------------------------------------------

def _register_fonts():
    """Originalschrift bevorzugen, sonst Arial."""

    font_pairs = [
        (
            "/Library/Fonts/DejaVuSans.ttf",
            "/Library/Fonts/DejaVuSans-Bold.ttf",
        ),
        (
            str(Path.home() / "Library/Fonts/DejaVuSans.ttf"),
            str(Path.home() / "Library/Fonts/DejaVuSans-Bold.ttf"),
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "C:/Windows/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        ),
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ),
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ),
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ),
    ]

    for regular_path, bold_path in font_pairs:
        if (
            Path(regular_path).is_file()
            and Path(bold_path).is_file()
        ):
            registered = pdfmetrics.getRegisteredFontNames()

            if "CoverRegular" not in registered:
                pdfmetrics.registerFont(
                    TTFont("CoverRegular", regular_path)
                )

            if "CoverBold" not in registered:
                pdfmetrics.registerFont(
                    TTFont("CoverBold", bold_path)
                )

            return "CoverRegular", "CoverBold"

    raise RuntimeError(
        "Keine geeignete Schrift gefunden. "
        "Bitte Arial oder DejaVu Sans installieren."
    )


# --------------------------------------------------
# TEXTVERARBEITUNG
# --------------------------------------------------

def _split_paragraphs(text):
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    paragraphs = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n\s*\n", text)
    ]

    return [p for p in paragraphs if p]


def _wrap(text, font, size, max_width=TEXT_WIDTH):
    """Text anhand der tatsächlichen Schriftbreite umbrechen."""

    result = []

    for original_line in str(text).splitlines() or [""]:
        words = original_line.split()

        if not words:
            result.append("")
            continue

        line = ""

        for word in words:
            candidate = f"{line} {word}" if line else word

            if (
                pdfmetrics.stringWidth(
                    candidate, font, size
                ) <= max_width
            ):
                line = candidate
                continue

            if line:
                result.append(line)
                line = ""

            if (
                pdfmetrics.stringWidth(
                    word, font, size
                ) <= max_width
            ):
                line = word
                continue

            # Sehr lange Wörter notfalls aufteilen.

            part = ""

            for char in word:
                width = pdfmetrics.stringWidth(
                    part + char, font, size
                )

                if part and width > max_width:
                    result.append(part)
                    part = char
                else:
                    part += char

            line = part

        if line:
            result.append(line)

    return result


def _draw_top(pdf, text, top, font, size, x=LEFT):
    """Text an einer Position gemessen ab Seitenoberkante."""

    pdf.setFont(font, size)
    pdf.setFillColor(INK)

    ascent, _ = pdfmetrics.getAscentDescent(
        font, size
    )

    pdf.drawString(
        x,
        PAGE_H - top - ascent,
        text
    )


def _filename(value):
    value = unicodedata.normalize(
        "NFKD", str(value)
    )

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(
        r"[^A-Za-z0-9._-]+", "_", value
    ).strip("._")

    return value[:75] or "Anschreiben"


# --------------------------------------------------
# PDF-LAYOUT
# --------------------------------------------------

def _render_candidate(
    target,
    applicant,
    subject,
    salutation,
    parts,
    closing,
    recipient,
    font,
    bold,
    body_size,
):
    """Einseitiges PDF mit Briefkopf und optionaler Empfängeranschrift erzeugen."""

    scale = body_size / 8.9

    lead = 12.8 * scale
    paragraph_gap = 11.0 * scale

    # Briefkopf wie im Original.

    header = [
        (
            applicant["name"],
            49.0,
            bold,
            12.5,
        ),
        (
            f'{applicant["street"]} · '
            f'{applicant["zip_city"]}',
            67.0,
            font,
            8.4,
        ),
        (
            f'{applicant["email"]} · '
            f'{applicant["phone"]}',
            78.2,
            font,
            8.4,
        ),
    ]

    # Optionale belegte Empfängeranschrift.

    recipient_lines = []

    if recipient.strip():
        for line in recipient.strip().splitlines():
            recipient_lines.extend(
                _wrap(line.strip(), font, 8.4)
            )

    extra = (
        len(recipient_lines) * 11.2
        + (11.0 if recipient_lines else 0.0)
    )

    date_top = 109.4 + extra
    subject_top = 138.8 + extra

    subject_lines = _wrap(
        subject.strip(), bold, 9.1
    )

    subject_extra = (
        max(len(subject_lines) - 1, 0) * 12.2
    )

    salutation_top = (
        167.7 + extra + subject_extra
    )

    body_top = salutation_top + 22.8

    # Zeilen des Anschreibens berechnen.

    draw_list = []
    top = body_top

    for paragraph in parts:
        lines = _wrap(
            paragraph, font, body_size
        )

        for line in lines:
            draw_list.append(
                (line, top, font, body_size)
            )

            top += lead

        top += paragraph_gap

    closing_top = top
    name_top = (
        closing_top + lead
    )

    last_bottom = name_top + body_size

    # Unteren Seitenrand schützen.

    if last_bottom > PAGE_H - 56.0:
        return False

    # PDF erzeugen.

    pdf = canvas.Canvas(
        str(target),
        pagesize=A4,
        pageCompression=1
    )

    pdf.setTitle(subject)
    pdf.setAuthor(applicant["name"])

    for text, y, face, size in header:
        _draw_top(
            pdf, text, y, face, size
        )

    # Empfängeranschrift, falls vorhanden.

    for i, line in enumerate(recipient_lines):
        _draw_top(
            pdf,
            line,
            98.8 + i * 11.2,
            font,
            8.4,
        )

    # Datum linksbündig.

    current_date = date.today().strftime(
        "%d.%m.%Y"
    )

    _draw_top(
        pdf,
        f'{applicant["city"]}, {current_date}',
        date_top,
        font,
        8.4,
    )

    # Fettgedruckter Betreff.

    for i, line in enumerate(subject_lines):
        _draw_top(
            pdf,
            line,
            subject_top + i * 12.2,
            bold,
            9.1,
        )

    # Anrede.

    _draw_top(
        pdf,
        salutation.strip(),
        salutation_top,
        font,
        body_size,
    )

    # Anschreibentext.

    for line, y, face, size in draw_list:
        _draw_top(
            pdf, line, y, face, size
        )

    # Grußformel und Unterschrift.

    _draw_top(
        pdf,
        closing.strip(),
        closing_top,
        font,
        body_size,
    )

    _draw_top(
        pdf,
        applicant["name"],
        name_top,
        font,
        body_size,
    )

    pdf.showPage()
    pdf.save()

    return True


# --------------------------------------------------
# HAUPTFUNKTION FÜR DEN KI-AGENTEN
# --------------------------------------------------

def make_pdf(
    job_id,
    company,
    title,
    applicant,
    subject,
    salutation,
    paragraphs,
    closing,
    recipient,
):
    """Erstellt ein einseitiges Anschreiben als PDF."""

    required_fields = (
        "name",
        "street",
        "zip_city",
        "city",
        "email",
        "phone",
    )

    missing = [
        field
        for field in required_fields
        if not str(
            applicant.get(field, "")
        ).strip()
    ]

    if missing:
        raise ValueError(
            "Absenderdaten fehlen: "
            + ", ".join(missing)
        )

    if not all(
        str(value).strip()
        for value in (
            subject,
            salutation,
            paragraphs,
            closing,
        )
    ):
        raise ValueError(
            "Betreff, Anrede, Text und "
            "Grußformel müssen ausgefüllt sein."
        )

    parts = _split_paragraphs(paragraphs)

    if not parts:
        raise ValueError(
            "Kein Bewerbungstext vorhanden."
        )

    regular_font, bold_font = _register_fonts()

    output_dir = (
        ROOT / "output" / "anschreiben"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    target = output_dir / (
        f"{int(job_id):04d}_"
        f"{_filename(company)}.pdf"
    )

    # Temporäre Datei verhindert beschädigte Enddateien.

    temp = output_dir / (
        f".{target.stem}."
        f"{uuid.uuid4().hex}.tmp.pdf"
    )

    try:
        for size in (8.9, 8.7, 8.5):

            fits = _render_candidate(
                temp,
                applicant,
                subject,
                salutation,
                parts,
                closing,
                recipient,
                regular_font,
                bold_font,
                size,
            )

            if not fits:
                continue

            pdf = PdfReader(str(temp))

            if len(pdf.pages) != 1:
                raise RuntimeError(
                    "Unerwartete Seitenanzahl."
                )

            extracted = (
                pdf.pages[0].extract_text() or ""
            )

            def compact(text):
                return re.sub(
                    r"\s+", " ", text
                ).strip()

            # Prüfen, dass kein Text verloren ging.

            if not all(
                compact(part) in compact(extracted)
                for part in parts
            ):
                raise RuntimeError(
                    "PDF enthält nicht den "
                    "vollständigen Bewerbungstext."
                )

            temp.replace(target)

            print(
                f"PDF erzeugt: {target.name} "
                f"(Textgröße: {size} pt)"
            )

            return target.relative_to(
                ROOT
            ).as_posix()

        raise ValueError(
            "Anschreiben passt nicht gut lesbar "
            "auf eine DIN-A4-Seite. "
            "Bitte den Text kürzen."
        )

    finally:
        temp.unlink(missing_ok=True)
