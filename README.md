# dodgewuh

**Dodgeball where your body is the controller.** Four friends, two teams, one big screen and
the phones already in their pockets. One teammate runs, the other throws, and when a ball is
about to hit you, the game drops into slow motion and you have to physically dodge it in front of
the camera.

**Play it live: [dodgewuh.fit](https://dodgewuh.fit/)**

> **Hackathon prompt:** *How can we leverage technology to promote health, social connection, and
> well-being in our communities?*

---

## The problem

Most screen time keeps us sitting still and apart. Video games are social in name, but each
player is usually on a couch with a controller, or in a separate room on a headset. Exercise
apps tend to be solo and easy to drop. Active games like VR fitness or motion-controller
consoles need hardware that most households, schools and community centres don't have.

## Our answer

dodgewuh turns any laptop/TV camera and four phones into a **full-body, in-person team game**:

- **Health:** you play by jogging in place, swinging your arm to throw and stepping out of the
  way of incoming balls. A best-of-3 match is several minutes of real movement, and it doesn't
  feel like a workout.
- **Social connection:** each character is controlled by **two people at once**: one is the
  *Legs*, one is the *Arms*. Neither can win alone, so teammates have to talk, call out
  positions and coordinate throws. Everyone plays in the same room around one screen, and
  friends can join as spectators on their own devices.
- **Well-being and access:** no consoles, no VR, no app install. It runs in the browser on
  phones people already own, and roles swap every round so everyone gets a turn at both jobs.

## How you play

1. A laptop or TV opens the site and taps **Create room**. It shows a 6-letter room code.
2. Four players join on their phones with that code and pick a team: **Blue** or **Orange**.
   Anyone else can join to **Watch**.
3. Each team has two roles:

| Role | What you do with your body | What the phone/camera does |
|---|---|---|
| **Legs** | Phone in your pocket. **Jog in place** to run; **turn your body** to steer. | The pocketed phone detects jogging in about 0.3 s. A screen webcam tracks which way you face with pose estimation. |
| **Arms** | Hold the phone like a stick. **Point** to aim, **tap** to grab a ball, **chop** toward the screen to throw. | Motion sensors read the aim direction, and the speed of the chop sets throw strength. Gesture-gated, so you can't throw by accident. |

4. When everyone is ready, the match starts automatically. Hit an opponent to win the round.
   You can't throw from inside the no-throw zone at the centre line.
5. **Best of 3.** After every round, teammates **swap roles** and recalibrate, so everyone
   both runs and throws.

### The camera dodge

With the webcam an incoming hit isn't automatically the end:

- The moment a ball **actually connects**, the whole room drops into **8× slow motion**. The
  ball freezes in front of you.
- Your camera feed enlarges and a ball is overlaid on your torso. You get **1.1 seconds** to
  physically step out of it, and you have to **stay in frame**, jumping out of the shot counts
  as a hit.
- If you clear it, the ball flies past and play continues. If you don't, you lose the round.
- **No dodging a ball thrown at your back.** If you're facing away, the hit just counts.

It's the most fun part of the game to watch, and it makes players move and react quickly with
their whole body.

---

## How we built it

```
    Arms phone ─┐                           ┌─ Screen(s): PlayCanvas 3D stadium
    Legs phone ─┤  HTTPS / WebSocket        │     + webcam pose tracking (MediaPipe)
    Arms phone ─┼──────────────▶ Coordinator ◀────┤
    Legs phone ─┘    (FastAPI)  │  rooms, auth,    └─ Spectators
                                │  PostgreSQL
                                │ private channel
                                ▼
                          Game worker
                   authoritative 60 Hz simulation
                   (pure Python, deterministic)
```

See [Tech stack](#tech-stack) below for the full breakdown.

## Challenges we ran into

- **The camera was too slow to detect running.** On recorded runs, knee lift seen by the webcam
  peaked at 6–10 cm against ±3 cm of jitter, so camera-only jog detection lagged 0.6–2.2 s.
  We split the job: the **pocketed phone detects *when* you jog** (~0.3 s), and the **camera
  decides *which way*** you face.
- **Making physics fun, not real.** With real gravity (9.81 m/s²) a throw carried only about
  5 m, and a defender standing at their back wall could never be hit. We tuned gravity, throw
  speed and court size through playtests until every spot on the court was reachable but you
  could still see the ball arc.
- **Tuning the dodge.** The first version triggered too early and judged the dodge long before
  the ball arrived. We moved the trigger to the moment of real contact, slowed time 8×, shrank
  the overlay ball and settled on a 1.1 s window through playtesting.
- **Real-time multiplayer without cheating.** Four phones, multiple screens and spectators all
  have to agree. Every input carries an epoch and sequence number, phase changes invalidate stale
  input, and the server is the only authority.

## Accomplishments we're proud of

- A complete, playable best-of-3 match with **no hardware beyond phones and a laptop**.
- Two people steering one character feels great, and it forces teammates to talk to each other.
- The slow-motion camera dodge: physical, dramatic, and fun even for people just watching.
- A deterministic, server-authoritative simulation with automated diagnostics of the game rules.
- One-command cloud deployment, a spectator mode, and a practice mode for the dodge.

## What we learned

- Phone sensors are good enough for real exercise games, as long as each sensor does the job
  it's best at.
- In a body-controlled game, game feel matters as much as correctness. Most of our best changes
  came from playtesting, not planning.
- A strict shared contract slows you down for an hour and saves you a day of integration bugs.

## What's next

- **More players and modes:** larger teams, free-for-all, and a solo practice ladder.
- **Health insights:** step counts, active minutes and calories per match, plus streaks for
  playing with friends.
- **Accessibility:** seated and low-mobility control schemes (e.g. arm-only Legs) so everyone
  in a community space can join.
- **Community play:** school gyms, youth centres and senior centres hosting matches on one TV,
  and tournaments between groups.

---

## Try it

**Live:** go to [dodgewuh.fit](https://dodgewuh.fit/) on a laptop or TV and tap **Create room**,
then join from four phones with the room code. The site is HTTPS, so phone motion sensors and
the webcam work with no setup.

**Practice the dodge:** open [dodgewuh.fit/dodge](https://dodgewuh.fit/dodge) on a laptop
with a webcam. A thrower aims at you over and over, so you can test the slow-motion dodge
without phones or a room.

**Debug views:** add `?view=overview`, `?view=fp1` or `?view=fp2` to `/screen` to change the
camera. Spectators can switch views with keys `1`–`4`.

### Run it locally

You need Docker (with Compose) and Node 22. Phones need **HTTPS** for motion and camera
access, so use a tunnel.

```sh
# 1. Backend: Postgres, game worker, coordinator
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator

# 2. Frontend
cd frontend && npm ci && npm run dev

# 3. HTTPS tunnel for phones, e.g.
cloudflared tunnel --url http://localhost:5173
```

Then open `http://localhost:5173` on the laptop and **Create room**, and open the tunnel URL on
each phone to join with the code. With fewer than four people, you can fill empty seats with
synthetic (idle) controllers:

```sh
docker compose exec coordinator /app/.venv/bin/python -m app.devtools.synthetic_phones CODE --count 3
```

If port 8000 is taken, set `COORDINATOR_PORT` (e.g. `8010`) and run the frontend with
`BACKEND_URL=http://127.0.0.1:8010`. More detail is in [backend/README.md](backend/README.md).

### Deploy

A single `terraform apply` creates the coordinator and worker VMs on AWS, builds the chosen
commit and starts everything behind Caddy. That's how [dodgewuh.fit](https://dodgewuh.fit/) is
deployed. See [infra/README.md](infra/README.md).

## Tech stack

![dodgewuh system architecture: four phone controllers and a shared screen connect over HTTPS/WSS to a Caddy-fronted FastAPI coordinator on EC2, which relays commands and snapshots over a private WebSocket to a game worker running the pure-Python 60 Hz simulation, with PostgreSQL on an encrypted EBS volume holding rooms, matches and results.](docs/images/architecture.svg)

- **Frontend:** Vue 3, Vite and TypeScript, with a **PlayCanvas** 3D stadium (crowd, ragdoll
  characters, first-person and spectator cameras) and strict **Zod** validation of every server
  message.
- **Phone controllers:** browser `DeviceMotion`/`DeviceOrientation` sensors, with our own jog
  detector (pocket frame and step cadence) and throw-gesture recogniser. Voice prompts guide you
  through calibration without looking at the screen.
- **Camera Legs and the dodge:** **MediaPipe Pose** runs in the screen's browser. It works out
  which way the Legs player faces from their shoulder line, and judges the dodge by testing the
  overlay ball against the player's skeleton (torso, head and limbs).
- **Backend:** a **FastAPI** coordinator handles rooms, registration, authentication and
  **PostgreSQL** match history through SQLAlchemy and Alembic. It hands each live room to a
  **game worker** that runs the authoritative simulation at 60 Hz and streams 30 Hz snapshots.
  The server alone decides pickups, throws, hits and the dodge, so phones can't cheat.
- **Simulation:** pure, socket-free Python. Ballistic ball arcs, swept-circle collision so fast
  balls can't pass through players, slow motion, and the full lobby → countdown → round →
  role swap → match flow.
- **Shared contract:** one protocol, kept in sync across Pydantic models, generated TypeScript
  types, Zod validators and a JSON Schema.
- **Infrastructure:** Docker Compose locally, and Terraform for two AWS EC2 VMs in production.
  Caddy provides HTTPS and serves the frontend; the worker sits on a private network.

## Repository map

| Path | What's there |
|---|---|
| `frontend/` | Vue + PlayCanvas app: screen, phone controllers, camera Legs, dodge, spectator and practice modes |
| `backend/app/` | FastAPI coordinator, game worker, WebSocket relay, rooms and SQL |
| `backend/simulation/` | Authoritative game simulation and its diagnostics (`python -m simulation.synthetic`) |
| `contracts/` | Shared protocol schema and example messages |
| `assets/` | Blender sources and build scripts for the character models |
| `infra/`, `deploy/` | Terraform and production Compose/Caddy |
| `plans/` | Architecture, game rules ([02](plans/02-game-specification.md)) and API contracts ([03](plans/03-api-contracts.md)) |

## Team

| | Built |
|---|---|
| **Alan** | Backend: coordinator, game workers, PostgreSQL, protocol, AWS deployment |
| **Richard** | Game simulation: physics, collisions, rounds and match logic |
| **Ryan** | Frontend: PlayCanvas screen, UI, integration and the camera dodge |
| **Morteza & Tysen** | Phone motion controllers: Arms throwing and Legs jogging |
