# ApplyAI Agent Infrastructure Upgrade

## New workspaces

- Applicant workspace: existing job application workflow, candidate profile, saved answers and resume library.
- Developer Studio: inspect the agent/tool registry, view JSON schemas, run constrained workflows and inspect nested tool-call traces.

Developer Studio is currently an engineering workspace, not an authorization role. It is read-only with respect to candidate profile and application data. If it must be restricted to selected accounts, add server-side role-based access control before exposing it publicly.

## Dynamic agent runtime

The new `backend/app/agents/tool_registry.py` provides:
- Specialist agents selected by a constrained Copilot routing call, with deterministic fallback.
- Registered tools with descriptions and JSON input schemas.
- Runtime argument validation and agent-specific tool allow-lists.
- Composite tools that invoke other tools (`job.prepare_application` invokes job analysis, candidate context and resume recommendation).
- Ordered tool plans with `$ref` references to earlier tool outputs.
- Bounded recursion/call count, audit logging and execution traces.

Browser control, credential handling, CAPTCHA handling and final application submission are not registered as LLM-callable tools. The existing deterministic Playwright orchestrator and human approval gate remain in charge of browser actions.

## Resume versioning

Resume documents now support `job_type`, `target_role`, `effective_from`, `effective_until`, `family_version`, and `job_type_active`. Existing MongoDB documents remain readable; absent fields are treated as legacy/other metadata. No destructive migration is required.

## Accuracy changes

Free-text generation now receives only fresh trusted profile facts, plus reusable verified non-sensitive saved answers. The prompt includes explicit anti-fabrication rules and a self-audit. The direct Draft endpoint passes the same fact provenance metadata as the browser workflow.

## Render deployment

For the backend service when `backend` is the Render Root Directory:
- Runtime: Docker
- Dockerfile Path: `Dockerfile`
- Docker Build Context: `.`
- Health check: `/api/ping`

The backend `.dockerignore` excludes secrets, local virtual environments, cached bytecode and local storage. Keep secrets in Render environment variables. Configure `STORAGE_DIR` to the mount path of a Render persistent disk (for example `/var/data`) so uploaded resume files survive container replacement.

For the React Static Site:
- Root Directory: `frontend`
- Build: `npm ci && npm run build`
- Publish directory: `dist`
- `VITE_API_URL`: `https://<backend-service>.onrender.com/api`
- Backend `CORS_ORIGINS`: exact frontend HTTPS origin.

## Validation performed

- Python source files compile successfully with `compileall`.
- Full pytest execution was not completed in this environment because the `motor` package is not installed in the execution environment.
- Frontend production build was not completed because the interrupted npm install left an incomplete `node_modules` directory without the Vite executable. Run `npm ci && npm run build` in the frontend directory or let Render perform the clean static-site build.
- No live Copilot, MongoDB Atlas, Playwright or Render integration test was performed.
