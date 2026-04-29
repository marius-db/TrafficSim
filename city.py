import math
import random

CITY_W = 1000
CITY_H = 780

MAIN_STREET_NAMES = [
    "Avda. de la Constitución", "Gran Vía", "Paseo de los Álamos",
    "Ronda Sur", "Calle Mayor", "Avda. del Parque",
    "Bulevar Norte", "Ronda del Este", "Calle de la Paz",
    "Avda. de Europa", "Paseo del Río", "Calle del Centro",
]
SIDE_NAMES = [
    "C/ San Juan", "C/ Ronda", "C/ Real", "C/ Nueva", "C/ Alta",
    "C/ Baja", "C/ del Molino", "C/ Olivos", "C/ Sol", "C/ Luna",
    "C/ Fuente", "C/ Palma", "C/ Cedros", "C/ Jardines", "C/ Flores",
    "C/ Cervantes", "C/ Colón", "C/ Isabel", "C/ Fernando", "C/ Castilla",
    "C/ Alcalá", "C/ Velázquez", "C/ Goya", "C/ Zurbarán", "C/ Murillo",
    "C/ Corredera", "C/ Ancha", "C/ Larga", "C/ Estrecha", "C/ Vieja",
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

    name_pool = SIDE_NAMES[:]
    rng.shuffle(name_pool)
    name_idx = [0]

    def next_side():
        n = name_pool[name_idx[0] % len(name_pool)]
        name_idx[0] += 1
        return n

    main_name_pool = MAIN_STREET_NAMES[:]
    rng.shuffle(main_name_pool)
    main_name_idx = [0]

    def next_main():
        n = main_name_pool[main_name_idx[0] % len(main_name_pool)]
        main_name_idx[0] += 1
        return n

    node_map_local = {}

    def make_node(x, y, is_main):
        n = {"id": nid(), "x": float(x), "y": float(y), "main": is_main}
        nodes.append(n)
        node_map_local[n["id"]] = n
        return n["id"]

    def add_road(a_id, b_id, lanes, is_main, name):
        edges.append({"id": eid(), "from": a_id, "to": b_id, "lanes": lanes, "main": is_main, "name": name})
        edges.append({"id": eid(), "from": b_id, "to": a_id, "lanes": lanes, "main": is_main, "name": name})

    def get_n(id_):
        return node_map_local.get(id_)

    #main grid: deliberately uneven column/row spacing to break uniform look
    #gaps vary a lot between columns so some blocks are wide, some cramped
    col_xs = [55, 160, 270, 400, 510, 640, 740, 855, 955]
    row_ys  = [60, 175, 310, 435, 560, 680, 755]

    n_cols = len(col_xs)
    n_rows = len(row_ys)

    spine_nodes = {}

    for ri, by in enumerate(row_ys):
        for ci, bx in enumerate(col_xs):
            border = (ci == 0 or ci == n_cols-1 or ri == 0 or ri == n_rows-1)
            jx = rng.randint(-6, 6) if border else rng.randint(-30, 30)
            jy = rng.randint(-5, 5) if border else rng.randint(-24, 24)
            spine_nodes[(ci, ri)] = make_node(bx + jx, by + jy, True)

    #horizontal connections with ~12% gaps
    for ri in range(n_rows):
        sname = next_main()
        for ci in range(n_cols - 1):
            if rng.random() < 0.12:
                continue
            add_road(spine_nodes[(ci, ri)], spine_nodes[(ci+1, ri)], 3, True, sname)

    #vertical connections with ~12% gaps
    for ci in range(n_cols):
        sname = next_main()
        for ri in range(n_rows - 1):
            if rng.random() < 0.12:
                continue
            add_road(spine_nodes[(ci, ri)], spine_nodes[(ci, ri+1)], 3, True, sname)

    #diagonal shortcuts: ~20% of blocks get a cut-through avenue
    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            if rng.random() < 0.20:
                add_road(spine_nodes[(ci, ri)], spine_nodes[(ci+1, ri+1)], 2, True, next_main())
            if rng.random() < 0.08:
                add_road(spine_nodes[(ci+1, ri)], spine_nodes[(ci, ri+1)], 2, True, next_main())

    for node_id in spine_nodes.values():
        for direction in ["N", "S", "E", "W"]:
            lights.append({"id": lid(), "node": node_id, "dir": direction})

    #secondary nodes: organic clusters inside blocks, connected to each other
    #AND connected to the surrounding main intersections via access roads
    #this is the key fix: side roads are NOT isolated, they connect to the main grid
    secondary_all = []

    for ci in range(n_cols - 1):
        for ri in range(n_rows - 1):
            tl = get_n(spine_nodes[(ci, ri)])
            tr = get_n(spine_nodes[(ci+1, ri)])
            bl = get_n(spine_nodes[(ci, ri+1)])
            br = get_n(spine_nodes[(ci+1, ri+1)])

            block_w = ((tr["x"] + br["x"]) - (tl["x"] + bl["x"])) / 2
            block_h = ((bl["y"] + br["y"]) - (tl["y"] + tr["y"])) / 2

            if block_w > 165 or block_h > 165:
                n_sec = rng.randint(2, 3)
            elif block_w > 100 or block_h > 100:
                n_sec = rng.randint(1, 2)
            else:
                n_sec = 1

            block_secs = []
            used_fracs = []

            for _ in range(n_sec):
                for attempt in range(14):
                    fx = rng.uniform(0.2, 0.8)
                    fy = rng.uniform(0.2, 0.8)
                    if not any(math.hypot(fx - ux, fy - uy) < 0.3 for ux, uy in used_fracs):
                        break
                used_fracs.append((fx, fy))

                cx = (tl["x"] * (1-fx) * (1-fy) + tr["x"] * fx * (1-fy)
                      + bl["x"] * (1-fx) * fy + br["x"] * fx * fy)
                cy = (tl["y"] * (1-fx) * (1-fy) + tr["y"] * fx * (1-fy)
                      + bl["y"] * (1-fx) * fy + br["y"] * fx * fy)
                cx += rng.randint(-12, 12)
                cy += rng.randint(-12, 12)

                min_x = min(tl["x"], tr["x"], bl["x"], br["x"]) + 14
                max_x = max(tl["x"], tr["x"], bl["x"], br["x"]) - 14
                min_y = min(tl["y"], tr["y"], bl["y"], br["y"]) + 14
                max_y = max(tl["y"], tr["y"], bl["y"], br["y"]) - 14
                if min_x < max_x: cx = max(min_x, min(max_x, cx))
                if min_y < max_y: cy = max(min_y, min(max_y, cy))

                sid = make_node(cx, cy, False)
                block_secs.append(sid)
                secondary_all.append(sid)

            sname = next_side()

            #connect secondary nodes within block as a chain
            for i in range(len(block_secs) - 1):
                add_road(block_secs[i], block_secs[i+1], 1, False, sname)

            #connect each secondary node to the nearest 1-2 main corners
            #this is what allows cars to transition between side streets and main roads
            corner_ids = [
                spine_nodes[(ci, ri)], spine_nodes[(ci+1, ri)],
                spine_nodes[(ci, ri+1)], spine_nodes[(ci+1, ri+1)]
            ]
            already = set()
            for sid in block_secs:
                sn = get_n(sid)
                sorted_corners = sorted(corner_ids, key=lambda cid: math.hypot(
                    get_n(cid)["x"] - sn["x"], get_n(cid)["y"] - sn["y"]))
                #always connect to nearest corner
                c1 = sorted_corners[0]
                k1 = (min(sid, c1), max(sid, c1))
                if k1 not in already:
                    add_road(sid, c1, 1, False, sname)
                    already.add(k1)
                #50% chance to connect to second nearest
                if rng.random() < 0.50:
                    c2 = sorted_corners[1]
                    k2 = (min(sid, c2), max(sid, c2))
                    if k2 not in already:
                        add_road(sid, c2, 1, False, sname)
                        already.add(k2)

    #cross-block secondary connections: side streets that pass through multiple blocks
    #proximity-based: only connect if within reasonable distance
    MAX_CROSS_DIST = 130
    for i in range(len(secondary_all)):
        sn_i = get_n(secondary_all[i])
        for j in range(i+1, len(secondary_all)):
            sn_j = get_n(secondary_all[j])
            d = math.hypot(sn_i["x"] - sn_j["x"], sn_i["y"] - sn_j["y"])
            if d < MAX_CROSS_DIST and rng.random() < 0.35:
                add_road(secondary_all[i], secondary_all[j], 1, False, next_side())

    return nodes, edges, lights


def build_adjacency(nodes, edges, densities=None):
    """
    traffic-aware routing: if densities passed, congested roads cost more
    so dijkstra naturally avoids jammed streets
    """
    node_map = {n["id"]: n for n in nodes}
    adj = {n["id"]: [] for n in nodes}

    for e in edges:
        nf = node_map.get(e["from"])
        nt = node_map.get(e["to"])
        if nf is None or nt is None:
            continue
        dist = math.hypot(nt["x"] - nf["x"], nt["y"] - nf["y"])
        speed_factor = 1.5 if e["main"] else 1.0
        base_cost = dist / speed_factor

        if densities:
            d = densities.get(e["id"], 0.0)
            #1x cost at free flow, up to 4x at standstill
            base_cost *= (1.0 + d * 3.0)

        adj[e["from"]].append((e["to"], base_cost, e["id"]))

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