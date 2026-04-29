import asyncio
import json
import time

import websockets

from simulation import Simulation
from visualizer import SimVisualizer

TICK_INTERVAL = 0.08

sim = Simulation()
visualizer = SimVisualizer(sim)

connected_clients: set = set()


async def handle_client(websocket):
    connected_clients.add(websocket)
    print(f"cliente conectado: {websocket.remote_address}")
    try:
        map_msg = sim.build_map_message()
        await websocket.send(json.dumps(map_msg))
        async for raw in websocket:
            await handle_command(raw, websocket)
    except websockets.exceptions.ConnectionClosedOK:
        print(f"cliente desconectado: {websocket.remote_address}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"conexion cerrada con error: {e}")
    except Exception as e:
        print(f"error en handle_client: {e}")
    finally:
        connected_clients.discard(websocket)


async def handle_command(raw: str, websocket):
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return

    tipo = msg.get("type")

    if tipo == "route":
        from_id = msg.get("from")
        to_id   = msg.get("to")
        #soporte de coordenadas de mapa ademas de ids de nodo
        if msg.get("from_xy"):
            fx, fy = msg["from_xy"]
            from_id = sim.nearest_node(fx, fy, main_only=True)
        if msg.get("to_xy"):
            tx, ty = msg["to_xy"]
            to_id = sim.nearest_node(tx, ty, main_only=True)
        if from_id and to_id:
            ok = sim.start_route(from_id, to_id)
            if not ok:
                await websocket.send(json.dumps({"type": "route_error", "msg": "No se encontró ruta"}))

    elif tipo == "cancel_route":
        sim.cancel_route()

    elif tipo == "override_light":
        light_id = msg.get("light_id")
        state = msg.get("state", "green")
        dur = msg.get("dur", 30)
        if light_id:
            sim.override_light(light_id, state, dur)

    else:
        print(f"comando desconocido: {tipo}")


async def broadcast_state():
    while True:
        start = time.monotonic()
        ev_done = sim.tick()

        if connected_clients:
            state_msg = sim.build_state_message(ev_done=ev_done)
            payload   = json.dumps(state_msg)
            await asyncio.gather(
                *[_safe_send(ws, payload) for ws in list(connected_clients)],
                return_exceptions=True
            )
            if ev_done:
                ev_done_msg = json.dumps({"type": "ev_done"})
                await asyncio.gather(
                    *[_safe_send(ws, ev_done_msg) for ws in list(connected_clients)],
                    return_exceptions=True
                )

        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0, TICK_INTERVAL - elapsed))


async def _safe_send(ws, payload: str):
    try:
        await ws.send(payload)
    except Exception:
        connected_clients.discard(ws)


async def main():
    print("iniciando simulacion de trafico...")
    print(f"nodos: {len(sim.nodes)}")
    print(f"aristas: {len(sim.edges)}")
    print(f"semaforos: {len(sim.lights)}")
    print(f"coches: {len(sim.cars)}")
    print(f"tick: {int(TICK_INTERVAL * 1000)}ms")
    print("servidor websocket en ws://localhost:8765")
    print("ventana pygame abierta (cierra con ESC o la X)")

    #lanzar ventana pygame en hilo daemon
    visualizer.start()

    async with websockets.serve(handle_client, "localhost", 8765):
        await broadcast_state()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        visualizer.stop()
        print("\nsimulacion detenida.")