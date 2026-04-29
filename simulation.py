import math
import random
import time

from city import build_city, build_adjacency, dijkstra

CAR_SPEED_MAIN = 88.0
CAR_SPEED_SIDE = 46.0
EV_SPEED = 120.0

MAX_CARS = 300

LIGHT_GREEN_DUR = 14.0
LIGHT_YELLOW_DUR = 3.0
LIGHT_ALLRED_DUR = 1.5

LIGHT_STOP_DIST = 0.88

MAIN_DEST_BIAS = 0.65

#minimum gap between cars on same edge, as fraction of edge progress
#cars will slow down to maintain this gap behind the car ahead
CAR_MIN_GAP = 0.045

#distance (in world units) at which a car starts pulling over for the EV
EV_YIELD_RADIUS = 180.0
#how much cars slow down when yielding (fraction of normal speed)
EV_YIELD_SPEED_FACTOR = 0.18


class TrafficLight:
    def __init__(self, lid, node_id, direction, phase_offset=0.0):
        self.id = lid
        self.node_id = node_id
        self.dir = direction
        self._phase = "red"
        self._timer = 0.0
        self.override = None
        self._state = "red"
        self._boot_offset = phase_offset

    def tick(self, dt):
        if self.override is not None:
            state, rem = self.override
            rem -= dt
            self._state = state
            self.override = (state, rem) if rem > 0 else None
            return
        self._timer -= dt

    def set_phase(self, phase, duration):
        self._phase = phase
        self._timer = duration
        self._state = phase

    def get_state(self):
        if self.override is not None:
            return self.override[0]
        return self._state

    def get_timer(self):
        if self.override is not None:
            return int(self.override[1])
        return max(0, int(self._timer))

    def set_override(self, state, duration):
        self.override = (state, float(duration))

    def phase_expired(self):
        return self._timer <= 0 and self.override is None


class IntersectionController:
    PHASES = [
        ("NS_green", LIGHT_GREEN_DUR),
        ("NS_yellow", LIGHT_YELLOW_DUR),
        ("allred_1", LIGHT_ALLRED_DUR),
        ("EW_green", LIGHT_GREEN_DUR),
        ("EW_yellow", LIGHT_YELLOW_DUR),
        ("allred_2", LIGHT_ALLRED_DUR),
    ]

    def __init__(self, node_id, lights_by_dir, phase_offset=0.0):
        self.node_id = node_id
        self.lights = lights_by_dir
        self._phase_idx = 0
        self._phase_timer = 0.0

        total_cycle = sum(d for _, d in self.PHASES)
        effective_offset = phase_offset % total_cycle

        acc = 0.0
        for i, (pname, pdur) in enumerate(self.PHASES):
            if acc + pdur > effective_offset:
                self._phase_idx = i
                self._phase_timer = (acc + pdur) - effective_offset
                break
            acc += pdur

        self._apply_phase(self.PHASES[self._phase_idx][0])

    def _apply_phase(self, phase_name):
        for d, lt in self.lights.items():
            if phase_name == "NS_green":
                lt.set_phase("green" if d in ("N", "S") else "red", LIGHT_GREEN_DUR)
            elif phase_name == "NS_yellow":
                lt.set_phase("yellow" if d in ("N", "S") else "red", LIGHT_YELLOW_DUR)
            elif phase_name in ("allred_1", "allred_2"):
                lt.set_phase("red", LIGHT_ALLRED_DUR)
            elif phase_name == "EW_green":
                lt.set_phase("green" if d in ("E", "W") else "red", LIGHT_GREEN_DUR)
            elif phase_name == "EW_yellow":
                lt.set_phase("yellow" if d in ("E", "W") else "red", LIGHT_YELLOW_DUR)

    def tick(self, dt):
        for lt in self.lights.values():
            lt.tick(dt)

        self._phase_timer -= dt
        if self._phase_timer <= 0:
            self._phase_idx = (self._phase_idx + 1) % len(self.PHASES)
            pname, pdur = self.PHASES[self._phase_idx]
            self._phase_timer = pdur
            self._apply_phase(pname)

    def is_green_for_direction(self, approach_dir):
        lt = self.lights.get(approach_dir)
        if lt is None:
            return True
        return lt.get_state() == "green"


def approach_direction(from_node, to_node):
    dx = to_node["x"] - from_node["x"]
    dy = to_node["y"] - from_node["y"]
    if abs(dx) >= abs(dy):
        return "W" if dx > 0 else "E"
    else:
        return "N" if dy > 0 else "S"


class Car:
    _id_counter = 0

    def __init__(self, node_a_id, node_b_id, node_map, edge_map, adj, main_nodes):
        Car._id_counter += 1
        self.id = f"c{Car._id_counter}"
        self.node_a = node_a_id
        self.node_b = node_b_id
        self.progress = 0.0
        self.waiting = False
        self.yielding_to_ev = False

        self.node_map = node_map
        self.edge_map = edge_map
        self.adj = adj
        self.main_nodes = main_nodes

        self.route = []
        self.route_idx = 0
        self.lane = random.randint(1, 2)

        edge = edge_map.get((node_a_id, node_b_id))
        self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE
        self._base_speed = self.speed

    def set_route(self, route):
        self.route = route
        self.route_idx = 0
        if len(route) >= 2:
            self.node_a = route[0]
            self.node_b = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE
            self._base_speed = self.speed

    def reroute(self):
        #pick a new random destination and reroute from current position
        dest = random.choice(self.main_nodes)
        route = dijkstra(self.adj, self.node_b, dest)
        if len(route) >= 2:
            self.route = route
            self.route_idx = 0
            self.node_a = route[0]
            self.node_b = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE
            self._base_speed = self.speed

    def get_xy(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 0.0, 0.0
        x = na["x"] + (nb["x"] - na["x"]) * self.progress
        y = na["y"] + (nb["y"] - na["y"]) * self.progress
        return x, y

    def edge_length(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 1.0
        return max(1.0, math.hypot(nb["x"] - na["x"], nb["y"] - na["y"]))

    def to_dict(self):
        x, y = self.get_xy()
        return {
            "id": self.id,
            "x": round(x, 2),
            "y": round(y, 2),
            "na": self.node_a,
            "nb": self.node_b,
            "p": round(self.progress, 4),
            "lane": self.lane,
        }


class EmergencyVehicle:
    def __init__(self, from_id, to_id, route, node_map):
        self.from_id = from_id
        self.to_id = to_id
        self.route = route
        self.node_map = node_map
        self.route_idx = 0
        self.node_a = route[0]
        self.node_b = route[1] if len(route) > 1 else route[0]
        self.progress = 0.0
        self.done = False

    def edge_length(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 1.0
        return max(1.0, math.hypot(nb["x"] - na["x"], nb["y"] - na["y"]))

    def get_xy(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 0.0, 0.0
        x = na["x"] + (nb["x"] - na["x"]) * self.progress
        y = na["y"] + (nb["y"] - na["y"]) * self.progress
        return x, y

    def next_node(self):
        if self.route_idx + 1 < len(self.route):
            return self.route[self.route_idx + 1]
        return self.to_id

    def tick(self, dt, cars_on_edge, edge_length):
        if self.done:
            return

        #find the closest car ahead on same edge that hasn't yielded out of the way
        #ev still can't teleport through a solid wall of unyielded cars
        ahead_progress = None
        for car in cars_on_edge:
            if car.progress > self.progress and not car.yielding_to_ev:
                if ahead_progress is None or car.progress < ahead_progress:
                    ahead_progress = car.progress

        #if something is blocking ahead that hasn't moved yet, slow down slightly
        #but ev is aggressive so gap is smaller than for normal cars
        EV_GAP = CAR_MIN_GAP * 0.5
        if ahead_progress is not None and (ahead_progress - self.progress) < EV_GAP:
            speed = EV_SPEED * 0.3
        else:
            speed = EV_SPEED

        self.progress += (speed * dt) / edge_length
        if self.progress >= 1.0:
            self.progress = 0.0
            self.route_idx += 1
            if self.route_idx >= len(self.route) - 1:
                self.done = True
                return
            self.node_a = self.route[self.route_idx]
            self.node_b = self.route[self.route_idx + 1]

    def to_dict(self):
        x, y = self.get_xy()
        return {
            "id": "ev1",
            "x": round(x, 2),
            "y": round(y, 2),
            "next": self.next_node(),
            "route": self.route,
        }


class Simulation:
    def __init__(self):
        nodes, edges, light_defs = build_city()

        self.nodes = nodes
        self.edges = edges
        self.node_map = {n["id"]: n for n in nodes}
        self.edge_map = {(e["from"], e["to"]): e for e in edges}
        self.adj = build_adjacency(nodes, edges)

        self.main_nodes = [n["id"] for n in nodes if n["main"]]
        self.border_nodes = self._find_border_nodes()

        self.lights: dict[str, TrafficLight] = {}
        self.intersections: dict[str, IntersectionController] = {}
        self._build_intersections(light_defs)

        self.cars: list[Car] = []
        self.ev: EmergencyVehicle | None = None

        self.last_tick = time.time()

        while len(self.cars) < MAX_CARS:
            self._spawn_car()

    def _build_intersections(self, light_defs):
        rng = random.Random(99)
        total_cycle = sum(d for _, d in IntersectionController.PHASES)

        by_node: dict[str, dict] = {}
        for ld in light_defs:
            nid = ld["node"]
            d = ld["dir"]
            lt = TrafficLight(ld["id"], nid, d)
            self.lights[ld["id"]] = lt
            if nid not in by_node:
                by_node[nid] = {}
            by_node[nid][d] = lt

        for node_id, lights_by_dir in by_node.items():
            offset = rng.uniform(0, total_cycle)
            ctrl = IntersectionController(node_id, lights_by_dir, phase_offset=offset)
            self.intersections[node_id] = ctrl

    def _find_border_nodes(self):
        from city import CITY_W, CITY_H
        border = [n["id"] for n in self.nodes
                  if n["x"] < 130 or n["x"] > CITY_W - 130
                  or n["y"] < 130 or n["y"] > CITY_H - 130]
        return border if len(border) >= 4 else self.main_nodes[:]

    def _random_destination(self, exclude_id):
        pool = self.main_nodes if random.random() < MAIN_DEST_BIAS else [n["id"] for n in self.nodes]
        pool = [nid for nid in pool if nid != exclude_id]
        return random.choice(pool) if pool else exclude_id

    def _spawn_car(self):
        spawn = random.choice(self.border_nodes)
        dest = self._random_destination(spawn)
        route = dijkstra(self.adj, spawn, dest)
        if len(route) < 2:
            return
        car = Car(route[0], route[1], self.node_map, self.edge_map, self.adj, self.main_nodes)
        car.set_route(route)
        self.cars.append(car)

    def _is_light_blocking(self, car: Car) -> bool:
        if car.progress < LIGHT_STOP_DIST:
            return False
        ctrl = self.intersections.get(car.node_b)
        if ctrl is None:
            return False
        na = self.node_map.get(car.node_a)
        nb = self.node_map.get(car.node_b)
        if na is None or nb is None:
            return False
        direction = approach_direction(na, nb)
        return not ctrl.is_green_for_direction(direction)

    def _build_edge_index(self):
        #group cars by which edge they're currently on for quick neighbor lookup
        idx: dict[tuple, list] = {}
        for car in self.cars:
            key = (car.node_a, car.node_b)
            if key not in idx:
                idx[key] = []
            idx[key].append(car)
        return idx

    def _check_ev_yield(self, car: Car) -> bool:
        #car is within yield radius of the EV and the EV is heading toward the same node
        if self.ev is None:
            return False
        ex, ey = self.ev.get_xy()
        cx, cy = car.get_xy()
        dist = math.hypot(cx - ex, cy - ey)
        if dist > EV_YIELD_RADIUS:
            return False
        #only yield if EV is approaching from behind or from a nearby parallel path
        #simple check: EV is on the same edge or an adjacent one and is close
        ev_edge = (self.ev.node_a, self.ev.node_b)
        car_edge = (car.node_a, car.node_b)
        if ev_edge == car_edge or self.ev.node_b == car.node_b:
            return True
        return dist < EV_YIELD_RADIUS * 0.55

    def tick(self):
        now = time.time()
        dt = min(now - self.last_tick, 0.15)
        self.last_tick = now

        for ctrl in self.intersections.values():
            ctrl.tick(dt)

        edge_idx = self._build_edge_index()

        for car in self.cars:
            #check if EV is nearby and car should yield
            car.yielding_to_ev = self._check_ev_yield(car)

            if car.yielding_to_ev:
                car.waiting = False
                #pull over: move at reduced speed and stay near the edge
                yield_speed = car._base_speed * EV_YIELD_SPEED_FACTOR
                car.progress += (yield_speed * dt) / car.edge_length()
                #clamp at 95% so the car parks near the end of the edge and waits
                if car.progress >= 0.95:
                    car.progress = 0.95
                continue

            #traffic light check
            if self._is_light_blocking(car):
                car.waiting = True
                continue

            #car-following: find the closest car ahead on the same edge
            same_edge = edge_idx.get((car.node_a, car.node_b), [])
            ahead_progress = None
            for other in same_edge:
                if other is car:
                    continue
                if other.progress > car.progress:
                    if ahead_progress is None or other.progress < ahead_progress:
                        ahead_progress = other.progress

            gap = (ahead_progress - car.progress) if ahead_progress is not None else 1.0

            if gap <= CAR_MIN_GAP:
                #fully stopped, too close to car ahead
                car.waiting = True
                continue
            elif gap < CAR_MIN_GAP * 2.5:
                #slow down proportionally as gap shrinks
                t = (gap - CAR_MIN_GAP) / (CAR_MIN_GAP * 1.5)
                effective_speed = car._base_speed * max(0.08, t)
            else:
                effective_speed = car._base_speed

            car.waiting = False
            car.progress += (effective_speed * dt) / car.edge_length()

            if car.progress >= 1.0:
                car.progress = 0.0
                car.route_idx += 1
                if car.route_idx >= len(car.route) - 1:
                    #reached destination: pick a new one and keep driving
                    car.reroute()
                    continue
                car.node_a = car.route[car.route_idx]
                car.node_b = car.route[car.route_idx + 1]
                edge = self.edge_map.get((car.node_a, car.node_b))
                car.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE
                car._base_speed = car.speed
                #update edge index for next cars processed this tick
                key = (car.node_a, car.node_b)
                if key not in edge_idx:
                    edge_idx[key] = []
                edge_idx[key].append(car)

        ev_done = False
        if self.ev is not None:
            ev_edge_cars = edge_idx.get((self.ev.node_a, self.ev.node_b), [])
            self.ev.tick(dt, ev_edge_cars, self.ev.edge_length())
            if self.ev.done:
                ev_done = True
                self.ev = None

        return ev_done

    def start_route(self, from_id, to_id):
        #if a secondary node id was passed directly, snap to nearest main node
        def to_main(nid):
            n = self.node_map.get(nid)
            if n and not n["main"]:
                return self.nearest_node(n["x"], n["y"], main_only=True)
            return nid
        from_id = to_main(from_id)
        to_id = to_main(to_id)
        route = dijkstra(self.adj, from_id, to_id)
        if len(route) < 2:
            print(f"no se encontro ruta de {from_id} a {to_id}")
            return False
        self.ev = EmergencyVehicle(from_id, to_id, route, self.node_map)
        print(f"ruta de emergencia: {' -> '.join(route)}")
        return True

    def cancel_route(self):
        self.ev = None

    def override_light(self, light_id, state, duration):
        lt = self.lights.get(light_id)
        if lt: lt.set_override(state, duration)

    def nearest_node(self, x, y, main_only=False):
        best_id, best_d = None, float("inf")
        for n in self.nodes:
            if main_only and not n["main"]:
                continue
            d = math.hypot(n["x"] - x, n["y"] - y)
            if d < best_d:
                best_d, best_id = d, n["id"]
        return best_id

    def compute_densities(self):
        #density based on average speed on each edge, not raw car count
        #a road is "congested" when cars are slow, not just when there are many cars
        speed_sums: dict[str, float] = {}
        speed_counts: dict[str, int] = {}
        max_speeds: dict[str, float] = {}

        for e in self.edges:
            speed_sums[e["id"]] = 0.0
            speed_counts[e["id"]] = 0
            max_speeds[e["id"]] = CAR_SPEED_MAIN if e.get("main") else CAR_SPEED_SIDE

        edge_id_map = {(e["from"], e["to"]): e["id"] for e in self.edges}

        for car in self.cars:
            eid = edge_id_map.get((car.node_a, car.node_b))
            if eid is None:
                continue
            if car.waiting or car.yielding_to_ev:
                speed_sums[eid] += 0.0
            else:
                speed_sums[eid] += car._base_speed
            speed_counts[eid] += 1

        densities = {}
        for e in self.edges:
            eid = e["id"]
            count = speed_counts[eid]
            if count == 0:
                densities[eid] = 0.0
            else:
                avg_speed = speed_sums[eid] / count
                free_flow = max_speeds[eid]
                #density = how slow relative to free flow, 0 = free flow, 1 = standstill
                densities[eid] = max(0.0, 1.0 - (avg_speed / free_flow))

        return densities

    def build_state_message(self, ev_done=False):
        densities = self.compute_densities()

        lights_data = []
        for lt in self.lights.values():
            lights_data.append({
                "id": lt.id,
                "node": lt.node_id,
                "dir": lt.dir,
                "state": lt.get_state(),
                "t": lt.get_timer(),
            })

        traffic_data = [
            {"id": eid, "density": round(d, 3)}
            for eid, d in densities.items()
        ]

        return {
            "type": "state",
            "cars": [c.to_dict() for c in self.cars],
            "lights": lights_data,
            "traffic": traffic_data,
            "ev": self.ev.to_dict() if self.ev else None,
            "ev_done": ev_done,
        }

    def build_map_message(self):
        lights_data = [
            {"id": lt.id, "node": lt.node_id, "dir": lt.dir}
            for lt in self.lights.values()
        ]
        return {
            "type": "map",
            "nodes": self.nodes,
            "edges": self.edges,
            "lights": lights_data,
        }