"""Minijuegos de los momentos clave del partido (penales, tiros libres y ocasiones claras).

La dificultad depende de las estadísticas: cuanto mejor sea el tiro del ejecutor frente al nivel del
portero rival, más lenta es la barra / el puntero, más pequeño el alcance del portero y más tiempo hay
para decidir. Si el tiempo se acaba, el disparo sale solo. Todos tienen un botón para *simular* la jugada
con la probabilidad del modelo (eventos.prob_conv).

La escena está dibujada en perspectiva (cámara detrás del balón, ver `proy`): arco con red en 3D,
césped con franjas, tribunas, barrera y portero con sombra. La lógica del juego sigue usando el plano de
la portería (PORTERIA) como zona de impacto.

Interfaz común: ``dibujar(ui) -> None | "ok" | "auto"``; al terminar el resultado queda en
``self.resultado`` ("gol" | "fallo" desde el punto de vista de quien dispara) y ``self.motivo``.
"""
import math
import random

import numpy as np
import pygame

from . import ui as U

PANEL = pygame.Rect(190, 110, 900, 560)
SCENE = pygame.Rect(PANEL.x + 12, PANEL.y + 96, PANEL.w - 24, 362)         # x 202..1078 · y 206..568
PORTERIA = pygame.Rect(400, 220, 480, 160)                                   # plano de la boca del arco
PUNTO = (640, 545)                                                           # punto penal (en pantalla)
COLS = ("izquierda", "centro", "derecha")

PX_M = 480 / 7.32                                           # píxeles por metro en el plano de la portería


def _camara(altura, dist_porteria):
    """Cámara a `altura` m y `dist_porteria` m del plano del arco, mirando al centro. Siempre dibuja la portería
    de 480x160 px en PORTERIA (así la zona de impacto no depende de la cámara). -> (horizonte, foco, altura, dist)."""
    return (PORTERIA.bottom - altura * PX_M, PX_M * dist_porteria, altura, dist_porteria)


# Penal y ocasión: detrás del punto penal (11 m), a 1,37 m de altura y 6 m del balón: el balón cae en (640, 545).
CAM_PENAL = _camara(1.37, 17.0)
# Tiro libre: el balón está a `dist` m del arco (18-28) y la barrera a 9,15 m de él. Cámara alta y retrasada (toma de
# TV), que deja ver el arco por encima de la barrera. El balón cae siempre en (640, 545) y el horizonte no se mueve;
# lo que cambia con la distancia es el tamaño del arco: a 18 m ocupa 480x160 px y, más lejos, se ve proporcionalmente
# más chico (a 28 m, 64 %). La zona de impacto, el portero y el puntero se escalan con él.
ALTURA_TV = 3.2
HORIZ_TV = 170.0
D_REF = 18.0
D_LIBRE_BASE = 22                                           # distancia por omisión (jugadas creadas sin `dist`)

BLANCO = (240, 244, 250)
PIEL = (238, 200, 168)


def k_libre(dist):
    return D_REF / dist


def cam_libre(dist):
    pxm_g = PX_M * k_libre(dist)                                    # px por metro en el plano del arco
    pxm_b = (PUNTO[1] - HORIZ_TV) / ALTURA_TV                       # px por metro en el balón (lo fija en y = 545)
    foco = dist / (1 / pxm_g - 1 / pxm_b)
    return (HORIZ_TV, foco, ALTURA_TV, foco / pxm_g)


def porteria_libre(dist):
    """Rect de la boca del arco en pantalla para un tiro libre a `dist` m."""
    k = k_libre(dist)
    y_gol = proy(0, 0, 0, cam_libre(dist))[1]
    return pygame.Rect(int(PUNTO[0] - PORTERIA.w * k / 2), int(y_gol - PORTERIA.h * k), int(PORTERIA.w * k),
                       int(PORTERIA.h * k))


def proy(u, d, h=0.0, cam=CAM_PENAL):
    """(lateral en m, distancia a la línea de gol en m, altura en m) -> píxeles de pantalla."""
    horiz, foco, alt, z0 = cam
    s = foco / (z0 - d)
    return (PUNTO[0] + u * s, horiz + (alt - h) * s)


def escala(d, cam=CAM_PENAL):
    return cam[1] / (cam[3] - d)


def dificultad(diff):
    """diff = tiro del ejecutor - nivel del portero (desde la perspectiva de quien dispara)."""
    if diff >= 6:
        return "Fácil", U.VERDE
    if diff >= -6:
        return "Media", U.AMARILLO
    return "Difícil", U.ROJO


def _triangulo(t):
    t = t % 2.0
    return t if t <= 1 else 2 - t


def _rot(p, ang, o):
    c, s = math.cos(ang), math.sin(ang)
    return (o[0] + p[0] * c - p[1] * s, o[1] + p[0] * s + p[1] * c)


# ====================================================================== escena (fondo en caché)
_FONDOS = {}


def _fondo(cam=CAM_PENAL):
    """Estadio nocturno visto desde detrás del balón: cielo, tribuna, vallas, césped con franjas y líneas."""
    if cam in _FONDOS:
        return _FONDOS[cam]
    W, H = SCENE.size
    s = pygame.Surface((W, H))
    oy = SCENE.y
    y_cesped = int(proy(0, -8, 0.0, cam)[1])
    y_valla = int(y_cesped - 0.9 * escala(-8, cam))               # techo de las vallas (0,9 m)
    for y in range(H):                                           # cielo
        s.fill(U.mezclar((7, 11, 24), (20, 32, 58), min(1.0, y / max(1, y_valla - oy))), (0, y, W, 1))
    rnd = random.Random(7)
    for y in range(8, y_valla - oy, 5):                          # tribuna: público como puntos de color
        base = 0.35 + 0.65 * y / max(1, y_valla - oy)
        for x in range(0, W, 5):
            if rnd.random() < 0.82:
                v = rnd.randint(50, 150)
                col = (int(v * base * rnd.uniform(0.8, 1.2)), int(v * base * 0.85), int(v * base * rnd.uniform(0.7, 1.3)))
                pygame.draw.rect(s, tuple(min(255, max(0, c)) for c in col), (x + rnd.randint(0, 2), y + rnd.randint(0, 2), 3, 3))
    foco = pygame.Surface((W, H), pygame.SRCALPHA)
    for cx in (50, W - 50):                                      # focos
        for r in range(260, 20, -22):
            pygame.draw.circle(foco, (200, 220, 255, 7), (cx, -10), r)
    s.blit(foco, (0, 0))
    pygame.draw.rect(s, (16, 38, 88), (0, y_valla - oy, W, y_cesped - y_valla))      # vallas publicitarias
    for x in range(0, W, 118):
        pygame.draw.rect(s, (24, 56, 122), (x + 4, y_valla - oy + 4, 108, y_cesped - y_valla - 8))
        for k in range(3):
            pygame.draw.rect(s, (196, 214, 244), (x + 16 + k * 28, y_valla - oy + 14, 18, 5))
            pygame.draw.rect(s, (120, 150, 200), (x + 16 + k * 28, y_valla - oy + 24, 12, 4))
    pygame.draw.line(s, (90, 120, 190), (0, y_valla - oy), (W, y_valla - oy), 2)
    d = -8.0                                                      # césped: franjas cada 2,5 m
    i = 0
    while d < cam[3] - 3 and proy(0, d, 0, cam)[1] < SCENE.bottom + 40:
        y0, y1 = proy(0, d, 0, cam)[1], proy(0, d + 2.5, 0, cam)[1]
        col = (30, 104, 54) if i % 2 == 0 else (37, 118, 62)
        pygame.draw.rect(s, col, (0, int(y0) - oy, W, int(y1 - y0) + 2))
        d += 2.5
        i += 1
    blanco = (228, 238, 232)
    for dd, grosor in ((0.0, 3), (5.5, 2), (16.5, 2)):           # línea de gol, área chica y borde del área grande
        y = int(proy(0, dd, 0, cam)[1]) - oy
        if -5 < y < H + 5:
            pygame.draw.line(s, blanco, (0, y), (W, y), grosor)
    arco = []                                                     # media luna del área (9,15 m del punto penal)
    for sg in (-1, 1):
        pts = []
        for k in range(15):
            dd = 16.5 + k * (11 + 9.15 - 16.5) / 14
            u = sg * math.sqrt(max(0.0, 9.15 ** 2 - (dd - 11) ** 2))
            x, y = proy(u, dd, 0, cam)
            pts.append((x - SCENE.x, y - oy))
        arco.append(pts)
    if all(-5000 < p[1] < 5000 for pts in arco for p in pts):
        pygame.draw.lines(s, blanco, False, arco[0], 2)
        pygame.draw.lines(s, blanco, False, arco[1], 2)
    sx, sy = proy(0, 11, 0, cam)                                  # punto penal
    anch = max(8, int(0.09 * escala(11, cam)))
    pygame.draw.ellipse(s, blanco, (sx - SCENE.x - anch // 2, sy - oy - anch // 4, anch, max(4, anch // 2)))
    for k in range(40):                                           # viñeta lateral
        a = int(110 * (1 - k / 40) ** 2)
        v = pygame.Surface((1, H), pygame.SRCALPHA)
        v.fill((0, 0, 0, a))
        s.blit(v, (k, 0))
        s.blit(v, (W - 1 - k, 0))
    _FONDOS[cam] = s
    return s


def _linea(s, col, a, b, w=1):
    pygame.draw.line(s, col, a, b, w)


def dibujar_porteria(ui, cam=CAM_PENAL):
    """Escena completa: fondo, red con profundidad y marco (postes y travesaño) en 3D."""
    s = ui.surf
    s.set_clip(SCENE)                                           # el techo de la red no debe invadir el encabezado
    s.blit(_fondo(cam), SCENE.topleft)

    def proy(u, d, h=0.0, cam=cam):                             # noqa: F811  (todo lo de esta función usa la cámara dada)
        return globals()["proy"](u, d, h, cam)
    ancho, alto, fondo = 3.66, 2.44, 2.1
    red = (82, 98, 124)
    # panel trasero (oscuro) y red
    bl, br = proy(-ancho, -fondo, 0), proy(ancho, -fondo, 0)
    tl, tr = proy(-ancho, -fondo, alto), proy(ancho, -fondo, alto)
    fl, fr = proy(-ancho, 0, 0), proy(ancho, 0, 0)
    ftl, ftr = proy(-ancho, 0, alto), proy(ancho, 0, alto)
    panel = pygame.Surface((SCENE.w, SCENE.h), pygame.SRCALPHA)
    ox, oy = SCENE.topleft

    def L(p):
        return (p[0] - ox, p[1] - oy)
    pygame.draw.polygon(panel, (10, 14, 24, 215), [L(bl), L(br), L(tr), L(tl)])
    for pts in ([fl, ftl, tl, bl], [fr, ftr, tr, br], [ftl, ftr, tr, tl]):          # laterales y techo
        pygame.draw.polygon(panel, (16, 22, 36, 150), [L(p) for p in pts])
    s.blit(panel, (ox, oy))
    for k in range(0, 19):                                                          # malla del fondo
        u = -ancho + k * (2 * ancho / 18)
        _linea(s, red, proy(u, -fondo, 0), proy(u, -fondo, alto), 1)
    for k in range(0, 7):
        h = k * alto / 6
        _linea(s, red, proy(-ancho, -fondo, h), proy(ancho, -fondo, h), 1)
    for k in range(0, 5):                                                           # malla de los laterales
        h = k * alto / 4
        for sg in (-1, 1):
            _linea(s, red, proy(sg * ancho, 0, h), proy(sg * ancho, -fondo, h), 1)
    for k in range(0, 19):                                                          # malla del techo
        u = -ancho + k * (2 * ancho / 18)
        _linea(s, red, proy(u, 0, alto), proy(u, -fondo, alto), 1)
    for pts in ((tl, tr), (bl, tl), (br, tr)):                                      # marco trasero
        _linea(s, (150, 160, 180), pts[0], pts[1], 3)
    for a, b in ((ftl, tl), (ftr, tr), (fl, bl), (fr, br)):                         # largueros hacia atrás
        _linea(s, (170, 180, 200), a, b, 3)
    pygame.draw.lines(s, BLANCO, False, [fl, ftl, ftr, fr], 8)                      # postes y travesaño delanteros
    pygame.draw.lines(s, (150, 160, 178), False, [(fl[0] + 3, fl[1]), (ftl[0] + 3, ftl[1]), (ftr[0] - 3, ftr[1]),
                                                   (fr[0] - 3, fr[1])], 2)
    pygame.draw.circle(s, BLANCO, (int(ftl[0]), int(ftl[1])), 4)
    pygame.draw.circle(s, BLANCO, (int(ftr[0]), int(ftr[1])), 4)
    s.set_clip(None)


def _sombra(s, cx, y, w, h=None):
    h = h or max(4, int(w * 0.26))
    pygame.draw.ellipse(s, (20, 70, 38), (int(cx - w / 2), int(y - h / 2), int(w), int(h)))


def dibujar_jugador(ui, cx, base, a, c1, c2, pose="muro"):
    """Futbolista de pie (barrera). `a` es su altura en píxeles."""
    s = ui.surf
    _sombra(s, cx, base, a * 0.55)
    for dx in (-0.075, 0.075):                                          # piernas y botines
        pygame.draw.line(s, (236, 238, 244), (cx + dx * a, base - 0.27 * a), (cx + dx * a, base - 0.04 * a), max(3, int(a * 0.08)))
        pygame.draw.ellipse(s, (22, 24, 30), (cx + dx * a - a * 0.07, base - a * 0.055, a * 0.14, a * 0.07))
    pygame.draw.rect(s, c2, (cx - a * 0.15, base - a * 0.47, a * 0.30, a * 0.21), border_radius=3)     # short
    pygame.draw.rect(s, c1, (cx - a * 0.17, base - a * 0.80, a * 0.34, a * 0.37), border_radius=int(a * 0.07))   # camiseta
    for sg in (-1, 1):                                                  # brazos
        pygame.draw.line(s, c1, (cx + sg * a * 0.16, base - a * 0.76), (cx + sg * a * 0.07, base - a * 0.52), max(3, int(a * 0.08)))
    if pose == "muro":                                                  # manos cubriendo
        pygame.draw.circle(s, PIEL, (int(cx), int(base - a * 0.50)), max(2, int(a * 0.055)))
    pygame.draw.circle(s, (46, 34, 28), (int(cx), int(base - a * 0.90)), int(a * 0.105))
    pygame.draw.circle(s, PIEL, (int(cx), int(base - a * 0.88)), int(a * 0.095))
    pygame.draw.rect(s, (20, 24, 34), (cx - a * 0.17, base - a * 0.80, a * 0.34, a * 0.37), 1, border_radius=int(a * 0.07))


ESC_PORTERO = 1.32            # un portero de 1,90 m mide ~78 % de los 2,44 m del arco (≈ 125 px con los brazos arriba: ~150)


def dibujar_portero(ui, cx, base_y, ang=0.0, color=(255, 193, 7), trim=(25, 28, 40), esc=ESC_PORTERO):
    """Portero con guantes, short y botines; `ang` lo inclina (estirada) alrededor de sus pies."""
    s = ui.surf
    o = (cx, base_y)
    _sombra(s, cx, base_y + 2, 62 * esc)

    def P(x, y):
        return _rot((x * esc, y * esc), ang, o)

    def g(v):                                                   # grosores y radios escalados
        return max(1, int(round(v * esc)))
    pygame.draw.polygon(s, trim, [P(-14, -14), P(14, -14), P(15, 4), P(-15, 4)])               # short
    for a in (-1, 1):                                                                           # piernas, medias y botines
        pygame.draw.line(s, (232, 234, 240), P(a * 8, 2), P(a * 12, 21), g(8))
        bt = P(a * 13, 24)
        pygame.draw.ellipse(s, (22, 24, 30), (bt[0] - g(9), bt[1] - g(4), g(18), g(8)))
    torso = [P(-14, -64), P(14, -64), P(14, -10), P(-14, -10)]
    pygame.draw.polygon(s, color, torso)
    pygame.draw.polygon(s, (18, 20, 28), torso, 2)
    for a in (-1, 1):                                                                           # brazos y guantes
        m, h = P(a * 12, -58), P(a * 31, -84)
        pygame.draw.line(s, color, m, h, g(8))
        pygame.draw.circle(s, (250, 250, 252), (int(h[0]), int(h[1])), g(7))
        pygame.draw.circle(s, (18, 20, 28), (int(h[0]), int(h[1])), g(7), 2)
    cabeza = P(0, -76)
    pygame.draw.circle(s, (46, 34, 28), (int(cabeza[0]), int(cabeza[1] - g(1))), g(11))
    pygame.draw.circle(s, PIEL, (int(cabeza[0]), int(cabeza[1] + g(1))), g(10))
    pygame.draw.circle(s, (18, 20, 28), (int(cabeza[0]), int(cabeza[1])), g(11), 2)


def dibujar_balon(ui, pos, r=9, giro=0.0, suelo=None):
    """Balón con panel central y parches; `suelo` es la y del césped bajo él (para la sombra)."""
    s = ui.surf
    x, y = int(pos[0]), int(pos[1])
    if suelo is not None:
        _sombra(s, x, suelo, r * 2.3, max(3, int(r * 0.75)))
    pygame.draw.circle(s, (208, 213, 224), (x, y), r)
    pygame.draw.circle(s, (248, 248, 250), (x - max(1, r // 6), y - max(1, r // 6)), max(1, r - 2))
    pent = [(x + r * 0.36 * math.cos(giro + k * 1.2566), y + r * 0.36 * math.sin(giro + k * 1.2566)) for k in range(5)]
    pygame.draw.polygon(s, (28, 28, 34), pent)
    for k in range(5):
        a = giro + k * 1.2566 + 0.628
        pygame.draw.circle(s, (34, 34, 40), (int(x + r * 0.80 * math.cos(a)), int(y + r * 0.80 * math.sin(a))), max(1, int(r * 0.22)))
    pygame.draw.circle(s, (34, 36, 44), (x, y), r, 1)


def _zonas():
    w, h = PORTERIA.w // 3, PORTERIA.h // 2
    return {(c, f): pygame.Rect(PORTERIA.x + c * w, PORTERIA.y + f * h, w, h) for c in range(3) for f in range(2)}


def _vuelo(a, f):
    """Posición, radio y sombra del balón en el instante f (0..1) de su viaje desde el punto penal hacia a['dest']."""
    x0, y0 = PUNTO[0], PUNTO[1] - 14
    x = x0 + (a["dest"][0] - x0) * f
    y = max(SCENE.y + 12, y0 + (a["dest"][1] - y0) * f - 22 * math.sin(math.pi * f))     # sin salirse de la escena
    suelo = PUNTO[1] + (a.get("suelo", PORTERIA.bottom) - PUNTO[1]) * f
    return (x, y), 14 - (14 - a.get("r_fin", 7)) * f, suelo


class Minijuego:
    titulo = ""

    def __init__(self, e, rng, col=None):
        self.e, self.rng = e, rng
        self.ejecutor, self.tiro = e["jug"], float(e["tiro"])
        self.portero, self.ovr_gk = e["gk"]
        self.col = col or {}
        self.fase = "jugar"
        self.resultado = None
        self.motivo = ""
        self.msg = ""
        self.detalle = ""
        self.t_rev = 0
        self.delegado = False
        self.t_ini = None                       # se fija al dibujar por primera vez
        self.limite = 8.0
        self.tarde = False

    # --- utilidades comunes
    def _cabecera(self, ui, sub, diff):
        ui.panel(PANEL, (12, 18, 30), 14, U.BORDE)
        ui.texto(self.titulo, (PANEL.centerx, PANEL.y + 10), 44, U.AMARILLO, anchor="tc", titulo=True)
        ui.texto(sub, (PANEL.centerx, PANEL.y + 56), 15, U.TEXTO, anchor="tc", maxw=PANEL.w - 40)
        d, col = dificultad(diff)
        ui.texto(f"Dificultad: {d}", (PANEL.centerx, PANEL.y + 76), 15, col, True, "tc")

    def _fijar_tiempo(self, diff, base):
        """Fácil +2 s, difícil -1 s respecto al tiempo base."""
        self.limite = base + (2 if diff >= 6 else -1 if diff < -6 else 0)

    def _tiempo(self, ui):
        """Barra de cuenta atrás (arriba a la derecha). Devuelve los segundos que quedan."""
        ahora = pygame.time.get_ticks()
        if self.t_ini is None:
            self.t_ini = ahora
        rest = max(0.0, self.limite - (ahora - self.t_ini) / 1000)
        frac = rest / self.limite
        col = U.VERDE if frac > 0.5 else U.AMARILLO if frac > 0.25 else U.ROJO
        x, y, w = PANEL.right - 250, PANEL.y + 34, 220
        ui.texto("TIEMPO", (x, y - 18), 12, U.APAGADO, True)
        ui.texto(f"{rest:.1f} s", (x + w, y - 18), 13, col, True, "tr")
        pygame.draw.rect(ui.surf, (40, 52, 76), (x, y, w, 12), border_radius=6)
        if frac > 0:
            pygame.draw.rect(ui.surf, col, (x, y, max(6, int(w * frac)), 12), border_radius=6)
        if rest < 2.0 and int(ahora / 220) % 2 == 0:
            ui.texto("¡Rápido!", (x + w // 2, y + 18), 14, U.ROJO, True, "tc")
        return rest

    def _pie(self, ui, instruccion, ayuda=""):
        """Texto de instrucciones debajo de la escena (no tapa la portería)."""
        ui.texto_fit(instruccion, (PANEL.x + 30, SCENE.bottom + 8), 21, 14, PANEL.w - 280, U.VERDE, True)
        if ayuda:
            ui.texto(ayuda, (PANEL.x + 30, SCENE.bottom + 38), 14, U.APAGADO, maxw=PANEL.w - 280)

    def _boton_auto(self, ui, etiqueta="Simular jugada"):
        if ui.boton((PANEL.right - 210, PANEL.bottom - 62, 190, 44), etiqueta, tam=15,
                    tip="El resultado se decide con las estadísticas,\nsin que tengas que jugar."):
            self.delegado = True

    def _revelado(self, ui, dur=600):
        """Devuelve la fracción 0..1 de la animación; al terminar muestra el resultado bajo la escena."""
        f = min(1.0, (pygame.time.get_ticks() - self.t_rev) / dur)
        if f >= 1.0:
            col = U.VERDE if self.color_ok else U.ROJO
            ui.texto(self.msg, (PANEL.x + 30, SCENE.bottom + 2), 46, col, anchor="tl", titulo=True)
            if self.detalle:
                ui.texto(self.detalle, (PANEL.x + 32, SCENE.bottom + 58), 16, U.TEXTO, anchor="tl", maxw=PANEL.w - 300)
        return f

    def _continuar(self, ui):
        if ui.boton((PANEL.right - 250, PANEL.bottom - 62, 220, 46), "Continuar", True, tam=18) or \
                pygame.K_SPACE in ui.teclas or pygame.K_RETURN in ui.teclas:
            return "ok"
        return None

    def _terminar(self, gol, msg, detalle="", motivo="", color_ok=None):
        self.resultado = "gol" if gol else "fallo"
        self.msg = msg
        self.detalle = ("¡Se acabó el tiempo! " if self.tarde else "") + detalle
        self.motivo = motivo
        self.color_ok = gol if color_ok is None else color_ok
        self.fase = "rev"
        self.t_rev = pygame.time.get_ticks()

    def _portero_color(self):
        base = self.col.get("gk", ((255, 193, 7), (25, 28, 40)))
        return base[0], base[1]

    def _zona_hover(self, ui, r, relleno=(255, 255, 255, 46), borde=BLANCO):
        sup = pygame.Surface(r.size, pygame.SRCALPHA)
        sup.fill(relleno)
        ui.surf.blit(sup, r.topleft)
        pygame.draw.rect(ui.surf, borde, r, 3)

    def _rejilla_zonas(self, ui):
        for r in _zonas().values():
            pygame.draw.rect(ui.surf, (255, 255, 255), r, 1)


# ===================================================================== penal a favor
class PenalFavor(Minijuego):
    titulo = "¡PENAL A FAVOR!"

    def __init__(self, e, rng, col=None):
        super().__init__(e, rng, col)
        self.zona = None
        self.diff = self.tiro - self.ovr_gk
        self.ancho = float(np.clip(0.16 + 0.004 * self.diff, 0.08, 0.30))
        self.vel = float(np.clip(1.1 - 0.012 * self.diff, 0.7, 1.8))
        self.centro = float(rng.uniform(0.4, 0.75))
        self.t0 = 0
        self.anim = None
        self._fijar_tiempo(self.diff, 9)

    def dibujar(self, ui):
        self._cabecera(ui, f"Tirador: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui)
        zonas = _zonas()
        kc, kt = self._portero_color()
        if self.fase == "jugar":
            rest = self._tiempo(ui)
            dibujar_portero(ui, PORTERIA.centerx, PORTERIA.bottom + 4, 0.0, kc, kt)
            self._rejilla_zonas(ui)
            self._boton_auto(ui)
            if self.delegado:
                return "auto"
            if self.zona is None:
                self._pie(ui, "1) Elige dónde disparar", "Arriba es más difícil de atajar, pero puedes irte por encima.")
                for z, r in zonas.items():
                    if r.collidepoint(ui.mouse):
                        self._zona_hover(ui, r)
                for z, r in zonas.items():
                    if ui.clic_en(r):
                        self.zona = z
                        self.t0 = pygame.time.get_ticks()
                        break
                if self.zona is None and rest <= 0:
                    self.tarde = True
                    self.zona = (int(self.rng.integers(3)), int(self.rng.integers(2)))
                    self._disparar(float(self.rng.random()))
            else:
                r = zonas[self.zona]
                self._zona_hover(ui, r, (255, 193, 7, 60), (255, 193, 7))
                self._pie(ui, "2) Detén la barra dentro de la zona verde")
                barra = pygame.Rect(PANEL.x + 30, PANEL.bottom - 58, 430, 26)
                pygame.draw.rect(ui.surf, (40, 52, 76), barra, border_radius=8)
                zv = pygame.Rect(barra.x + int(barra.w * (self.centro - self.ancho)), barra.y,
                                 int(barra.w * 2 * self.ancho), barra.h)
                pygame.draw.rect(ui.surf, (46, 204, 113), zv, border_radius=6)
                pos = _triangulo((pygame.time.get_ticks() - self.t0) / 1000 * self.vel)
                mx = barra.x + int(barra.w * pos)
                pygame.draw.rect(ui.surf, (255, 255, 255), (mx - 3, barra.y - 6, 6, barra.h + 12), border_radius=3)
                ui.texto("Clic o ESPACIO para disparar", (barra.right + 14, barra.centery), 14, U.APAGADO, anchor="ml")
                if rest <= 0:
                    self.tarde = True
                    self._disparar(pos)
                elif ui.click or pygame.K_SPACE in ui.teclas:
                    ui.consumir_click()
                    self._disparar(pos)
            if self.fase == "jugar":                                  # si el disparo salió por tiempo, ya no se dibuja quieto
                dibujar_balon(ui, (PUNTO[0], PUNTO[1] - 14), 14, suelo=PUNTO[1] + 2)
            return None
        # --- revelado
        f = self._revelado(ui)
        a = self.anim
        kx = PORTERIA.centerx + (a["gk_x"] - PORTERIA.centerx) * f
        dibujar_portero(ui, kx, PORTERIA.bottom + 4, a["ang"] * f, kc, kt)
        pos, r, suelo = _vuelo(a, f)
        dibujar_balon(ui, pos, int(r), giro=f * 9, suelo=suelo)
        return self._continuar(ui) if f >= 1.0 else None

    def _disparar(self, pos):
        rng = self.rng
        col, fila = self.zona
        e = abs(pos - self.centro)
        zr = _zonas()[self.zona]
        dest = zr.center
        p_leer = float(np.clip(0.30 + 0.005 * (self.ovr_gk - self.tiro), 0.12, 0.55))
        col_k = col if rng.random() < p_leer else int(rng.choice([c for c in range(3) if c != col]))
        gk_x = PORTERIA.x + PORTERIA.w // 6 + col_k * PORTERIA.w // 3
        ang = (col_k - 1) * 0.9
        if e > 2.4 * self.ancho:
            lado = 1 if rng.random() < 0.5 else -1
            self.anim = {"dest": (dest[0] + lado * 150, PORTERIA.y - 70), "gk_x": gk_x, "ang": ang}
            self._terminar(False, "¡FUERA!", "El disparo se fue desviado.", "se fue desviado")
            return
        if fila == 0 and e > 1.3 * self.ancho and rng.random() < 0.4:
            self.anim = {"dest": (dest[0], PORTERIA.y - 60), "gk_x": gk_x, "ang": ang}
            self._terminar(False, "¡POR ENCIMA!", "Pasó sobre el travesaño.", "por encima del travesaño")
            return
        calidad = 0.55 if e < 0.5 * self.ancho else 1.0 if e < self.ancho else 1.15
        p_save = float(np.clip((0.45 if fila == 0 else 0.62) * calidad, 0.1, 0.85))
        self.anim = {"dest": dest, "gk_x": gk_x, "ang": ang}
        if col_k == col and rng.random() < p_save:
            self._terminar(False, "¡ATAJADO!", f"{self.portero} adivinó el lado.", "atajado")
        else:
            self._terminar(True, "¡GOOOL!", f"{self.ejecutor} la manda al fondo de la red.")


# ===================================================================== penal en contra
class PenalContra(Minijuego):
    titulo = "¡PENAL EN CONTRA!"

    def __init__(self, e, rng, col=None):
        super().__init__(e, rng, col)
        self.diff = self.ovr_gk - self.tiro                 # desde la perspectiva del portero propio
        sesgo = sum(map(ord, self.ejecutor)) % 3
        pc = np.array([0.28, 0.28, 0.28])
        pc[sesgo] += 0.16
        pc[1] -= 0.10
        self.pcol = pc / pc.sum()
        self.sesgo = sesgo
        self.anim = None
        self._fijar_tiempo(self.diff, 8)

    def dibujar(self, ui):
        # aquí e["gk"] es el portero PROPIO (el del equipo del usuario)
        self._cabecera(ui, f"Ejecuta: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Tu portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui)
        zonas = _zonas()
        kc, kt = self._portero_color()
        if self.fase == "jugar":
            rest = self._tiempo(ui)
            self._rejilla_zonas(ui)
            self._pie(ui, "Elige hacia dónde se lanza tu portero",
                      f"Pista: suele patear hacia la {COLS[self.sesgo]} ({self.pcol[self.sesgo]:.0%} de sus penales).")
            self._boton_auto(ui)
            if self.delegado:
                return "auto"
            for z, r in zonas.items():
                if r.collidepoint(ui.mouse):
                    self._zona_hover(ui, r)
            for z, r in zonas.items():
                if ui.clic_en(r):
                    self._resolver(z)
                    return None
            if rest <= 0:
                self.tarde = True
                self._resolver((1, 1))                      # no se movió: se queda en el centro
                return None
            dibujar_portero(ui, PORTERIA.centerx, PORTERIA.bottom + 4, 0.0, kc, kt)
            dibujar_balon(ui, (PUNTO[0], PUNTO[1] - 14), 14, suelo=PUNTO[1] + 2)
            return None
        f = self._revelado(ui)
        a = self.anim
        kx = PORTERIA.centerx + (a["gk_x"] - PORTERIA.centerx) * f
        dibujar_portero(ui, kx, PORTERIA.bottom + 4, a["ang"] * f, kc, kt)
        pos, r, suelo = _vuelo(a, f)
        dibujar_balon(ui, pos, int(r), giro=f * 9, suelo=suelo)
        return self._continuar(ui) if f >= 1.0 else None

    def _resolver(self, dive):
        rng = self.rng
        col_t = int(rng.choice(3, p=self.pcol))
        fila_t = 0 if rng.random() < 0.45 else 1
        zona = (col_t, fila_t)
        dest = _zonas()[zona].center
        gk_x = PORTERIA.x + PORTERIA.w // 6 + dive[0] * PORTERIA.w // 3
        ang = (dive[0] - 1) * 0.9
        p_fuera = float(np.clip(0.12 - 0.002 * (self.tiro - 75), 0.03, 0.2))
        if rng.random() < p_fuera:
            self.anim = {"dest": (dest[0] + 140, PORTERIA.y - 70), "gk_x": gk_x, "ang": ang}
            self._terminar(False, "¡FALLÓ!", f"{self.ejecutor} la manda fuera.", "se fue fuera", color_ok=True)
            return
        if dive == zona:
            p_save = 0.72
        elif dive[0] == col_t:
            p_save = 0.28
        else:
            p_save = 0.0
        p_save = float(np.clip(p_save + (0.004 * (self.ovr_gk - 75) if p_save else 0), 0, 0.9))
        self.anim = {"dest": dest, "gk_x": gk_x, "ang": ang}
        if rng.random() < p_save:
            self._terminar(False, "¡ATAJASTE!", f"{self.portero} detiene el penal.", "atajado", color_ok=True)
        else:
            self._terminar(True, "GOL DEL RIVAL", f"{self.ejecutor} la manda " +
                           ("al lado contrario." if dive[0] != col_t else "pese a tu estirada."), color_ok=False)


# ===================================================================== ocasión / tiro libre
class Remate(Minijuego):
    def __init__(self, e, rng, col=None):
        super().__init__(e, rng, col)
        self.libre = e["tipo"] == "tiro_libre"
        self.dist = int(e.get("dist") or D_LIBRE_BASE)
        self.titulo = "¡TIRO LIBRE!" if self.libre else "¡OCASIÓN CLARA!"
        self.diff = self.tiro - self.ovr_gk
        if self.libre:                                       # cada metro más lejos pesa 0,5 puntos de ventaja del portero
            self.diff -= 0.5 * (self.dist - 23)
        s = float(np.clip(1.0 - 0.012 * self.diff, 0.6, 1.6))
        self.vel = s * (1.15 if self.libre else 1.0)
        self.ph = (float(rng.uniform(0, 6.28)), float(rng.uniform(0, 6.28)))
        # geometría: en el tiro libre todo se escala con el tamaño del arco (k = 1 a 18 m, 0,64 a 28 m)
        self.k = k_libre(self.dist) if self.libre else 1.0
        self.cam = cam_libre(self.dist) if self.libre else CAM_PENAL
        self.por = porteria_libre(self.dist) if self.libre else PORTERIA
        self.margen = (30 + (3.0 * (self.dist - D_REF) if self.libre else 0)) * self.k      # la mira se aleja más del arco
        self.kw = float(np.clip(110 + (self.ovr_gk - 70) * 1.6, 80, 170)) * self.k
        self.kx = float(rng.uniform(self.por.x + self.kw / 2, self.por.right - self.kw / 2))
        self.esc_gk = ESC_PORTERO * self.k
        self.muro = None
        if self.libre:
            # Barrera de 5 jugadores a 9,15 m del balón, bien adelantada respecto al portero.
            lado = 1 if rng.random() < 0.5 else -1
            u0 = lado * float(rng.uniform(0.8, 1.8))                     # desvío lateral en metros
            d_barrera = self.dist - 9.15
            s_b = escala(d_barrera, self.cam)
            self.muro_dib = {"x0": PUNTO[0] + u0 * s_b, "base": proy(0, d_barrera, 0, self.cam)[1],
                             "alto": 1.75 * s_b, "paso": 0.48 * s_b}
            m = self.muro_dib
            ancho = 5 * m["paso"]
            self.muro = pygame.Rect(int(m["x0"] - ancho / 2), int(m["base"] - m["alto"]), int(ancho), int(m["alto"]))
        self.t0 = pygame.time.get_ticks()
        self.anim = None
        self._fijar_tiempo(self.diff, 7)

    def _retícula(self, ahora):
        t = (ahora - self.t0) / 1000 * self.vel
        cx, cy = self.por.center
        return (cx + (self.por.w / 2 + self.margen) * math.sin(t * 1.7 + self.ph[0]),
                cy + (self.por.h / 2 + 22 * self.k) * math.sin(t * 2.3 + self.ph[1]))

    def _marca_distancia(self, ui):
        """Línea de puntos del balón a la línea de gol, con la distancia en metros."""
        x = PUNTO[0] + 1
        for y in range(PUNTO[1] - 30, self.por.bottom + 8, -12):
            pygame.draw.line(ui.surf, (240, 244, 250), (x, y), (x, y - 6), 2)
        txt = f"{self.dist} m"
        w = ui.fuente(15, True).size(txt)[0] + 14
        r = pygame.Rect(0, 0, w, 22)
        r.center = (x + 36, PUNTO[1] - 38)
        ui.panel(r, (10, 14, 24), 6, (120, 140, 180))
        ui.texto(txt, r.center, 15, (240, 244, 250), True, "mc")

    def _dibujar_muro(self, ui):
        c1, c2 = self.col.get("muro", ((96, 108, 130), (30, 34, 46)))
        d = self.muro_dib
        for i in range(5):
            dibujar_jugador(ui, d["x0"] + (i - 2) * d["paso"], d["base"], d["alto"], c1, c2)

    def dibujar(self, ui):
        quien = f"Tiro libre a {self.dist} m" if self.libre else "Mano a mano"
        self._cabecera(ui, f"{quien}: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui, self.cam)
        ahora = pygame.time.get_ticks()
        kc, kt = self._portero_color()
        base_gk = self.por.bottom + 4 * self.k
        if self.fase == "jugar":
            rest = self._tiempo(ui)
            if self.libre:
                self._marca_distancia(ui)
            dibujar_portero(ui, self.kx, base_gk, 0.0, kc, kt, self.esc_gk)
            if self.muro:
                self._dibujar_muro(ui)
            self._pie(ui, "Clic o ESPACIO para disparar: apunta lejos del portero" +
                      (" y por encima de la barrera." if self.libre else "."),
                      "Si se acaba el tiempo, el disparo sale solo.")
            rx, ry = self._retícula(ahora)
            ui.surf.set_clip(SCENE)                                # la mira no se dibuja fuera de la escena
            for rr, w in ((15, 2), (4, 0)):
                pygame.draw.circle(ui.surf, (255, 80, 80), (int(rx), int(ry)), rr, w)
            pygame.draw.line(ui.surf, (255, 80, 80), (rx - 24, ry), (rx + 24, ry), 2)
            pygame.draw.line(ui.surf, (255, 80, 80), (rx, ry - 24), (rx, ry + 24), 2)
            ui.surf.set_clip(None)
            dibujar_balon(ui, (PUNTO[0], PUNTO[1] - 14), 14, suelo=PUNTO[1] + 2)
            self._boton_auto(ui)
            if self.delegado:
                return "auto"
            if rest <= 0:
                self.tarde = True
                self._disparar(rx, ry)
            elif ui.click or pygame.K_SPACE in ui.teclas:
                ui.consumir_click()
                self._disparar(rx, ry)
            return None
        f = self._revelado(ui)
        a = self.anim
        kx = self.kx + (a["gk_x"] - self.kx) * f
        dibujar_portero(ui, kx, base_gk, a["ang"] * f, kc, kt, self.esc_gk)
        if self.muro:
            self._dibujar_muro(ui)
        pos, r, suelo = _vuelo(a, f)
        dibujar_balon(ui, pos, int(r), giro=f * 9, suelo=suelo)
        return self._continuar(ui) if f >= 1.0 else None

    def _disparar(self, x, y):
        rng, k, por = self.rng, self.k, self.por
        p_leer = float(np.clip(0.15 + 0.004 * (self.ovr_gk - self.tiro), 0.05, 0.4))
        lee = rng.random() < p_leer
        gk_x = x if lee else self.kx
        gk_x = float(np.clip(gk_x, por.x + self.kw / 2, por.right - self.kw / 2))
        ang = float(np.clip((gk_x - self.kx) / (160 * k), -1, 1)) * 0.9
        alto = (124 + (24 if lee else 0)) * k                  # alcance vertical acorde al tamaño del portero
        kb = pygame.Rect(int(gk_x - self.kw / 2), int(por.bottom - alto), int(self.kw), int(alto))
        self.anim = {"dest": (x, y), "gk_x": gk_x, "ang": ang, "suelo": por.bottom, "r_fin": max(4, int(7 * k))}
        dentro = por.collidepoint(x, y)
        borde = dentro and min(x - por.x, por.right - x, y - por.y) < 8 * k
        if self.muro and self.muro.collidepoint(x, y):
            self._terminar(False, "¡A LA BARRERA!", "El balón rebota en la barrera.", "dio en la barrera")
        elif not dentro:
            self.anim["dest"] = (x, min(y, por.y - 40 * k) if y < por.y else y)
            self._terminar(False, "¡FUERA!", "Se va desviado.", "se fue desviado")
        elif borde:
            self._terminar(False, "¡AL PALO!", "El balón pega en el palo.", "dio en el palo")
        elif kb.collidepoint(x, y):
            self._terminar(False, "¡ATAJÓ!", f"{self.portero} " + ("leyó la jugada." if lee else "llega a tapar."),
                           "atajado")
        else:
            self._terminar(True, "¡GOOOL!", f"¡Qué definición de {self.ejecutor}!")


def crear(e, lado_usuario, rng, clubes=None):
    """Minijuego que corresponde a la jugada e desde el punto de vista del usuario.

    `clubes` ({"a": club, "b": club}) permite vestir la barrera y al portero con los colores del equipo que defiende.
    """
    col = None
    if clubes:
        from .camisetas import color_portero
        defensor = clubes["b" if e["lado"] == "a" else "a"]
        col = {"muro": (defensor.color, defensor.color2), "gk": color_portero(defensor.color, defensor.color2)}
    if e["tipo"] == "penal":
        if e["lado"] == lado_usuario:
            return PenalFavor(e, rng, col)
        # el rival patea: e["gk"] es el portero del usuario (portero del lado contrario al ejecutor)
        return PenalContra(e, rng, col)
    return Remate(e, rng, col)
