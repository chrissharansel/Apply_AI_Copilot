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

## Docker deployment

The repository includes Docker support for the complete local stack:
- `backend/Dockerfile`: Python/FastAPI, Node.js 22, GitHub Copilot CLI, Playwright and Chromium.
- `frontend/Dockerfile`: builds the React/Vite app and serves it with Nginx.
- `docker-compose.yml`: starts MongoDB, backend and frontend, with named volumes for MongoDB and uploaded files.

### Run locally with Docker

1. Copy `backend/.env.example` to `backend/.env`.
2. Set at least `SECRET_KEY` (16+ characters) and `COPILOT_GITHUB_TOKEN`. Keep this file private; it is excluded from the Docker build context and Git.
3. From the repository root, run:

   ```bash
   docker compose up --build
   ```

4. Open `http://localhost:5173`. The API is at `http://localhost:8000/api` and health check at `http://localhost:8000/api/ping`.
5. Stop the stack with `docker compose down`. Named volumes keep MongoDB data and `/app/storage` across container recreation. `docker compose down -v` deletes those volumes and their data.

The Compose stack uses `HEADLESS=true`, which is required for a hosted/container browser. A remote container cannot display a normal desktop browser window to your local machine.

### Deploy the backend to Render with Docker

Create/update the backend as a **Web Service → Docker**:
- Dockerfile path: `backend/Dockerfile`
- Docker build context: repository root (`.`)
- Health check path: `/api/ping`

Set these environment variables in Render (do not bake secrets into the image):
- `MONGODB_URI`: MongoDB Atlas connection string
- `DATABASE_NAME`: `applyai`
- `SECRET_KEY`: a randomly generated secret (at least 16 characters)
- `ENCRYPTION_KEY`: optional Fernet key
- `COPILOT_GITHUB_TOKEN`: GitHub Copilot CLI token supported for headless use
- `COPILOT_BIN`: `/usr/local/bin/copilot`
- `CORS_ORIGINS`: exact React frontend origin, e.g. `https://your-frontend.onrender.com`
- `STORAGE_DIR`: `/var/data`
- `HEADLESS`: `true`
- `MAX_CONCURRENT_SESSIONS`: choose a value appropriate for the service's memory

Attach a Render persistent disk mounted at `/var/data` so uploaded resumes and screenshots survive redeploys. Without a persistent disk or external object storage, container-local uploads are ephemeral. Keep MongoDB Atlas network access restricted to the deployment's required outbound IPs where possible.

Deploy the React frontend separately as a Render Static Site using `frontend` as its root directory, `npm install && npm run build` as the build command, and `dist` as the publish directory. Set `VITE_API_URL` to `https://YOUR-BACKEND.onrender.com/api` at build time. Set the backend's `CORS_ORIGINS` to the frontend's exact HTTPS origin.

**Important:** `HEADLESS=true` means you cannot interact with a visible browser window inside Render. The application can still run Playwright headlessly, but login/MFA/CAPTCHA steps that require a visible browser need a separately designed remote/manual interaction workflow. Also verify the Copilot CLI token and account entitlement in the deployed environment; installing the CLI does not itself authenticate it.
