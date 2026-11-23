# ApplyAI — autonomous job application agent

React + FastAPI + MongoDB + Playwright + **GitHub Copilot CLI** as the LLM. No local model, no LangGraph; the agent is an explicit Python state machine.

## Run it

**Prerequisites:** Python 3.11+, Node 22+, MongoDB (or `docker compose up -d`), a GitHub account with Copilot (CLI policy enabled if it comes from an organization).

```bash
npm install -g @github/copilot
copilot                               # first run: type /login, then exit  (or set COPILOT_GITHUB_TOKEN)

cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env                                   # then set SECRET_KEY
uvicorn app.main:app --port 8000                       # Windows: do NOT use --reload (Playwright needs the Proactor loop)

cd ../frontend
npm install && npm run dev                             # http://localhost:5173
```
Tests: `cd backend && SECRET_KEY=test-secret-key-123456 pytest`.

## What the form engine does

1. **Smart detection.** Every field is identified from all its signals, strongest first: `autocomplete` attribute, visible label, aria-label, placeholder, `name`/`id`, hint text and section heading. Shadow DOM and iframes are searched too.
2. **Semantic mapping.** "Mobile Number", "Contact No.", `name="phone_number"` and `autocomplete="tel"` all resolve to your phone. Fields about someone else (referrer, reference, emergency contact) are never filled with your data. Anything the rules can't place goes to one batched LLM classification call; if still unknown, it asks you.
3. **Controls.** Text, masked inputs (phone formats), native and multi-selects, radios, checkboxes, ARIA radios/checkboxes/switches, searchable dropdowns (React-Select/MUI style: opens the menu, reads the choices, types to filter, picks, verifies), date pickers (reads `DD/MM/YYYY`-style hints and formats accordingly), contenteditable rich text, file uploads. Every write is read back and verified; failures are flagged, never silently ignored.
4. **Dynamic forms.** After filling, the page is re-observed (up to 6 passes per step); newly revealed fields are planned and filled without restarting. If React re-renders a node, the field is re-found by meaning and retried.
5. **Multi-page.** Next / Continue / Save & continue / Review are recognised; Back, Skip, Save draft and "Continue with Google/LinkedIn" are ignored. The site's own "Step 2 of 5" drives the progress bar. Optional step-by-step mode waits for you after every page.

## Candidate profile intelligence

- **Centralized profile:** personal and contact details, education, employment *and internships*, skills, certifications, projects, links. Edited on the **Profile** page (Details tab).
- **Multiple resumes:** upload one per job category with a label (Python Developer, Java Developer, AI Engineer…), a category and optional keywords. On the Apply page choose **Auto-pick the best match for this job**: resumes are scored against the job title and description (term coverage, label/keyword alignment; one tie-break call to Copilot only when two are very close) and the chosen one is uploaded, with the reason shown. The Resumes tab also has a paste-a-job-description recommender.
- **Automatic experience:** calculated from employment and internship dates. Overlapping jobs are counted once, internships are separate, and the form's own wording decides the category: total, professional (no internships), internship, current role, or a specific skill ("years of Python"). Range dropdowns ("3-5 years") are matched to the right bucket, integer-only boxes get the floor (never overstated), and "months" fields are converted. Skill-specific years are estimates and are only ever *suggested*.
- **Knowledge memory:** confirmed answers are stored and reused (exact, then similar wording). Free-text answers you approved at review are saved too, but for that job only, never auto-reused elsewhere unless you mark them reusable.
- **Conflict detection:** a resume is compared with your saved profile (name, email, phone, links, designation, employer titles and start/end dates, graduation years, certifications, stated vs calculated experience). Differences are listed with severity; you pick profile / resume / enter another. Rulings are remembered per resume value so you aren't asked twice.
- **Fact confidence:** every detail records a source and confidence: *Confirmed by you* (100%), *Approved* / *Calculated* (90%), *Resume link* (85%), *Typed, not confirmed* (80%), *Read from resume* (60%), *Unverified* (30%), or *Missing*. **The agent types in only confirmed facts.** Anything else becomes a one-click suggestion ("I found this on your resume, use it?"), and answering confirms the fact. Volatile facts (notice period, salary, availability) expire and are re-checked.

## Resume links (LinkedIn / GitHub / portfolio)

Clickable labels like "LinkedIn" keep their URL in the PDF's link annotations or the DOCX hyperlink relationships, not in the visible text. These are now read directly (including DOCX headers, footers, tables and text boxes) and classified by domain, and they override anything the LLM guessed. Press **Fetch links from my resume** on the Profile page for an already-uploaded resume (no AI involved), or **Re-read** to re-extract everything.

## Flexibility

- **Settings:** AI drafts vs. you write free-text answers (with *Draft with AI* on any question), tone, length, standing writing instructions, step-by-step mode, similar-question reuse on/off, show/hide browser.
- **Per application:** choose the resume, add job-specific notes for the AI, override visibility and AI mode.
- **Pause and take over** the browser at any time; your manual edits are never overwritten when you continue.
- **"I'll submit it myself"** at review: the agent leaves the filled form open and does not submit.

## How the work is split

| Component | Does | Never does |
|---|---|---|
| **Python orchestrator** (`agents/orchestrator.py`) | Owns every state transition, retries, pauses, approval gate | — |
| **Playwright** (`observer.py`, `executor.py`) | Reads the DOM, fills, uploads, clicks, **reads values back to verify** | Decide what to answer |
| **MongoDB** | Profile, knowledge base, session state, history | — |
| **Copilot CLI** (`llm_service.py`) | Extract resume, summarise job, classify odd fields, draft free text, map an answer onto dropdown options, confirm paraphrased questions | Control the browser, submit, answer sensitive questions |

Flow: `INIT → OPEN_PAGE → ANALYZE → MAP → (ASK_USER → MAP)* → FILL → NEXT_STEP → … → REVIEW → AWAIT_APPROVAL → SUBMIT → DONE`

## Persistent memory (the core idea)

Every value the agent uses has a **source**, shown as a chip in the UI and stored with the application:

- **From profile**: only the profile you explicitly *confirmed*.
- **Saved answer**: from `knowledge_base`. Auto-used only if *user-verified*, *fresh* (per-category TTL, e.g. salary 90 days), and matched exactly, or by close wording / a strict Copilot paraphrase check when the question is not sensitive. Matches never cross categories (sponsorship ≠ work authorization).
- **AI-written**: free-text answers (“why us”, cover letter). Grounded only in your profile and confirmed facts, always flagged *Read before approving*, **never written back into the knowledge base**.
- **You answered**: collected via the chat; you choose *save for future*, *this application only*, or *don’t save*.

Sensitive categories (work authorization, sponsorship, salary, demographics, criminal record, consent/legal declarations, DOB…) are never invented or inferred. A near-match or a profile value is only offered as a *suggestion* you must accept.

## How Copilot CLI is used

Each LLM call is one headless run: `copilot -s` with the prompt on stdin, JSON back on stdout. Copilot CLI is a coding agent, so every call is locked down: empty sandbox directory, `--deny-tool=shell --deny-tool=write`, no MCP servers, no custom instructions, no ask-user tool, and a filtered environment. Non-interactive mode also denies any tool request that isn't explicitly allowed. The reply is parsed as data only.

**Things to know**
- **Privacy changed:** resume text, profile facts, job text and form questions are now sent to GitHub Copilot's service, not processed locally.
- **Usage:** every call counts against your Copilot plan's usage/premium-request allowance. A typical application makes roughly 4–10 calls (resume parse once, job summary, one field-classification per form step, one per free-text answer, occasional option/paraphrase checks).
- **Speed:** each call starts a CLI process, so expect a few seconds per call. `COPILOT_CONCURRENCY` limits parallel runs.
- **Semantic matching:** Copilot CLI has no embeddings API, so saved-answer matching is exact, then lexical similarity, then one strict yes/no paraphrase check for plausible candidates.
- Sign-in problems surface as a clear error on the first real call (the dashboard health check only confirms the CLI is installed, so it doesn't spend a request).

## Safety

- Submission requires an explicit Approve click; `Executor.click(submit=True)` raises without it, and the SUBMIT state is never auto-retried.
- CAPTCHA, login, MFA → the agent stops and asks you to act in the visible browser. “Access denied”/403/429 → stops. No bypass logic exists.
- SSRF: URL validated (public hosts only) and **every browser request** is re-checked, including redirects and subresources.
- Page/job text is treated as untrusted data in all prompts; LLM output never becomes an action — only validated JSON fields (option indexes are range-checked, etc.), and Copilot's own tools are denied.
- scrypt password hashes, JWT auth, per-user data scoping, optional Fernet encryption of stored resumes (`ENCRYPTION_KEY`), audit log, and one-click data deletion.

## Known limits (be aware)

- Tested in real Chromium against a synthetic form with the widgets above (`backend/tests/e2e`), not against live company sites, which vary a lot. Failed verification is flagged and left for you in the browser.
- Not supported yet: repeating sections ("Add another job"), button-style Yes/No groups with no ARIA roles, address autocomplete widgets, and canvas/PDF-style forms. Async-search dropdowns are best effort.
- Edits in the review screen apply to the *current* step only; edit earlier steps directly in the browser window.
- After a server restart a session’s browser is gone: press **Resume**. Saved answers are kept, nothing is re-asked.
- Keep the browser window visible (`HEADLESS=false`) so you can solve CAPTCHAs/logins. Many sites’ terms prohibit automation; you are responsible for using it appropriately.
- For production: put MongoDB behind auth, serve over HTTPS, add login rate limiting, and consider httpOnly-cookie auth instead of localStorage.
