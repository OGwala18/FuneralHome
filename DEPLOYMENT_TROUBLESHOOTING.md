# FuneralHome deployment runbook

This file is the source of truth for humans and AI agents diagnosing or deploying this repository.

## Quick facts

| Item | Correct value |
| --- | --- |
| Git repository | `OGwala18/FuneralHome` |
| Production branch | `main` |
| Application type | Vite + React + TypeScript single-page application |
| Application directory | `induduzo-care-site-main` |
| Package manager | npm, using `induduzo-care-site-main/package-lock.json` |
| Supported deployment Node.js version | 22.x |
| Install command from repository root | `npm --prefix induduzo-care-site-main ci` |
| Build command from repository root | `npm --prefix induduzo-care-site-main run build` |
| Build output from repository root | `induduzo-care-site-main/dist` |
| Version-controlled Vercel config | `vercel.json` in the repository root |

Do not use `npm build`. npm treats `build` as an unknown npm command. The valid syntax for a package script is `npm run build`.

## What failed in July 2026

The latest inspected production deployment was:

- Vercel deployment ID: `8GvSN2j9Zs17dY22YU3k8eYyGLV2`
- Git commit: `faaa85f08144ffa2509f226ced4da3a73c128cca`
- Branch: `main`
- Created: July 22, 2026
- Result: failed after about two seconds
- Final log line: `Error: Command "npm build " exited with 1`
- Important preceding log line: `Unknown command: "build"`

The April 5, 2026 preview deployment `6icjVytPtrZxQs8BrRRJbAvn1FMi` failed for the same reason. This proves the problem was a persistent Vercel project configuration error, not the code change in either commit.

The Vercel project settings inspected on July 24, 2026 contained three mismatches:

1. Framework Preset was `Angular`, but this application is Vite.
2. Build Command override was `npm build `, but the valid command is `npm run build`.
3. Root Directory was empty, but the application's `package.json` is in `induduzo-care-site-main`.

Because the invalid Build Command was an override, Vercel stopped before installing dependencies or compiling application code.

## Permanent fix in this repository

The repository-root `vercel.json` now overrides the incorrect dashboard framework, install command, build command, and output directory. It also sends client-side routes to `index.html`, which prevents React Router pages from returning a Vercel 404 when opened directly or refreshed.

The configuration intentionally works from the repository root:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "vite",
  "installCommand": "npm --prefix induduzo-care-site-main ci",
  "buildCommand": "npm --prefix induduzo-care-site-main run build",
  "outputDirectory": "induduzo-care-site-main/dist",
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

Keep this file at the repository root while the Vercel Root Directory setting is blank. If the Vercel Root Directory is later changed to `induduzo-care-site-main`, move and simplify the configuration deliberately; do not leave two conflicting deployment layouts.

## Clean deployment procedure

### 1. Check the repository state

From the repository root:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
```

Production should normally deploy from `main`. Do not discard unrelated local changes.

### 2. Use a supported Node.js version

Use Node.js 22.x to match Vercel:

```powershell
node --version
npm --version
```

Do not continue with Node.js 16. This project has dependencies that require Node.js 18 or later, and the deployment standard is Node.js 22.

### 3. Reproduce a clean install and build

From the application directory:

```powershell
Set-Location .\induduzo-care-site-main
npm ci
npm run build
```

Success means:

- npm exits with code `0`.
- Vite reports `built`.
- `induduzo-care-site-main/dist/index.html` exists.
- Bundled assets exist under `induduzo-care-site-main/dist/assets`.

Return to the repository root before Git or Vercel commands:

```powershell
Set-Location ..
```

### 4. Verify the committed Vercel contract

Check `vercel.json` and confirm these exact values:

```text
framework       = vite
installCommand  = npm --prefix induduzo-care-site-main ci
buildCommand    = npm --prefix induduzo-care-site-main run build
outputDirectory = induduzo-care-site-main/dist
```

Also keep the `/(.*)` rewrite to `/index.html` for React Router deep links.

### 5. Commit and push only with authorization

A Git-connected Vercel project creates a new deployment when a new commit is pushed. An AI agent must not commit or push unless the user has asked for it.

Typical human workflow:

```powershell
git add vercel.json DEPLOYMENT_TROUBLESHOOTING.md
git commit -m "Fix Vercel deployment configuration"
git push origin main
```

Pushing a feature branch creates a Preview deployment. Pushing or merging into `main` creates a Production deployment.

### 6. Watch the new Vercel deployment

In Vercel:

1. Open the `funeral-home` project.
2. Open **Deployments**.
3. Select the deployment for the commit just pushed.
4. Confirm the commit SHA and branch match the intended source.
5. Read the build log from the top until the first error, if any.
6. Confirm the status becomes **Ready**.

Do not use **Redeploy** on an old commit that does not contain the fixed `vercel.json` unless the dashboard settings have also been corrected. A new commit containing the configuration is safer and reproducible.

### 7. Perform post-deployment smoke tests

Open the deployment URL and check:

1. The home page loads without a blank screen.
2. Static images and CSS load.
3. Navigate to at least one non-home route.
4. Refresh that non-home route; it must not return 404.
5. Check the browser console for uncaught errors.
6. Test the main navigation and the phone/contact links affected by the deployed commit.

## Vercel dashboard settings

The committed `vercel.json` is authoritative for deployments. For clarity, the dashboard should still be corrected so it does not mislead future maintainers:

| Dashboard setting | Recommended value |
| --- | --- |
| Framework Preset | Vite |
| Build Command | Disable the override, or use `npm --prefix induduzo-care-site-main run build` |
| Install Command | Automatic, or `npm --prefix induduzo-care-site-main ci` |
| Output Directory | `induduzo-care-site-main/dist` if overridden |
| Root Directory | Leave blank when using the repository-root `vercel.json` |
| Node.js Version | 22.x |

Saving dashboard settings is an external project change. An AI agent must obtain confirmation immediately before saving them.

## Troubleshooting decision table

| First useful error or symptom | Likely cause | Fix |
| --- | --- | --- |
| `Unknown command: "build"` | Command is `npm build` | Change it to `npm run build`, or use the repository-root command from this runbook |
| `Could not read package.json` / `ENOENT package.json` | Vercel is building from the wrong directory | Keep the root `vercel.json`, or deliberately set Root Directory to `induduzo-care-site-main` and adjust config paths |
| `Missing script: "build"` | Wrong `package.json` was found | Verify the working/root directory and inspect the scripts in the selected package |
| Build succeeds but Vercel cannot find output | Wrong Output Directory | Use `induduzo-care-site-main/dist` from repository root |
| Direct URL or refreshed route returns 404 | SPA fallback is missing | Keep the rewrite from `/(.*)` to `/index.html` |
| `EBADENGINE`, esbuild install errors, or syntax errors during install | Unsupported local/deployment Node.js version | Use Node.js 22.x, reinstall with `npm ci`, and retry |
| `npm ci` says lockfile and package file disagree | Stale lockfile | Update dependencies intentionally, regenerate `package-lock.json`, then run `npm ci` again |
| Build reports a missing `VITE_*` variable | Missing build-time environment variable | Add the exact variable in Vercel for the correct environment, then redeploy; never commit secrets |
| Deployment uses an unexpected commit | Wrong branch or stale redeploy | Compare the Vercel Source SHA with `git rev-parse HEAD`; deploy the intended branch/commit |
| Site is blank but deployment is Ready | Runtime JavaScript error or bad asset path | Inspect browser console/network errors and verify Vite `base` settings and generated asset URLs |

## AI diagnostic checklist

When asked to fix a future deployment, an AI agent should follow this order:

1. Read this file and `vercel.json`.
2. Inspect `git status`, the current branch, and the latest commit without changing files.
3. Open the newest failed Vercel deployment and record deployment ID, commit SHA, branch, environment, duration, and the first error.
4. Compare the failure with the decision table above.
5. Run a clean local install and build with Node.js 22.x.
6. Fix the smallest root cause in version-controlled configuration or code.
7. Run the clean build again and confirm `dist/index.html` exists.
8. Report any npm audit findings separately; do not run a broad `npm audit fix` unless explicitly authorized because it can change dependency versions and application behavior.
9. Ask before external side effects such as saving dashboard settings, pushing Git commits, or triggering a redeploy.
10. After deployment, verify status **Ready** and run the smoke tests.

## Files that do not configure Vercel

- `netlify.toml` is only for Netlify and does not fix Vercel settings.
- `induduzo-care-site-main/public/_redirects` is useful on Netlify but is not the Vercel SPA routing configuration.
- Vercel behavior for this repository is controlled by the root `vercel.json` plus the Vercel project settings.

## Last verified state

On July 24, 2026:

- A clean `npm ci` succeeded with a modern Node.js runtime.
- `npm run build` completed successfully with Vite 5.4.19.
- Vite transformed 1,767 modules.
- `dist/index.html` and the compiled assets were generated.
- npm reported 16 dependency audit findings under Node.js 22 (3 moderate and 13 high). These findings did not block the build and were not automatically modified.
