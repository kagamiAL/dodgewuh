# Repository, ownership and local workflow

All paths below are relative to the future monorepo root (parent of this plans directory). The repository now includes owner-separated directories with .gitkeep placeholders; application implementation has not started. Do not create another nested plans directory. One owner per path; other developers send proposed edits to its owner.

| Owner | Exclusive paths | Responsibilities |
|---|---|---|
| Richard | backend/simulation/**; backend/tests/simulation/** | Pure types, constants, engine, synthetic runner, simulation tests |
| Ryan | frontend/** EXCEPT paths assigned below; tests/e2e/**; docs/demo/** | package.json/lockfile, Vite, app/router/session store, views, screen renderer, PhoneShell, screen mocks, UI tests |
| Morteza | frontend/src/controllers/arms/**; frontend/tests/arms/** | Arms Vue component, calibration, gesture processing, fixtures/tests |
| Tysen | frontend/src/controllers/legs/**; frontend/src/sensors/**; frontend/src/playground/**; frontend/tests/legs/**; frontend/tests/sensors/**; docs/device-tests/** | Legs, shared sensor service, sensor playground, real-phone report |
| Alan | backend/** EXCEPT Richard paths; contracts/**; frontend/src/net/**; frontend/src/generated/**; frontend/tests/net/**; infra/**; deploy/**; .github/**; root README.md, .gitignore, .env.example, Makefile | Network protocol, backend adapter, infrastructure, shared fixtures, CI and root bootstrap |

Plans are frozen references; Alan records coordinated contract amendments in 03, Richard in 02. Any other plan correction has one named editor agreed before editing. Root bootstrap is Alan's; Ryan owns frontend dependency files even for controller dependencies. No five agents editing App.vue or requirements independently.

```text
backend/
  pyproject.toml, requirements.lock
  app/{main,rooms,protocol,ws,runner,simulation_adapter}.py
  simulation/{types,constants,engine,geometry,synthetic}.py
  tests/{simulation,integration,contracts}/
frontend/
  package.json, package-lock.json, vite.config.ts
  src/
    main.ts, App.vue, router.ts
    stores/session.ts
    views/{Home,Lobby,Screen,PhoneShell}.vue
    game/{scene,interpolation,mockSource}.ts
    net/{transport,mockTransport}.ts
    generated/{protocol,validators}.ts
    controllers/{arms,legs}/
    sensors/sensorService.ts
    playground/SensorPlayground.vue
  tests/{arms,legs,sensors,net,game}/
contracts/fixtures/{valid,invalid}/
infra/{versions,main,variables,outputs}.tf
infra/terraform.tfvars.example
deploy/{Caddyfile,dodgeball.service,bootstrap.sh,deploy.sh}
tests/e2e/
docs/{device-tests,demo}/
plans/
```

## Dependency choices and bootstrap

Use Python 3.12, FastAPI, Uvicorn standard extras, Pydantic v2; pytest and httpx for backend tests. Simulation uses standard library only. Vue 3, TypeScript, Vite, PlayCanvas, Vue Router, Zod and Vitest in frontend; Playwright only for a small browser smoke if time allows. No state management library required: small reactive session store. Use current compatible versions selected during bootstrap, commit exact npm lockfile and Python requirements lock, and record Node version matching selected Vite engines. Do not invent version compatibility before installation. Caddy runs as a host service; no containerization requirement.

Alan creates root/backend scaffolds and canonical protocol fixtures first; Ryan creates the frontend scaffold and PhoneShell placeholders inside his owned files. Morteza/Tysen create their own controller/sensor exports; Alan creates net/generated exports. Ryan never creates placeholder files in their directories. Richard supplies types/Simulation signatures immediately. Controller owners work in assigned directories against the frozen signatures. Shared interfaces in [03](03-api-contracts.md) precede implementation; placeholders must compile and have final method signatures.

## Local commands (implementation target)

From monorepo root, Alan must make these work:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.lock
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Vite proxies /api and /ws (ws enabled) to 127.0.0.1:8000 without prefix rewriting. Browser transport derives scheme/host from location; no hardcoded cloud URL. Desktop localhost can develop without cloud. Sensor mocks need no backend; screen mock route `/screen?mock=1` uses validated snapshots; `/sensors` opens Tysen's playground. Mock routes must be disabled in production builds or clearly marked and unreachable from normal flow. Synthetic inputs never become the public phone control scheme.

```sh
PYTHONPATH=backend python -m simulation.synthetic
PYTHONPATH=backend pytest backend/tests
cd frontend
npm run typecheck
npm test -- --run
npm run build
```

Ryan defines these npm scripts. Each agent runs its focused tests before handing off; integrated checks run at merge windows. A physical phone connecting over LAN HTTP is not the secure-context solution. Use locally trusted HTTPS Caddy with a dev CA installed and explicitly trusted on each phone, or the public EC2 HTTPS origin; local-only CA setup in [08](08-deployment-runbook.md).

## Configuration and Git

Root .env.example documents PUBLIC_ORIGIN, LOG_LEVEL, BUILD_SHA, ROOM_LIMIT; deploy environment additionally DOMAIN. Browser contains no secrets. AWS_PROFILE and AWS_REGION are operator environment only. Ignore .env, .venv, node_modules, build output, private keys, Terraform state/plan and real tfvars; commit lockfiles and example values.

Branches `feat/richard-sim`, `feat/ryan-screen`, `feat/morteza-arms`, `feat/tysen-legs`, `feat/alan-network`. Small PRs to main at integration windows; one peer verifies a real acceptance case, then merge. Ryan is integration coordinator because he can verify the final screen/phone flow without adding orchestration work to Alan. Alan approves wire changes; Richard approves game constants; affected owner acknowledges each change. Update spec, DTOs, validators and fixtures together in one coordinated merge before dependents rebase. No silent changes. Merge order: bootstrap/contracts → pure simulation stub + UI/sensors scaffolds → transport adapter + renderer → Legs vertical slice → Arms → round lifecycle. Independent directories can merge earlier; do not wait for a complete subsystem.

## Parallel scaffold rules

The repository root now contains the directory tree above with .gitkeep in 27 owned leaf directories, including `.github/workflows`. Each owner removes only their own .gitkeep when adding real files. Parent directories need no extra placeholder. Do not create shared package manifests in parallel: Alan alone owns backend/root manifests and CI; Ryan alone owns frontend manifests/lockfile. Send dependency requests to the manifest owner.

Each agent uses its named branch in a separate checkout/worktree. Do not switch five branches in one shared working directory. Alan creates the root/backend bootstrap and Ryan the frontend bootstrap first; others can write in their owned directories against 03 immediately after freeze. Merge those two bootstrap commits before integrated builds. No agent creates stubs in another owner's paths. The scaffold deliberately contains no package.json, pyproject.toml, App.vue or generated protocol implementation.
