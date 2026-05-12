# TrafficSim

> 🇪🇸 [Versión en español](README.es.md)

Traffic simulation server built for [CentralCore](https://github.com/marius-db/CentralCore). Generates a procedural city with cars, traffic lights, and an emergency vehicle system, then streams the state in real time over WebSocket so CentralCore's traffic module can visualize and control it.

It also opens a local pygame window so you can watch the simulation directly without needing CentralCore at all.

---

## What it does

The simulation runs a procedural city on a graph of intersections and roads. Up to 500 cars navigate through it using Dijkstra, respecting traffic lights and keeping a gap from the car ahead. Road density is calculated per edge every tick and fed back into routing so cars naturally avoid congested streets.

Traffic lights run on a standard NS/EW phase cycle with randomized offsets per intersection so they don't all sync up.

When CentralCore sends an emergency vehicle route, an EV spawns and follows it at higher speed. Nearby cars pull over, and the intersections ahead get preempted to clear the way. When the route is done, everything returns to normal.

The server sends two types of messages:
- `map` once on connect: the full city graph (nodes, edges, lights)
- `state` every 80ms: all car positions, light states, traffic densities, and EV state if active

CentralCore can send three types of commands back:
- `route`: start an emergency vehicle route between two node IDs or map coordinates
- `cancel_route`: cancel the active EV route
- `override_light`: force a specific traffic light to a state for a set duration

---

## Requirements

- Python 3.11 or newer
- pip

Install dependencies:

```
pip install websockets pygame fastapi
```

pygame is optional. If it's not installed the server still runs fine, it just won't open the visual window.

---

## Running it

```
python main.py
```

That's it. The server starts on `ws://localhost:8765` and the pygame window opens alongside it.

Controls for the pygame window:

| Input | Action |
|-------|--------|
| Scroll | Zoom in/out |
| Left click + drag | Pan |
| R | Reset zoom and position |
| ESC or close button | Quit |

---

## Project structure

```
TrafficSim/
├── main.py          - entry point, WebSocket server, command handling
├── simulation.py    - core simulation: cars, lights, EV, tick loop
├── city.py          - procedural city generation and Dijkstra routing
└── visualizer.py    - pygame window running on a separate daemon thread
```

---

## How the city is generated

The city is built from a fixed seed so it's always the same layout. A 9x7 grid of main intersections gets placed with intentionally uneven spacing so it doesn't look like a perfect grid. About 12% of horizontal and vertical connections are dropped to create natural gaps, and around 20% of grid blocks get a diagonal shortcut.

Secondary roads are generated between nearby main intersections with 1 to 3 intermediate nodes each, offset perpendicular to the direct line so they curve slightly. Each secondary road gets a unique street name drawn from a pool.

The result is a city that looks lived-in rather than generated, with wide main avenues, narrower side streets, and diagonal cuts that create shortcuts across the grid.

---

## How traffic works

Each car gets a random destination and uses Dijkstra to find a route. Cars have a small random speed variance (±12%) so they don't all move identically. They maintain a minimum gap from the car ahead and slow down progressively as the gap closes rather than stopping suddenly.

At intersections, cars check the traffic light for their approach direction and stop if it's red. The light check activates within the last 15% of the road segment or within 50 world units of the intersection, whichever is longer.

Every 8 seconds the routing adjacency is rebuilt using current traffic densities as edge costs, so cars naturally reroute away from congested areas without any explicit logic for it.

---

## How the emergency vehicle works

When a route is sent, an EV spawns at the start node and follows the Dijkstra path at 130 units/second (vs 88 for cars on main roads). As it moves, intersections within 220 units ahead get preempted: the light in the EV's approach direction goes green and the others go red for about 15 seconds. Cars within 160 units pull over to the side and slow to 15% of normal speed until the EV passes.

When the EV reaches its destination, the server sends an `ev_done` message and the EV is removed. All overridden lights expire on their own timers.

---

## WebSocket protocol

### Messages sent by the server

**map** (sent once on connect)
```json
{
  "type": "map",
  "nodes": [{"id": "n1", "x": 55.0, "y": 60.0, "main": true}, ...],
  "edges": [{"id": "e1", "from": "n1", "to": "n2", "lanes": 3, "main": true, "name": "Gran Via"}, ...],
  "lights": [{"id": "l1", "node": "n1", "dir": "N"}, ...]
}
```

**state** (sent every ~80ms)
```json
{
  "type": "state",
  "cars": [{"id": "c1", "x": 120.5, "y": 340.2, "na": "n3", "nb": "n4", "p": 0.42, "lane": 1}, ...],
  "lights": [{"id": "l1", "node": "n1", "dir": "N", "state": "green", "t": 11}, ...],
  "traffic": [{"id": "e1", "density": 0.34}, ...],
  "ev": null
}
```

**ev_done** (sent when EV reaches destination)
```json
{"type": "ev_done"}
```

### Commands sent by the client

**route**
```json
{"type": "route", "from": "n5", "to": "n42"}
```
or by map coordinates (snaps to nearest main node):
```json
{"type": "route", "from_xy": [120.0, 340.0], "to_xy": [800.0, 600.0]}
```

**cancel_route**
```json
{"type": "cancel_route"}
```

**override_light**
```json
{"type": "override_light", "light_id": "l12", "state": "green", "dur": 30}
```

---

## Notes

The simulation is self-contained and has no dependency on CentralCore. You can connect any WebSocket client to it. The pygame window and the WebSocket server run concurrently using asyncio and a daemon thread, so closing the pygame window doesn't stop the server.

The city seed is fixed at 123 in `city.py`. Changing it generates a completely different city layout.