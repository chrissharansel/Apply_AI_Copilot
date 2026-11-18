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

- Custom widgets (React-Select style comboboxes, drag-drop uploaders) are best-effort; failed verification is flagged and left for you in the browser.
- Edits in the review screen apply to the *current* step only; edit earlier steps directly in the browser window.
- After a server restart a session’s browser is gone: press **Resume**. Saved answers are kept, nothing is re-asked.
- Keep the browser window visible (`HEADLESS=false`) so you can solve CAPTCHAs/logins. Many sites’ terms prohibit automation; you are responsible for using it appropriately.
- For production: put MongoDB behind auth, serve over HTTPS, add login rate limiting, and consider httpOnly-cookie auth instead of localStorage.
