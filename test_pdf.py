"""Manuelle PDF-Layoutprobe mit ausschließlich fiktiven Referenzdaten."""
import re

from app.database import ROOT


def parse_reference(text):
    """Extrahiere die Briefteile aus einer TXT- oder Markdown-Vorlage."""
    if not text.strip():
        raise ValueError('Die Stilreferenz ist leer. Bitte zuerst einen eigenen Beispielbrief eintragen.')
    lines = [
        re.sub(r"^\s*#{1,6}\s*", "", line)
        .replace("**", "").replace("__", "").strip()
        for line in text.splitlines()
    ]
    salutation_index = next(
        i for i, line in enumerate(lines)
        if re.match(r"^(Liebes|Liebe|Lieber|Sehr geehrte[rsn]?|Hallo|Guten Tag)\b",
                    line, re.IGNORECASE)
    )
    subject = next(
        (line.removeprefix("Betreff:").strip()
         for line in lines[:salutation_index] if "bewerbung" in line.lower()),
        None,
    )
    if not subject:
        raise ValueError("Keinen Bewerbungsbetreff erkannt.")
    closing_index = next(
        i for i in range(salutation_index + 1, len(lines))
        if re.match(r"^(Viele Grüße|Beste Grüße|Herzliche Grüße|Mit freundlichen Grüßen)",
                    lines[i], re.IGNORECASE)
    )
    return {
        "subject": subject,
        "salutation": lines[salutation_index],
        "paragraphs": re.sub(r"\n{3,}", "\n\n",
                             "\n".join(lines[salutation_index + 1:closing_index]).strip()),
        "closing": lines[closing_index],
    }


def main():
    sample = ROOT / "data" / "input" / "stilreferenzen" / "startup_sample.txt"
    text = sample.read_text(encoding="utf-8-sig")
    if not text.strip():
        print('PDF-Layoutprobe übersprungen: startup_sample.txt ist leer. '
              'Für die Layoutprobe zuerst einen eigenen Beispielbrief eintragen.')
        return
    letter = parse_reference(text)
    from app.pdf_generator import make_pdf
    applicant = {
        "name": "Alex Musterperson",
        "street": "Beispielweg 1",
        "zip_city": "00000 Beispielstadt",
        "city": "Beispielstadt",
        "email": "alex@example.invalid",
        "phone": "0000 000000",
    }
    pdf_path = make_pdf(
        job_id=9999,
        company="Fiktives_Beispielwerk_Layouttest",
        title="Layouttest",
        applicant=applicant,
        recipient="",
        **letter,
    )
    print(f"Fiktive PDF-Layoutprobe erstellt: {pdf_path}")
    print("Keine API-Aufrufe durchgeführt.")


if __name__ == "__main__":
    main()
