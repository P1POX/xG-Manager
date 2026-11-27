"""Minijuegos de los momentos clave del partido (penales, tiros libres y ocasiones claras).

La dificultad depende de las estadísticas: cuanto mejor sea el tiro del ejecutor frente al nivel del
portero rival, más lenta es la barra / el puntero y más pequeño el alcance del portero. Todos tienen
un botón para *simular* la jugada con la probabilidad del modelo (eventos.prob_conv).

Interfaz común: ``dibujar(ui) -> None | "ok" | "auto"``; al terminar el resultado queda en
``self.resultado`` ("gol" | "fallo" desde el punto de vista de quien dispara) y ``self.motivo``.
"""
import math

import numpy as np
import pygame

from . import ui as U

PANEL = pygame.Rect(190, 110, 900, 560)
PORTERIA = pygame.Rect(400, 220, 480, 160)
PUNTO = (640, 545)
COLS = ("izquierda", "centro", "derecha")


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


def dibujar_porteria(ui, rect=PORTERIA):
    s = ui.surf
    pygame.draw.rect(s, (30, 78, 48), (PANEL.x + 8, rect.bottom, PANEL.w - 16, PANEL.bottom - rect.bottom - 8),
                     border_radius=8)
    pygame.draw.rect(s, (22, 30, 44), rect)
    for x in range(rect.x, rect.right + 1, 20):
        pygame.draw.line(s, (48, 62, 84), (x, rect.y), (x, rect.bottom), 1)
    for y in range(rect.y, rect.bottom + 1, 20):
        pygame.draw.line(s, (48, 62, 84), (rect.x, y), (rect.right, y), 1)
    pygame.draw.lines(s, (240, 244, 250), False, [rect.bottomleft, rect.topleft, rect.topright, rect.bottomright], 6)
    pygame.draw.line(s, (240, 244, 250), (rect.x - 60, rect.bottom), (rect.right + 60, rect.bottom), 3)
    pygame.draw.circle(s, (240, 244, 250), PUNTO, 4)


def dibujar_portero(ui, cx, base_y, ang=0.0, color=(255, 193, 7)):
    o = (cx, base_y)
    s = ui.surf
    torso = [_rot(p, ang, o) for p in ((-13, -62), (13, -62), (13, -6), (-13, -6))]
    pygame.draw.polygon(s, color, torso)
    pygame.draw.polygon(s, (20, 20, 20), torso, 2)
    for a in (-1, 1):
        pygame.draw.line(s, color, _rot((a * 12, -56), ang, o), _rot((a * 30, -82), ang, o), 7)
        pygame.draw.line(s, color, _rot((a * 8, -6), ang, o), _rot((a * 14, 18), ang, o), 7)
    cabeza = _rot((0, -74), ang, o)
    pygame.draw.circle(s, (238, 200, 168), cabeza, 10)
    pygame.draw.circle(s, (20, 20, 20), cabeza, 10, 2)


def dibujar_balon(ui, pos, r=9):
    pygame.draw.circle(ui.surf, (255, 255, 255), (int(pos[0]), int(pos[1])), r)
    pygame.draw.circle(ui.surf, (25, 25, 25), (int(pos[0]), int(pos[1])), r, 2)
    pygame.draw.circle(ui.surf, (25, 25, 25), (int(pos[0]), int(pos[1])), max(2, r // 3))


def _zonas():
    w, h = PORTERIA.w // 3, PORTERIA.h // 2
    return {(c, f): pygame.Rect(PORTERIA.x + c * w, PORTERIA.y + f * h, w, h) for c in range(3) for f in range(2)}


class Minijuego:
    titulo = ""

    def __init__(self, e, rng):
        self.e, self.rng = e, rng
        self.ejecutor, self.tiro = e["jug"], float(e["tiro"])
        self.portero, self.ovr_gk = e["gk"]
        self.fase = "jugar"
        self.resultado = None
        self.motivo = ""
        self.msg = ""
        self.t_rev = 0
        self.delegado = False

    # --- utilidades comunes
    def _cabecera(self, ui, sub, diff):
        ui.panel(PANEL, (12, 18, 30), 14, U.BORDE)
        ui.texto(self.titulo, (PANEL.centerx, PANEL.y + 10), 44, U.AMARILLO, anchor="tc", titulo=True)
        ui.texto(sub, (PANEL.centerx, PANEL.y + 56), 15, U.TEXTO, anchor="tc", maxw=PANEL.w - 40)
        d, col = dificultad(diff)
        ui.texto(f"Dificultad: {d}", (PANEL.centerx, PANEL.y + 78), 15, col, True, "tc")

    def _boton_auto(self, ui, etiqueta="Simular jugada"):
        if ui.boton((PANEL.right - 210, PANEL.bottom - 62, 190, 44), etiqueta, tam=15,
                    tip="El resultado se decide con las estadísticas,\nsin que tengas que jugar."):
            self.delegado = True

    def _revelado(self, ui, dur=600):
        """Devuelve la fracción 0..1 de la animación; muestra el cartel y 'Continuar' al terminar."""
        f = min(1.0, (pygame.time.get_ticks() - self.t_rev) / dur)
        if f >= 1.0:
            col = U.VERDE if self.color_ok else U.ROJO
            ui.texto(self.msg, (PANEL.centerx, PANEL.y + 292), 52, col, anchor="tc", titulo=True)
            if self.detalle:
                ui.texto(self.detalle, (PANEL.centerx, PANEL.y + 352), 16, U.TEXTO, anchor="tc")
        return f

    def _continuar(self, ui):
        if ui.boton((PANEL.centerx - 110, PANEL.bottom - 62, 220, 46), "Continuar", True, tam=18) or \
                pygame.K_SPACE in ui.teclas or pygame.K_RETURN in ui.teclas:
            return "ok"
        return None

    def _terminar(self, gol, msg, detalle="", motivo="", color_ok=None):
        self.resultado = "gol" if gol else "fallo"
        self.msg, self.detalle, self.motivo = msg, detalle, motivo
        self.color_ok = gol if color_ok is None else color_ok
        self.fase = "rev"
        self.t_rev = pygame.time.get_ticks()


# ===================================================================== penal a favor
class PenalFavor(Minijuego):
    titulo = "¡PENAL A FAVOR!"

    def __init__(self, e, rng):
        super().__init__(e, rng)
        self.zona = None
        self.diff = self.tiro - self.ovr_gk
        self.ancho = float(np.clip(0.16 + 0.004 * self.diff, 0.08, 0.30))
        self.vel = float(np.clip(1.1 - 0.012 * self.diff, 0.7, 1.8))
        self.centro = float(rng.uniform(0.4, 0.75))
        self.t0 = 0
        self.anim = None

    def dibujar(self, ui):
        self._cabecera(ui, f"Tirador: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui)
        zonas = _zonas()
        if self.fase == "jugar":
            if self.zona is None:
                ui.texto("1) Elige dónde disparar", (PANEL.centerx, PANEL.y + 290), 22, U.VERDE, True, "tc")
                self._boton_auto(ui)
                for z, r in zonas.items():
                    if r.collidepoint(ui.mouse):
                        pygame.draw.rect(ui.surf, (255, 255, 255), r, 3)
                        pygame.draw.rect(ui.surf, (46, 204, 113), r.inflate(-10, -10), 2)
                for z, r in zonas.items():
                    if ui.clic_en(r):
                        self.zona = z
                        self.t0 = pygame.time.get_ticks()
                        break
                dibujar_portero(ui, PORTERIA.centerx, PORTERIA.bottom)
            else:
                r = zonas[self.zona]
                pygame.draw.rect(ui.surf, (255, 193, 7), r, 3)
                dibujar_portero(ui, PORTERIA.centerx, PORTERIA.bottom)
                ui.texto("2) Detén la barra dentro de la zona verde", (PANEL.centerx, PANEL.y + 290), 22, U.VERDE,
                         True, "tc")
                barra = pygame.Rect(PANEL.centerx - 220, PANEL.y + 340, 440, 26)
                pygame.draw.rect(ui.surf, (40, 52, 76), barra, border_radius=8)
                zv = pygame.Rect(barra.x + int(barra.w * (self.centro - self.ancho)), barra.y,
                                 int(barra.w * 2 * self.ancho), barra.h)
                pygame.draw.rect(ui.surf, (46, 204, 113), zv, border_radius=6)
                pos = _triangulo((pygame.time.get_ticks() - self.t0) / 1000 * self.vel)
                mx = barra.x + int(barra.w * pos)
                pygame.draw.rect(ui.surf, (255, 255, 255), (mx - 3, barra.y - 6, 6, barra.h + 12), border_radius=3)
                ui.texto("Clic o ESPACIO para disparar", (PANEL.centerx, barra.bottom + 12), 14, U.APAGADO, anchor="tc")
                if ui.click or pygame.K_SPACE in ui.teclas:
                    ui.consumir_click()
                    self._disparar(pos)
                self._boton_auto(ui)
            dibujar_balon(ui, PUNTO)
            return "auto" if self.delegado else None
        # --- revelado
        f = self._revelado(ui)
        a = self.anim
        bx = PUNTO[0] + (a["dest"][0] - PUNTO[0]) * f
        by = PUNTO[1] + (a["dest"][1] - PUNTO[1]) * f
        kx = PORTERIA.centerx + (a["gk_x"] - PORTERIA.centerx) * f
        dibujar_portero(ui, kx, PORTERIA.bottom, a["ang"] * f)
        dibujar_balon(ui, (bx, by), 9 - int(3 * f))
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

    def __init__(self, e, rng):
        super().__init__(e, rng)
        self.diff = self.ovr_gk - self.tiro                 # desde la perspectiva del portero propio
        sesgo = sum(map(ord, self.ejecutor)) % 3
        pc = np.array([0.28, 0.28, 0.28])
        pc[sesgo] += 0.16
        pc[1] -= 0.10
        self.pcol = pc / pc.sum()
        self.sesgo = sesgo
        self.anim = None

    def dibujar(self, ui):
        # aquí e["gk"] es el portero PROPIO (el del equipo del usuario)
        self._cabecera(ui, f"Ejecuta: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Tu portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui)
        zonas = _zonas()
        if self.fase == "jugar":
            ui.texto("Elige hacia dónde se lanza tu portero", (PANEL.centerx, PANEL.y + 290), 22, U.VERDE, True, "tc")
            ui.texto(f"Pista: suele patear hacia la {COLS[self.sesgo]} ({self.pcol[self.sesgo]:.0%} de sus penales).",
                     (PANEL.centerx, PANEL.y + 330), 16, U.AMARILLO, anchor="tc")
            self._boton_auto(ui)
            for z, r in zonas.items():
                if r.collidepoint(ui.mouse):
                    pygame.draw.rect(ui.surf, (255, 255, 255), r, 3)
            for z, r in zonas.items():
                if ui.clic_en(r):
                    self._resolver(z)
                    return None
            dibujar_portero(ui, PORTERIA.centerx, PORTERIA.bottom)
            dibujar_balon(ui, PUNTO)
            return "auto" if self.delegado else None
        f = self._revelado(ui)
        a = self.anim
        bx = PUNTO[0] + (a["dest"][0] - PUNTO[0]) * f
        by = PUNTO[1] + (a["dest"][1] - PUNTO[1]) * f
        kx = PORTERIA.centerx + (a["gk_x"] - PORTERIA.centerx) * f
        dibujar_portero(ui, kx, PORTERIA.bottom, a["ang"] * f)
        dibujar_balon(ui, (bx, by), 9 - int(3 * f))
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
    def __init__(self, e, rng):
        super().__init__(e, rng)
        self.libre = e["tipo"] == "tiro_libre"
        self.titulo = "¡TIRO LIBRE!" if self.libre else "¡OCASIÓN CLARA!"
        self.diff = self.tiro - self.ovr_gk
        s = float(np.clip(1.0 - 0.012 * self.diff, 0.6, 1.6))
        self.vel = s * (1.15 if self.libre else 1.0)
        self.ph = (float(rng.uniform(0, 6.28)), float(rng.uniform(0, 6.28)))
        self.kw = float(np.clip(110 + (self.ovr_gk - 70) * 1.6, 80, 170))
        self.kx = float(rng.uniform(PORTERIA.x + self.kw / 2, PORTERIA.right - self.kw / 2))
        self.muro = None
        if self.libre:
            lado = 1 if rng.random() < 0.5 else -1
            cx = PORTERIA.centerx + lado * float(rng.uniform(50, 120))
            self.muro = pygame.Rect(int(cx - 75), PORTERIA.bottom - 88, 150, 88)
        self.t0 = pygame.time.get_ticks()
        self.anim = None

    def _retícula(self, ahora):
        t = (ahora - self.t0) / 1000 * self.vel
        cx, cy = PORTERIA.center
        return (cx + (PORTERIA.w / 2 + 30) * math.sin(t * 1.7 + self.ph[0]),
                cy + (PORTERIA.h / 2 + 22) * math.sin(t * 2.3 + self.ph[1]))

    def _dibujar_muro(self, ui):
        m = self.muro
        for i in range(5):
            x = m.x + 15 + i * 30
            pygame.draw.rect(ui.surf, (96, 108, 130), (x - 11, m.y + 20, 22, m.h - 20), border_radius=6)
            pygame.draw.circle(ui.surf, (238, 200, 168), (x, m.y + 12), 9)

    def dibujar(self, ui):
        quien = "Tiro libre" if self.libre else "Mano a mano"
        self._cabecera(ui, f"{quien}: {self.ejecutor} (tiro {self.tiro:.0f})  ·  Portero: {self.portero} (OVR {self.ovr_gk})",
                       self.diff)
        dibujar_porteria(ui)
        if self.muro:
            self._dibujar_muro(ui)
        ahora = pygame.time.get_ticks()
        if self.fase == "jugar":
            kb = pygame.Rect(int(self.kx - self.kw / 2), PORTERIA.bottom - 110, int(self.kw), 110)
            pygame.draw.rect(ui.surf, (255, 193, 7), kb, 1, border_radius=6)
            dibujar_portero(ui, self.kx, PORTERIA.bottom)
            ui.texto("Clic o ESPACIO para disparar: apunta lejos del portero" +
                     (" y por encima de la barrera." if self.libre else "."),
                     (PANEL.centerx, PANEL.y + 290), 19, U.VERDE, True, "tc")
            rx, ry = self._retícula(ahora)
            for rr, w in ((15, 2), (4, 0)):
                pygame.draw.circle(ui.surf, (255, 80, 80), (int(rx), int(ry)), rr, w)
            pygame.draw.line(ui.surf, (255, 80, 80), (rx - 24, ry), (rx + 24, ry), 2)
            pygame.draw.line(ui.surf, (255, 80, 80), (rx, ry - 24), (rx, ry + 24), 2)
            dibujar_balon(ui, PUNTO)
            self._boton_auto(ui)
            if self.delegado:
                return "auto"
            if ui.click or pygame.K_SPACE in ui.teclas:
                ui.consumir_click()
                self._disparar(rx, ry)
            return None
        f = self._revelado(ui)
        a = self.anim
        kx = self.kx + (a["gk_x"] - self.kx) * f
        dibujar_portero(ui, kx, PORTERIA.bottom, a["ang"] * f)
        bx = PUNTO[0] + (a["dest"][0] - PUNTO[0]) * f
        by = PUNTO[1] + (a["dest"][1] - PUNTO[1]) * f
        dibujar_balon(ui, (bx, by), 9 - int(3 * f))
        return self._continuar(ui) if f >= 1.0 else None

    def _disparar(self, x, y):
        rng = self.rng
        p_leer = float(np.clip(0.15 + 0.004 * (self.ovr_gk - self.tiro), 0.05, 0.4))
        lee = rng.random() < p_leer
        gk_x = x if lee else self.kx
        gk_x = float(np.clip(gk_x, PORTERIA.x + self.kw / 2, PORTERIA.right - self.kw / 2))
        ang = float(np.clip((gk_x - self.kx) / 160, -1, 1)) * 0.9
        alto = 110 + (30 if lee else 0)
        kb = pygame.Rect(int(gk_x - self.kw / 2), PORTERIA.bottom - alto, int(self.kw), alto)
        self.anim = {"dest": (x, y), "gk_x": gk_x, "ang": ang}
        dentro = PORTERIA.collidepoint(x, y)
        borde = dentro and min(x - PORTERIA.x, PORTERIA.right - x, y - PORTERIA.y) < 8
        if self.muro and self.muro.collidepoint(x, y):
            self._terminar(False, "¡A LA BARRERA!", "El balón rebota en la barrera.", "dio en la barrera")
        elif not dentro:
            self.anim["dest"] = (x, min(y, PORTERIA.y - 40) if y < PORTERIA.y else y)
            self._terminar(False, "¡FUERA!", "Se va desviado.", "se fue desviado")
        elif borde:
            self._terminar(False, "¡AL PALO!", "El balón pega en el palo.", "dio en el palo")
        elif kb.collidepoint(x, y):
            self._terminar(False, "¡ATAJÓ!", f"{self.portero} " + ("leyó la jugada." if lee else "llega a tapar."),
                           "atajado")
        else:
            self._terminar(True, "¡GOOOL!", f"¡Qué definición de {self.ejecutor}!")


def crear(e, lado_usuario, rng):
    """Minijuego que corresponde a la jugada e desde el punto de vista del usuario."""
    if e["tipo"] == "penal":
        if e["lado"] == lado_usuario:
            return PenalFavor(e, rng)
        # el rival patea: e["gk"] es el portero del usuario (portero del lado contrario al ejecutor)
        return PenalContra(e, rng)
    return Remate(e, rng)
