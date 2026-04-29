import math
import random
import time

from city import build_city, build_adjacency, dijkstra

#velocidades en unidades/segundo
CAR_SPEED_MAIN = 88.0
CAR_SPEED_SIDE = 46.0
EV_SPEED = 135.0

MAX_CARS = 1500

#duraciones de fase del semaforo (segundos)
#verde largo, amarillo corto, breve rojo total antes de ceder paso
LIGHT_GREEN_DUR = 14.0
LIGHT_YELLOW_DUR =  3.0
LIGHT_ALLRED_DUR =  1.5 #rojo total entre cambios (seguridad)

#radio de deteccion de semaforo (el coche empieza a frenar dentro de este radio)
LIGHT_STOP_DIST = 0.88 #fraccion de progreso a partir de la cual puede parar

#probabilidad de destino en nodo principal
MAIN_DEST_BIAS = 0.65


#semaforo direccional: un semaforo por carril de entrada
class TrafficLight:
    """
    representa el semaforo de una sola direccion de entrada a una interseccion.
    dir: 'N','S','E','W'
    phase: 'green' | 'yellow' | 'allred' | 'red'
    """

    #fase inicial aleatoria para evitar sincronismo entre intersecciones
    def __init__(self, lid, node_id, direction, phase_offset=0.0):
        self.id = lid
        self.node_id = node_id
        self.dir = direction

        #el ciclo completo es: green → yellow → allred → red (hasta que le toca) → ...
        #los opuestos (N+S, E+W) van juntos en verde
        self._phase = "red"
        self._timer = 0.0
        self.override  = None #(state_str, remaining_secs) | None

        #estado derivado calculado en tick
        self._state = "red"

        #para el arranque, repartir las intersecciones en el tiempo
        self._boot_offset = phase_offset

    def tick(self, dt):
        if self.override is not None:
            state, rem = self.override
            rem -= dt
            self._state = state
            self.override = (state, rem) if rem > 0 else None
            return

        #la logica real la gestiona el IntersectionController
        #este metodo solo consume el timer y notifica cuando expira
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


#controlador de interseccion, esto coordina los 4 semaforos de un nodo
class IntersectionController:
    """
    gestiona el ciclo de los 4 semaforos de una interseccion.
    ciclo: NS_green → yellow → allred → EW_green → yellow → allred → repeat
    los semaforos N y S van juntos; E y W van juntos.
    """

    PHASES = [
        ("NS_green",  LIGHT_GREEN_DUR),
        ("NS_yellow", LIGHT_YELLOW_DUR),
        ("allred_1",  LIGHT_ALLRED_DUR),
        ("EW_green",  LIGHT_GREEN_DUR),
        ("EW_yellow", LIGHT_YELLOW_DUR),
        ("allred_2",  LIGHT_ALLRED_DUR),
    ]

    def __init__(self, node_id, lights_by_dir, phase_offset=0.0):
        """
        lights_by_dir: dict {dir: TrafficLight} para 'N','S','E','W'
        phase_offset: segundos de avance inicial para desincronizar intersecciones
        """
        self.node_id = node_id
        self.lights = lights_by_dir #{'N': light, 'S': light, ...}
        self._phase_idx = 0
        self._phase_timer = 0.0

        #calcular el total del ciclo para aplicar el offset
        total_cycle = sum(d for _, d in self.PHASES)
        effective_offset = phase_offset % total_cycle

        #avanzar hasta el punto correcto del ciclo segun el offset
        acc = 0.0
        for i, (pname, pdur) in enumerate(self.PHASES):
            if acc + pdur > effective_offset:
                self._phase_idx = i
                self._phase_timer = (acc + pdur) - effective_offset
                break
            acc += pdur

        self._apply_phase(self.PHASES[self._phase_idx][0])

    def _apply_phase(self, phase_name):
        """actualiza el estado visible de cada semaforo segun la fase de interseccion"""
        for d, lt in self.lights.items():
            if phase_name == "NS_green":
                lt.set_phase("green" if d in ("N", "S") else "red",   LIGHT_GREEN_DUR)
            elif phase_name == "NS_yellow":
                lt.set_phase("yellow" if d in ("N", "S") else "red",  LIGHT_YELLOW_DUR)
            elif phase_name in ("allred_1", "allred_2"):
                lt.set_phase("red", LIGHT_ALLRED_DUR)
            elif phase_name == "EW_green":
                lt.set_phase("green" if d in ("E", "W") else "red",   LIGHT_GREEN_DUR)
            elif phase_name == "EW_yellow":
                lt.set_phase("yellow" if d in ("E", "W") else "red",  LIGHT_YELLOW_DUR)

    def tick(self, dt):
        #si algun semaforo tiene override activo, solo tickear overrides
        for lt in self.lights.values():
            lt.tick(dt)

        self._phase_timer -= dt
        if self._phase_timer <= 0:
            self._phase_idx = (self._phase_idx + 1) % len(self.PHASES)
            pname, pdur = self.PHASES[self._phase_idx]
            self._phase_timer = pdur
            self._apply_phase(pname)

    def is_green_for_direction(self, approach_dir):
        """devuelve True si el semaforo de la direccion dada esta en verde"""
        lt = self.lights.get(approach_dir)
        if lt is None:
            return True   #si no hay semaforo, paso libre
        return lt.get_state() == "green"


#helper para calcular direccion de aproximacion a un nodo
def approach_direction(from_node, to_node):
    """
    devuelve la direccion cardinal desde la que un coche llega a to_node
    (desde from_node).  Es la inversa del movimiento: si el coche va hacia
    el norte, llega desde el sur → 'S'.
    """
    dx = to_node["x"] - from_node["x"]
    dy = to_node["y"] - from_node["y"]
    if abs(dx) >= abs(dy):
        return "W" if dx > 0 else "E"   #viaja al este → llega por el oeste
    else:
        return "N" if dy > 0 else "S"   #viaja al sur → llega por el norte


#coche
class Car:
    _id_counter = 0

    def __init__(self, node_a_id, node_b_id, node_map, edge_map, adj, main_nodes):
        Car._id_counter += 1
        self.id = f"c{Car._id_counter}"
        self.node_a = node_a_id
        self.node_b = node_b_id
        self.progress = 0.0
        self.waiting = False

        self.node_map  = node_map
        self.edge_map = edge_map
        self.adj = adj
        self.main_nodes = main_nodes

        self.route     = []
        self.route_idx = 0
        self.lane      = random.randint(1, 2)

        edge = edge_map.get((node_a_id, node_b_id))
        self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

    def set_route(self, route):
        self.route = route
        self.route_idx = 0
        if len(route) >= 2:
            self.node_a = route[0]
            self.node_b = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

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


#vehiculo de emergencia
class EmergencyVehicle:
    def __init__(self, from_id, to_id, route, node_map):
        self.from_id  = from_id
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

    def tick(self, dt):
        if self.done:
            return
        elen = self.edge_length()
        self.progress += (EV_SPEED * dt) / elen
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


#simulacion principal
class Simulation:
    def __init__(self):
        nodes, edges, light_defs = build_city()

        self.nodes = nodes
        self.edges = edges
        self.node_map = {n["id"]: n for n in nodes}
        self.edge_map = {(e["from"], e["to"]): e for e in edges}
        self.adj  = build_adjacency(nodes, edges)

        self.main_nodes = [n["id"] for n in nodes if n["main"]]
        self.border_nodes = self._find_border_nodes()

        #construir semaforos y controladores de interseccion
        self.lights: dict[str, TrafficLight] = {}
        self.intersections: dict[str, IntersectionController] = {}
        self._build_intersections(light_defs)

        self.cars: list[Car] = []
        self.ev: EmergencyVehicle | None = None

        self.last_tick = time.time()

        #arrancar con el maximo de coches desde el inicio
        while len(self.cars) < MAX_CARS:
            self._spawn_car()

    def _build_intersections(self, light_defs):
        """
        agrupa los semaforos por nodo y crea un IntersectionController por nodo.
        phase_offset aleatorio por interseccion para desincronizar los ciclos.
        """
        rng = random.Random(99)

        #total del ciclo para calcular offsets
        total_cycle = sum(d for _, d in IntersectionController.PHASES)

        #agrupar definiciones por nodo
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
        """
        comprueba si el coche debe detenerse por el semaforo del nodo destino.
        solo aplica en intersecciones principales con semaforo.
        """
        if car.progress < LIGHT_STOP_DIST:
            return False

        ctrl = self.intersections.get(car.node_b)
        if ctrl is None:
            return False   #nodo sin interseccion controlada: paso libre

        na = self.node_map.get(car.node_a)
        nb = self.node_map.get(car.node_b)
        if na is None or nb is None:
            return False

        direction = approach_direction(na, nb)
        return not ctrl.is_green_for_direction(direction)

    def tick(self):
        now = time.time()
        dt = min(now - self.last_tick, 0.15)
        self.last_tick = now

        #avanzar controladores de interseccion (que a su vez tickean sus semaforos)
        for ctrl in self.intersections.values():
            ctrl.tick(dt)

        #mover coches
        to_remove = []
        for car in self.cars:
            if self._is_light_blocking(car):
                car.waiting = True
                continue
            car.waiting = False
            car.progress += (car.speed * dt) / car.edge_length()

            if car.progress >= 1.0:
                car.progress = 0.0
                car.route_idx += 1
                if car.route_idx >= len(car.route) - 1:
                    to_remove.append(car)
                    continue
                car.node_a = car.route[car.route_idx]
                car.node_b = car.route[car.route_idx + 1]
                edge = self.edge_map.get((car.node_a, car.node_b))
                car.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

        for c in to_remove:
            self.cars.remove(c)

        #reponer coches inmediatamente para mantener MAX_CARS 24/7
        while len(self.cars) < MAX_CARS:
            self._spawn_car()

        #vehiculo de emergencia
        ev_done = False
        if self.ev is not None:
            self.ev.tick(dt)
            if self.ev.done:
                ev_done = True
                self.ev = None

        return ev_done

    def start_route(self, from_id, to_id):
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

    def nearest_node(self, x, y):
        """devuelve el nodo mas cercano a las coordenadas dadas"""
        best_id, best_d = None, float("inf")
        for n in self.nodes:
            d = math.hypot(n["x"] - x, n["y"] - y)
            if d < best_d:
                best_d, best_id = d, n["id"]
        return best_id

    def compute_densities(self):
        counts = {}
        for car in self.cars:
            key = (car.node_a, car.node_b)
            counts[key] = counts.get(key, 0) + 1
        densities = {}
        for e in self.edges:
            key = (e["from"], e["to"])
            count = counts.get(key, 0)
            capacity = e.get("lanes", 1) * 4
            densities[e["id"]] = min(1.0, count / capacity)
        return densities

    def build_state_message(self, ev_done=False):
        densities = self.compute_densities()

        lights_data = []
        for lt in self.lights.values():
            lights_data.append({
                "id":    lt.id,
                "node":  lt.node_id,
                "dir":   lt.dir,
                "state": lt.get_state(),
                "t":     lt.get_timer(),
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