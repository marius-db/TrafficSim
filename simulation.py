import math
import random
import time

from city import build_city, build_adjacency, dijkstra

CAR_SPEED_MAIN = 88.0
CAR_SPEED_SIDE = 46.0
EV_SPEED = 130.0

MAX_CARS = 500

LIGHT_GREEN_DUR = 14.0
LIGHT_YELLOW_DUR = 3.0
LIGHT_ALLRED_DUR = 1.5

LIGHT_STOP_DIST = 0.88

CAR_MIN_GAP = 0.045

#distancia maxima a la que el VE preempta los semaforos (unidades del mundo)
EV_PREEMPT_RADIUS = 220.0
#distancia a la que los coches empiezan a apartarse para el VE
EV_YIELD_RADIUS = 160.0
EV_YIELD_SPEED_FACTOR = 0.15

#cada cuanto se reconstruye la adyacencia con conciencia de trafico para reroutar coches (segundos)
ADJ_REBUILD_INTERVAL = 8.0


class TrafficLight:
    def __init__(self, lid, node_id, direction):
        self.id = lid
        self.node_id = node_id
        self.dir = direction
        self._state = "red"
        self._timer = 0.0
        self.override = None
        #flag activado por la preempcion del VE para que el visualizador lo resalte de forma diferente
        self.ev_preempted = False

    def tick(self, dt):
        if self.override is not None:
            state, rem = self.override
            rem -= dt
            self._state = state
            if rem <= 0:
                self.override = None
                self.ev_preempted = False
            else:
                self.override = (state, rem)
        else:
            self._timer -= dt

    def set_phase(self, phase, duration):
        self._state = phase
        self._timer = duration

    def get_state(self):
        if self.override is not None:
            return self.override[0]
        return self._state

    def get_timer(self):
        if self.override is not None:
            return int(self.override[1])
        return max(0, int(self._timer))

    def set_override(self, state, duration, ev=False):
        self.override = (state, float(duration))
        self.ev_preempted = ev

    def phase_expired(self):
        return self._timer <= 0 and self.override is None


class IntersectionController:
    PHASES = [
        ("NS_green",  LIGHT_GREEN_DUR),
        ("NS_yellow", LIGHT_YELLOW_DUR),
        ("allred_1",  LIGHT_ALLRED_DUR),
        ("EW_green",  LIGHT_GREEN_DUR),
        ("EW_yellow", LIGHT_YELLOW_DUR),
        ("allred_2",  LIGHT_ALLRED_DUR),
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

    def preempt_for_ev(self, approach_dir):
        #forzar todos los semaforos de esta interseccion para despejar el camino al VE
        for d, lt in self.lights.items():
            if d == approach_dir:
                lt.set_override("green", LIGHT_GREEN_DUR + LIGHT_ALLRED_DUR, ev=True)
            else:
                lt.set_override("red", LIGHT_GREEN_DUR + LIGHT_ALLRED_DUR, ev=True)


def approach_direction(from_node, to_node):
    dx = to_node["x"] - from_node["x"]
    dy = to_node["y"] - from_node["y"]
    if abs(dx) >= abs(dy):
        return "W" if dx > 0 else "E"
    else:
        return "N" if dy > 0 else "S"


class Car:
    _id_counter = 0

    def __init__(self, node_a_id, node_b_id, node_map, edge_map, adj_ref, all_nodes):
        Car._id_counter += 1
        self.id = f"c{Car._id_counter}"
        self.node_a = node_a_id
        self.node_b = node_b_id
        self.progress = 0.0
        self.waiting = False
        self.yielding_to_ev = False
        #yield_offset es una fraccion de desplazamiento lateral usada por el visualizador para mostrar el apartado
        self.yield_offset = 0.0

        self.node_map = node_map
        self.edge_map = edge_map
        self.adj_ref = adj_ref  #referencia mutable: lista de [adj_dict]
        self.all_nodes = all_nodes

        self.route = []
        self.route_idx = 0
        self.lane = random.randint(1, 2)

        #variacion aleatoria de velocidad: +-12% (algunos coches mas rapidos, otros mas lentos)
        self.speed_factor = random.uniform(0.88, 1.12)

        edge = edge_map.get((node_a_id, node_b_id))
        self._base_speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

    def set_route(self, route):
        self.route = route
        self.route_idx = 0
        if len(route) >= 2:
            self.node_a = route[0]
            self.node_b = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self._base_speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

    def reroute(self):
        dest = random.choice(self.all_nodes)["id"]
        #usar la adyacencia con conciencia de trafico actual desde la referencia compartida
        route = dijkstra(self.adj_ref[0], self.node_b, dest)
        if len(route) >= 2:
            self.route = route
            self.route_idx = 0
            self.node_a = route[0]
            self.node_b = route[1]
            self.progress = 0.0
            edge = self.edge_map.get((self.node_a, self.node_b))
            self._base_speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE

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
            "waiting": self.waiting,
            "yielding": self.yielding_to_ev,
        }


class EmergencyVehicle:
    def __init__(self, start_id, end_id, route, node_map):
        self.id = "ev1"
        self.start_id = start_id
        self.end_id = end_id
        self.route = route
        self.node_map = node_map
        self.node_a = route[0]
        self.node_b = route[1]
        self.route_idx = 0
        self.progress = 0.0
        self.done = False

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

    def tick(self, dt, same_edge_cars, edge_len):
        self.progress += (EV_SPEED * dt) / edge_len

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
            "id": self.id,
            "x": round(x, 2),
            "y": round(y, 2),
            "na": self.node_a,
            "nb": self.node_b,
            "p": round(self.progress, 4),
            "route": self.route,
            "route_idx": self.route_idx,
        }


class Simulation:
    def __init__(self):
        self.nodes, self.edges, lights_list = build_city()
        self.node_map = {n["id"]: n for n in self.nodes}
        self.edge_map = {(e["from"], e["to"]): e for e in self.edges}
        self._adj_ref = [build_adjacency(self.nodes, self.edges)]
        self.cars = []
        self.ev = None

        self.lights = {}
        for lt_data in lights_list:
            lt = TrafficLight(lt_data["id"], lt_data["node"], lt_data["dir"])
            self.lights[lt.id] = lt

        self.intersections = {}
        for nid in self.node_map:
            lights_at_node = {}
            for lt in self.lights.values():
                if lt.node_id == nid:
                    lights_at_node[lt.dir] = lt
            if lights_at_node:
                phase_offset = random.uniform(0, 30)
                self.intersections[nid] = IntersectionController(nid, lights_at_node, phase_offset)

        #generar trafico inicial
        for _ in range(MAX_CARS):
            a_node = random.choice(self.nodes)
            b_node = random.choice(self.nodes)
            if a_node["id"] != b_node["id"]:
                car = Car(a_node["id"], b_node["id"], self.node_map, self.edge_map, self._adj_ref, self.nodes)
                route = dijkstra(self._adj_ref[0], a_node["id"], b_node["id"])
                if len(route) >= 2:
                    car.set_route(route)
                    self.cars.append(car)

        self.last_tick = time.time()
        self._last_adj_rebuild = time.time()
        self._density_smoothed = {}

    def _is_light_blocking(self, car):
        na = self.node_map.get(car.node_b)
        if na is None:
            return False
        ctrl = self.intersections.get(car.node_b)
        if ctrl is None:
            return False

        #comprobar semaforos desde mas atras: dentro de 50 unidades O ultimo 15% de la calle
        edge_len = car.edge_length()
        normalized_stop_dist = LIGHT_STOP_DIST / edge_len
        check_threshold = min(0.15, max(normalized_stop_dist, 50.0 / edge_len))

        if car.progress < 1.0 - check_threshold:
            return False

        prev_nid = car.node_a
        prev_node = self.node_map.get(prev_nid)
        if prev_node is None:
            return False

        approach_dir = approach_direction(prev_node, na)
        return not ctrl.is_green_for_direction(approach_dir)

    def _check_ev_yield(self, car):
        if self.ev is None:
            return False
        ex, ey = self.ev.get_xy()
        cx, cy = car.get_xy()
        dist = math.hypot(ex - cx, ey - cy)
        return dist < EV_YIELD_RADIUS

    def _preempt_ev_lights(self):
        #forzar verde para el VE en todas las intersecciones que se aproxima dentro del radio
        if self.ev is None:
            return
        ex, ey = self.ev.get_xy()
        #mirar hacia adelante a traves de los siguientes nodos de la ruta
        for step in range(min(3, len(self.ev.route) - self.ev.route_idx - 1)):
            ahead_idx = self.ev.route_idx + 1 + step
            if ahead_idx >= len(self.ev.route):
                break
            next_nid = self.ev.route[ahead_idx]
            next_node = self.node_map.get(next_nid)
            if next_node is None:
                continue
            dist = math.hypot(next_node["x"] - ex, next_node["y"] - ey)
            if dist > EV_PREEMPT_RADIUS:
                break
            ctrl = self.intersections.get(next_nid)
            if ctrl is None:
                continue
            #determinar la direccion desde la que el VE se aproxima
            if ahead_idx > 0:
                prev_nid = self.ev.route[ahead_idx - 1]
                prev_node = self.node_map.get(prev_nid)
                if prev_node:
                    dir_ = approach_direction(prev_node, next_node)
                    ctrl.preempt_for_ev(dir_)

    def _rebuild_traffic_adj(self):
        densities = self.compute_densities()
        new_adj = build_adjacency(self.nodes, self.edges, densities=densities)
        self._adj_ref[0] = new_adj

    def tick(self):
        now = time.time()
        dt = min(now - self.last_tick, 0.15)
        self.last_tick = now

        #reconstruir adyacencia con conciencia de trafico periodicamente
        if now - self._last_adj_rebuild > ADJ_REBUILD_INTERVAL:
            self._rebuild_traffic_adj()
            self._last_adj_rebuild = now

        for ctrl in self.intersections.values():
            ctrl.tick(dt)

        #preemptar semaforos por delante del VE en cada tick
        self._preempt_ev_lights()

        edge_idx = self._build_edge_index()

        for car in self.cars:
            was_yielding = car.yielding_to_ev
            car.yielding_to_ev = self._check_ev_yield(car)

            if car.yielding_to_ev:
                car.waiting = False
                #animar yield_offset hacia la posicion maxima de apartado
                car.yield_offset = min(1.0, car.yield_offset + dt * 2.5)
                yield_speed = car._base_speed * EV_YIELD_SPEED_FACTOR * car.speed_factor
                car.progress += (yield_speed * dt) / car.edge_length()
                if car.progress >= 0.94:
                    car.progress = 0.94
                continue
            else:
                #volver suavemente al carril normal
                if car.yield_offset > 0:
                    car.yield_offset = max(0.0, car.yield_offset - dt * 1.5)

            if self._is_light_blocking(car):
                car.waiting = True
                continue

            same_edge = edge_idx.get((car.node_a, car.node_b), [])
            ahead_progress = None
            for other in same_edge:
                if other is car:
                    continue
                if other.progress > car.progress:
                    if ahead_progress is None or other.progress < ahead_progress:
                        ahead_progress = other.progress

            #lookahead: si esta cerca del final del tramo actual, comprobar coches en el siguiente
            if car.progress > 0.85 and car.route_idx + 1 < len(car.route) - 1:
                next_edge_key = (car.route[car.route_idx + 1], car.route[car.route_idx + 2])
                next_edge_cars = edge_idx.get(next_edge_key, [])
                for other in next_edge_cars:
                    if other.progress < 0.15:  #coche muy cerca del inicio del siguiente tramo
                        #tratarlo como si estuviera en 1.0 + su progreso en el siguiente tramo
                        virtual_progress = 1.0 + other.progress
                        if ahead_progress is None or virtual_progress < ahead_progress:
                            ahead_progress = virtual_progress

            gap = (ahead_progress - car.progress) if ahead_progress is not None else 1.0

            if gap <= CAR_MIN_GAP:
                car.waiting = True
                continue
            elif gap < CAR_MIN_GAP * 2.5:
                t = (gap - CAR_MIN_GAP) / (CAR_MIN_GAP * 1.5)
                effective_speed = car._base_speed * max(0.08, t)
            else:
                effective_speed = car._base_speed

            car.waiting = False
            car.progress += (effective_speed * car.speed_factor * dt) / car.edge_length()

            #limitar a 1.0 para evitar saltos, comprobar cada frame si puede avanzar al siguiente tramo
            if car.progress >= 1.0:
                car.progress = 1.0
                #solo pasar al siguiente tramo si la interseccion de destino esta libre
                if car.route_idx + 1 < len(car.route) - 1:
                    next_node_a = car.route[car.route_idx + 1]
                    next_node_b = car.route[car.route_idx + 2]
                    next_edge_key = (next_node_a, next_node_b)
                    next_edge_cars = edge_idx.get(next_edge_key, [])

                    #comprobar si el siguiente tramo esta libre (ningun coche demasiado cerca del inicio)
                    next_clear = True
                    for other in next_edge_cars:
                        if other.progress < 0.1:  #coche al inicio del siguiente tramo
                            next_clear = False
                            break

                    if next_clear:
                        #seguro avanzar al siguiente tramo
                        car.progress = 0.0
                        car.route_idx += 1
                        if car.route_idx >= len(car.route) - 1:
                            car.reroute()
                            continue
                        car.node_a = car.route[car.route_idx]
                        car.node_b = car.route[car.route_idx + 1]
                        edge = self.edge_map.get((car.node_a, car.node_b))
                        car._base_speed = CAR_SPEED_MAIN if (edge and edge.get("main")) else CAR_SPEED_SIDE
                        key = (car.node_a, car.node_b)
                        if key not in edge_idx:
                            edge_idx[key] = []
                        edge_idx[key].append(car)
                else:
                    #fin de ruta, reroutar
                    car.route_idx += 1
                    if car.route_idx >= len(car.route) - 1:
                        car.reroute()
                continue

        ev_done = False
        if self.ev is not None:
            ev_edge_cars = edge_idx.get((self.ev.node_a, self.ev.node_b), [])
            self.ev.tick(dt, ev_edge_cars, self.ev.edge_length())
            if self.ev.done:
                ev_done = True
                self.ev = None

        return ev_done

    def start_route(self, from_id, to_id):
        #si from_id o to_id son ids de nodo validos, usarlos directamente
        from_node = self.node_map.get(from_id)
        to_node = self.node_map.get(to_id)

        if from_node is None:
            return False
        if to_node is None:
            return False

        route = dijkstra(self._adj_ref[0], from_id, to_id)
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
        if lt:
            lt.set_override(state, duration)

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
        speed_sums: dict[str, float] = {}
        speed_counts: dict[str, int] = {}
        waiting_counts: dict[str, int] = {}
        max_speeds: dict[str, float] = {}

        for e in self.edges:
            speed_sums[e["id"]] = 0.0
            speed_counts[e["id"]] = 0
            waiting_counts[e["id"]] = 0
            max_speeds[e["id"]] = CAR_SPEED_MAIN if e.get("main") else CAR_SPEED_SIDE

        edge_id_map = {(e["from"], e["to"]): e["id"] for e in self.edges}

        for car in self.cars:
            eid = edge_id_map.get((car.node_a, car.node_b))
            if eid is None:
                continue

            #marcar como esperando si: parado en semaforo O apenas moviendose (congestionado)
            is_waiting = car.waiting or car.yielding_to_ev

            #tambien contar coches como esperando si estan muy cerca del destino (95%+ de progreso)
            #esto captura congestion en intersecciones sin semaforos
            if car.progress > 0.95:
                is_waiting = True

            speed_sums[eid] += 0.0 if is_waiting else car._base_speed
            speed_counts[eid] += 1
            if is_waiting:
                waiting_counts[eid] += 1

        #calcular densidad cruda y aplicar suavizado exponencial
        alpha = 0.25  #0.25 para persistencia visual (decae en ~2 segundos)
        raw_densities = {}
        for e in self.edges:
            eid = e["id"]
            count = speed_counts[eid]
            if count == 0:
                raw_densities[eid] = 0.0
            else:
                avg = speed_sums[eid] / count
                max_speed = max_speeds[eid]

                #degradacion de velocidad: 0 = velocidad maxima, 1 = parada total
                speed_factor = max(0.0, 1.0 - (avg / max_speed))

                #densidad de vehiculos: coches por unidad de longitud (normalizado)
                #mas sensible: incluso pocos coches deben mostrar algo de color
                edge_obj = self.edge_map.get((e["from"], e["to"]))
                if edge_obj:
                    edge_len = max(1.0, math.hypot(
                        self.node_map[e["to"]]["x"] - self.node_map[e["from"]]["x"],
                        self.node_map[e["to"]]["y"] - self.node_map[e["from"]]["y"]
                    ))
                    #capacidad: 1 coche cada ~30 unidades = visible, 5+ coches = maximo
                    vehicle_density = min(1.0, (count * 30.0) / edge_len)
                else:
                    vehicle_density = count / 10.0  #fallback

                #presencia minima: cualquier coche en la calle añade al menos 0.05 de densidad
                min_presence = 0.05 if count > 0 else 0.0

                #señalizacion suavizada basada en coches esperando con interpolacion
                #puntos clave: (numero_coches_esperando, valor_densidad)
                waiting = waiting_counts[eid]
                waiting_points = [
                    (0, 0.0),      #sin coches
                    (2, 0.25),     #apenas amarillo
                    (4, 0.48),     #amarillo
                    (7, 0.70),     #amarillo a rojo
                    (10, 0.95),    #rojo
                ]

                #interpolar entre puntos clave
                waiting_density = 0.0
                if waiting > 0:
                    for i in range(len(waiting_points) - 1):
                        w1, d1 = waiting_points[i]
                        w2, d2 = waiting_points[i + 1]
                        if w1 <= waiting <= w2:
                            #interpolacion lineal
                            t = (waiting - w1) / (w2 - w1) if w2 > w1 else 0.0
                            waiting_density = d1 + (d2 - d1) * t
                            break
                    else:
                        #mas alla del ultimo punto
                        waiting_density = waiting_points[-1][1]

                #combinar: priorizar señal de coches esperando, pero considerar tambien velocidad y flujo
                #si muchos coches estan realmente esperando, dejar que eso domine; si no, usar velocidad y densidad
                if waiting > 0:
                    raw_densities[eid] = (waiting_density * 0.8) + (speed_factor * 0.2)
                else:
                    #aumentar presencia de vehiculos cuando no hay espera: 60% velocidad, 40% presencia
                    #garantizar visibilidad minima si hay coches presentes
                    raw_densities[eid] = max(min_presence, (speed_factor * 0.6) + (vehicle_density * 0.4))

        #suavizar con media movil exponencial
        densities = {}
        for e in self.edges:
            eid = e["id"]
            prev_smooth = self._density_smoothed.get(eid, 0.0)
            raw = raw_densities[eid]
            smoothed = alpha * raw + (1.0 - alpha) * prev_smooth
            self._density_smoothed[eid] = smoothed
            densities[eid] = smoothed

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
                "ev": lt.ev_preempted,
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

    def _build_edge_index(self):
        edge_idx = {}
        for car in self.cars:
            key = (car.node_a, car.node_b)
            if key not in edge_idx:
                edge_idx[key] = []
            edge_idx[key].append(car)
        return edge_idx