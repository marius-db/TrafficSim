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

#paleta de colores (tema oscuro tipo google maps nocturno)
BG  = (11,  13,  18)
ROAD_MAIN = (35,  40,  64)
ROAD_SIDE = (25,  28,  42)
ROAD_BORDER = (46,  52,  80)
LANE_DASH = (58,  64,  96)
NODE_FILL = (30,  34,  54)
NODE_STROKE = (43, 127, 255, 128)
CAR_COLOR = (90, 159, 255)
EV_COLOR = (0,  229, 255)
ROUTE_COLOR = (43, 127, 255, 160)
POINT_A = (34, 197,  94)
POINT_B = (239, 68,  68)
TEXT_ROAD = (120, 130, 170)
TEXT_MUTED = (80,  88, 120)
LIGHT_GREEN = (34, 197,  94)
LIGHT_YELLOW = (245, 158, 11)
LIGHT_RED = (239,  68,  68)
LIGHT_BG = (12,  14,  20)
PANEL_BG = (16,  18,  28)
PANEL_BORDER = (40,  46,  72)
WHITE = (255, 255, 255)

WIN_W, WIN_H = 1280, 820
FPS = 60

#grosor de carretera en px (antes de escalar)
ROAD_MAIN_W = 28
ROAD_SIDE_W = 16

#zoom min/max
SCALE_MIN = 0.25
SCALE_MAX = 8.0


class SimVisualizer:
    """
    ventana pygame que renderiza el estado de la simulacion.
    uso:
        vis = SimVisualizer(sim)
        vis.start()        # lanza el hilo
        ...
        vis.stop()
    """

    def __init__(self, sim):
        self._sim = sim
        self._thread = None
        self._running = False

    def start(self):
        if not PYGAME_AVAILABLE:
            print("[visualizer] pygame no disponible, ventana desactivada")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run, name="sim-visualizer", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    #loop principal (corre en su propio hilo)
    def _run(self):
        pygame.init()
        screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        pygame.display.set_caption("CentralCore: Simulación de Tráfico")
        clock = pygame.time.Clock()

        font_road = pygame.font.SysFont("segoeui", 11, bold=False)
        font_small = pygame.font.SysFont("segoeui", 10)
        font_big = pygame.font.SysFont("segoeui", 13, bold=True)
        font_panel = pygame.font.SysFont("segoeui", 12)

        #transformacion inicial: centrar la ciudad en la ventana
        city_cx = sum(n["x"] for n in self._sim.nodes) / max(1, len(self._sim.nodes))
        city_cy = sum(n["y"] for n in self._sim.nodes) / max(1, len(self._sim.nodes))
        scale = 1.0
        offset_x = WIN_W / 2 - city_cx * scale
        offset_y = WIN_H / 2 - city_cy * scale

        drag_start = None
        drag_offset = (0.0, 0.0)

        while self._running:
            dt = clock.tick(FPS) / 1000.0
            w, h = screen.get_size()

            #eventos
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
                        #reset camara
                        scale = 1.0
                        offset_x = w / 2 - city_cx * scale
                        offset_y = h / 2 - city_cy * scale

            def to_screen(sx, sy):
                return sx * scale + offset_x, sy * scale + offset_y

            #fondo
            screen.fill(BG)

            sim = self._sim   #snapshot de referencia (no lock, acepta datos ligeramente desincronizados)

            #calles
            self._draw_edges(screen, sim, to_screen, scale, font_road)

            #ruta ev
            if sim.ev is not None:
                self._draw_ev_route(screen, sim, to_screen, scale)

            #nodos
            self._draw_nodes(screen, sim, to_screen, scale)

            #semaforos
            self._draw_lights(screen, sim, to_screen, scale)

            #coches
            self._draw_cars(screen, sim, to_screen, scale)

            #vehiculo de emergencia
            if sim.ev is not None:
                self._draw_ev(screen, sim.ev, to_screen, scale)

            #panel de info
            self._draw_panel(screen, sim, font_panel, font_big, w, h)

            #hint zoom
            hint = font_small.render(f"Zoom: {scale:.2f}x   [scroll] zoom  [drag] mover  [R] reset  [ESC] cerrar", True, TEXT_MUTED)
            screen.blit(hint, (10, h - 20))

            pygame.display.flip()

        pygame.quit()

    #metodos de dibujo
    def _draw_edges(self, screen, sim, to_screen, scale, font_road):
        density_map = sim.compute_densities()

        #acumular aristas a dibujar
        for e in sim.edges:
            na = sim.node_map.get(e["from"])
            nb = sim.node_map.get(e["to"])
            if na is None or nb is None:
                continue

            ax, ay = to_screen(na["x"], na["y"])
            bx, by = to_screen(nb["x"], nb["y"])
            is_main = e.get("main", False)
            road_w = int((ROAD_MAIN_W if is_main else ROAD_SIDE_W) * scale)
            road_w = max(2, road_w)

            #color segun densidad
            dens = density_map.get(e["id"], 0.0)
            if dens < 0.4:
                road_col = ROAD_MAIN if is_main else ROAD_SIDE
            elif dens < 0.7:
                road_col = _lerp_color(ROAD_MAIN if is_main else ROAD_SIDE, (80, 55, 10), (dens - 0.4) / 0.3)
            else:
                road_col = _lerp_color((80, 55, 10), (90, 20, 20), (dens - 0.7) / 0.3)

            #borde
            border_w = road_w + max(2, int(2 * scale))
            pygame.draw.line(screen, ROAD_BORDER, (ax, ay), (bx, by), border_w)
            #cuerpo
            pygame.draw.line(screen, road_col, (ax, ay), (bx, by), road_w)

            #lineas de carril punteadas en calles principales
            if is_main and e.get("lanes", 1) > 1 and scale > 0.6:
                self._draw_lane_dashes(screen, ax, ay, bx, by, e.get("lanes", 2), road_w)

        #nombres de calles (por encima de todo)
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
                #mantener texto siempre legible (no al reves)
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
                pygame.draw.line(surf, (43, 127, 255, 120),
                                 (int(points[i][0]), int(points[i][1])),
                                 (int(points[i+1][0]), int(points[i+1][1])), lw)
            screen.blit(surf, (0, 0))

    def _draw_nodes(self, screen, sim, to_screen, scale):
        for n in sim.nodes:
            sx, sy = to_screen(n["x"], n["y"])
            r = int((10 if n["main"] else 6) * scale)
            r = max(2, r)
            pygame.draw.circle(screen, NODE_FILL, (int(sx), int(sy)), r)
            pygame.draw.circle(screen, (43, 80, 160), (int(sx), int(sy)), r, max(1, int(scale)))

    def _draw_lights(self, screen, sim, to_screen, scale):
        if scale < 0.45:
            return   #demasiado alejado para ver los semaforos

        #dibujar un punto de color por semaforo en la posicion de su nodo
        #desplazado segun la direccion que cubre
        DIR_OFFSETS = {
            "N": (0,  -1),
            "S": (0,   1),
            "E": ( 1,  0),
            "W": (-1,  0),
        }
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
            col = LIGHT_GREEN if state == "green" else LIGHT_YELLOW if state == "yellow" else LIGHT_RED

            pygame.draw.circle(screen, LIGHT_BG, (lx, ly), r_lt + 1)
            pygame.draw.circle(screen, col,      (lx, ly), r_lt)

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

            #offset de carril
            nx_, ny_ = -math.sin(angle), math.cos(angle)
            lane_off  = (car.lane - 1.5) * max(2, int(4 * scale))
            cx = sx + nx_ * lane_off
            cy = sy + ny_ * lane_off

            _draw_rotated_rect(screen, CAR_COLOR, cx, cy, car_w, car_h, angle)

    def _draw_ev(self, screen, ev, to_screen, scale):
        x, y = ev.get_xy()
        sx, sy = to_screen(x, y)
        ew = max(5, int(14 * scale))
        eh = max(3, int(8 * scale))
        pygame.draw.rect(screen, EV_COLOR, (int(sx - ew/2), int(sy - eh/2), ew, eh), border_radius=3)
        #cruz roja
        cw = max(2, int(3 * scale))
        ch = max(3, int(6 * scale))
        cross_y = int(sy - eh/2 - ch - 1)
        pygame.draw.rect(screen, (255, 60, 60), (int(sx - cw//2), cross_y, cw, ch))
        pygame.draw.rect(screen, (255, 60, 60), (int(sx - ch//2), cross_y + ch//2 - cw//2, ch, cw))

    def _draw_panel(self, screen, sim, font, font_big, w, h):
        pw, ph = 220, 140
        px, py = w - pw - 10, 10
        panel  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((*PANEL_BG, 210))
        pygame.draw.rect(panel, PANEL_BORDER, (0, 0, pw, ph), 1)

        lines = [
            ("Simulación de Tráfico", font_big, WHITE),
            (f"Nodos: {len(sim.nodes)}", font, TEXT_ROAD),
            (f"Aristas: {len(sim.edges)}", font, TEXT_ROAD),
            (f"Semáforos: {len(sim.lights)}", font, TEXT_ROAD),
            (f"Coches: {len(sim.cars)}", font, TEXT_ROAD),
            (f"Vehículo emergencia:  {'Activo' if sim.ev else 'Inactivo'}", font,
             EV_COLOR if sim.ev else TEXT_MUTED),
        ]

        y_off = 10
        for text, f, col in lines:
            surf = f.render(text, True, col)
            panel.blit(surf, (12, y_off))
            y_off += surf.get_height() + 4

        screen.blit(panel, (px, py))


# helpers
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
    corners = [
        (-hw, -hh), ( hw, -hh), ( hw,  hh), (-hw,  hh)
    ]
    rotated = [
        (cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a)
        for x, y in corners
    ]
    pygame.draw.polygon(surface, color, [(int(x), int(y)) for x, y in rotated])