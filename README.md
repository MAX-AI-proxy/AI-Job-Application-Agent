# AI Application Assistant

This project was originally developed to automate parts of my own job application process. The public version retains the core functionality while excluding my personal application history, documents, credentials, and individual preferences.

A Python AI agent that automates job research, suitability checks, and the preparation
of individual application drafts. It combines LLM-driven research and writing with
explicit Python rules, local application tracking, and PDF generation.

Built as a portfolio project, it demonstrates a practical workflow from an original
job listing to a reviewable application draft. The current prompts target
German-language working-student applications in Germany. Every application remains
under human control: the assistant neither submits applications nor sends emails.

## Key features

- **Research:** investigate original job listings using the OpenAI Agents SDK and
  hosted web search; save up to five new opportunities per search run.
- **Evaluate:** record a 0–10 fit score, source evidence, requirements, uncertainties,
  attendance frequency, and the requested application format.
- **Filter:** check employer exclusions, previous applications, possible duplicates,
  and a configurable road-distance limit for weekly attendance.
- **Write:** prepare individual single-page A4 cover-letter PDFs or short email
  drafts using CV facts, confirmed project information, and optional style references.
- **Track:** import application history, manage statuses in SQLite, and inspect jobs,
  drafts, run summaries, token usage, and approximate model costs from the terminal.
- **Automate:** prevent concurrent agent runs and optionally schedule two daily runs
  through macOS LaunchAgent. Scheduled runs can incur API charges.

## Architecture and tech stack

One agent definition supports two modes: **search** and **draft**. Its Python tools
control database access, eligibility checks, reference reading, and document output.

```text
Configuration + CV facts + application history
                      ↓
CLI → Search / draft agent → Hosted web search + Python tools
                      ↓
Eligibility rules + duplicate checks + distance policy
                      ↓
SQLite records → PDF / email draft → Human review
```

| Area | Implementation |
|---|---|
| CLI and workflow | Python, `argparse`, OpenAI Agents SDK |
| Persistence | SQLite, CSV import, SHA-256 document change detection |
| Configuration | JSON, Markdown, environment variables, `python-dotenv` |
| Documents | ReportLab for PDFs; pypdf for page and text checks |
| Distance checks | HTTPX, Nominatim geocoding, OSRM road routing |
| Local tests | `unittest`, isolated SQLite fixtures, mocked external clients |

The main modules are `agent.py` (agent modes and tools), `policy.py` / `rules.py`
(filters), `configuration.py` (distance settings), `urls.py` (shared URL identity),
`database.py` / `application_manager.py` (persistence and statuses), `documents.py` /
`style_references.py` (inputs), `pdf_generator.py` / `operations.py` (outputs and
usage), and `scheduler.py` (macOS scheduling). `main.py` provides the CLI.

The model supplies scores and listing evidence; Python checks decide whether a job
is ready (`bereit`), needs review (`pruefen`), or is blocked (`gesperrt`). Blocked
results are not saved through the job tool. Weekly attendance uses road distance;
uncertain conditions require review. Scores and evidence are not independently
verified by a separate crawler and do not guarantee suitability or availability.

Draft mode rechecks the listing and uses the requested format: `anschreiben` for a
PDF, `kurze_email` for a text draft, and no extra document for `nur_cv` or an unknown
format. Output tools check eligibility and existing drafts. PDFs validate sender
fields, fit the text on one page, and check paragraph text; email drafts have
length and basic placeholder checks.

SQLite stores applications, imported documents, jobs, PDF/email drafts, runs, and
usage records. TXT/Markdown inputs retain their text and digest. Input PDFs are
registered with page counts, not used as CV facts. Removed style files are pruned
on re-import; the latest imported TXT CV supplies the agent's factual profile.

## Installation

Use Python 3.12 and a virtual environment. The source uses Python 3.10+ features;
compatibility with every interpreter and dependency version is not claimed.
From the repository root on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, use `python -m venv .venv` and activate `.venv\Scripts\Activate.ps1`
in PowerShell. Dependency installation requires internet access; versions are not
pinned. PDF generation requires a supported installed font pair: DejaVu Sans,
Arial, or Liberation Sans in one of the paths checked by the generator.
`beautifulsoup4` is listed in the existing requirements but is currently unused.

## Configuration

Copy the neutral templates to their local destinations. These macOS/Linux commands
preserve existing files; on Windows, create and copy the same paths manually.

```bash
mkdir -p config data/input/lebenslauf data/input/stilreferenzen
cp -n examples/config/absender.json config/absender.json
cp -n examples/config/suchprofil.md config/suchprofil.md
cp -n examples/config/projektstand.md config/projektstand.md
cp -n examples/config/bewerbungsregeln.md config/bewerbungsregeln.md
cp -n examples/config/entfernung.json config/entfernung.json
cp -n examples/data/bewerbungen.csv data/input/bewerbungen.csv
cp -n examples/data/lebenslauf.txt data/input/lebenslauf/lebenslauf.txt
cp -n .env.example .env
```

**Complete the copied templates before live research or drafting.** They contain
no confirmed qualifications, real application history, exclusions, or coordinates.

| Local input | Required content |
|---|---|
| `config/absender.json` | `name`, `street`, `zip_city`, `city`, `email`, `phone` |
| `config/suchprofil.md` | Desired tasks, hours, availability, and work model |
| `config/projektstand.md` | Confirmed facts about your own projects |
| `config/bewerbungsregeln.md` | Writing rules and confirmed availability constraints |
| `config/entfernung.json` | Origin city, coordinates, and maximum weekly road distance |
| `data/input/lebenslauf/*.txt` | Your actual CV facts; replace the template instructions |
| `data/input/bewerbungen.csv` | Your history, or just the supplied header |

Keep `## Ausgeschlossene Unternehmen` in the search profile even when empty.
Private exclusions use one bullet per employer; `|` separates aliases.
The CSV header is `unternehmen,stelle,status,bewerbungsdatum,stellen_url,notiz`.
Statuses are `beworben`, `absage`, `nicht_beworben`, `entwurf`, and `unklar`.
Dates use `YYYY-MM-DD`; quote fields containing commas. A header-only CSV is valid.

In `entfernung.json`, set `origin_city`, `origin_longitude` (−180 to 180),
`origin_latitude` (−90 to 90), and a nonnegative `max_weekly_distance_km`.
Missing or invalid settings require review for weekly attendance. Distances above
that limit are blocked; equality is accepted. Cache keys include the origin and
destination, so changing the origin does not reuse previous distances. Optional
`near_cities` / `far_cities` lists support the older city-band helper. Geocoding is
scoped to Germany; keep the search profile consistent with these settings.

### API key and model

Edit the ignored `.env`, or export the variables in your process environment:

```dotenv
OPENAI_API_KEY=your-own-api-key
AGENT_MODEL=your-supported-api-model
MAX_DAILY_MODEL_USD=1.50
```

These values are placeholders. Choose an API model available to your account that
supports the Agents SDK and hosted web search. Availability is not verified here;
set the model explicitly instead of relying on the existing fallback. Exported
variables take precedence over `.env`. Live model and search calls can incur charges.

### Style references

`config/00_START_HIER.md` and `config/00_STILKOMPASS_ANSCHREIBEN.md` guide personal,
formal, and technical writing. The public `startup_sample.txt`, `corporate_sample.txt`,
and `tech_sample.txt` are deliberately empty; the agent falls back to style guidance.

Add private `.txt` or `.md` letters with different filenames under
`data/input/stilreferenzen/`. The agent discovers them and can read one to three
references, up to 12,000 characters each. Assign private filenames to styles in
`config/bewerbungsregeln.md`. References guide tone and structure, not factual claims.
**Keep the three public placeholders empty:** they are included by Git, while
additional reference files are ignored. Optional reference PDFs are layout inputs.

## Terminal usage

Activate the environment and run commands from the repository root:

```bash
python main.py init
python main.py import
python main.py status
```

Re-import after updating the CV or references. A TXT CV is required; a PDF alone
is insufficient. The following IDs are examples; job and application IDs differ.

| Command | Purpose |
|---|---|
| `python main.py applications` | List applications and statuses |
| `python main.py jobs` | List jobs, scores, workflow states, and output paths |
| `python main.py search` | Research up to five new jobs |
| `python main.py draft 1` | Recheck job 1 and draft in its requested format |
| `python main.py email 1` | Alias for the same format-aware draft flow |
| `python main.py draft-all` | Attempt drafts for up to three ready jobs |
| `python main.py run` | Research followed by batch drafting |
| `python main.py mark-job 1 beworben` | Manually update a job/application status |
| `python main.py set-status 1 absage` | Update an application by its application ID |
| `python main.py usage` | Show recorded approximate daily model costs |
| `python main.py schedule-mac` | Create an optional macOS schedule |

PDFs go to `output/anschreiben/`; email drafts to `output/emails/`. Status commands
only update local records, with safeguards against certain backward transitions.
Display commands also initialize tables and are not strictly read-only.

The macOS schedule requires `.venv/bin/python`, writes a user LaunchAgent, and
prints manual activation/deactivation commands. It runs `run` at 08:00 and 18:00
local time while the user is logged in and the machine is running. Logs are local.

## Privacy, tests, and limitations

`.gitignore` excludes private configuration, CVs, history, databases, outputs,
credentials, and temporary files. Review publication contents: tracked files,
forced additions, and archives can bypass these rules. Public templates must stay neutral.
During live use, OpenAI may receive profile, CV, history, and reference content.
SDK tracing is disabled, but model requests still occur. Nominatim receives city
queries and OSRM receives coordinates; local storage does not mean local-only processing.

```bash
python -B -m unittest discover -s tests -v
```

Tests use invented fixtures and mocked external services, not paid APIs. PDF tests
need PDF libraries and a supported font pair or are skipped. Prompt tests isolate
the actual function bodies from the SDK. `python -B test_pdf.py` is a manual layout
probe with fictional sender data; it skips the empty startup reference.

- Offline tests do not verify live SDK/model compatibility, current prices, or listing availability.
- Model scores, evidence, and generated claims always need human review.
- The pre-run budget check estimates recorded model spend, not a hard cost cap.
  Web-search charges and failed calls are incomplete; unknown models estimate zero.
  The provider's billing dashboard is authoritative.
- CSV import inserts new company/role pairs but does not update existing rows or
  export status changes. Removed CVs are not pruned; maintain one current TXT CV.
- `draft-all` can revisit `nur_cv` jobs. Bounded agent turns do not guarantee an output.
- URL identity preserves job parameters and fragments; redirect aliases may need
  review. Output creation and status updates can leave partial progress after errors.
- Public routing services may fail or limit usage; cached lookups are not a bulk rate limiter.
- Stale locks need inspection and manual removal. Scheduling is macOS-only.
