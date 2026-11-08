**Tagline:** Two people, one dodgeball player. One runs, one throws, and you swap every round.

## Inspiration

Our prompt asked how technology could promote health, social connection and well-being in our communities. Most technology does the opposite. It's something you do sitting down, alone, looking at your own screen, even when your friends are in the room.

We thought about places that already do this well, like the YMCA and Activate. People go there to move, and they keep coming back because of who they move with. Dodgeball in a gym was never really about throwing. It was about the yelling: "behind you," "left, *left*."

So we set three rules for ourselves:

- **Moving can't be optional.** If you stop, your character stops.
- **You can't play alone.** Every action needs two people working together.
- **You have to be in the same room.** There's no online mode. The game happens between people standing next to each other.

## What it does

dodgewuh is 2v2 dodgeball where each team shares one character.

- **Legs** puts their phone in a pocket and jogs on the spot. While they jog, the character runs. When they stop, it stops.
- **Arms** holds a button to pick up a ball, points the phone to aim, and swings to throw. A harder swing makes a harder throw.

Neither of you can do anything alone. Arms can't reach a ball without Legs, and Legs can't hit anyone without Arms. So you talk, constantly.

A round lasts 60 seconds and one hit wins it. Best of three. The balls start next to the centre line, inside a no-throw zone, so you have to run in to grab one and get back out before you can throw. You can still be hit while you're in there.

After every round the teammates swap roles, so both people run and both people throw.

If there's a webcam pointed at you, a hit isn't automatic. The game drops into slow motion, draws the incoming ball over your camera feed, and gives you about a second to physically step out of its way. That doesn't work if the ball was thrown at your back.

To start, someone opens the page on a laptop and reads out a room code. Everyone types it into their phone. There's no app and no accounts. Once all four phones are calibrated, the match begins. Play with someone you know well, like a friend or a parent, because you'll be shouting at them.

## How we built it

The game runs on a server: plain Python, 60 steps a second. Phones send commands, not sensor readings: "move this way," "I let go of the button." The server decides what's legal and the screens just draw what they're handed, so two laptops in the same room can never show different scores.

Each room's game runs on its own worker server, so adding capacity means adding servers, not rewriting anything. Vue and PlayCanvas on the front, FastAPI and Postgres behind, MediaPipe for the webcam, all on AWS. Five of us built it at the same time from one spec document and one shared message format that every message had to pass.

The Legs controls took the longest. We spent a long time trying to work out where someone was standing from their phone before accepting that phones just can't do that. What they can do is notice you're jogging, and notice it fast. We recorded four people jogging, walking, turning, fidgeting and doing knee lifts with phones in their pockets, and tuned against those recordings. The detector now starts and stops within about a third of a second of your body, with no false starts across 25 recordings of people not jogging. That speed matters: if the character lags behind your body, the game stops feeling like exercise and starts feeling like a bad controller. The direction you're facing comes off a webcam. Together, the two work better than we expected.

## Challenges we ran into

- **Making exercise required, not optional.** It's easy to build a game where moving is a bonus and most people end up standing still. We left out every shortcut: Legs has no joystick and no touch controls. The only way to move is to jog.
- **Making teamwork required, not optional.** If one teammate could carry the team, the other would drift off. Splitting one character across two phones, and swapping roles every round, means neither of you can check out.
- **Real physics made the game unwinnable.** At Earth's gravity, a thrown ball hit the floor after about five metres. A defender who stood against their back wall could never be hit, and every round ended in a draw. We set gravity to 1.9 m/s². The ball still visibly drops, it just reaches.
- **Your thigh lies about which way you're facing.** A phone in a pocket twists up to 65° while you jog in place, so the gyroscope thinks you've turned. We lock direction while you're jogging, and afterwards only count fast, deliberate turns.
- **Phones get dropped.** They lock, they lose wifi, they end up in pockets. Any dropped connection pauses the match cleanly and gives you 30 seconds to rejoin, instead of leaving the game in a broken state.

## Accomplishments that we're proud of

### Health

- The movement is real exercise. There's no joystick hiding in there. Stop jogging and your character stops.
- Everyone does both kinds of movement. Swapping roles every round means you jog one round and throw the next, whether you're good at it or not.

### Social connection

- You can't play it quietly. By the first round everyone's shouting at their teammate.
- It only works with people in the same room. It's built to get people together in person, not to keep them apart.

### Well-being

- Nobody sits out. Lose a round and you're back in a few seconds later, in the other role.
- Skill gaps matter less. A fast runner paired with a good thrower, or a parent paired with a kid, both get something to do every round.
- It runs on a laptop and four phones people already own. No equipment, no install, no cost.

## What we learned

Accurate physics made the game worse, and we picked playable over realistic more than once. Building for phones means building for pockets, lock screens and dead wifi, because a button on a screen can't be dropped and a phone can. Five people need to agree on their interfaces before anyone writes code. It's boring, but it's the only reason the pieces fit together at the end.

The biggest lesson was that the social part had to be built into the rules, not left to hope. We didn't add a chat feature or a friends list. We made a character that two people have to share, and the talking happened on its own.

## What's next for dodgewuh

- **Seated play.** Jogging on the spot leaves people out, which is the exact thing we set out to fix. We want a wheelchair user and a standing player on the same team, swapping roles, without either one getting a special mode.
- **A real gym and a seniors' centre.** So far the only people who've played it are the people who built it. We want to know whether it gets people moving and talking who wouldn't have otherwise.
- **A whole gym at once.** Rooms already run on separate game servers. Next is adding servers automatically as rooms open, so a class of 30 can play seven or eight courts at the same time.
- **A view for whoever's running the room**, so a teacher or coach can rotate groups through a whole class.
- **Bigger teams.** Three or four people per character would push the talking even further.
