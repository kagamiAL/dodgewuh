"""Manual diagnostic: fill phone seats with synthetic controllers that report ready.

Plan 05 allows synthetic clients in the remaining slots so one real phone can drive the
first vertical slice. They speak the real protocol, report ready whenever the room needs
it and send no gameplay input. This is a developer tool, not a test and not a control scheme.

    docker compose exec coordinator /app/.venv/bin/python -m app.devtools.synthetic_phones ABC234 --count 3

Phones take seats in join order (T1 Arms, T1 Legs, T2 Arms, T2 Legs), so three synthetic
phones joined first leave Team 2 Legs for the real phone.
"""
import argparse
import asyncio
import itertools
import json

import httpx
import websockets


def envelope(kind, payload):
    return json.dumps(dict(v=1, type=kind, payload=payload))


async def phone(base, origin, code, name):
    async with httpx.AsyncClient(base_url=base) as http:
        response = await http.post(f'/api/rooms/{code}/members', json=dict(name=name, device='phone'))
        if response.status_code != 201:
            print(f'{name}: join failed {response.status_code} {response.text}')
            return
        reg = response.json()
    me = reg['member_id']
    url = base.replace('http', 'ws', 1) + reg['ws_path']
    async with websockets.connect(url, origin=origin) as ws:
        await ws.send(envelope('session.hello', dict(token=reg['token'])))

        async def heartbeat():
            for nonce in itertools.count(1):
                await asyncio.sleep(5)
                await ws.send(envelope('session.ping', dict(nonce=nonce)))

        pinger = asyncio.create_task(heartbeat())
        room = state = None
        sent = None
        try:
            async for raw in ws:
                message = json.loads(raw)
                kind, payload = message['type'], message['payload']
                if kind == 'session.welcome':
                    room, state = payload['room'], payload['state']
                    seat = next((a for a in room['assignments'] if a['member_id'] == me), None)
                    print(f'{name}: connected as ' + (f"T{seat['team']} {seat['role']}" if seat else 'unassigned'))
                elif kind == 'room.updated':
                    room = payload['room']
                elif kind in ('state.snapshot', 'phase.changed'):
                    state = payload['state']
                elif kind == 'error':
                    print(f"{name}: {payload['code']} {payload['message']}")
                if kind not in ('session.welcome', 'room.updated') or room['phase'] not in ('lobby', 'role_switch'):
                    continue
                member = next(m for m in room['members'] if m['member_id'] == me)
                key = (state['epoch'], room['assignment_version'])
                if member['ready'] or key == sent or not any(a['member_id'] == me for a in room['assignments']):
                    continue
                sent = key
                await ws.send(envelope('controller.ready', dict(epoch=state['epoch'],
                    assignment_version=room['assignment_version'], ready=True,
                    permission='granted', calibrated=True)))
        finally:
            pinger.cancel()
    print(f'{name}: disconnected')


async def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('room_code')
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--base', default='http://localhost:8000')
    parser.add_argument('--origin', default='http://localhost:5173')
    args = parser.parse_args()
    # Join one at a time so seats are taken in a predictable order.
    tasks = []
    for n in range(1, args.count + 1):
        tasks.append(asyncio.create_task(phone(args.base, args.origin, args.room_code.upper(), f'Synthetic {n}')))
        await asyncio.sleep(0.5)
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
