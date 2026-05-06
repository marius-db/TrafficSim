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


def build_city(seed=123):
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

    #secondary roads: connect between main roads only
    #collect all main road nodes (grid intersections)
    main_road_nodes = list(spine_nodes.values())
    secondary_all = []
    
    #helper: check if line segment intersects with existing secondary road
    def line_intersects_segment(p1, p2, seg_p1, seg_p2, tolerance=6.0):
        """Check if line p1-p2 intersects segment seg_p1-seg_p2"""
        def ccw(A, B, C):
            return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
        
        #check segment intersection
        if ccw(p1,seg_p1,seg_p2) != ccw(p2,seg_p1,seg_p2) and ccw(p1,p2,seg_p1) != ccw(p1,p2,seg_p2):
            return True
        return False
    
    #collect existing secondary road segments for intersection checking
    secondary_segments = []  #list of (node1_pos, node2_pos, edge_id)
    
    #helper: find intersection point between two line segments
    def find_intersection(p1, p2, p3, p4):
        """Find intersection point of line segments p1-p2 and p3-p4"""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(denom) < 1e-6:
            return None
        
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        if 0 < t < 1:
            ix = x1 + t*(x2-x1)
            iy = y1 + t*(y2-y1)
            return (ix, iy)
        return None
    
    #generate secondary roads: connect nearby main road nodes
    #with sparse, varied routing
    MAX_SECONDARY_DIST = 200
    used_pairs = set()
    roads_per_node = {}  #track how many secondary roads connect to each main node
    
    for main_idx, main_node_id in enumerate(main_road_nodes):
        mn = get_n(main_node_id)
        
        #find nearby main nodes to connect to
        candidates = []
        for other_idx, other_node_id in enumerate(main_road_nodes):
            if main_idx >= other_idx:
                continue
            on = get_n(other_node_id)
            dist = math.hypot(mn["x"] - on["x"], mn["y"] - on["y"])
            if 80 < dist < MAX_SECONDARY_DIST and rng.random() < 0.15:
                candidates.append((dist, other_idx, other_node_id, on))
        
        for dist, other_idx, other_node_id, on in sorted(candidates):
            pair = (min(main_idx, other_idx), max(main_idx, other_idx))
            if pair in used_pairs:
                continue
            
            #create 1-3 intermediate nodes between the main roads
            num_intermediate = rng.randint(1, 3)
            path_nodes = [main_node_id]
            
            for step in range(num_intermediate):
                t = (step + 1) / (num_intermediate + 1)
                #add randomness perpendicular to direct line
                mid_x = mn["x"] + (on["x"] - mn["x"]) * t
                mid_y = mn["y"] + (on["y"] - mn["y"]) * t
                
                #perpendicular offset
                dx = on["x"] - mn["x"]
                dy = on["y"] - mn["y"]
                length = math.hypot(dx, dy)
                if length > 0:
                    perp_x = -dy / length
                    perp_y = dx / length
                    offset = rng.uniform(-40, 40)
                    mid_x += perp_x * offset
                    mid_y += perp_y * offset
                
                #clamp to map bounds
                mid_x = max(30, min(970, mid_x))
                mid_y = max(30, min(750, mid_y))
                
                sec_id = make_node(mid_x, mid_y, False)
                secondary_all.append(sec_id)
                path_nodes.append(sec_id)
            
            path_nodes.append(other_node_id)
            
            #connect path nodes with roads
            sname = next_side()
            for pi in range(len(path_nodes) - 1):
                add_road(path_nodes[pi], path_nodes[pi+1], 1, False, sname)
            
            used_pairs.add(pair)

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