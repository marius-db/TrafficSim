import asyncio
import json
import time

import websockets

from simulation import Simulation

# intervalo de tick de la simulacion en segundos (~80ms para latencia baja)
TICK_INTERVAL = 0.08

# instancia global de la simulacion (se crea una sola vez)
sim = Simulation()

# clientes websocket conectados actualmente
connected_clients: set = set()


async def handle_client(websocket):
    """gestiona la conexion de un cliente (modulo java)"""
    connected_clients.add(websocket)
    print(f"cliente conectado: {websocket.remote_address}")

    try:
        # enviar el mapa al conectar (una sola vez)
        map_msg = sim.build_map_message()
        await websocket.send(json.dumps(map_msg))

        # escuchar comandos del cliente
        async for raw in websocket:
            await handle_command(raw, websocket)

    except websockets.exceptions.ConnectionClosedOK:
        print(f"cliente desconectado limpiamente: {websocket.remote_address}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"conexion cerrada con error: {e}")
    except Exception as e:
        print(f"error en handle_client: {e}")
    finally:
        connected_clients.discard(websocket)


async def handle_command(raw: str, websocket):
    """procesa un comando recibido del modulo java"""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        print(f"mensaje invalido recibido: {raw[:80]}")
        return

    tipo = msg.get("type")

    if tipo == "route":
        from_id = msg.get("from")
        to_id   = msg.get("to")
        if from_id and to_id:
            ok = sim.start_route(from_id, to_id)
            if not ok:
                # notificar al cliente que no se encontro ruta
                await websocket.send(json.dumps({"type": "route_error", "msg": "No se encontró ruta"}))

    elif tipo == "cancel_route":
        sim.cancel_route()

    elif tipo == "override_light":
        light_id = msg.get("light_id")
        state    = msg.get("state", "ns_green")
        dur      = msg.get("dur", 30)
        if light_id:
            sim.override_light(light_id, state, dur)

    else:
        print(f"tipo de comando desconocido: {tipo}")


async def broadcast_state():
    """
    loop principal de la simulacion: avanza el estado y lo envia a todos los clientes.
    corre independientemente de las conexiones activas.
    """
    while True:
        start = time.monotonic()

        # avanzar simulacion
        ev_done = sim.tick()

        # enviar estado a todos los clientes conectados
        if connected_clients:
            state_msg = sim.build_state_message(ev_done=ev_done)
            payload   = json.dumps(state_msg)

            # enviar a todos en paralelo, ignorar clientes caidos
            await asyncio.gather(
                *[_safe_send(ws, payload) for ws in list(connected_clients)],
                return_exceptions=True
            )

            if ev_done:
                # notificar fin de ruta por separado tambien
                ev_done_msg = json.dumps({"type": "ev_done"})
                await asyncio.gather(
                    *[_safe_send(ws, ev_done_msg) for ws in list(connected_clients)],
                    return_exceptions=True
                )

        # calcular tiempo a esperar para mantener el intervalo constante
        elapsed = time.monotonic() - start
        wait    = max(0, TICK_INTERVAL - elapsed)
        await asyncio.sleep(wait)


async def _safe_send(ws, payload: str):
    """envia un mensaje ignorando silenciosamente conexiones cerradas"""
    try:
        await ws.send(payload)
    except Exception:
        connected_clients.discard(ws)


async def main():
    print("iniciando simulacion de trafico...")
    print(f"  nodos:    {len(sim.nodes)}")
    print(f"  aristas:  {len(sim.edges)}")
    print(f"  semaforos:{len(sim.lights)}")
    print(f"  tick:     {int(TICK_INTERVAL * 1000)}ms")
    print("servidor websocket en ws://localhost:8765")

    # correr el broadcast y el servidor websocket de forma concurrente
    async with websockets.serve(handle_client, "localhost", 8765):
        await broadcast_state()  # corre indefinidamente


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nsimulacion detenida.")
