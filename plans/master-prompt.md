# Hack the Change 2026 — Master Development Planning Agent

## 1. Your Role and Objective

You are acting as a **principal software architect, technical project manager, senior multiplayer game developer, and hackathon engineering lead**.

We are a team of five developers participating in Hack the Change 2026.

Our challenge statement is:

**How can we leverage technology to promote health, social connection, and well-being in our communities?**

We are building a cooperative, motion-controlled multiplayer dodgeball game.

Our technology stack and team assignments are finalized.

**Your task is NOT to implement the game. Your task is to create a complete, executable development blueprint consisting of multiple Markdown files that we will hand off to separate AI coding agents.**

Each coding agent must be able to independently implement its assigned subsystem while adhering to shared architectural contracts.

Your deliverables must support parallel development, minimize integration conflicts, and maximize our probability of delivering a functional hackathon MVP.

Do not produce a vague overview. Produce concrete engineering specifications and task assignments.

**Primary optimization goal: deliver a playable, demonstrable MVP as quickly and reliably as possible.**

We have approximately 24 hours for development and five human developers, supported by AI coding agents.

---

# 2. Project Overview

## Core Concept

We are building a **2v2 cooperative dodgeball game**.

Two human players jointly control one virtual dodgeball character.

There are two teams, four players, and two virtual characters.

Within each team:

- **Arms Player:** Controls aiming, ball pickup, and throwing using physical movements of a smartphone.
- **Legs Player:** Controls the character's locomotion and dodging using physical body movements detected by a smartphone.

Both players must coordinate their physical actions to succeed.

For example:

The Legs player moves toward a dodgeball while the Arms player prepares to grab it.

The Arms player then needs the Legs player to position the character appropriately before physically swinging their phone to throw.

Meanwhile, the opposing team is doing the same thing.

**Our central design principle is that physical activity and social cooperation are inseparable from the core gameplay.**

The game is not merely a traditional multiplayer game with motion controls added as a novelty.

The shared character must genuinely require two people to operate effectively.

At the end of every round, teammates switch their Arms and Legs roles.

## Intended Hackathon Value

Our game addresses the challenge through:

1. **Physical activity:** Players physically move their bodies to control game actions.
2. **Social connection:** Players must communicate and coordinate to control a shared character.
3. **Accessibility:** Users participate using smartphones and web browsers without installing native applications.
4. **Community engagement:** Players can create private rooms and invite others to play together.

Do not make unsupported claims that the game produces clinically validated health benefits.

---

# 3. Finalized Technology Stack

The following technology decisions are LOCKED.

| Component | Technology |
|---|---|
| 3D game engine | PlayCanvas Engine |
| Web application | Vue 3 |
| Frontend language | TypeScript |
| Frontend tooling | Vite |
| Backend framework | Python FastAPI |
| Real-time communication | Native WebSockets |
| Cloud provider | AWS |
| Infrastructure as Code | Terraform |
| Phone controller | Mobile web browser |
| Game display | Desktop/laptop web browser |
| Multiplayer | Cloud-hosted private rooms |
| Room joining | Room codes, with QR links if feasible |
| Matchmaking | None |
| Native mobile applications | None |

Use PlayCanvas Engine programmatically within the Vue/TypeScript application.

Prefer a code-first workflow using Git rather than depending on PlayCanvas Editor projects.

Choose supporting libraries when necessary, but avoid introducing unnecessary complexity.

**Do not replace FastAPI with Node.js, Express, or Socket.IO.**

Node.js may be used for frontend development tooling, but the backend must remain Python FastAPI.

Do not introduce Unity, Godot, Firebase, Kubernetes, microservices, or an unrelated game engine.

## Technical Verification Requirement

You must verify important technical assumptions before finalizing the plan, especially:

- PlayCanvas Engine integration with Vue and TypeScript
- iPhone Safari motion sensor access
- DeviceMotion and DeviceOrientation permissions
- HTTPS requirements for motion sensors
- WebSocket compatibility with the selected AWS infrastructure
- Multiple browser displays receiving synchronized game state
- Browser limitations around motion and touch input
- Deployment and Terraform compatibility

Distinguish verified facts from assumptions.

If internet or documentation access is unavailable, explicitly mark information requiring verification. Never invent framework APIs or AWS capabilities.

---

# 4. Finalized User Experience

## Game Connection Flow

Users visit a public website.

### Step 1 — Visit the Website

The user opens the website.

They can either:

- Create a new game
- Join an existing game using a join code

There is no matchmaking.

### Step 2 — Create Game

Creating a game generates a unique room code.

The room exists in the cloud-hosted FastAPI backend.

The user can share the room code with other participants.

### Step 3 — Join Game

A participant enters the room code.

After joining, they select their device type:

**Screen**

A screen displays the game.

Screens may be laptops, desktop computers, or other compatible devices.

Multiple screens may join the same room and should display the same synchronized match.

**Phone**

A phone is a physical game controller.

Each match requires exactly four phone players.

Phones are assigned to one of the following positions:

- Team 1 — Arms
- Team 1 — Legs
- Team 2 — Arms
- Team 2 — Legs

Recommend the simplest practical way to assign roles and teams.

### Step 4 — Lobby

The lobby displays:

- Room code
- Connected screens
- Connected phones
- Team assignments
- Arms and Legs assignments
- Controller readiness
- Motion sensor permission status

The match cannot start until four phone players have connected and at least one screen is available.

Recommend how to handle the host, readiness, and permission failures.

### Step 5 — Start Game

Once four phones have joined and the required controllers are ready, the host starts the game.

All connected screens display the match.

Phones become active physical controllers.

### Step 6 — Continue Playing

The game proceeds round by round.

After every round, teammates switch Arms and Legs roles.

All screens remain synchronized.

### Step 7 — Game End

The game displays the winner and final score.

Players may start another match in the same room.

The exact overall match-ending condition is not finalized. Recommend a simple MVP rule, such as first to five points.

---

# 5. Finalized Gameplay Specification

## Arena

The game uses a stylized 3D dodgeball arena rendered with PlayCanvas.

The arena contains:

- Two opposing player-controlled characters
- A central dividing line
- Two team halves
- Four dodgeballs initially positioned in the middle
- Clearly marked no-throw zones near the center
- Visible court boundaries

Players cannot cross into the opposing team's half.

Keep the geometry and physics simple.

An elevated or slightly isometric camera is preferred unless another camera angle is substantially better.

## Dodgeballs

At the beginning of each round:

- Four balls spawn near the middle of the court.
- Both teams attempt to acquire them.
- The Arms controller manages grabbing and throwing.
- The Legs controller moves the team's character into pickup range.

Recommend exact ball pickup distance, ownership rules, respawn behavior, and collision mechanics.

Balls should have easily understandable trajectories.

## No-Throw Zones

There are no-throw zones near the center of the court.

A player may enter their team's no-throw zone.

While inside:

- The character may still move.
- The character may pick up a ball.
- The character may be hit by an opponent's ball.
- The character cannot launch a throw.

The purpose of these zones is to create risk when collecting balls and prevent players from camping near the middle while throwing.

Define precise boundaries and determine what happens if the Arms player releases the Hold button while the character is inside a no-throw zone.

Ensure the rule is deterministic, understandable, and clearly communicated through the UI.

## Round System

Each round has a maximum duration of **60 seconds**.

A round ends immediately when either virtual character is hit by a valid opposing throw.

The team that successfully hits the opponent receives one point.

After the round:

1. The round ends.
2. The score updates.
3. The arena resets.
4. Balls respawn.
5. Teammates switch Arms and Legs roles.
6. Players receive a brief opportunity to reposition and recalibrate their phones.
7. The next round begins.

If the timer reaches zero without a hit, recommend treating the round as a draw with no points awarded.

Determine the simplest match victory condition.

All round state and scoring must remain consistent across screens.

## Arms Controller

The Arms player physically holds their smartphone.

The phone acts as their virtual throwing arm.

### Hold/Throw Interaction

**We have selected a large on-screen Hold button. This decision is final.**

Do not attempt to capture the physical iPhone volume buttons.

The intended interaction is:

1. The Legs player moves the character into pickup range of a dodgeball.
2. The Arms player presses and holds a large on-screen button.
3. The virtual character acquires the ball.
4. The Arms player aims using the phone's physical orientation or movement.
5. The Arms player performs a throwing motion with the phone.
6. Releasing the on-screen button launches the ball.

The throw should use motion-derived information to determine direction and, where practical, speed.

**Important technical constraint:** Smartphone gyroscopes and accelerometers cannot reliably provide exact absolute throwing velocity through naive sensor integration.

Design a practical, calibrated gesture-classification or gesture-estimation approach.

The controls should feel responsive and satisfying rather than attempting physically perfect simulation.

Evaluate whether throw strength should be fixed, classified into a few levels, or derived from measured motion.

Prioritize reliability over realism.

### Requirements

- Large, thumb-accessible Hold button
- iPhone Safari support
- Motion permission flow
- Calibration
- Aim detection
- Throw gesture recognition
- Throw direction
- Accidental throw prevention
- Safe cancellation
- Clear feedback
- No requirement to physically release the phone

Touch cancellation, browser focus loss, disconnects, and role switches must not cause accidental throws.

## Legs Controller

The Legs player uses physical body movement to move the character.

The phone may be placed in a pocket or held, depending on the recommended control scheme.

We have NOT finalized the exact movement gestures.

**Your responsibility is to choose the most reliable, intuitive, physically active control scheme for the hackathon MVP.**

Potential approaches include:

- Stepping or jogging in place
- Turning the body
- Tilting or leaning
- Recognizable movement gestures
- Combining step detection with orientation information

Do not assume a gyroscope measures physical position.

Do not rely on inaccurate indoor absolute displacement tracking.

Specify how the controls support moving around a two-dimensional court.

Determine whether the chosen controller requires a specific phone placement.

Develop a low-complexity calibration approach.

Provide a realistic fallback that still requires meaningful physical activity.

Do not replace the core physical movement with a traditional joystick unless absolutely necessary as an emergency demo fallback.

## Role Switching

At the end of every round:

- Arms becomes Legs.
- Legs becomes Arms.
- Each phone changes its controller interface.
- Sensor interpretation changes according to its new role.
- Necessary calibration is performed.
- The next round begins once both teams are ready or after a suitable transition process.

Role switching is a mandatory MVP feature.

---

# 6. Multiplayer and State Synchronization

All devices connect over the internet to a cloud-hosted FastAPI backend.

The backend uses WebSockets for real-time communication.

A room contains:

- Exactly two teams
- Exactly four phone controllers during gameplay
- One or more screen clients
- One active match
- Shared scores and round information

## Critical Architecture Decision

We want multiple screens to display the same match.

You must design a clear authoritative game-state model.

Our initial preference is:

- One designated screen acts as the authoritative game simulation host.
- It runs the PlayCanvas simulation.
- FastAPI manages rooms and relays inputs and game-state messages.
- Other screen clients render synchronized game state rather than independently simulating authoritative physics.
- Phones send motion-derived input events through FastAPI.

However, evaluate whether running a lightweight authoritative simulation in FastAPI would be simpler or more reliable for our exact requirements.

**Make a single architectural decision and justify it.**

Do not create multiple independent simulations that can disagree on collisions, timers, or scores.

Explicitly define:

- Who owns the official match state
- Who resolves collisions
- Who owns the 60-second timer
- Who awards points
- Who triggers role switching
- How screen clients synchronize
- What happens if the authoritative host disconnects
- How phones receive controller-role updates
- How room ownership and host permissions work

For the hackathon, terminating or safely resetting a room after authoritative host loss may be preferable to implementing complex host migration.

Favor simplicity and determinism.

## Networking Requirements

Use FastAPI WebSockets.

Specify:

- REST API endpoints
- WebSocket endpoint paths
- Event names
- JSON payload schemas
- Input sampling rates
- Input transmission rates
- Server-to-client broadcast rules
- State snapshot frequencies
- Reconnection behavior
- Heartbeats if necessary
- Player identity and session tokens
- Input validation
- Room expiration
- Error handling

Avoid unnecessary enterprise infrastructure.

---

# 7. AWS and Terraform Requirements

We have selected **AWS as our cloud provider and Terraform for infrastructure provisioning**.

These decisions are final.

Your job is to recommend the simplest practical AWS architecture that satisfies:

- Publicly accessible frontend
- HTTPS
- Cloud-hosted FastAPI backend
- WSS WebSocket connections
- Private room creation
- Multiple simultaneous devices
- Compatibility with iPhone Safari motion permissions
- Fast deployment
- Minimal operating costs
- Minimal infrastructure complexity
- Terraform-managed infrastructure

Possible AWS services may include:

- S3
- CloudFront
- EC2
- Route 53
- ACM
- Other appropriate AWS services

Do not automatically include all these services.

Select only the infrastructure we actually need.

Verify that your chosen hosting architecture properly supports long-lived WebSocket connections.

Investigate TLS certificates, domain requirements, DNS, and any challenges involved in obtaining public HTTPS/WSS endpoints within a hackathon.

If a custom domain is required, explicitly state that dependency and provide a practical fallback.

Prefer a single FastAPI backend instance with in-memory rooms for the MVP.

Do not introduce Redis, managed databases, Kubernetes, or distributed infrastructure unless clearly necessary.

## Terraform Deliverables

Specify:

- Terraform module/file structure
- AWS resources
- Required configuration variables
- Outputs
- Secrets handling
- Deployment commands
- How frontend and backend endpoints are configured
- How to deploy updates
- How to inspect logs
- How to troubleshoot common failures
- How to destroy resources after the hackathon

Do not hardcode credentials.

Do not commit AWS secrets or Terraform state containing sensitive values into the repository.

## Local Development

Cloud provisioning must not block all development.

Design a local development mode where the frontend, backend, and game can be developed independently.

Specify a clear transition from local development to cloud deployment.

Early testing on real iPhones must use a secure context where required.

Do not assume accessing a local development server over plain HTTP from an iPhone provides the required sensor access.

---

# 8. Finalized Development Teams

We have exactly five developers.

Their assignments are final.

## Team A — PlayCanvas Game

**Richard + Ryan**

Owns the shared visual game experience and gameplay simulation.

Primary responsibilities:

- PlayCanvas integration
- 3D arena
- Characters
- Ball objects
- Movement simulation
- Collision detection
- Throw trajectories
- Ball pickup mechanics
- No-throw zones
- Round timer
- Scoring
- Role-switch transitions
- Scoreboard and main game display
- Rendering synchronized game state for additional screens

The team may divide responsibilities further between Richard and Ryan.

Your job is to recommend the most efficient internal division.

## Team B — Motion Controllers

**Morteza + Tysen**

Owns the phone-controller experience and conversion of physical movement into game commands.

Primary responsibilities:

- Vue mobile controller UI
- Motion sensor permissions
- Sensor capture
- Sensor calibration
- Legs input processing
- Arms aiming
- Hold button
- Throw gesture detection
- Device compatibility
- Input normalization
- Motion event transmission
- Role-dependent controller behavior
- Real-device testing

The team may divide responsibilities further between Morteza and Tysen.

Your job is to recommend the most efficient internal division.

## Team C — Backend and Infrastructure

**Alan**

Owns the backend and infrastructure.

Primary responsibilities:

- FastAPI application
- Room creation
- Join codes
- QR join-link support
- Room membership
- Team/role assignment
- WebSocket connection management
- Event forwarding
- Screen/phone registration
- Room lifecycle
- AWS infrastructure
- Terraform
- Backend deployment
- Network connectivity
- Basic operational logging

**Alan is one person, while the other teams each contain two people.**

You must account for this workload imbalance.

Do not blindly assign Alan an unrealistic amount of work.

Design the system to minimize unnecessary backend complexity.

Identify work that Richard, Ryan, Morteza, or Tysen can assist with once their critical components are functional, without creating conflicting ownership.

The backend's primary job should be to connect clients and coordinate rooms, unless your architecture decision explicitly requires more functionality.

---

# 9. Team Optimization Requirement

Although the three team assignments are final, you have discretion to optimize work **within those teams**.

Your objective is not equalizing the number of assigned tasks.

Your objective is minimizing the overall time required to reach a functional MVP.

Consider:

- Critical-path dependencies
- Technical risk
- Work that can run in parallel
- Work that must be completed sequentially
- Integration complexity
- Workload imbalance
- Specialized responsibilities
- Testing effort
- Availability of AI coding agents

For each five-person assignment, define:

- Primary subsystem
- Secondary responsibilities
- Exact files owned
- APIs consumed
- APIs implemented
- Dependencies
- Acceptance criteria
- Testing requirements
- Integration responsibilities

Identify which developers should pair-program, review, or integrate together.

Specify the best handoff order.

**We want five humans organized into three collaborative teams, not five isolated developers building incompatible components.**

---

# 10. Required Planning Deliverables

You must create actual Markdown files in a `plans/` directory.

Do not output only a long chat response.

The planning artifacts are the primary deliverable.

Use the following minimum structure:

## Shared Planning Documents

**`plans/README.md`**

Master index containing:

- Project overview
- All plan files
- Team ownership
- Implementation order
- Major milestones
- How to use the plans with coding agents
- Dependencies between teams
- Immediate next actions

**`plans/01-architecture.md`**

Complete system architecture.

Must include:

- Architecture diagram using Mermaid
- PlayCanvas/Vue integration
- FastAPI responsibilities
- Cloud connectivity
- Authoritative game-state decision
- Multiplayer synchronization
- Device lifecycle
- Hosting assumptions
- Security boundaries
- Important architectural decisions and justifications

**`plans/02-game-specification.md`**

Complete gameplay specification.

Must include:

- Court layout
- Coordinate system
- Character movement
- Ball pickup
- Throwing
- No-throw zones
- Collision rules
- Scoring
- Timer
- Round state machine
- Role switching
- Match victory condition
- Gameplay constants
- Edge cases
- Deterministic behavior expected from the simulation

**`plans/03-api-contracts.md`**

Complete shared communication specifications.

This is one of the most important files.

Must include:

- REST endpoints
- WebSocket endpoints
- All event names
- JSON payload structures
- Event direction
- Sender and receiver
- TypeScript interface definitions
- Pydantic schema definitions or equivalent specification
- Input normalization
- Coordinate conventions
- Timestamp conventions
- Player identity
- Room state
- Game state
- Error events
- Reconnection behavior
- Event examples

Include complete examples for:

1. Creating a room
2. Joining as a screen
3. Joining as a phone
4. Assigning a team and role
5. Requesting sensor permissions
6. Reporting controller readiness
7. Sending Legs movement
8. Sending Arms aim data
9. Pressing Hold
10. Releasing Hold to throw
11. Updating ball ownership
12. Broadcasting game state
13. Registering a successful hit
14. Ending a round
15. Switching roles
16. Starting the next round
17. Disconnecting a player

Do not leave critical message formats for individual coding agents to invent.

**`plans/04-repository-structure.md`**

Monorepo architecture.

Specify:

- Directory tree
- Important source files
- Package and dependency choices
- Ownership boundaries
- Shared protocol files
- Local development commands
- Environment configuration
- Test locations
- Deployment files
- Terraform layout
- Build and run instructions

Prefer a straightforward repository that supports concurrent agent development.

**`plans/05-development-roadmap.md`**

Complete 24-hour execution plan.

Must include:

- Phases
- Milestones
- Dependencies
- Critical path
- Parallelizable tasks
- Estimated person-hours
- Integration windows
- Feature-freeze deadline
- Testing period
- Demo preparation
- Scope reduction triggers

Include a recommended schedule for:

- First 30 minutes
- First hour
- First two hours
- Hours 2–6
- Hours 6–12
- Hours 12–18
- Final six hours

Treat the 24-hour duration as an assumption if the actual available time has not been confirmed.

**`plans/06-integration-and-testing.md`**

Integration and testing strategy.

Must include:

- Shared interface contract verification
- Mock implementations
- Local component tests
- Real-device tests
- Four-phone multiplayer tests
- Multiple-screen synchronization tests
- Backend deployment smoke tests
- Full end-to-end test
- Common troubleshooting procedures
- Demo readiness checklist

**`plans/07-risks-and-fallbacks.md`**

Risk register.

For each risk, identify:

- Likelihood
- Impact
- Earliest validation point
- Mitigation
- Fallback
- Developer responsible

Include scope cuts that preserve the central cooperative physical-control mechanic.

**`plans/08-deployment-runbook.md`**

AWS and Terraform execution guide.

Must include:

- Selected AWS services
- Terraform structure
- Required configuration
- HTTPS/WSS setup
- Deploy commands
- Application environment variables
- Backend startup
- Frontend hosting
- Logging
- Troubleshooting
- Rollback
- Cleanup and cost considerations

**`plans/09-demo-plan.md`**

Hackathon presentation plan.

Must include:

- Two- to three-minute demonstration
- Setup requirements
- Presenter roles
- Physical activity demonstration
- Cooperation demonstration
- Role-switch demonstration
- Explanation of sustainability challenge alignment
- Live-demo failure fallback

---

# 11. Team-Specific Development Plans

In addition to the shared documents, produce three detailed team plans.

## `plans/teams/playcanvas-richard-ryan.md`

This is the implementation specification for Richard and Ryan.

Include:

- Team objective
- Exact subsystem scope
- Internal division between Richard and Ryan
- PlayCanvas scene structure
- Vue integration
- Game entities and components
- Character movement
- Ball physics and trajectories
- Court and collision geometry
- Game state machine
- Timer and scoring
- Role switching
- Main screen rendering
- Secondary-screen state rendering
- Required backend interfaces
- Required controller input interfaces
- Mock data and test harnesses
- Implementation order
- File ownership
- Task checklist
- Integration points
- Acceptance criteria
- Definition of done

Define how the team can begin game development before real sensor input or cloud WebSockets are ready.

For example, allow fake input commands to drive characters while preserving the same final input interface.

Do not build the game around a temporary control API that must later be discarded.

## `plans/teams/motion-morteza-tysen.md`

This is the implementation specification for Morteza and Tysen.

Include:

- Team objective
- Internal division between Morteza and Tysen
- Vue controller screens
- Sensor permission flow
- Device compatibility
- Arms controller
- Legs controller
- Large Hold button
- Sensor processing
- Calibration
- Gesture detection
- Input normalization
- Role switching
- Network event emission
- Connection feedback
- Sensor debugging UI
- Test procedures using real phones
- Required game interfaces
- Required backend interfaces
- File ownership
- Task checklist
- Integration points
- Acceptance criteria
- Definition of done

Prioritize testing physical controls on actual iPhones as early as possible.

The plan must include an isolated sensor playground that lets developers see raw and processed motion values without depending on the full game.

## `plans/teams/backend-alan.md`

This is the implementation specification for Alan.

Include:

- Team objective
- Complete backend scope
- FastAPI application structure
- REST endpoints
- WebSocket connection handling
- Room creation
- Join-code generation and validation
- Room membership
- Device registration
- Team/role assignments
- Host registration
- Screen clients
- Motion event relay
- Game-state broadcast
- Ready/start events
- Disconnect handling
- Room cleanup
- Terraform setup
- AWS deployment
- TLS configuration
- Backend health checks
- Local testing
- Cloud smoke tests
- Required frontend interfaces
- File ownership
- Task checklist
- Integration points
- Acceptance criteria
- Definition of done

Because Alan is working alone, distinguish absolutely necessary backend behavior from optional infrastructure features.

Identify backend capabilities that can be implemented with small, understandable Python modules rather than complex services.

---

# 12. Individual Coding-Agent Handoffs

Each human developer may use a separate AI coding agent.

Therefore, in addition to the three team plans, generate **five independently usable coding-agent briefs**.

Create:

- `plans/agents/richard.md`
- `plans/agents/ryan.md`
- `plans/agents/morteza.md`
- `plans/agents/tysen.md`
- `plans/agents/alan.md`

These are executable instructions for coding agents, not project summaries.

Each file must include:

### A. Agent Identity

State which developer the agent supports and which team it belongs to.

### B. Project Context

Provide enough relevant project context that an agent can begin without needing the entire planning conversation.

Reference shared planning documents.

### C. Exact Scope

Define the specific modules and features this agent must implement.

Include explicit exclusions.

### D. File Ownership

List files and directories the agent may modify.

Identify shared files it must not independently redesign.

### E. Dependencies

Define the libraries, services, API contracts, and neighboring modules the agent consumes.

### F. Implementation Instructions

Provide a concrete, ordered checklist of implementation tasks.

Tasks must be small enough to execute and verify individually.

### G. Interface Contracts

Reference the exact shared message schemas, types, endpoints, and component interfaces the agent must respect.

### H. Testing

List tests the agent must implement or perform.

Include mock inputs where necessary.

### I. Acceptance Criteria

Define observable behavior that proves the subsystem works.

### J. Definition of Done

Specify the conditions necessary before the agent's work can be considered ready for integration.

### K. Handoff Information

Identify what the agent must communicate to neighboring developers before integration.

### L. Final Agent Instructions

Explicitly tell the coding agent:

- Follow the shared architecture.
- Do not silently change API contracts.
- Do not modify files owned by another workstream without coordination.
- Do not replace locked technologies.
- Do not introduce unrelated infrastructure.
- Prefer functioning implementations over unnecessary abstractions.
- Run relevant tests.
- Report blockers and assumptions.
- Produce a concise summary of completed work and remaining integration tasks.

---

# 13. Shared Contracts Must Be Finalized Before Parallel Implementation

This is a critical requirement.

The five coding agents must not independently invent incompatible interfaces.

Before producing the individual agent briefs:

1. Decide the authoritative game-state architecture.
2. Define the room lifecycle.
3. Define the complete WebSocket protocol.
4. Define the game input schema.
5. Define character coordinate conventions.
6. Define round and match state machines.
7. Define role assignment and switching events.
8. Define screen synchronization.
9. Define the frontend/backend directory structure.
10. Establish module ownership.

Include an explicit **contract freeze milestone**.

After that milestone, coding agents should implement against the agreed contracts.

If a contract must change, specify how the team coordinates the change.

## Example Contract Considerations

For Legs input, determine whether the game receives:

- Normalized movement vectors
- Discrete movement actions
- Raw sensor data

Prefer processed game commands rather than making the backend interpret raw sensor streams.

For Arms input, determine how the game receives:

- Aim direction
- Hold state
- Throw event
- Estimated throwing strength

Clearly specify ranges and coordinate systems.

For screen synchronization, determine whether viewers receive:

- Authoritative snapshots
- Interpolated entity transforms
- Gameplay events
- A combination of these

Document the exact protocol.

---

# 14. Required Integration Strategy

Design the project so teams can work independently but integrate continuously.

We do not want to spend 18 hours building independent components and discover they cannot communicate.

Recommend a vertical-slice-first strategy.

## Suggested First Vertical Slice

The earliest meaningful end-to-end test should prove:

1. FastAPI is running.
2. A phone browser connects to the backend.
3. An iPhone grants motion sensor permission.
4. A movement input reaches FastAPI.
5. FastAPI forwards it to the PlayCanvas game.
6. A visible object moves in the game.
7. The system works across a real network.

This slice should use the final communication protocol wherever practical.

Define the earliest achievable deadline for this milestone.

## Subsequent Integration Milestones

Establish milestones for:

- One Legs controller moving one character
- One Arms controller aiming and throwing
- Two phones jointly controlling one character
- Four phones controlling two characters
- Ball pickup and hit detection
- Round scoring
- Role switching
- Multiple screen synchronization
- AWS-hosted end-to-end demonstration
- Full match completion

Every milestone must have a concrete test.

---

# 15. Mocking and Parallel Development

The game and phone-controller teams must not be blocked waiting for Alan's backend.

Design mock-compatible interfaces.

For example:

- The game team can inject synthetic movement and throw commands.
- The controller team can visualize processed inputs independently.
- The backend team can send and receive synthetic WebSocket traffic.
- Screen state synchronization can be tested using mock snapshots.

Mocks must implement the same shared contracts used by production components.

Do not allow each team to invent temporary message shapes that will require extensive rewriting.

Specify what is mocked, how, and when mocks are replaced with real components.

---

# 16. Technical Risk Priorities

Evaluate the following risks carefully.

## Risk 1 — iPhone Motion Sensors

Can a mobile Safari web app capture the necessary movement with sufficient responsiveness?

Validate early.

## Risk 2 — Legs Controls

Can we reliably map real physical movement to directional character movement without absolute position tracking?

This is a major design risk.

## Risk 3 — Throw Detection

Can swinging the phone while releasing the Hold button produce a consistent, controllable throw?

Do not assume perfect velocity estimation.

## Risk 4 — Real-Time Latency

Can motion commands travel through cloud FastAPI and still feel responsive?

Consider latency, jitter, and input update frequency.

## Risk 5 — AWS Deployment

Can the team deploy a publicly accessible HTTPS/WSS application quickly enough?

Avoid provisioning delays that block gameplay work.

## Risk 6 — Multi-Screen Consistency

Can multiple screen clients display the same match without diverging game states?

## Risk 7 — Integration

Can three teams and five coding agents produce compatible components?

## Risk 8 — Backend Workload

Can one developer handle the FastAPI backend and AWS/Terraform infrastructure within the hackathon?

Recommend the smallest viable implementation.

## Risk 9 — Gameplay Complexity

Will implementing detailed ball physics, pickup behavior, and collision detection overwhelm the MVP schedule?

Favor a simple, deterministic gameplay implementation.

For each risk, provide an early experiment and fallback.

---

# 17. Gameplay Ambiguities You Must Resolve

The core mechanics are decided, but certain values and edge cases remain open.

Do not block the planning process by asking us dozens of design questions.

Make reasonable recommendations and document them as explicit assumptions.

Resolve:

- Match victory condition
- Round draw behavior
- Court dimensions
- Character dimensions
- Player movement speed
- Ball pickup radius
- Throw range and speed
- Ball respawn rules
- Ball ownership conflicts
- No-throw zone dimensions
- Throw cancellation behavior
- Hit detection rules
- Whether a held ball can block an incoming throw
- Handling throws at the exact time the round ends
- Ready state after role switching
- Disconnected controller handling
- Multiple screen synchronization behavior
- Maximum room occupancy
- Game host permissions

Prefer the simplest sensible rule.

Do not introduce complex competitive mechanics merely because they are common in commercial games.

The MVP must feel understandable within seconds.

---

# 18. Development Timeline and Critical Path

Assume a 24-hour hackathon window.

We have five developers, potentially supported by five coding agents.

Provide realistic estimates.

Do not assume parallel coding eliminates integration time.

### Timeline Requirements

Your plan must identify:

- What must be decided before anyone codes
- What can begin immediately
- Which tasks are blocking others
- Which tasks can run in parallel
- When to merge initial implementations
- When to begin real-device testing
- When to complete AWS deployment
- When to freeze features
- When to focus exclusively on testing and polishing

Avoid scheduling all integration at the end.

Include fallback milestones.

For example, if physical directional movement remains unreliable after a specified time, recommend a simpler motion-based scheme.

If AWS deployment is delayed, local development should continue while infrastructure is debugged.

If multiple-screen synchronization becomes a risk, prioritize one functional screen before implementing additional viewers.

Define objective **go/no-go criteria** for each major milestone.

---

# 19. GitHub and Multi-Agent Coordination

Recommend a lightweight Git workflow.

Assume all developers work in one GitHub monorepo.

Include:

- Initial repository bootstrap
- Shared contracts committed first
- Branch naming
- Feature ownership
- Pull request workflow
- Integration branch or trunk-based strategy
- Conflict prevention
- Contract change approval
- Merge order
- Testing before merge

Do not prescribe unnecessary enterprise processes.

The primary goal is to let independent AI coding agents make progress without overwriting each other's work.

Assign ownership of shared files and integration decisions.

Explicitly identify which person should act as the final integration coordinator and why.

---

# 20. Acceptance Criteria for the Entire MVP

The project is not complete until the following end-to-end scenario works:

1. A user visits the publicly hosted website.
2. The user creates a room.
3. The application generates a room code.
4. At least one screen joins the room.
5. Four phones join using the room code.
6. The phones receive team and role assignments.
7. Required motion permissions are granted.
8. The game starts.
9. Each team jointly controls one virtual character.
10. Legs movements physically control character movement.
11. Arms players acquire balls using the large Hold button.
12. Arms players aim and throw using physical phone movements.
13. Four dodgeballs are initially available near the center.
14. No-throw zones prevent throws but do not prevent hits.
15. A successful hit immediately ends the round and awards a point.
16. A round ends after 60 seconds if no hit occurs.
17. Teammates switch roles after each round.
18. The next round begins with reset game state.
19. All connected screens display consistent match state.
20. The match eventually produces a winner.
21. The system works using cloud-hosted FastAPI.
22. The application can be accessed over HTTPS with secure WebSocket connectivity.
23. Four real phones can participate in the same match.
24. The entire experience is demonstrable without native app installation.

A task is not complete merely because its code compiles.

It must satisfy observable acceptance criteria.

---

# 21. Final Output Instructions

**Create the actual Markdown files in the repository.**

Do not stop after describing which files should exist.

If you have filesystem access, write all files under `plans/`.

If filesystem access is unavailable, output complete Markdown content in clearly labeled file sections so the documents can be saved without additional planning.

Your final deliverables must include:

### Shared Documents

- `plans/README.md`
- `plans/01-architecture.md`
- `plans/02-game-specification.md`
- `plans/03-api-contracts.md`
- `plans/04-repository-structure.md`
- `plans/05-development-roadmap.md`
- `plans/06-integration-and-testing.md`
- `plans/07-risks-and-fallbacks.md`
- `plans/08-deployment-runbook.md`
- `plans/09-demo-plan.md`

### Team Plans

- `plans/teams/playcanvas-richard-ryan.md`
- `plans/teams/motion-morteza-tysen.md`
- `plans/teams/backend-alan.md`

### Individual Coding-Agent Briefs

- `plans/agents/richard.md`
- `plans/agents/ryan.md`
- `plans/agents/morteza.md`
- `plans/agents/tysen.md`
- `plans/agents/alan.md`

You may create additional supporting documents if they materially improve execution.

## Document Quality Requirements

Every document must be:

- Technically concrete
- Internally consistent
- Actionable
- Clearly scoped
- Linked to dependencies
- Compatible with the other documents
- Appropriate for a hackathon
- Free of unnecessary architectural complexity

Avoid duplicated or contradictory specifications.

Shared technical contracts must have one authoritative source.

Team and agent documents should reference those contracts instead of independently redefining them.

## Final Verification

Before finishing, audit your plans.

Confirm:

1. All locked technologies are respected.
2. All gameplay requirements are represented.
3. Every MVP feature has an owner.
4. Every required interface is defined.
5. No two agents have conflicting file ownership.
6. No subsystem depends on an undefined event or API.
7. The backend workload is realistic for Alan.
8. The teams can begin implementation independently.
9. Mock interfaces enable parallel work.
10. All integration milestones have acceptance tests.
11. The deployment plan supports HTTPS and WSS.
12. The complete MVP can plausibly be delivered within the hackathon timeframe.
13. Every coding-agent brief is detailed enough to execute.
14. There are no contradictions between architecture, gameplay rules, backend contracts, and team plans.

If you find inconsistencies, correct the planning documents before finalizing.

## Final Response

After creating the Markdown files, provide a concise execution summary containing:

- The selected architecture
- The final division of work among Richard, Ryan, Morteza, Tysen, and Alan
- The most important technical risks
- The critical path
- The first integration milestone
- Exactly what each developer should do in the first 60 minutes
- The order in which we should distribute the documents to coding agents

**Do not begin implementing the game. Do not produce application source code. Your sole deliverable is a complete, implementation-ready planning package for five developers and their coding agents.**

**Make the engineering decisions necessary to produce a coherent plan. Optimize for shipping a working multiplayer dodgeball game—not designing an unnecessarily sophisticated system.**
