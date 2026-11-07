# Risks and minimal fallbacks

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

The plan aims for a working game, not a platform. Likelihood/impact are planning estimates. Each fallback preserves physical cooperation unless explicitly labelled a demo contingency.

| Risk | Likelihood / impact | Earliest experiment | Mitigation and cutoff | Fallback | Owner |
|---|---|---|---|---|---|
| iPhone permission or no samples | High / blocking | H0–1 HTTPS playground, tap permission | Request both APIs feature-detected in same user gesture; inspect null fields; do not await unrelated work before requests | Use tested phones/browser; fix TLS; no hidden keyboard substitute | Tysen |
| Legs directional detection noisy | High / high | H1 neutral and four-direction ten trials | Held portrait phone at waist, lean relative to neutral, dead zone; H3 cutoff | Larger body lean with discrete four-direction sectors; abandon step detection/pocket mode | Tysen |
| Release gesture unreliable | High / high | H2 twenty controlled swings/releases | Short motion window and threshold; aim clamp; cancel without motion | Fixed strength with motion-gated release; never release-only throwing | Morteza |
| Accidental throw on cancel | Medium / high | H2 pointercancel/background/disconnect | State machine: only pointerup + recent gesture may release | Explicit cancel drops ball; disable controller while stale | Morteza |
| Cloud latency/jitter | Medium / high | H4 p95 response over real network | Region near venue, 20 Hz messages, no queued snapshots | Latest snapshot display, lower cosmetic detail; use reliable Wi-Fi/hotspot | Alan + Ryan |
| AWS quota or credentials | Medium / blocking | H0 account/STSes and EC2 availability | Single small instance, no services beyond necessities | Local trusted HTTPS for development; prerecorded demo if public hosting unavailable (requirement remains unmet) | Alan |
| DNS/TLS issuance | Medium / blocking | H1 verify authoritative NS/A, ports | Correct GoDaddy zone, remove conflicting AAAA, start early | Local trusted CA while fixing public DNS; do not claim self-signed public TLS is sufficient | Alan |
| Screen divergence | Low / high | H6 two browser fixture readers, H10 live | Full immutable snapshots, shared epoch, same interpolation | Both render latest snapshot without interpolation | Ryan |
| Contract mismatch | Medium / blocking | H0 freeze, H2 fixture roundtrip | Shared good/bad fixture corpus, one schema owner | Pair and correct canonical contract atomically; no compatibility shim API | Alan |
| Alan overloaded | High / high | H2 workload check | No DB/accounts/QR; simple modules and one deployment script | Others provide tests, fixture conversions and paired reviews; Alan edits owned files | Ryan coordinator |
| Physics too complex | Medium / high | H2 pure swept-circle test | Flat 2D constant-speed balls | Keep straight shots, no bounce/spin mechanics/rigid bodies | Richard |
| Match transition bugs | Medium / high | H6 synthetic full match | Epoch reset, explicit ready after each swap | Return lobby on disconnect; no resume/host migration | Richard + Alan |
| Backend overload/slow consumer | Low / medium | H8 two rooms + slow screen | Max ten rooms, bounded queues, single mutation path | Lower room cap for demo, close slow viewer | Alan |
| Phone rotates/sleeps | High / medium | H2 rotate/lock and resume | Portrait instructions, recalibrate after rotation, keep foreground | Restart readiness; use tested orientation and phone placement | Tysen |
| Long draw chain | Medium / medium | H8 60-second timeout test | Clear aim/zone feedback and cooperative instructions | Presenter plays an intentional valid hit; never fabricate a score | Richard + Ryan |

Unverified externally: exact domain, DNS credentials, EC2 quota/AMI availability, venue internet, phone models/OS versions and measured motion quality. Docs establish API capabilities, not these conditions. No clinical health claims; challenge alignment is active play and communication using existing devices. No unsupported environmental savings claims.

Cut optional art, sound, QR codes, fancy animations, automated deployment pipelines and sophisticated gesture filters immediately. Do not spend time implementing multiple fallback modes before the primary lean/throw scheme is tested. Emergency touch/keyboard controls may be used only in a clearly labelled developer/debug or prerecorded walkthrough; they do not pass physical-play acceptance.
