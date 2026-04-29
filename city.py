import math
import random

#dimensiones del espacio de simulacion
CITY_W = 1000
CITY_H = 780

MAIN_STREET_NAMES_H = [
    "Avda. de la Constitución",
    "Gran Vía",
    "Paseo de los Álamos",
    "Ronda Sur",
]
MAIN_STREET_NAMES_V = [
    "Calle Mayor",
    "Avda. del Parque",
    "Bulevar Norte",
    "Ronda del Este",
    "Calle de la Paz",
]
SIDE_NAMES = [
    "C/ San Juan", "C/ Ronda", "C/ Real", "C/ Nueva", "C/ Alta",
    "C/ Baja", "C/ del Molino", "C/ Olivos", "C/ Sol", "C/ Luna",
    "C/ Fuente", "C/ Palma", "C/ Cedros", "C/ Jardines", "C/ Flores",
    "C/ Cervantes", "C/ Colón", "C/ Isabel", "C/ Fernando", "C/ Castilla",
    "C/ Alcalá", "C/ Velázquez", "C/ Goya", "C/ Zurbarán", "C/ Murillo",
]


def build_city(seed=42):
    """
    genera una ciudad con aspecto organico:
    - cuadricula base con espaciado no uniforme (bloques de tamaño variado)
    - algunas conexiones de la cuadricula eliminadas o sustituidas por diagonales
    - calles secundarias con trazado irregular, no siempre centradas en el bloque
    - callejones en fondo de saco en zonas perifericas

    devuelve (nodes, edges, lights)
    """
    rng = random.Random(seed)

    nodes  = []
    edges  = []
    lights = []

    node_counter  = [0]
    edge_counter  = [0]
    light_counter = [0]

    def nid():
        node_counter[0] += 1
        return f"n{node_counter[0]}"

    def eid():
        edge_counter[0] += 1
        return f"e{edge_counter[0]}"

    def lid():
        light_counter[0] += 1
        return f"l{light_counter[0]}"

    side_pool = SIDE_NAMES[:]
    rng.shuffle(side_pool)
    side_idx = [0]

    def next_side():
        name = side_pool[side_idx[0] % len(side_pool)]
        side_idx[0] += 1
        return name

    #cuadricula principal con espaciado no uniforme
    #columnas y filas con gaps variables para simular bloques reales
    #los gaps son mas grandes en el centro (distrito comercial) y
    #mas pequeños en los bordes (barrios residenciales)

    col_gaps = [0, 110, 175, 145, 190, 160, 130, 110]   #8 columnas
    row_gaps = [0, 120, 165, 145, 175, 140, 120]         #7 filas

    #calcular posiciones absolutas acumulando gaps
    margin_x, margin_y = 60, 55
    col_xs = [margin_x]
    for g in col_gaps[1:]:
        col_xs.append(col_xs[-1] + g)
    row_ys = [margin_y]
    for g in row_gaps[1:]:
        row_ys.append(row_ys[-1] + g)

    n_cols = len(col_xs)
    n_rows = len(row_ys)

    main_grid = {}   #(ci, ri) -> node_id

    for ci, bx in enumerate(col_xs):
        for ri, by in enumerate(row_ys):
            #jitter organico: mas en zonas interiores, menos en bordes
            interior = (ci > 0 and ci < n_cols-1 and ri > 0 and ri < n_rows-1)
            jmax = 18 if interior else 6
            jx = rng.randint(-jmax, jmax)
            jy = rng.randint(-jmax, jmax)
            node = {"id": nid(), "x": float(bx + jx), "y": float(by + jy), "main": True}
            nodes.append(node)
            main_grid[(ci, ri)] = node["id"]

    #conexiones horizontales (calles principales)
    h_street_names = {}
    for ri in range(n_rows):
        h_street_names[ri] = MAIN_STREET_NAMES_H[ri % len(MAIN_STREET_NAMES_H)]

    def add_road(a_id, b_id, lanes, is_main, name):
        edges.append({"id": eid(), "from": a_id, "to": b_id, "lanes": lanes, "main": is_main, "name": name})
        edges.append({"id": eid(), "from": b_id, "to": a_id, "lanes": lanes, "main": is_main, "name": name})

    #probabilidad de eliminar una conexion de cuadricula (crea variedad)
    SKIP_PROB = 0.08

    for ri in range(n_rows):
        sname = h_street_names[ri]
        for ci in range(n_cols - 1):
            if rng.random() < SKIP_PROB:
                continue   #conexion eliminada: el bloque queda sin salida directa
            a = main_grid[(ci, ri)]
            b = main_grid[(ci+1, ri)]
            add_road(a, b, 3, True, sname)

    #conexiones verticales (calles principales N-S)
    v_street_names = {}
    for ci in range(n_cols):
        v_street_names[ci] = MAIN_STREET_NAMES_V[ci % len(MAIN_STREET_NAMES_V)]

    for ci in range(n_cols):
        sname = v_street_names[ci]
        for ri in range(n_rows - 1):
            if rng.random() < SKIP_PROB:
                continue
            a = main_grid[(ci, ri)]
            b = main_grid[(ci, ri+1)]
            add_road(a, b, 3, True, sname)

    #diagonales organicas (aprox 30% de los bloques)
    DIAG_PROB = 0.28
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            if rng.random() < DIAG_PROB:
                #diagonal principal del bloque (top left -> bottom right)
                a = main_grid[(ci, ri)]
                b = main_grid[(ci+1, ri+1)]
                sname = next_side()
                add_road(a, b, 1, False, sname)
            if rng.random() < DIAG_PROB * 0.5:
                #diagonal inversa (top right -> bottom left) solo en algunos bloques
                a = main_grid[(ci+1, ri)]
                b = main_grid[(ci, ri+1)]
                sname = next_side()
                add_road(a, b, 1, False, sname)

    #semaforos en intersecciones principales
    #cada interseccion principal tiene 4 semaforos (uno por direccion)
    for (ci, ri), node_id in main_grid.items():
        for direction in ["N", "S", "E", "W"]:
            lights.append({"id": lid(), "node": node_id, "dir": direction})

    #nodos secundarios — uno por bloque, posicion organica
    #regla de sanidad: un nodo secundario solo se conecta a las esquinas
    #que le quedan en la misma mitad del bloque (no cruza el bloque entero).
    #esto evita calles que se solapan o atraviesan bloques de forma ilógica.

    secondary = {}   #(ci, ri) -> node_id
    node_map_local = {n["id"]: n for n in nodes}  #lookup rapido

    def get_n(nid_):
        return node_map_local.get(nid_)

    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            tl = get_n(main_grid[(ci,   ri)])    #top-left
            tr = get_n(main_grid[(ci+1, ri)])    #top-right
            bl = get_n(main_grid[(ci,   ri+1)])  #bottom-left
            br = get_n(main_grid[(ci+1, ri+1)])  #bottom-right

            #centro del bloque con jitter organico
            cx = (tl["x"] + tr["x"] + bl["x"] + br["x"]) / 4 + rng.randint(-28, 28)
            cy = (tl["y"] + tr["y"] + bl["y"] + br["y"]) / 4 + rng.randint(-28, 28)

            #clamp estricto: el nodo secundario debe quedar dentro del bloque
            min_x = min(tl["x"], tr["x"], bl["x"], br["x"]) + 12
            max_x = max(tl["x"], tr["x"], bl["x"], br["x"]) - 12
            min_y = min(tl["y"], tr["y"], bl["y"], br["y"]) + 12
            max_y = max(tl["y"], tr["y"], bl["y"], br["y"]) - 12
            if min_x < max_x: cx = max(min_x, min(max_x, cx))
            if min_y < max_y: cy = max(min_y, min(max_y, cy))

            sec = {"id": nid(), "x": cx, "y": cy, "main": False}
            nodes.append(sec)
            node_map_local[sec["id"]] = sec
            secondary[(ci, ri)] = sec["id"]

            sname = next_side()

            #determinar a que esquinas conectar:
            #conectar solo a las esquinas cuya linea directa NO cruza el centro del bloque
            #en la practica: conectar a 2 esquinas adyacentes (que forman un lado del bloque)
            #eligiendo el par horizontal o vertical segun donde este el nodo secundario
            block_cx = (tl["x"] + br["x"]) / 2
            block_cy = (tl["y"] + br["y"]) / 2
            prefer_h = abs(cy - block_cy) < abs(cx - block_cx)  # mas cerca del eje horizontal

            #elegir 2 o 3 esquinas, priorizando las mas cercanas y evitando cruces
            corners_dist = sorted(
                [(ci, ri, tl), (ci+1, ri, tr), (ci, ri+1, bl), (ci+1, ri+1, br)],
                key=lambda x: math.hypot(x[2]["x"] - cx, x[2]["y"] - cy)
            )
            #siempre conectar las 2 mas cercanas
            n_connect = rng.choice([2, 2, 3])
            connected_corners = set()
            for (cic, ric, cn) in corners_dist[:n_connect]:
                corner_id = main_grid[(cic, ric)]
                if corner_id not in connected_corners:
                    add_road(sec["id"], corner_id, 1, False, sname)
                    connected_corners.add(corner_id)

    #conectar nodos secundarios vecinos (callejuelas internas)
    #solo conectar vecinos si la distancia entre ellos es razonable
    #(evita calles largas que cruzan bloques enteros)

    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            cur_id = secondary.get((ci, ri))
            if cur_id is None:
                continue
            cur_n = get_n(cur_id)

            #vecino a la derecha
            right_id = secondary.get((ci+1, ri))
            if right_id:
                right_n = get_n(right_id)
                dist = math.hypot(cur_n["x"] - right_n["x"], cur_n["y"] - right_n["y"])
                #bloque de referencia para limitar la longitud maxima aceptable
                ref_w = col_gaps[ci+1] if ci+1 < len(col_gaps) else 160
                if dist < ref_w * 0.85 and rng.random() < 0.45:
                    add_road(cur_id, right_id, 1, False, next_side())

            #vecino abajo
            down_id = secondary.get((ci, ri+1))
            if down_id:
                down_n = get_n(down_id)
                dist = math.hypot(cur_n["x"] - down_n["x"], cur_n["y"] - down_n["y"])
                ref_h = row_gaps[ri+1] if ri+1 < len(row_gaps) else 145
                if dist < ref_h * 0.85 and rng.random() < 0.45:
                    add_road(cur_id, down_id, 1, False, next_side())


    #callejones en fondo de saco en zona periferica

    #añadir 6-10 callejones cortos desde nodos de borde
    border_main = [
        main_grid[(ci, ri)]
        for ci in range(n_cols) for ri in range(n_rows)
        if ci == 0 or ci == n_cols-1 or ri == 0 or ri == n_rows-1
    ]
    rng.shuffle(border_main)
    n_alleys = rng.randint(6, 10)

    for base_id in border_main[:n_alleys]:
        base = node_map_local.get(base_id)
        #callejon corto en direccion aleatoria hacia el exterior
        angle = rng.uniform(0, 2 * math.pi)
        length = rng.randint(50, 90)
        end_x = base["x"] + math.cos(angle) * length
        end_y = base["y"] + math.sin(angle) * length
        #mantener dentro del canvas
        end_x = max(20, min(CITY_W - 20, end_x))
        end_y = max(20, min(CITY_H - 20, end_y))
        alley = {"id": nid(), "x": end_x, "y": end_y, "main": False}
        nodes.append(alley)
        add_road(base_id, alley["id"], 1, False, next_side())

    return nodes, edges, lights


def _get_node(nodes, nid):
    for n in nodes:
        if n["id"] == nid:
            return n
    return None


def build_adjacency(nodes, edges):
    node_map = {n["id"]: n for n in nodes}
    adj = {n["id"]: [] for n in nodes}

    for e in edges:
        nf = node_map.get(e["from"])
        nt = node_map.get(e["to"])
        if nf is None or nt is None:
            continue
        dist = math.hypot(nt["x"] - nf["x"], nt["y"] - nf["y"])
        cost = dist / (1.5 if e["main"] else 1.0)
        adj[e["from"]].append((e["to"], cost, e["id"]))

    return adj


def dijkstra(adj, source, target):
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

    if dist.get(target, float("inf")) == float("inf"):
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