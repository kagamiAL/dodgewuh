# dodgewuh

**A dodgeball game where one character needs two people.**

Hack the Change 2026 · Team of five · [dodgewuh.fit](https://dodgewuh.fit)

> **Challenge prompt:** How can we leverage technology to promote health, social
> connection, and well-being in our communities?

---

## What it is

Four phones. Two characters. Nobody plays alone.

Each team's dodgeball character is operated by **two people at once**. One player
is the **Legs** — they jog in place to move the character. The other is the
**Arms** — they physically aim and throw with their phone. Neither half can play
without the other. The Arms player cannot chase down a ball; the Legs player
cannot throw one.

At the end of **every** round, teammates **swap roles**. Nobody becomes the
specialist; everyone does both halves of the work.

No app install. Open a browser, enter a room code, play.

### A match in eight steps

1. Someone creates a room and gets a short code.
2. A laptop joins as the **screen**; four phones join as **controllers** and are
   assigned Team 1/2 × Arms/Legs.
3. Each phone grants motion permission and calibrates.
4. The host starts once all four are ready.
5. **60-second rounds.** Four balls spawn mid-court. Legs players jog to them;
   Arms players hold to pick up, aim with the phone, and swing to throw.
6. **No-throw zones** sit either side of the centre line. You can collect balls
   there and you can still be hit there — but you cannot throw from there. No
   camping the middle.
7. A hit **ends the round instantly** and scores a point. Sixty seconds with no
   hit is a draw. Roles swap, everyone recalibrates, next round.
8. **Best of three** — first to 2 points wins; level after three rounds is a
   draw. Rematch stays in the same room.

---

## 1. Innovation & Creativity

**The shared body is the mechanic, not a gimmick.**

Motion games almost always bolt gestures onto a loop that one person could play
with a gamepad. We inverted that: we split a single character's control surface
across two bodies, so cooperation is a *physical constraint* rather than a
feature we hope players use.

The consequences are what make it interesting to play:

- **Communication is forced, not encouraged.** The Arms player can see a ball
  they cannot reach. The only way to get it is to say so out loud. There is no
  silent path to a point.
- **Role-swapping every round defeats specialisation.** A team cannot park its
  athletic player on Legs and its accurate player on Arms. Both people learn
  both jobs within one match.
- **The no-throw zone creates a genuine dilemma.** The balls are in the middle,
  and the middle is exactly where you are not allowed to throw from — but you
  *can* be hit there. Collecting ammunition is risky, and retreating to throw
  costs you time. That tension comes from one rule.

**Creative technical choices fell out of the design.** Because a phone has no
vertical-aim channel, every throw leaves the hand horizontally — which let us
simulate a genuine ballistic arc while keeping collision as a provably correct
2D test. And because our Legs controller needed to be fast, we fused two
signals: the pocketed phone detects jogging in ~0.3 s, far sooner than pose
landmarks can confirm it, while an optional screen camera supplies *facing*
direction. The phone is the trigger; the camera is the steering.

## 2. Impact & Relevance to Prompt

The prompt asks for health, social connection, and well-being. dodgewuh
addresses all three structurally, not incidentally.

| Prompt dimension | How the design delivers it |
|---|---|
| **Physical activity** | Movement *is* jogging in place; throwing *is* a throwing motion. There is no joystick in the shipped control scheme. Stop moving and your character stops. |
| **Social connection** | A character with two drivers makes continuous talking the only viable strategy. Players end up coaching each other mid-round. |
| **Well-being** | Short 60-second rounds, a 3-second countdown, and role swaps give natural rest and reset beats. Play is cooperative-competitive, not elimination-based — nobody sits out. |
| **Accessibility** | Any modern phone browser plus any laptop screen. No downloads, no accounts, no console, no peripherals. |
| **Community** | Private room codes mean a classroom, rec centre, youth group or living room can start a match in under a minute on devices people already own. |

**Who it is for.** Settings that already have a screen and a few phones but no
budget for hardware: schools, community centres, after-school programs, office
breaks, family gatherings. The barrier to a group game is usually equipment and
setup time; we reduced both to a URL and a code.

*We deliberately make no clinical health claims. This is active play, not a
medical intervention.*

## 3. Feasibility & Scalability

**Cost and infrastructure are deliberately small.**

- Two EC2 instances (a coordinator and a game worker) plus one encrypted
  database volume, provisioned by Terraform in `us-east-2`. Caddy terminates
  TLS. That is the entire production footprint.
- **No per-user cost.** No app store review, no device provisioning, no
  accounts, no third-party game service. Players bring the hardware.
- **Zero install friction** is the real scalability story: anyone who can open a
  link can join in seconds.

**It scales the way the architecture was built to scale.** Each room is one
independent, in-memory simulation object with a single serialized mutation path.
The coordinator allocates rooms to game workers, so adding capacity means adding
workers — there is no shared gameplay state to contend on. PostgreSQL stores
only room/member records and completed match results; it is never in the
gameplay path, and no blocking SQL happens inside a simulation tick.

**Honest status.** The game is playable end to end locally today: room
create/join, readiness gating, host start/reset, Legs movement, Arms
pickup/aim/throw, hit detection, scoring, timeout draws, role switching,
best-of-3, rematch, and disconnect-resets-to-lobby. Local verification is
recorded in `docs/demo/`. Terraform for the AWS footprint is written but, as of
this writing, **has not been applied, and a public four-device acceptance run
has not yet been recorded.** We would rather show a solid local demo and say so
than claim a deployment we have not verified.

**Beyond the demo.** The same room model supports spectator screens already
(multiple screens render the same match from the same snapshots). Natural next
steps are a tournament/queue layer on top of rooms and a lightweight facilitator
view for a teacher or coach running several matches.

## 4. Technical Execution

**One authoritative simulation, in pure Python.**

The tempting hackathon design is to let one screen run the game and have the
others mirror it. We rejected it: if the host screen drops, the match dies, and
two screens running physics will eventually disagree about a collision.

```
4 phones  ──normalized commands──┐
                                 ├─►  FastAPI coordinator  ─►  game worker
2+ screens ◄───20 Hz snapshots───┘     (rooms, Postgres)       (60 Hz sim)
```

- Phones send **normalized game commands** (`move {x,z}`, `aim`, `press` /
  `release` / `cancel`) — never raw sensor streams. Gesture recognition happens
  on the phone; the server alone decides whether a throw is *legal*.
- The simulation is a **fixed 60 Hz step**, ~4,600 lines of **standard-library-only
  Python**. No FastAPI, Pydantic, asyncio or database imports appear anywhere
  inside it. It is a plain synchronous object you can drive from a script.
- Screens receive **20 Hz full snapshots** and only render. They decide no
  outcomes.
- Determinism is a design goal: the same commands on the same ticks produce the
  same final state.

That boundary is why the game logic could be built and rigorously checked before
the network, the renderer, or a single phone existed.

### Four problems worth calling out

**Naive collision tunnels straight through people.** We sweep the ball's segment
against *the opponent's movement segment* — relative-motion swept circles —
solve for the earliest impact inside the tick, and clip to the wall or floor
endpoint first. It is verified by firing a ball at 600 m/s, 10 m in a single
tick, where both tick endpoints sit clear of the character and only a swept test
can find the hit.

**Ballistic arcs without a 3D collision test.** Balls fall under gravity, arc
downward, and come to rest where they land. Collision nonetheless stayed a flat
2D test — and that is sound, not a shortcut. Because a phone has no vertical-aim
channel, every throw leaves the hand horizontally, so the ball only ever falls,
never rises above its 1.5 m release height, and stays inside a 1.8 m character
for its whole flight. Gravity changes *where a ball ends up*, not *how a hit is
computed*.

**We rejected real gravity because it broke the game.** Range is
`speed × √(2·drop/g)`. At Earth's 9.81 m/s² a fixed-strength throw carries 5.4 m
— but the longest throw the court can demand is 9.15 m, from the no-throw
boundary to a defender hugging their own back wall. Under real gravity that
defender is *literally unhittable*, so the optimal strategy becomes standing
still and every round times out as a draw. We run at 3.4 m/s², with the
derivation recorded next to the constant. The check is automated, so when a
later change doubled the ball radius — raising the resting height and shortening
every throw — the suite failed immediately instead of quietly shipping a
draw-only game.

**Input ordering is where "that felt wrong" bugs live.** Arms inputs arrive as
ordered *edges* and are replayed in receive order, never collapsed into a final
button state. That is what makes press-and-release inside a single tick throw
correctly, stops a late `cancel` from un-throwing a ball already in the air, and
stops a later `aim` from redirecting a throw that has already left.

### Verification without a test framework

The project deliberately banned automated tests. Instead the simulation ships a
**diagnostic runner** that drives the real engine through the real interface and
prints **442 observations**, each naming the specification clause it came from:

```
ok  pickup at exactly 1.2 m succeeds (inclusive)
ok  a ball crossing the character within one tick still hits (no tunnelling)
ok  two opposing hits within 1e-9 are a draw
ok  a release queued at the deadline does not launch
ok  the MVP's fixed strength still reaches a defender at their back wall
```

A deviation prints expected-versus-observed and exits non-zero. It reads as a
specification audit rather than a test suite — which is what a frozen-contract
project built by five people in parallel actually needed.

### Stack

Vue 3 · TypeScript · Vite · PlayCanvas (code-first, no editor project) ·
FastAPI · Pydantic v2 · pure-Python simulation · PostgreSQL 17 · SQLAlchemy 2 ·
Alembic · Docker Compose · Terraform · AWS EC2 · Caddy.

Five developers, 77 commits, and one frozen contract document that every
workstream implemented against in parallel.

## 5. User Experience & Design

**The whole onboarding is a URL and a code.** No install, no account, no pairing
screen. The lobby shows exactly what a new player needs: the room code, who is
connected, which seat they hold, their sensor permission state, and whether they
are ready. Nothing starts until all four phones are genuinely ready — the server
will not force-start an unready controller.

**The controller UI fits the physical act.** Arms gets a large, thumb-accessible
Hold button, chosen specifically so a player can keep their eyes on the screen
and their attention on their teammate rather than on their phone. Legs players
pocket the phone entirely and simply move.

**Failure states were designed, not patched on.** Accidental throws were treated
as a first-class risk from the start:

- Releasing inside a no-throw zone is a **safe cancellation** — the ball is set
  down and the phone is told *why*, instead of silently doing nothing.
- A limp release, a lost touch, a backgrounded tab or a dropped connection
  **cancels** rather than firing.
- Losing a required phone or the last screen resets cleanly to the lobby with a
  clear message, rather than leaving a half-dead match on screen.

**Feedback is legible at a glance.** Balls glow in the colour of the team
holding or throwing them, so possession reads instantly from across a room. The
screen shows the zone, the score, the phase and the server's own clock — the
display never decides an outcome, it only reports one, so every screen in the
room agrees.

**Presentation.** A stylised stadium with a crowd, an optional per-team
first-person view, and an elevated default camera that keeps both characters and
all four balls readable for spectators — because in practice the people watching
are as much the audience as the players.

---

## Try it

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
cd frontend && npm ci && npm run dev
```

Phones need HTTPS for motion and camera access — a trusted tunnel to port 5173
works for local play. Full instructions are in the repository README.

## Team

Richard · Ryan · Morteza · Tysen · Alan — Hack the Change 2026.
