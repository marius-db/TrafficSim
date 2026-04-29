"""
visualizador pygame de la simulacion de trafico.
corre en un hilo daemon separado del loop asyncio del servidor.
"""

import math
import threading
import time

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

BG = (11, 13, 18)
ROAD_MAIN = (35, 40, 64)
ROAD_SIDE = (25, 28, 42)
ROAD_BORDER = (46, 52, 80)
LANE_DASH = (58, 64, 96)
NODE_FILL = (30, 34, 54)
CAR_COLOR = (90, 159, 255)
CAR_YIELD_COLOR = (255, 180, 40)
EV_COLOR = (0, 229, 255)
EV_SIREN_A = (0, 200, 255)
EV_SIREN_B = (255, 50, 50)
TEXT_ROAD = (120, 130, 170)
TEXT_MUTED = (80, 88, 120)
LIGHT_GREEN = (34, 197, 94)
LIGHT_YELLOW = (245, 158, 11)
LIGHT_RED = (239, 68, 68)
LIGHT_EV = (255, 255, 80)
LIGHT_BG = (12, 14, 20)
PANEL_BG = (16, 18, 28)
PANEL_BORDER = (40, 46, 72)
WHITE = (255, 255, 255)

WIN_W, WIN_H = 1280, 820
FPS = 60
ROAD_MAIN_W = 28
ROAD_SIDE_W = 14
SCALE_MIN = 0.25
SCALE_MAX = 8.0


class SimVisualizer:
    def __init__(self, sim):
        self._sim = sim
        self._thread = None
        self._running = False

    def start(self):
        if not PYGAME_AVAILABLE:
            print("[visualizer] pygame no disponible, ventana desactivada")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="sim-visualizer", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        pygame.init()
        screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        pygame.display.set_caption("CentralCore: Simulacion de Trafico")
        clock = pygame.time.Clock()

        font_road = pygame.font.SysFont("segoeui", 11)
        font_small = pygame.font.SysFont("segoeui", 10)
        font_big = pygame.font.SysFont("segoeui", 13, bold=True)
        font_panel = pygame.font.SysFont("segoeui", 12)

        city_cx = sum(n["x"] for n in self._sim.nodes) / max(1, len(self._sim.nodes))
        city_cy = sum(n["y"] for n in self._sim.nodes) / max(1, len(self._sim.nodes))
        scale = 1.0
        offset_x = WIN_W / 2 - city_cx * scale
        offset_y = WIN_H / 2 - city_cy * scale

        drag_start = None
        drag_offset = (0.0, 0.0)
        t_total = 0.0

        while self._running:
            dt = clock.tick(FPS) / 1000.0
            t_total += dt
            w, h = screen.get_size()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        drag_start = event.pos
                        drag_offset = (offset_x, offset_y)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        drag_start = None
                elif event.type == pygame.MOUSEMOTION:
                    if drag_start:
                        dx = event.pos[0] - drag_start[0]
                        dy = event.pos[1] - drag_start[1]
                        offset_x = drag_offset[0] + dx
                        offset_y = drag_offset[1] + dy
                elif event.type == pygame.MOUSEWHEEL:
                    factor = 1.12 if event.y > 0 else 0.89
                    new_scale = max(SCALE_MIN, min(SCALE_MAX, scale * factor))
                    mx, my = pygame.mouse.get_pos()
                    offset_x = mx - (mx - offset_x) * (new_scale / scale)
                    offset_y = my - (my - offset_y) * (new_scale / scale)
                    scale = new_scale
                elif event.type == pygame.VIDEORESIZE:
                    w, h = event.size
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._running = False
                    elif event.key == pygame.K_r:
                        scale = 1.0
                        offset_x = w / 2 - city_cx * scale
                        offset_y = h / 2 - city_cy * scale

            def to_screen(sx, sy):
                return sx * scale + offset_x, sy * scale + offset_y

            screen.fill(BG)
            sim = self._sim

            self._draw_edges(screen, sim, to_screen, scale, font_road)

            if sim.ev is not None:
                self._draw_ev_route(screen, sim, to_screen, scale)

            self._draw_nodes(screen, sim, to_screen, scale)
            self._draw_lights(screen, sim, to_screen, scale, t_total)
            self._draw_cars(screen, sim, to_screen, scale)

            if sim.ev is not None:
                self._draw_ev(screen, sim.ev, to_screen, scale, t_total)

            self._draw_panel(screen, sim, font_panel, font_big, w, h)

            hint = font_small.render(
                f"Zoom: {scale:.2f}x   [scroll] zoom  [drag] mover  [R] reset  [ESC] cerrar",
                True, TEXT_MUTED)
            screen.blit(hint, (10, h - 20))

            pygame.display.flip()

        pygame.quit()

    def _draw_edges(self, screen, sim, to_screen, scale, font_road):
        density_map = sim.compute_densities()

        for e in sim.edges:
            na = sim.node_map.get(e["from"])
            nb = sim.node_map.get(e["to"])
            if na is None or nb is None:
                continue
            ax, ay = to_screen(na["x"], na["y"])
            bx, by = to_screen(nb["x"], nb["y"])
            is_main = e.get("main", False)
            road_w = max(2, int((ROAD_MAIN_W if is_main else ROAD_SIDE_W) * scale))

            dens = density_map.get(e["id"], 0.0)
            if dens < 0.4:
                road_col = ROAD_MAIN if is_main else ROAD_SIDE
            elif dens < 0.7:
                road_col = _lerp_color(ROAD_MAIN if is_main else ROAD_SIDE, (80, 55, 10), (dens - 0.4) / 0.3)
            else:
                road_col = _lerp_color((80, 55, 10), (90, 20, 20), (dens - 0.7) / 0.3)

            border_w = road_w + max(2, int(2 * scale))
            pygame.draw.line(screen, ROAD_BORDER, (ax, ay), (bx, by), border_w)
            pygame.draw.line(screen, road_col, (ax, ay), (bx, by), road_w)

            if is_main and e.get("lanes", 1) > 1 and scale > 0.6:
                self._draw_lane_dashes(screen, ax, ay, bx, by, e.get("lanes", 2), road_w)

        if scale > 0.55:
            drawn_names = set()
            for e in sim.edges:
                name = e.get("name")
                if not name or name in drawn_names:
                    continue
                drawn_names.add(name)
                na = sim.node_map.get(e["from"])
                nb = sim.node_map.get(e["to"])
                if na is None or nb is None:
                    continue
                ax, ay = to_screen(na["x"], na["y"])
                bx, by = to_screen(nb["x"], nb["y"])
                mx, my = (ax + bx) / 2, (ay + by) / 2
                dx, dy = bx - ax, by - ay
                angle = math.degrees(math.atan2(dy, dx))
                if angle > 90 or angle < -90:
                    angle += 180
                surf = font_road.render(name, True, TEXT_ROAD)
                rotated = pygame.transform.rotate(surf, -angle)
                rect = rotated.get_rect(center=(int(mx), int(my)))
                screen.blit(rotated, rect)

    def _draw_lane_dashes(self, screen, ax, ay, bx, by, lanes, road_w):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length < 1:
            return
        nx, ny = -dy / length, dx / length
        dash_len = max(4, int(road_w * 0.35))
        gap_len = max(4, int(road_w * 0.3))
        steps = int(length / (dash_len + gap_len))
        for i in range(1, lanes):
            offset = (i - lanes / 2.0) * (road_w / lanes)
            for s in range(steps):
                t0 = s * (dash_len + gap_len) / length
                t1 = (s * (dash_len + gap_len) + dash_len) / length
                if t1 > 1.0:
                    break
                x0 = ax + dx * t0 + nx * offset
                y0 = ay + dy * t0 + ny * offset
                x1 = ax + dx * t1 + nx * offset
                y1 = ay + dy * t1 + ny * offset
                pygame.draw.line(screen, LANE_DASH, (int(x0), int(y0)), (int(x1), int(y1)), 1)

    def _draw_ev_route(self, screen, sim, to_screen, scale):
        route = sim.ev.route if sim.ev else []
        if len(route) < 2:
            return
        points = []
        for nid in route:
            n = sim.node_map.get(nid)
            if n:
                points.append(to_screen(n["x"], n["y"]))
        if len(points) >= 2:
            lw = max(3, int(9 * scale))
            surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            for i in range(len(points) - 1):
                pygame.draw.line(surf, (43, 127, 255, 100),
                                 (int(points[i][0]), int(points[i][1])),
                                 (int(points[i+1][0]), int(points[i+1][1])), lw)
            screen.blit(surf, (0, 0))

    def _draw_nodes(self, screen, sim, to_screen, scale):
        for n in sim.nodes:
            sx, sy = to_screen(n["x"], n["y"])
            r = max(2, int((10 if n["main"] else 5) * scale))
            pygame.draw.circle(screen, NODE_FILL, (int(sx), int(sy)), r)
            pygame.draw.circle(screen, (43, 80, 160), (int(sx), int(sy)), r, max(1, int(scale)))

    def _draw_lights(self, screen, sim, to_screen, scale, t_total):
        if scale < 0.42:
            return

        DIR_OFFSETS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
        r_lt = max(2, int(4 * scale))
        dist = max(4, int(14 * scale))

        for lt in sim.lights.values():
            node = sim.node_map.get(lt.node_id)
            if node is None:
                continue
            nx, ny = to_screen(node["x"], node["y"])
            off = DIR_OFFSETS.get(lt.dir, (0, 0))
            lx = int(nx + off[0] * dist)
            ly = int(ny + off[1] * dist)

            state = lt.get_state()
            ev_preempted = getattr(lt, "ev_preempted", False)

            if ev_preempted:
                #fast strobe between bright yellow-white and state color to signal EV override
                flash = (math.sin(t_total * math.pi * 8) > 0)
                col = LIGHT_EV if flash else (LIGHT_GREEN if state == "green" else LIGHT_RED)
                glow_r = r_lt + max(2, int(3 * scale))
                glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (*LIGHT_EV, 80), (glow_r + 2, glow_r + 2), glow_r)
                screen.blit(glow_surf, (lx - glow_r - 2, ly - glow_r - 2))
            else:
                col = LIGHT_GREEN if state == "green" else LIGHT_YELLOW if state == "yellow" else LIGHT_RED

            pygame.draw.circle(screen, LIGHT_BG, (lx, ly), r_lt + 1)
            pygame.draw.circle(screen, col, (lx, ly), r_lt)

    def _draw_cars(self, screen, sim, to_screen, scale):
        car_w = max(3, int(9 * scale))
        car_h = max(2, int(4 * scale))

        for car in sim.cars:
            na = sim.node_map.get(car.node_a)
            nb = sim.node_map.get(car.node_b)
            if na is None or nb is None:
                continue
            sx, sy = to_screen(car.get_xy()[0], car.get_xy()[1])
            dx, dy = nb["x"] - na["x"], nb["y"] - na["y"]
            angle = math.atan2(dy, dx)
            perp_x = -math.sin(angle)
            perp_y = math.cos(angle)

            lane_off = (car.lane - 1.5) * max(2, int(4 * scale))
            #yielding cars get pushed far to the right so it's very visible
            yield_off = getattr(car, "yield_offset", 0.0)
            pull_over = yield_off * max(4, int(10 * scale))
            total_off = lane_off + pull_over

            cx = sx + perp_x * total_off
            cy = sy + perp_y * total_off

            color = CAR_YIELD_COLOR if car.yielding_to_ev else CAR_COLOR
            _draw_rotated_rect(screen, color, cx, cy, car_w, car_h, angle)

    def _draw_ev(self, screen, ev, to_screen, scale, t_total):
        x, y = ev.get_xy()
        sx, sy = to_screen(x, y)

        #pulsing blue/red siren glow
        siren_phase = (math.sin(t_total * math.pi * 4) + 1) / 2
        siren_col = _lerp_color(EV_SIREN_A, EV_SIREN_B, siren_phase)
        glow_r = max(10, int(28 * scale))
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*siren_col, 55), (glow_r + 2, glow_r + 2), glow_r)
        screen.blit(glow_surf, (int(sx) - glow_r - 2, int(sy) - glow_r - 2))

        ew = max(5, int(14 * scale))
        eh = max(3, int(8 * scale))
        pygame.draw.rect(screen, EV_COLOR, (int(sx - ew/2), int(sy - eh/2), ew, eh), border_radius=3)

        cw = max(2, int(3 * scale))
        ch = max(3, int(6 * scale))
        cross_y = int(sy - eh/2 - ch - 1)
        pygame.draw.rect(screen, (255, 60, 60), (int(sx - cw//2), cross_y, cw, ch))
        pygame.draw.rect(screen, (255, 60, 60), (int(sx - ch//2), cross_y + ch//2 - cw//2, ch, cw))

    def _draw_panel(self, screen, sim, font, font_big, w, h):
        pw, ph = 230, 160
        px, py = w - pw - 10, 10
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((*PANEL_BG, 210))
        pygame.draw.rect(panel, PANEL_BORDER, (0, 0, pw, ph), 1)

        ev_preempted_count = sum(1 for lt in sim.lights.values() if getattr(lt, "ev_preempted", False))

        lines = [
            ("Simulacion de Trafico", font_big, WHITE),
            (f"Nodos: {len(sim.nodes)}", font, TEXT_ROAD),
            (f"Aristas: {len(sim.edges)}", font, TEXT_ROAD),
            (f"Semaforos: {len(sim.lights)}", font, TEXT_ROAD),
            (f"Coches: {len(sim.cars)}", font, TEXT_ROAD),
            (f"Vehiculo emergencia: {'Activo' if sim.ev else 'Inactivo'}", font,
             EV_COLOR if sim.ev else TEXT_MUTED),
        ]
        if ev_preempted_count > 0:
            lines.append((f"Semaforos EV activos: {ev_preempted_count}", font, LIGHT_EV))

        y_off = 10
        for text, f, col in lines:
            surf = f.render(text, True, col)
            panel.blit(surf, (12, y_off))
            y_off += surf.get_height() + 4

        screen.blit(panel, (px, py))


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _draw_rotated_rect(surface, color, cx, cy, w, h, angle):
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    hw, hh = w / 2, h / 2
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    rotated = [
        (cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a)
        for x, y in corners
    ]
    pygame.draw.polygon(surface, color, [(int(x), int(y)) for x, y in rotated])