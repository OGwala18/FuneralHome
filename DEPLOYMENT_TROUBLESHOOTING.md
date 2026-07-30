# Induduzo deployment and security runbook

This is the source of truth for humans and AI agents deploying or diagnosing the
Induduzo Funeral Home website.

## Current production contract

| Item | Required value |
| --- | --- |
| Canonical website | `https://induduzo.co.za/` |
| Current production host | Netlify |
| Git repository | `OGwala18/FuneralHome` |
| Production branch | `main` |
| Application type | Static Vite + React + TypeScript site |
| Application directory | `induduzo-care-site-main` |
| Node.js | 22.13 or newer |
| Package manager | npm with the committed `package-lock.json` |
| Netlify base directory | `induduzo-care-site-main` |
| Netlify install/build command | `npm ci && npm run build` |
| Netlify publish directory | `dist` relative to the base directory |
| Netlify configuration | Repository-root `netlify.toml` |

## Environment promotion workflow

This repository uses three controlled stages:

| Stage | Branch | Deployment | Purpose |
| --- | --- | --- | --- |
| Development | `Dev` | Local development | Shared starting point for developers |
| Internal testing | `internal` | `https://internal--induduzo.netlify.app/` | Stable unlisted URL for non-developer testers |
| Production | `main` | `https://induduzo.co.za/` | Public client-facing release |

Developers must update their local `Dev` branch, create a short-lived feature
branch, and merge reviewed work back into `Dev`. Do not treat `Dev` as a place
for several developers to push unrelated changes directly.

Promotion order is always:

```text
feature branch -> Dev -> internal -> main
```

Every promotion must pass lint, TypeScript, production build, dependency audit,
and the applicable browser/security checks. The `internal` deployment is
unlisted rather than authenticated while the Netlify Free plan is in use. An
unlisted URL is not private and must never contain production secrets, real
member data, or an administrative portal.

The canonical Netlify project is the project that owns `induduzo.co.za`.
Ordinary deploy entries are immutable rollback history and should not be
deleted as duplicates. Delete a Netlify project only after verifying that it
does not own the production domain, environment variables, forms, functions,
or a required deploy.

As of July 30, 2026, the Netlify team contains one project:
`induduzo` (Site ID `732df56c-6681-4a26-aac3-b5d0832eb08e`). It owns
`induduzo.co.za`, deploys `main` to production, and deploys only `internal` as a
branch deploy. Deploy Previews are disabled. The duplicate Netlify projects
`induduzofuneral` and `induduzo-care-site-main` were deleted.

Before backend development begins:

- change the GitHub repository to private;
- verify that the Netlify GitHub App still has access to the repository;
- run and verify a harmless deployment before adding backend secrets;
- use separate development/internal and production database environments;
- keep service-role keys and database credentials out of all browser bundles.

The production site does not contain a customer portal or authentication page.
Requests to `/auth`, `/auth/*`, `/portal`, and `/portal/*` must return an HTTP 404 before the
single-page application fallback runs.

Do not use `npm build`. The correct npm script syntax is `npm run build`.

## Why the earlier Vercel deployments failed

The failed Vercel deployments inspected in July 2026 did not reach application
compilation. The Vercel project dashboard had three conflicting settings:

1. Framework Preset was `Angular`, although this repository uses Vite.
2. Build Command was `npm build`, which is not a valid npm script command.
3. Root Directory was blank while the application package is in
   `induduzo-care-site-main`.

The decisive build-log message was:

```text
Unknown command: "build"
Error: Command "npm build " exited with 1
```

The correct repository-root Vercel build command is:

```text
npm --prefix induduzo-care-site-main run build
```

The Vercel project and repository `vercel.json` were removed on July 30, 2026.
The values above are retained only to diagnose the historical failure. Do not
recreate a Vercel project or use Vercel deployment URLs unless the hosting
decision is explicitly changed.

## Security decisions that must remain true

- Only the public routes `/`, `/about`, `/services`, `/contact`, `/join`,
  `/gallery`, `/testimonials`, and `/founder` are shipped.
- Portal components, fake authentication, mock customer data, mock policies,
  claims, family records, and payments are not included in the source or bundle.
- Netlify handles the portal/auth 404 rules before the public SPA fallback.
- The site sends CSP, anti-framing, MIME-sniffing, referrer, browser-permission,
  cross-origin, and HSTS headers from `netlify.toml`.
- `public/_redirects` and `public/_headers` mirror those production rules into
  `dist` so an authorized direct deploy receives the same protections.
- The canonical URL and Open Graph URL use `https://induduzo.co.za/`.
- No secrets belong in Vite `VITE_*` variables. Vite variables are compiled into
  public browser JavaScript.
- A future portal must use managed authentication, backend authorization on every
  protected request, PostgreSQL/Supabase Row Level Security, least privilege,
  encrypted secrets, and audit logs. Hiding a button or route is not security.
- Real member, identity, policy, payment, claim, or bank data must not be added to
  this marketing-site repository.

## Clean pre-deployment procedure

Run all commands from the repository root unless a step says otherwise.

### 1. Confirm what will be deployed

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
```

Do not discard unrelated local changes. Production normally deploys from `main`.

### 2. Confirm the supported runtime

```powershell
node --version
npm --version
```

Node must be 22.13 or newer. The application also includes `.nvmrc`, and
`package.json` declares the minimum supported engine.

### 3. Reproduce Netlify's clean build

```powershell
Set-Location .\induduzo-care-site-main
npm ci
npm run lint
npm run typecheck
npm run build
npm audit --omit=dev --audit-level=high
Set-Location ..
```

All five commands must exit with code `0`. Confirm:

```powershell
Test-Path .\induduzo-care-site-main\dist\index.html
Get-ChildItem .\induduzo-care-site-main\dist\assets
```

### 4. Check that the portal cannot re-enter the bundle

```powershell
rg -n "My Portal|/portal/customer|mockCustomer|mockPolicy|mockClaims|react-router-dom" `
  .\induduzo-care-site-main\src `
  .\induduzo-care-site-main\package.json
```

No match is expected. Then confirm both `netlify.toml` and `public/_redirects`
still place the `/auth`, `/portal`, and `/portal/*` 404 rules before the
`/* -> /index.html` status-200 fallback.

### 5. Check for accidentally committed secrets

```powershell
rg -n "PRIVATE KEY|API_KEY|SECRET|PASSWORD|TOKEN|DATABASE_URL|SUPABASE" . `
  --glob "!**/node_modules/**" `
  --glob "!**/dist/**"
```

Investigate every match. Never paste a secret into a deployment log or commit.
If a secret was committed, removing it from the latest file is not enough:
revoke/rotate it first, then clean history with an approved procedure.

## Deploying to Netlify

### Git-connected production deployment

1. Commit only the intended reviewed changes.
2. Push or merge the reviewed commit to `main`.
3. In Netlify, open the production site's **Deploys** page.
4. Match the Netlify deploy's Git commit SHA to the pushed commit.
5. Read the build log from the top and stop at the first error.
6. Wait for the deploy state to become **Published**.
7. Keep the previous published deploy available for rollback.

An AI agent may commit, push, or change hosting settings only when the user has
authorized those external actions.

### Netlify configuration values

The repository `netlify.toml` is authoritative:

```text
Base directory    = induduzo-care-site-main
Build command     = npm ci && npm run build
Publish directory = dist
Node              = 22
```

If the Netlify dashboard has overrides, remove them or make them identical. A
dashboard override can silently supersede a correct repository configuration.
For an authorized direct deploy, upload the contents of `dist`, which includes
`_headers` and `_redirects`; do not upload only `index.html`.

## Post-deployment verification

Verify the custom domain, not a generated deploy URL:

```powershell
$publicRoutes = @(
  "/",
  "/about",
  "/services",
  "/contact",
  "/join",
  "/gallery",
  "/testimonials",
  "/founder"
)

foreach ($route in $publicRoutes) {
  $response = Invoke-WebRequest "https://induduzo.co.za$route"
  "$route $($response.StatusCode)"
}

$blockedRoutes = @("/auth", "/auth/sign-in", "/portal/customer", "/portal/admin")
foreach ($route in $blockedRoutes) {
  try {
    Invoke-WebRequest "https://induduzo.co.za$route" -ErrorAction Stop
  } catch {
    "$route $([int]$_.Exception.Response.StatusCode)"
  }
}
```

Expected:

- Every public route returns `200`.
- Every blocked route returns `404`.
- Refreshing a public non-home route still works.
- The header does not show **My Portal**.
- Browser console has no uncaught errors.
- Navigation, language buttons, phone links, WhatsApp links, and public forms
  behave as expected. The public phone number must display as
  `+27 (79) 751-0648`, telephone links must use `tel:+27797510648`, and WhatsApp
  links must use `https://wa.me/27797510648`.
- Test every public route at phone (390px), tablet (768px), and desktop (1440px)
  widths. Confirm there is no horizontal scrolling and the mobile/tablet menu
  exposes every public route.
- Run the public flows in Chromium/Chrome and WebKit/Safari-compatible testing.
  Confirm there are no uncaught console errors in either engine.

Check response headers:

```powershell
$headers = (Invoke-WebRequest "https://induduzo.co.za/").Headers
$required = @(
  "Content-Security-Policy",
  "Cross-Origin-Opener-Policy",
  "Cross-Origin-Resource-Policy",
  "Permissions-Policy",
  "Referrer-Policy",
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options"
)

foreach ($name in $required) {
  "$name = $($headers[$name])"
}
```

Missing headers mean the correct `netlify.toml` was not used, a dashboard base
directory is preventing Netlify from reading it, or the inspected deploy predates
the security change.

## Failure diagnosis: use the first real error

Do not troubleshoot the final generic `build failed` line. Find the first useful
error above it.

| First error or symptom | Likely cause | Corrective action |
| --- | --- | --- |
| `Unknown command: "build"` | Command is `npm build` | Use `npm run build` |
| `ENOENT package.json` | Wrong base/root directory | Set Netlify base to `induduzo-care-site-main` |
| `Missing script: "build"` | Wrong `package.json` selected | Inspect the working directory and selected package |
| `npm ci` reports lock mismatch | `package.json` changed without lockfile | Regenerate the lockfile intentionally and rerun `npm ci` |
| `EBADENGINE` | Old Node runtime | Use Node 22.13 or newer |
| Vite cannot load a module | Import points to a removed/mis-cased file | Fix the first module path; remember Netlify uses case-sensitive Linux |
| Build succeeds but no published files | Wrong publish directory | Use `dist` relative to the Netlify base directory |
| Public deep link returns 404 | SPA fallback missing/ordered incorrectly | Keep the final `/* -> /index.html 200` Netlify rule |
| Portal URL returns 200 | SPA fallback is winning | Put forced `/auth`, `/portal`, and `/portal/*` 404 rules before the fallback |
| CSP blocks a required resource | Resource origin is not allowed | Prefer self-hosting; otherwise add only the exact required origin |
| Site is `Published` but blank | Runtime JS or asset-path error | Inspect browser console/network and generated asset URLs |
| Custom domain shows an old site | DNS, wrong Netlify site, or cached deploy | Inspect DNS, domain assignment, deploy SHA, and CDN headers |
| HTTPS/certificate warning | Domain/certificate provisioning problem | Check Netlify Domain Management and DNS before redeploying code |
| Unexpected Vercel deployment | A Vercel project or Git integration was recreated | Inspect the new project, then delete or disconnect it after explicit approval |

## Rollback procedure

If a production smoke test fails:

1. Stop changing DNS.
2. In Netlify **Deploys**, publish the last known-good deploy.
3. Record the failed deploy ID, commit SHA, first error, and rollback deploy ID.
4. Reproduce the failure locally from the failed commit.
5. Fix the smallest root cause on a branch.
6. Repeat the clean build and complete post-deployment verification.

Rollback is faster and safer than making untested edits directly in hosting
settings.

## AI diagnostic checklist

An AI agent handling a future deployment must follow this order:

1. Read this runbook, `netlify.toml`, `package.json`, and `.nvmrc`.
2. Inspect Git status, branch, commit SHA, and remote without changing them.
3. Identify the canonical host and latest production deploy.
4. Record deploy ID, commit SHA, branch, status, duration, and the first error.
5. Compare dashboard build settings with the repository contract.
6. Run `npm ci`, lint, build, audit, and secret/portal searches locally.
7. Fix only the smallest supported root cause.
8. Repeat all checks after the fix.
9. Deploy only with authorization.
10. Verify public routes, blocked routes, console, headers, domain, and deploy SHA.
11. Report what changed, evidence of success, remaining risk, and rollback point.

## Planned backend and database boundary

This marketing site should remain static. When backend features are required:

- Run a FastAPI service on a managed backend host designed for persistent APIs
  (for example Render, Railway, or Fly.io), not inside this public repository.
- Use a separately managed PostgreSQL database such as Supabase Postgres.
- Use managed authentication and enforce authorization in the API and database
  RLS policies; never rely on frontend route guards.
- Keep development, staging, and production isolated.
- Store backend secrets only in backend environment variables or a secret manager.
- Allow only the production frontend origin, validate every request, rate-limit
  sensitive endpoints, and produce immutable audit events.
- Complete POPIA controls and a threat model before using real member data.

## Last local verification

On July 29, 2026:

- Clean `npm ci` completed successfully.
- ESLint completed with zero errors.
- TypeScript completed with zero errors.
- Vite 8.1.5 production build completed successfully.
- npm audit reported zero known vulnerabilities.
- Portal/auth source and mock customer records were removed.
- Netlify security headers and forced 404 rules were added.

Production verification must be repeated after the corresponding commit is
published to Netlify.
