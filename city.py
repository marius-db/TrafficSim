import math
import random

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
    rng = random.Random(seed)

    nodes = []
    edges = []
    lights = []

    node_counter = [0]
    edge_counter = [0]
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

    #grid spacing with much more variance so blocks are clearly different sizes
    #some blocks are narrow (tight residential), some wide (commercial districts)
    #this breaks the uniform look while keeping the city readable
    col_gaps = [0, 85, 200, 120, 220, 95, 185, 115, 160]   #9 columns
    row_gaps = [0, 95, 190, 110, 200, 85, 175, 115]         #8 rows

    margin_x, margin_y = 50, 45
    col_xs = [margin_x]
    for g in col_gaps[1:]:
        col_xs.append(col_xs[-1] + g)
    row_ys = [margin_y]
    for g in row_gaps[1:]:
        row_ys.append(row_ys[-1] + g)

    n_cols = len(col_xs)
    n_rows = len(row_ys)

    main_grid = {}

    for ci, bx in enumerate(col_xs):
        for ri, by in enumerate(row_ys):
            #more jitter in interior, nodes can drift quite a bit from the grid line
            interior = (ci > 0 and ci < n_cols-1 and ri > 0 and ri < n_rows-1)
            jmax = 28 if interior else 8
            jx = rng.randint(-jmax, jmax)
            jy = rng.randint(-jmax, jmax)
            node = {"id": nid(), "x": float(bx + jx), "y": float(by + jy), "main": True}
            nodes.append(node)
            main_grid[(ci, ri)] = node["id"]

    h_street_names = {}
    for ri in range(n_rows):
        h_street_names[ri] = MAIN_STREET_NAMES_H[ri % len(MAIN_STREET_NAMES_H)]

    def add_road(a_id, b_id, lanes, is_main, name):
        edges.append({"id": eid(), "from": a_id, "to": b_id, "lanes": lanes, "main": is_main, "name": name})
        edges.append({"id": eid(), "from": b_id, "to": a_id, "lanes": lanes, "main": is_main, "name": name})

    SKIP_PROB = 0.10

    for ri in range(n_rows):
        sname = h_street_names[ri]
        for ci in range(n_cols - 1):
            if rng.random() < SKIP_PROB:
                continue
            a = main_grid[(ci, ri)]
            b = main_grid[(ci+1, ri)]
            add_road(a, b, 3, True, sname)

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

    #diagonal shortcuts between main intersections, these are still main-to-main
    #so they're fine, they behave like cut-through avenues
    DIAG_PROB = 0.22
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            if rng.random() < DIAG_PROB:
                a = main_grid[(ci, ri)]
                b = main_grid[(ci+1, ri+1)]
                add_road(a, b, 2, True, next_side())
            if rng.random() < DIAG_PROB * 0.4:
                a = main_grid[(ci+1, ri)]
                b = main_grid[(ci, ri+1)]
                add_road(a, b, 2, True, next_side())

    for (ci, ri), node_id in main_grid.items():
        for direction in ["N", "S", "E", "W"]:
            lights.append({"id": lid(), "node": node_id, "dir": direction})

    #secondary nodes: placed inside blocks, only ever connect to OTHER secondary nodes
    #never to main intersections. side streets run parallel/between blocks, not into them.
    #this gives side roads their own network that feeds into the main grid only via routing

    secondary = {}
    node_map_local = {n["id"]: n for n in nodes}

    def get_n(nid_):
        return node_map_local.get(nid_)

    #some blocks get 2 secondary nodes instead of 1 (wider blocks feel more filled)
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            tl = get_n(main_grid[(ci, ri)])
            tr = get_n(main_grid[(ci+1, ri)])
            bl = get_n(main_grid[(ci, ri+1)])
            br = get_n(main_grid[(ci+1, ri+1)])

            block_w = (tr["x"] + br["x"]) / 2 - (tl["x"] + bl["x"]) / 2
            block_h = (bl["y"] + br["y"]) / 2 - (tl["y"] + tr["y"]) / 2

            #wider/taller blocks get a second secondary node
            n_sec = 2 if (block_w > 155 or block_h > 145) and rng.random() < 0.65 else 1

            block_sec_ids = []
            for _ in range(n_sec):
                #position in thirds of the block so multiple nodes spread out
                frac_x = rng.uniform(0.2, 0.8)
                frac_y = rng.uniform(0.2, 0.8)
                cx = tl["x"] + (tr["x"] - tl["x"]) * frac_x + (bl["x"] - tl["x"]) * frac_y
                cy = tl["y"] + (tr["y"] - tl["y"]) * frac_x + (bl["y"] - tl["y"]) * frac_y
                cx += rng.randint(-20, 20)
                cy += rng.randint(-20, 20)

                min_x = min(tl["x"], tr["x"], bl["x"], br["x"]) + 14
                max_x = max(tl["x"], tr["x"], bl["x"], br["x"]) - 14
                min_y = min(tl["y"], tr["y"], bl["y"], br["y"]) + 14
                max_y = max(tl["y"], tr["y"], bl["y"], br["y"]) - 14
                if min_x < max_x: cx = max(min_x, min(max_x, cx))
                if min_y < max_y: cy = max(min_y, min(max_y, cy))

                sec = {"id": nid(), "x": cx, "y": cy, "main": False}
                nodes.append(sec)
                node_map_local[sec["id"]] = sec
                block_sec_ids.append(sec["id"])

            #connect the secondary nodes within this block to each other if there are 2
            if len(block_sec_ids) == 2:
                add_road(block_sec_ids[0], block_sec_ids[1], 1, False, next_side())

            #store first secondary node per block for neighbor connections
            secondary[(ci, ri)] = block_sec_ids[0]
            #store extras under offset keys
            if len(block_sec_ids) == 2:
                secondary[(ci, ri, "b")] = block_sec_ids[1]

    #connect secondary nodes to neighboring secondary nodes only, never to main grid
    #this forms the side road network running through the interior of blocks
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            cur_id = secondary.get((ci, ri))
            if cur_id is None:
                continue
            cur_n = get_n(cur_id)

            right_id = secondary.get((ci+1, ri))
            if right_id:
                right_n = get_n(right_id)
                dist = math.hypot(cur_n["x"] - right_n["x"], cur_n["y"] - right_n["y"])
                ref_w = col_gaps[ci+1] if ci+1 < len(col_gaps) else 160
                if dist < ref_w * 0.9 and rng.random() < 0.55:
                    add_road(cur_id, right_id, 1, False, next_side())

            down_id = secondary.get((ci, ri+1))
            if down_id:
                down_n = get_n(down_id)
                dist = math.hypot(cur_n["x"] - down_n["x"], cur_n["y"] - down_n["y"])
                ref_h = row_gaps[ri+1] if ri+1 < len(row_gaps) else 145
                if dist < ref_h * 0.9 and rng.random() < 0.55:
                    add_road(cur_id, down_id, 1, False, next_side())

            #also try diagonal neighbor connections for more irregular side road layout
            diag_id = secondary.get((ci+1, ri+1))
            if diag_id and rng.random() < 0.25:
                diag_n = get_n(diag_id)
                dist = math.hypot(cur_n["x"] - diag_n["x"], cur_n["y"] - diag_n["y"])
                if dist < 200:
                    add_road(cur_id, diag_id, 1, False, next_side())

            #connect extra secondary node in this block to neighbors too
            extra_id = secondary.get((ci, ri, "b"))
            if extra_id:
                extra_n = get_n(extra_id)
                for neighbor_key in [(ci+1, ri), (ci, ri+1), (ci-1, ri), (ci, ri-1)]:
                    nb_id = secondary.get(neighbor_key)
                    if nb_id and rng.random() < 0.4:
                        nb_n = get_n(nb_id)
                        dist = math.hypot(extra_n["x"] - nb_n["x"], extra_n["y"] - nb_n["y"])
                        if dist < 220:
                            add_road(extra_id, nb_id, 1, False, next_side())

    #dead-end alleys from border secondary nodes, not border main nodes
    #so they extend outward from the side road network, not from main avenues
    border_secondary = []
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            if ci == 0 or ci == n_cols-2 or ri == 0 or ri == n_rows-2:
                sid = secondary.get((ci, ri))
                if sid:
                    border_secondary.append(sid)

    rng.shuffle(border_secondary)
    n_alleys = rng.randint(5, 9)

    for base_id in border_secondary[:n_alleys]:
        base = node_map_local.get(base_id)
        angle = rng.uniform(0, 2 * math.pi)
        length = rng.randint(45, 80)
        end_x = base["x"] + math.cos(angle) * length
        end_y = base["y"] + math.sin(angle) * length
        end_x = max(20, min(CITY_W - 20, end_x))
        end_y = max(20, min(CITY_H - 20, end_y))
        alley = {"id": nid(), "x": end_x, "y": end_y, "main": False}
        nodes.append(alley)
        add_road(base_id, alley["id"], 1, False, next_side())

    return nodes, edges, lights


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