import math
import random

# genera el grafo de la ciudad: nodos (intersecciones) y aristas (calles)
# diseño realista: cuadricula principal + calles secundarias entre bloques

# dimensiones del espacio de simulacion (unidades internas)
CITY_W = 900
CITY_H = 700

# nombres de calles principales y secundarias para dar contexto
MAIN_STREET_NAMES_H = [
    "Avda. de la Constitución",
    "Paseo de los Álamos",
    "Gran Vía Central",
]
MAIN_STREET_NAMES_V = [
    "Calle Mayor",
    "Avda. del Parque",
    "Bulevar Norte",
    "Ronda del Sur",
]
SIDE_NAMES = [
    "C/ San Juan", "C/ Ronda", "C/ Real", "C/ Nueva", "C/ Alta",
    "C/ Baja", "C/ del Molino", "C/ Olivos", "C/ Sol", "C/ Luna",
    "C/ Fuente", "C/ Palma", "C/ Cedros", "C/ Jardines", "C/ Flores",
]


def build_city():
    """
    genera la ciudad y devuelve (nodes, edges, lights).
    - nodes:  lista de dicts {id, x, y, main}
    - edges:  lista de dicts {id, from, to, lanes, main, name}
    - lights: lista de dicts {id, node} — solo en intersecciones principales
    """

    nodes  = []
    edges  = []
    lights = []
    side_name_pool = SIDE_NAMES[:]
    random.shuffle(side_name_pool)

    # --- cuadricula de calles principales ---
    # 4 filas x 5 columnas de intersecciones principales
    # distribuidas con margenes para dejar espacio en los bordes

    main_cols = [100, 280, 460, 640, 820]
    main_rows = [100, 260, 420, 580]

    main_grid = {}   # (col_idx, row_idx) -> node_id
    node_counter  = [0]
    edge_counter  = [0]
    light_counter = [0]

    def new_node_id():
        node_counter[0] += 1
        return f"n{node_counter[0]}"

    def new_edge_id():
        edge_counter[0] += 1
        return f"e{edge_counter[0]}"

    def new_light_id():
        light_counter[0] += 1
        return f"l{light_counter[0]}"

    # crear nodos de la cuadricula principal
    for ci, cx in enumerate(main_cols):
        for ri, ry in enumerate(main_rows):
            nid = new_node_id()
            # pequena variacion para que no quede perfectamente robotico
            jx = random.randint(-8, 8)
            jy = random.randint(-8, 8)
            nodes.append({"id": nid, "x": cx + jx, "y": ry + jy, "main": True})
            main_grid[(ci, ri)] = nid

    # conectar horizontalmente (calles principales horizontales)
    for ri in range(len(main_rows)):
        street_name = MAIN_STREET_NAMES_H[ri % len(MAIN_STREET_NAMES_H)]
        for ci in range(len(main_cols) - 1):
            a = main_grid[(ci, ri)]
            b = main_grid[(ci + 1, ri)]
            edges.append({
                "id": new_edge_id(), "from": a, "to": b,
                "lanes": 3, "main": True, "name": street_name
            })
            edges.append({
                "id": new_edge_id(), "from": b, "to": a,
                "lanes": 3, "main": True, "name": street_name
            })

    # conectar verticalmente (calles principales verticales)
    for ci in range(len(main_cols)):
        street_name = MAIN_STREET_NAMES_V[ci % len(MAIN_STREET_NAMES_V)]
        for ri in range(len(main_rows) - 1):
            a = main_grid[(ci, ri)]
            b = main_grid[(ci, ri + 1)]
            edges.append({
                "id": new_edge_id(), "from": a, "to": b,
                "lanes": 3, "main": True, "name": street_name
            })
            edges.append({
                "id": new_edge_id(), "from": b, "to": a,
                "lanes": 3, "main": True, "name": street_name
            })

    # semaforos en cada interseccion principal
    for nid in main_grid.values():
        lights.append({"id": new_light_id(), "node": nid})

    # --- calles secundarias entre bloques ---
    # un nodo secundario aproximadamente en el centro de cada bloque
    # conectado a los 4 nodos principales que lo rodean

    secondary_nodes = {}   # (ci, ri) -> node_id  (bloque entre ci,ri y ci+1,ri+1)
    side_pool_idx = [0]

    def next_side_name():
        name = side_name_pool[side_pool_idx[0] % len(side_name_pool)]
        side_pool_idx[0] += 1
        return name

    for ci in range(len(main_cols) - 1):
        for ri in range(len(main_rows) - 1):
            # posicion del nodo secundario: centro del bloque con variacion
            nA = _find_node(nodes, main_grid[(ci,   ri)])
            nB = _find_node(nodes, main_grid[(ci+1, ri+1)])
            cx = (nA["x"] + nB["x"]) / 2 + random.randint(-15, 15)
            cy = (nA["y"] + nB["y"]) / 2 + random.randint(-15, 15)

            nid = new_node_id()
            nodes.append({"id": nid, "x": cx, "y": cy, "main": False})
            secondary_nodes[(ci, ri)] = nid

            sname = next_side_name()

            # conectar con los 4 nodos principales del bloque
            for corner in [(ci, ri), (ci+1, ri), (ci, ri+1), (ci+1, ri+1)]:
                corner_id = main_grid[corner]
                edges.append({
                    "id": new_edge_id(), "from": nid, "to": corner_id,
                    "lanes": 1, "main": False, "name": sname
                })
                edges.append({
                    "id": new_edge_id(), "from": corner_id, "to": nid,
                    "lanes": 1, "main": False, "name": sname
                })

    # conectar nodos secundarios vecinos entre si (callejuelas internas)
    for ci in range(len(main_cols) - 1):
        for ri in range(len(main_rows) - 1):
            current = secondary_nodes.get((ci, ri))
            # vecino a la derecha
            right = secondary_nodes.get((ci + 1, ri))
            if right:
                sname = next_side_name()
                edges.append({
                    "id": new_edge_id(), "from": current, "to": right,
                    "lanes": 1, "main": False, "name": sname
                })
                edges.append({
                    "id": new_edge_id(), "from": right, "to": current,
                    "lanes": 1, "main": False, "name": sname
                })
            # vecino abajo
            down = secondary_nodes.get((ci, ri + 1))
            if down:
                sname = next_side_name()
                edges.append({
                    "id": new_edge_id(), "from": current, "to": down,
                    "lanes": 1, "main": False, "name": sname
                })
                edges.append({
                    "id": new_edge_id(), "from": down, "to": current,
                    "lanes": 1, "main": False, "name": sname
                })

    return nodes, edges, lights


def _find_node(nodes, nid):
    for n in nodes:
        if n["id"] == nid:
            return n
    return None


def build_adjacency(nodes, edges):
    """
    construye el mapa de adyacencia para dijkstra.
    devuelve dict: node_id -> [(neighbor_id, cost)]
    """
    node_map = {n["id"]: n for n in nodes}
    adj = {n["id"]: [] for n in nodes}

    for e in edges:
        nf = node_map.get(e["from"])
        nt = node_map.get(e["to"])
        if nf is None or nt is None:
            continue
        dist = math.hypot(nt["x"] - nf["x"], nt["y"] - nf["y"])
        # calles principales son mas rapidas (menos coste por carril extra)
        cost = dist / (1.5 if e["main"] else 1.0)
        adj[e["from"]].append((e["to"], cost, e["id"]))

    return adj


def dijkstra(adj, source, target):
    """
    calcula la ruta mas corta de source a target.
    devuelve lista de node_ids o [] si no hay ruta.
    """
    import heapq

    dist = {nid: float("inf") for nid in adj}
    prev = {}
    dist[source] = 0
    heap = [(0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        if u == target:
            break
        for (v, cost, _) in adj.get(u, []):
            nd = dist[u] + cost
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if dist[target] == float("inf"):
        return []

    path = []
    cur = target
    while cur != source:
        path.append(cur)
        cur = prev.get(cur)
        if cur is None:
            return []
    path.append(source)
    path.reverse()
    return path
