import math
import random
import time

from city import build_city, build_adjacency, dijkstra

# velocidad base de los coches en unidades/segundo
CAR_SPEED_MAIN = 85.0
CAR_SPEED_SIDE = 45.0
EV_SPEED       = 130.0

# numero de coches activos al mismo tiempo
MAX_CARS = 28

# duracion de cada fase del semaforo en segundos
LIGHT_GREEN_DUR  = 12.0
LIGHT_YELLOW_DUR = 3.0

# distancia minima entre coches para considerar congestion
CONGESTION_MIN_GAP = 18.0

# probabilidad de que un coche elija una calle principal como destino
MAIN_DEST_BIAS = 0.65


class TrafficLight:
    def __init__(self, lid, node_id):
        self.id      = lid
        self.node_id = node_id
        # fase actual: "ns_green", "yellow_ns", "ew_green", "yellow_ew"
        self.phase   = "ns_green"
        self.timer   = LIGHT_GREEN_DUR
        # override externo: (estado, tiempo_restante) o None
        self.override = None

    def tick(self, dt):
        # si hay override activo, consumirlo y no avanzar el ciclo normal
        if self.override is not None:
            state, remaining = self.override
            remaining -= dt
            if remaining <= 0:
                self.override = None
            else:
                self.override = (state, remaining)
            return

        self.timer -= dt
        if self.timer <= 0:
            self._advance_phase()

    def _advance_phase(self):
        if self.phase == "ns_green":
            self.phase = "yellow"
            self.timer = LIGHT_YELLOW_DUR
        elif self.phase == "yellow" and self._prev_phase == "ns_green":
            self.phase = "ew_green"
            self.timer = LIGHT_GREEN_DUR
        elif self.phase == "ew_green":
            self.phase = "yellow"
            self._prev_phase = "ew_green"
            self.timer = LIGHT_YELLOW_DUR
        else:
            self.phase = "ns_green"
            self.timer = LIGHT_GREEN_DUR

        self._prev_phase = self.phase

    _prev_phase = "ns_green"

    def set_override(self, state, duration):
        self.override = (state, float(duration))

    def get_state(self):
        if self.override is not None:
            return self.override[0]
        return self.phase

    def get_timer(self):
        if self.override is not None:
            return int(self.override[1])
        return int(self.timer)


class Car:
    _id_counter = 0

    def __init__(self, node_a_id, node_b_id, node_map, edge_map, adj, main_nodes):
        Car._id_counter += 1
        self.id       = f"c{Car._id_counter}"
        self.node_a   = node_a_id
        self.node_b   = node_b_id
        self.progress = 0.0   # 0.0 -> 1.0 a lo largo de la arista actual
        self.waiting  = False  # detenido por semaforo en rojo

        self.node_map = node_map
        self.edge_map = edge_map   # (from, to) -> edge dict
        self.adj      = adj
        self.main_nodes = main_nodes

        # ruta completa como lista de node_ids
        self.route      = []
        self.route_idx  = 0  # indice del segmento actual en la ruta
        self.lane       = random.randint(1, 2)

        # calcular velocidad segun tipo de calle
        edge = edge_map.get((node_a_id, node_b_id))
        self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

    def set_route(self, route):
        self.route     = route
        self.route_idx = 0
        if len(route) >= 2:
            self.node_a   = route[0]
            self.node_b   = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

    def get_xy(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 0, 0
        x = na["x"] + (nb["x"] - na["x"]) * self.progress
        y = na["y"] + (nb["y"] - na["y"]) * self.progress
        return x, y

    def edge_length(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 1
        return max(1, math.hypot(nb["x"] - na["x"], nb["y"] - na["y"]))

    def to_dict(self):
        x, y = self.get_xy()
        return {
            "id": self.id,
            "x":  round(x, 2),
            "y":  round(y, 2),
            "na": self.node_a,
            "nb": self.node_b,
            "p":  round(self.progress, 4),
            "lane": self.lane,
        }


class EmergencyVehicle:
    def __init__(self, from_id, to_id, route, node_map):
        self.from_id  = from_id
        self.to_id    = to_id
        self.route    = route
        self.node_map = node_map
        self.route_idx = 0
        self.node_a   = route[0]
        self.node_b   = route[1] if len(route) > 1 else route[0]
        self.progress  = 0.0
        self.done      = False

    def edge_length(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 1
        return max(1, math.hypot(nb["x"] - na["x"], nb["y"] - na["y"]))

    def get_xy(self):
        na = self.node_map.get(self.node_a)
        nb = self.node_map.get(self.node_b)
        if na is None or nb is None:
            return 0, 0
        x = na["x"] + (nb["x"] - na["x"]) * self.progress
        y = na["y"] + (nb["y"] - na["y"]) * self.progress
        return x, y

    def next_node(self):
        """devuelve el id del siguiente nodo de la ruta que aun no ha alcanzado"""
        if self.route_idx + 1 < len(self.route):
            return self.route[self.route_idx + 1]
        return self.to_id

    def tick(self, dt):
        if self.done:
            return
        dist = EV_SPEED * dt
        elen = self.edge_length()
        self.progress += dist / elen

        if self.progress >= 1.0:
            self.progress  = 0.0
            self.route_idx += 1
            if self.route_idx >= len(self.route) - 1:
                self.done = True
                return
            self.node_a = self.route[self.route_idx]
            self.node_b = self.route[self.route_idx + 1]

    def to_dict(self):
        x, y = self.get_xy()
        return {
            "id":    "ev1",
            "x":     round(x, 2),
            "y":     round(y, 2),
            "next":  self.next_node(),
            "route": self.route,
        }


class Simulation:
    def __init__(self):
        nodes, edges, light_defs = build_city()

        self.nodes     = nodes
        self.edges     = edges
        self.node_map  = {n["id"]: n for n in nodes}
        # indice de aristas por (from, to) para lookup rapido
        self.edge_map  = {(e["from"], e["to"]): e for e in edges}
        self.adj       = build_adjacency(nodes, edges)

        self.main_nodes  = [n["id"] for n in nodes if n["main"]]
        self.border_nodes = self._find_border_nodes()

        # semaforos
        self.lights    = {ld["id"]: TrafficLight(ld["id"], ld["node"]) for ld in light_defs}
        # mapa nodo -> semaforo para lookups rapidos
        self.light_by_node = {lt.node_id: lt for lt in self.lights.values()}

        self.cars: list[Car] = []
        self.ev: EmergencyVehicle | None = None

        self.last_tick = time.time()

    def _find_border_nodes(self):
        """nodos en los bordes del mapa, usados como spawn points para coches"""
        border = []
        for n in self.nodes:
            if n["x"] < 120 or n["x"] > 780 or n["y"] < 120 or n["y"] > 580:
                border.append(n["id"])
        # si hay pocos nodos de borde usar todos los principales
        return border if len(border) >= 4 else self.main_nodes[:]

    def _random_destination(self, exclude_id):
        """elige un destino aleatorio con sesgo hacia nodos principales"""
        pool = self.main_nodes if random.random() < MAIN_DEST_BIAS else [n["id"] for n in self.nodes]
        pool = [nid for nid in pool if nid != exclude_id]
        return random.choice(pool) if pool else exclude_id

    def _spawn_car(self):
        """crea un coche nuevo desde un nodo de borde con ruta aleatoria"""
        spawn = random.choice(self.border_nodes)
        dest  = self._random_destination(spawn)
        route = dijkstra(self.adj, spawn, dest)
        if len(route) < 2:
            return
        car = Car(route[0], route[1], self.node_map, self.edge_map, self.adj, self.main_nodes)
        car.set_route(route)
        self.cars.append(car)

    def _is_light_blocking(self, car: Car):
        """
        devuelve True si el coche esta proximo al nodo destino de su arista
        y el semaforo en ese nodo esta en rojo para su direccion de aproximacion.
        """
        if car.progress < 0.80:
            return False

        lt = self.light_by_node.get(car.node_b)
        if lt is None:
            return False

        state = lt.get_state()
        if state == "yellow":
            return True

        # determinar si el coche viaja en eje ns o ew
        na = self.node_map.get(car.node_a)
        nb = self.node_map.get(car.node_b)
        if na is None or nb is None:
            return False

        dx = abs(nb["x"] - na["x"])
        dy = abs(nb["y"] - na["y"])
        moving_ew = dx > dy

        if moving_ew and state == "ew_green":
            return False
        if not moving_ew and state == "ns_green":
            return False
        return True

    def tick(self):
        now   = time.time()
        dt    = now - self.last_tick
        dt    = min(dt, 0.15)   # cap por si el sistema va lento
        self.last_tick = now

        # avanzar semaforos
        for lt in self.lights.values():
            lt.tick(dt)

        # mover coches
        cars_to_remove = []
        for car in self.cars:
            if self._is_light_blocking(car):
                car.waiting = True
                continue

            car.waiting = False
            elen = car.edge_length()
            car.progress += (car.speed * dt) / elen

            if car.progress >= 1.0:
                car.progress  = 0.0
                car.route_idx += 1

                if car.route_idx >= len(car.route) - 1:
                    # ha llegado al destino, eliminarlo
                    cars_to_remove.append(car)
                    continue

                # avanzar al siguiente segmento de la ruta
                car.node_a = car.route[car.route_idx]
                car.node_b = car.route[car.route_idx + 1]
                edge = self.edge_map.get((car.node_a, car.node_b))
                car.speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

        for c in cars_to_remove:
            self.cars.remove(c)

        # mantener el numero de coches activos
        while len(self.cars) < MAX_CARS:
            self._spawn_car()

        # mover vehiculo de emergencia
        ev_done = False
        if self.ev is not None:
            self.ev.tick(dt)
            if self.ev.done:
                ev_done = True
                self.ev = None

        return ev_done

    def start_route(self, from_id, to_id):
        """inicia una ruta de vehiculo de emergencia"""
        route = dijkstra(self.adj, from_id, to_id)
        if len(route) < 2:
            print(f"no se encontro ruta de {from_id} a {to_id}")
            return False
        self.ev = EmergencyVehicle(from_id, to_id, route, self.node_map)
        print(f"ruta de emergencia iniciada: {' -> '.join(route)}")
        return True

    def cancel_route(self):
        self.ev = None

    def override_light(self, light_id, state, duration):
        lt = self.lights.get(light_id)
        if lt:
            lt.set_override(state, duration)

    def compute_densities(self):
        """
        calcula la densidad de trafico por arista (0.0 a 1.0).
        la densidad es funcion del numero de coches en la arista relativo a su capacidad.
        """
        counts = {}
        for car in self.cars:
            key = (car.node_a, car.node_b)
            counts[key] = counts.get(key, 0) + 1

        densities = {}
        for e in self.edges:
            key       = (e["from"], e["to"])
            count     = counts.get(key, 0)
            capacity  = e.get("lanes", 1) * 4   # 4 coches por carril como referencia
            densities[e["id"]] = min(1.0, count / capacity)

        return densities

    def build_state_message(self, ev_done=False):
        """
        construye el mensaje de estado completo que se envia al modulo java.
        incluye coches, semaforos, densidades y estado del vehiculo de emergencia.
        """
        densities = self.compute_densities()

        lights_data = []
        for lt in self.lights.values():
            lights_data.append({
                "id":    lt.id,
                "node":  lt.node_id,
                "state": lt.get_state(),
                "t":     lt.get_timer(),
            })

        traffic_data = [{"id": eid, "density": round(d, 3)} for eid, d in densities.items()]

        msg = {
            "type":    "state",
            "cars":    [c.to_dict() for c in self.cars],
            "lights":  lights_data,
            "traffic": traffic_data,
            "ev":      self.ev.to_dict() if self.ev else None,
            "ev_done": ev_done,
        }
        return msg

    def build_map_message(self):
        """
        construye el mensaje de mapa inicial que se envia al conectar.
        solo se envia una vez por conexion.
        """
        lights_data = [{"id": lt.id, "node": lt.node_id} for lt in self.lights.values()]
        return {
            "type":   "map",
            "nodes":  self.nodes,
            "edges":  self.edges,
            "lights": lights_data,
        }
