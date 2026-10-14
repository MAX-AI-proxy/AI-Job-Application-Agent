# A fictional application workflow, end to end

**Start here: [open the generated cover letter](cover_letter.pdf).**
All people, employers, listings and applicant facts below are invented.
No OpenAI, search, geocoding or routing request was made.

## The scenario in 60 seconds

Robin Muster is a fictional business-informatics student with Python and SQL
experience from synthetic-data projects, looking for a 16-hour working-student
role in AI and process automation. Weekly commuting is limited to 60 km.

| Listing | Prepared fit score | Actual Python rule decision | What happens |
|---|---:|---|---|
| **A - AI & Business Operations** | 9.1/10 | **Ready** (`bereit`) | Remote with occasional team meetings. Stored, selected, and given a PDF draft. |
| **B - Digital Operations** | 7.4/10 | **Review** (`pruefen`) | Weekly attendance at one of two unspecified offices. Distance cannot be established safely. Stored for clarification. |
| **C - Process Automation** | 6.8/10 | **Blocked** (`gesperrt`) | Weekly attendance with a **prepared** 180 km distance exceeds the 60 km limit. Not saved; no draft. |

These are **prepared scores**, not measurements from a live model. The decisions
are calculated by the unchanged application rules. A favorable score cannot bypass
the attendance checks.

## What actually runs

1. A temporary workspace receives the fictional profile, an empty history CSV,
   local settings and CV facts. The real import functions load **six documents**
   and **zero previous applications**.
2. The existing job-save tool bodies process all three prepared listings. Python
   checks the profile's exclusion section, previous applications, format, evidence
   fields and attendance. A and B enter SQLite; C is rejected.
3. SQLite selects the highest-scoring ready job. Listing A is the only eligible
   candidate, while B remains pending clarification.
4. The reference-reading tool reads the empty technical-style placeholder. It
   returns the existing style-guide fallback. The technical tone of the prepared
   letter is chosen for this fixture; no model performs that selection.
5. The original PDF tool receives the prepared fictional letter, rechecks the job,
   and calls `app.pdf_generator.make_pdf`. It renders one A4 page and checks its text.
6. The normal draft-status function changes A from `bereit` to `entwurf`, creates
   one application record, and leaves the draft marked `pruefen` for human review.
   A second draft request is rejected by the existing guard.
7. The existing CLI formatters display the resulting records. The temporary
   SQLite database and all runtime inputs are removed; nothing is submitted.

**Result:** two stored jobs, one application draft, one generated PDF.
The final application status is **draft**, not **sent**.

## Prepared responses versus executed code

| Prepared/simulated inputs | Executed application code |
|---|---|
| Search results and fictional listing content | CV/CSV/document imports and SHA-256 change tracking |
| Scores, fit explanations and source-evidence text | Exclusion, duplicate, format and attendance checks |
| Cover-letter prose | Original job-save and PDF tool function bodies |
| 180 km route-cache value | Actual cache lookup and configured threshold comparison |
| Technical style choice for this fixture | Reference reading and empty-file fallback |
| Fixed sample date | SQLite selection, PDF rendering, status updates and CLI formatters |

The fixture's “original application open” flags are invented. No real website was
checked. A/B/C do not describe actual employers or job opportunities.

The script loads the original tool bodies directly from `app/agent.py` and bypasses
only SDK decorators/imports, so no `.env` is loaded and no agent Runner is invoked.
It redirects data paths to a temporary workspace and fixes the PDF clock and
serialization for reproducible artifacts. It does **not** replace business-rule
results or change productive modules. Unexpected network attempts fail explicitly.

## Inspect the evidence

- [Generated PDF](cover_letter.pdf) - produced by the existing generator; fictional metadata.
- [Letter text](cover_letter.txt) - the text saved by the existing PDF tool.
- [Terminal transcript](terminal.txt) - captured execution output, including real CLI formatters.
- [Structured results](results.json) - decisions, persisted counts and final statuses.
- [Scenario and prepared responses](scenario.json) - all fictional inputs.
- [Reproduction script](../../scripts/run_showcase.py) - isolated execution of the existing code.

## Reproduce without credentials

After installing the repository's PDF dependencies and a supported font pair:

```bash
python -B scripts/run_showcase.py
```

This regenerates the four result artifacts here. No API key or personal runtime
configuration is needed. All runtime data lives in an automatically deleted
`.portfolio-test-showcase-*` directory. The script never reads a real CV or database.
Only the general, public style-guide files and the fictional scenario are inputs.

To write results elsewhere: `python -B scripts/run_showcase.py --output-dir PATH`.
Review the regenerated files before committing them. Keep personal letters and
databases outside this showcase. Real AI research/drafting still needs your own
OpenAI API key and remains available through the existing CLI.

[Back to the project overview](../../README.md)
