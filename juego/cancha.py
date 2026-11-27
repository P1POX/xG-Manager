"""Vista animada del partido (estilo Haxball): 22 jugadores que se mueven según su formación y una pelota que viaja
entre ellos. Es solo presentación: el resultado lo decide siempre la crónica (juego/eventos.py); aquí cada gol, fallo,
falta o tarjeta de la crónica se "actúa" en el campo.

Coordenadas normalizadas: X de 0 (arco del local, a la izquierda) a 1 (arco del visitante); Y de 0 a 1 (ancho).
El local ataca hacia la derecha (+X) y el visitante hacia la izquierda.
"""
import math
import random

import pygame

from .camisetas import color_portero
from .modelo import FORMACIONES

LINEA = (225, 240, 228)
ESC = 0.648                      # proporción ancho/largo de la cancha (68 m / 105 m), para medir distancias
V_JUG = 0.30                     # velocidad de los jugadores (largos de cancha por segundo, a x1)
V_PASE = 1.05
V_TIRO = 1.9
POSTE = 0.045                    # mitad de la boca del arco (los tiros que "entran" caen dentro de ±POSTE)


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, (ay - by) * ESC)


class Jug:
    __slots__ = ("nombre", "lado", "gk", "sx", "t", "x", "y", "fuera", "numero")

    def __init__(self, j, lado, slot, numero):
        grupo, sx, sy = slot
        self.nombre = j.nombre
        self.lado = lado
        self.gk = grupo == "POR"
        self.sx = sx
        self.t = 1 - sy                       # profundidad en la formación: 0 portero ... ~0.8 delantero
        self.x = self.y = 0.5
        self.fuera = False                    # expulsado
        self.numero = numero


class VistaPartido:
    def __init__(self, local, visita, posesion_local=0.5, semilla=0):
        self.rng = random.Random(semilla)
        self.clubes = {"a": local, "b": visita}
        self.p_pos = {"a": posesion_local, "b": 1 - posesion_local}
        self.eq = {"a": self._equipo(local, "a"), "b": self._equipo(visita, "b")}
        ca, cb = local.color, visita.color
        sep = sum((u - v) ** 2 for u, v in zip(ca, cb)) ** 0.5
        self.col = {"a": (local.color, local.color2),
                    "b": (visita.color, visita.color2) if sep > 110 else (visita.color2, visita.color)}
        self.col_gk = {"a": color_portero(*self.col["a"]), "b": color_portero(*self.col["b"])}
        self.cola = []
        self.marcas = []                      # (Jug, tipo, hasta_t) iconos sobre un jugador: tarjeta, cruz...
        self.aviso = None                     # (texto, hasta_t) cerca de la pelota, p. ej. "Falta"
        self.t = 0.0
        self.hold = 0.0
        self.portero_vuela = None
        self.reiniciar("a", pausa=0.0)

    @staticmethod
    def _equipo(club, lado):
        slots = FORMACIONES[club.formacion]
        res, usados = [], set()
        for i, j in enumerate(club.once):
            if j is not None:
                n = j.dorsal if j.dorsal and j.dorsal not in usados else None     # dorsal real si no se repite en el once
                if n is None:
                    n = next(k for k in range(1, 100) if k not in usados)
                usados.add(n)
                res.append(Jug(j, lado, slots[i], n))
        return res

    # ------------------------------------------------------------------ estado
    def reiniciar(self, saca, pausa=0.9):
        """Saque inicial: todos a su posición base y la pelota al centro, con el equipo `saca`."""
        self.bx = self.by = 0.5
        self.fase = "espera"
        self.espera = pausa
        self.tras_espera = ("saque", saca)
        self.poseedor = None
        self.lado_pos = saca
        self.vuelo = None
        self.guion = None
        for lado in ("a", "b"):
            for p in self.eq[lado]:
                p.x, p.y = self._base(p)

    def _base(self, p):
        prog = 0.03 if p.gk else 0.07 + 0.50 * p.t
        x = prog if p.lado == "a" else 1 - prog
        y = 0.5 + (p.sx - 0.5) * 0.9 if p.lado == "a" else 0.5 - (p.sx - 0.5) * 0.9
        return x, y

    def _objetivo(self, p):
        bprog = self.bx if p.lado == "a" else 1 - self.bx
        base = 0.03 if p.gk else 0.08 + 0.62 * p.t
        prog = min(0.94, max(0.03, base + (bprog - 0.5) * (0.05 if p.gk else 0.36)))
        x = prog if p.lado == "a" else 1 - prog
        y = 0.5 + (p.sx - 0.5) * 0.9 if p.lado == "a" else 0.5 - (p.sx - 0.5) * 0.9
        if not p.gk:
            w = max(0.0, 1 - _dist(x, y, self.bx, self.by) / 0.45)
            x += (self.bx - x) * 0.55 * w
            y += (self.by - y) * 0.55 * w
        else:
            y += (self.by - y) * 0.25
        return x, y

    def _vivos(self, lado):
        return [p for p in self.eq[lado] if not p.fuera]

    def _buscar(self, lado, nombre):
        for p in self.eq[lado]:
            if p.nombre == nombre:
                return p
        return None

    def _delantero(self, lado):
        vivos = [p for p in self._vivos(lado) if not p.gk]
        return max(vivos, key=lambda p: p.t) if vivos else self.eq[lado][0]

    def _portero(self, lado):
        return next((p for p in self._vivos(lado) if p.gk), self.eq[lado][0])

    @staticmethod
    def _prog(p, x):
        return x if p.lado == "a" else 1 - x

    # ------------------------------------------------------------------ eventos de la crónica
    def evento(self, e):
        """Encola una jugada de la crónica para actuarla. Se llama cuando el minuto del evento ya pasó."""
        if len(self.cola) > 4:                                    # a x4 podrían acumularse: se conservan las importantes
            self.cola = [g for g in self.cola if g["tipo"] in ("gol", "fallo", "roja")][-3:]
        lado = e["lado"]
        if e["tipo"] in ("gol", "penal", "tiro_libre", "ocasion") and e["res"] in (None, "gol", "fallo"):
            if e["tipo"] == "gol" or e["res"] == "gol":
                self.cola.append({"tipo": "gol", "lado": lado, "quien": e["jug"]})
            elif e["res"] == "fallo":
                self.cola.append({"tipo": "fallo", "lado": lado, "quien": e["jug"],
                                  "palo": "palo" in str(e.get("motivo", ""))})
        elif e["tipo"] == "falta":
            self.cola.append({"tipo": "falta", "lado": lado, "quien": e["jug"]})
        elif e["tipo"] in ("amarilla", "roja", "lesion"):
            self.cola.append({"tipo": e["tipo"], "lado": lado, "quien": e["jug"]})

    def _iniciar_guion(self, g):
        lado, rival = g["lado"], "b" if g["lado"] == "a" else "a"
        quien = self._buscar(lado, g["quien"])
        if g["tipo"] in ("gol", "fallo"):
            if quien is None or quien.gk or quien.fuera:
                quien = self._delantero(lado)
            self.guion = dict(g, quien=quien, fase="llegar")
            self.fase = "pase_guion"
            self.lado_pos = lado
            self.poseedor = None
            self._lanzar_pase(quien, rapido=True)
        elif g["tipo"] == "falta":
            self.fase = "espera"
            self.espera = 0.8
            self.tras_espera = ("falta", rival)
            self.aviso = ("Falta", self.t + 0.9)
            self.vuelo = None
            self.poseedor = None
        else:                                                     # tarjeta o lesión: marca sobre el jugador
            quien = self._buscar(lado, g["quien"]) or self.rng.choice(self._vivos(lado))
            self.marcas.append((quien, g["tipo"], self.t + 2.4))
            self.fase = "espera"
            self.espera = 0.9
            self.tras_espera = ("falta", rival)
            self.vuelo = None
            self.poseedor = None
            if g["tipo"] == "roja":
                quien.fuera = True

    # ------------------------------------------------------------------ balón
    def _lanzar_pase(self, rec, rapido=False):
        d = 1 if rec.lado == "a" else -1
        ex, ey = rec.x + d * 0.02, rec.y
        if self.guion and rec is self.guion["quien"]:               # el goleador se ofrece cerca del área
            ex = 0.80 if rec.lado == "a" else 0.20
            ey = 0.5 + self.rng.uniform(-0.12, 0.12)
            self.guion["punto"] = (ex, ey)
        dist = _dist(self.bx, self.by, ex, ey)
        dur = max(0.25, dist / (V_PASE * (1.6 if rapido else 1)))
        self.vuelo = {"sx": self.bx, "sy": self.by, "ex": ex, "ey": ey, "t": 0.0, "dur": dur, "rec": rec}
        self.poseedor = None
        if self.fase != "pase_guion":
            self.fase = "pase"

    def _lanzar_tiro(self, tirador, destino_y, dentro):
        dx = 1.0 if tirador.lado == "a" else 0.0
        rival = "b" if tirador.lado == "a" else "a"
        if not dentro and abs(destino_y - 0.5) < POSTE:          # atajada: la pelota muere en el portero, no en la red
            dx = self._portero(rival).x
        dist = _dist(self.bx, self.by, dx, destino_y)
        self.vuelo = {"sx": self.bx, "sy": self.by, "ex": dx, "ey": destino_y, "t": 0.0,
                      "dur": max(0.3, dist / V_TIRO), "rec": None, "tirador": tirador, "dentro": dentro}
        self.fase = "tiro"
        self.poseedor = None
        self.portero_vuela = (self._portero(rival), destino_y)

    def _decidir(self):
        h = self.poseedor
        if h is None:
            return
        prog = self._prog(h, self.bx)
        if prog > 0.70 and not h.gk and self.rng.random() < 0.30:
            wide = self.rng.random() < 0.55
            ey = 0.5 + self.rng.choice((-1, 1)) * (self.rng.uniform(0.09, 0.2) if wide else self.rng.uniform(0.0, 0.03))
            self._lanzar_tiro(h, ey, dentro=False)                 # tiro de juego: nunca entra (los goles son los de la crónica)
            return
        mates = [p for p in self._vivos(h.lado) if p is not h]
        if not mates:
            return

        def puntaje(c):
            avance = self._prog(c, c.x) - prog
            return avance * 1.5 - _dist(h.x, h.y, c.x, c.y) * 1.2 + self.rng.uniform(-0.2, 0.2) - (0.5 if c.gk and not h.gk else 0)
        self._lanzar_pase(max(mates, key=puntaje))

    def _resolver_pase(self, v):
        rec = v["rec"]
        otro = "b" if rec.lado == "a" else "a"
        ic = min(0.20, max(0.05, 0.10 * self.p_pos[otro] / max(0.2, self.p_pos[rec.lado])))
        if self.fase == "pase" and self.rng.random() < ic:
            rivales = [p for p in self._vivos(otro) if not p.gk]
            ladron = min(rivales, key=lambda p: _dist(p.x, p.y, v["ex"], v["ey"]))
            self.poseedor, self.lado_pos = ladron, otro
        else:
            self.poseedor, self.lado_pos = rec, rec.lado
        self.vuelo = None
        self.hold = self.rng.uniform(0.25, 0.65)

    # ------------------------------------------------------------------ paso de tiempo
    def actualizar(self, dt_ms, vel=1):
        dt = min(dt_ms, 100) / 1000 * vel
        self.t += dt
        self.marcas = [m for m in self.marcas if m[2] > self.t]
        if self.aviso and self.aviso[1] <= self.t:
            self.aviso = None
        self._mover_balon(dt)
        self._mover_jugadores(dt)

    def _mover_balon(self, dt):
        if self.fase == "espera":
            if self.poseedor is not None and self.tras_espera[0] == "tiro_guion":   # el goleador controla antes de rematar
                self.bx, self.by = self.poseedor.x, self.poseedor.y
            self.espera -= dt
            if self.espera <= 0:
                self._terminar_espera()
            return
        if self.fase == "celebra":
            self.espera -= dt
            if self.espera <= 0:
                self.reiniciar("b" if self.guion["lado"] == "a" else "a")
            return
        if self.fase == "juego":
            if self.cola:
                self._iniciar_guion(self.cola.pop(0))
                return
            h = self.poseedor
            if h is None:
                return
            self.bx, self.by = h.x + (0.012 if h.lado == "a" else -0.012), h.y
            self.hold -= dt
            if self.hold <= 0:
                self._decidir()
            return
        v = self.vuelo
        if v is None:
            return
        v["t"] += dt
        k = min(1.0, v["t"] / v["dur"])
        self.bx = v["sx"] + (v["ex"] - v["sx"]) * k
        self.by = v["sy"] + (v["ey"] - v["sy"]) * k
        if k < 1.0:
            return
        if self.fase == "pase":
            self._resolver_pase(v)
            self.fase = "juego"
        elif self.fase == "pase_guion":
            g = self.guion
            self.poseedor, self.lado_pos = g["quien"], g["lado"]
            self.vuelo = None
            self.fase = "espera"
            self.espera = 0.35
            self.tras_espera = ("tiro_guion", None)
        elif self.fase == "tiro":
            self._fin_tiro(v)

    def _terminar_espera(self):
        accion, lado = self.tras_espera
        if accion == "saque":
            cand = [p for p in self._vivos(lado) if not p.gk]
            if not cand:
                cand = self._vivos(lado)
            self.poseedor = max(cand, key=lambda p: p.t)
            self.poseedor.x, self.poseedor.y = 0.5 + (0.015 if lado == "a" else -0.015), 0.5
            self.lado_pos = lado
            self.fase = "juego"
            self.hold = 0.5
        elif accion == "falta":                                   # reanuda el equipo que recibió la falta
            cand = [p for p in self._vivos(lado) if not p.gk]
            ref = min(cand, key=lambda p: _dist(p.x, p.y, self.bx, self.by))
            self.poseedor, self.lado_pos = ref, lado
            self.fase = "juego"
            self.hold = 0.35
        elif accion == "tiro_guion":
            g = self.guion
            if g["tipo"] == "gol":
                self._lanzar_tiro(g["quien"], 0.5 + self.rng.uniform(-POSTE, POSTE) * 0.9, dentro=True)
            else:
                lado_y = self.rng.choice((-1, 1))
                if g.get("palo"):
                    ey = 0.5 + lado_y * 0.054
                elif self.rng.random() < 0.5:
                    ey = 0.5 + lado_y * self.rng.uniform(0.0, 0.03)
                else:
                    ey = 0.5 + lado_y * self.rng.uniform(0.09, 0.18)
                self._lanzar_tiro(g["quien"], ey, dentro=False)

    def _fin_tiro(self, v):
        t = v["tirador"]
        if v["dentro"]:                                           # gol de la crónica: celebración y saque del rival
            self.fase = "celebra"
            self.espera = 1.5
            self.guion = self.guion or {"lado": t.lado}
            self.guion["lado"] = t.lado
            self.guion["quien"] = t
            self.lado_pos = t.lado
            self.vuelo = None
            return
        rival = "b" if t.lado == "a" else "a"
        gk = self._portero(rival)
        self.poseedor, self.lado_pos = gk, rival                   # saque de meta / atajada
        self.vuelo = None
        self.guion = None
        self.portero_vuela = None
        self.fase = "juego"
        self.hold = 0.8
        self.bx, self.by = gk.x, gk.y

    def _mover_jugadores(self, dt):
        esc = self.fase == "celebra"
        for lado in ("a", "b"):
            for p in self._vivos(lado):
                if esc and lado == self.guion["lado"] and p is not self.guion["quien"] and not p.gk:
                    q = self.guion["quien"]
                    ang = (p.numero * 2.4)
                    tx, ty = q.x + math.cos(ang) * 0.05, q.y + math.sin(ang) * 0.08
                elif esc and p is self.guion["quien"]:
                    tx, ty = p.x, p.y
                elif self.fase == "tiro" and p.gk and self.portero_vuela and p is self.portero_vuela[0]:
                    tx, ty = p.x, self.portero_vuela[1]
                elif p is self.poseedor and self.fase == "juego":
                    d = 1 if p.lado == "a" else -1
                    tx, ty = p.x + d * 0.06, p.y
                elif self.fase in ("pase", "pase_guion") and self.vuelo and p is self.vuelo["rec"]:
                    tx, ty = self.vuelo["ex"], self.vuelo["ey"]
                elif self.fase == "espera" and self.tras_espera[0] == "saque":
                    tx, ty = self._base(p)
                else:
                    tx, ty = self._objetivo(p)
                vel = V_JUG * (1.7 if esc else 1.0)
                if self.fase == "espera" and self.tras_espera[0] == "saque":
                    vel *= 1.6
                self._acercar(p, tx, ty, vel * dt)

    @staticmethod
    def _acercar(p, tx, ty, paso):
        dx, dy = tx - p.x, (ty - p.y) * ESC
        d = math.hypot(dx, dy)
        if d <= paso or d < 1e-6:
            p.x, p.y = tx, ty
        else:
            p.x += dx * paso / d
            p.y += dy * paso / d / ESC
        p.x = min(1.0, max(0.0, p.x))
        p.y = min(1.0, max(0.0, p.y))

    # ------------------------------------------------------------------ dibujo
    def dibujar(self, ui, campo):
        s = ui.surf
        pygame.draw.rect(s, (36, 128, 60), campo, border_radius=10)
        for i in range(10):
            if i % 2:
                pygame.draw.rect(s, (41, 140, 66), (campo.x + i * campo.w // 10, campo.y, campo.w // 10, campo.h))
        m = 14
        r = pygame.Rect(campo.x + m, campo.y + m, campo.w - 2 * m, campo.h - 2 * m)
        px = lambda X: r.x + X * r.w          # noqa: E731
        py = lambda Y: r.y + Y * r.h          # noqa: E731
        pygame.draw.rect(s, LINEA, r, 2)
        pygame.draw.line(s, LINEA, (r.centerx, r.y), (r.centerx, r.bottom), 2)
        rc = int(r.h * 9.15 / 68)
        pygame.draw.circle(s, LINEA, r.center, rc, 2)
        pygame.draw.circle(s, LINEA, r.center, 3)
        pa, pb = int(r.w * 16.5 / 105), int(r.h * 40.3 / 68)
        ga, gb = int(r.w * 5.5 / 105), int(r.h * 18.3 / 68)
        pm = int(r.w * 11 / 105)
        semi = math.acos(max(-1, min(1, (pa - pm) / rc)))
        for izq in (True, False):
            x0 = r.x if izq else r.right
            sg = 1 if izq else -1
            pygame.draw.rect(s, LINEA, (x0 if izq else x0 - pa, r.centery - pb // 2, pa, pb), 2)
            pygame.draw.rect(s, LINEA, (x0 if izq else x0 - ga, r.centery - gb // 2, ga, gb), 2)
            pygame.draw.circle(s, LINEA, (x0 + sg * pm, r.centery), 3)
            c = 0.0 if izq else math.pi
            pygame.draw.arc(s, LINEA, (x0 + sg * pm - rc, r.centery - rc, 2 * rc, 2 * rc), c - semi, c + semi, 2)
            ay = int(r.h * 7.32 / 68)
            pygame.draw.rect(s, (200, 210, 220), (x0 - 7 if izq else x0, r.centery - ay // 2, 7, ay), 2)
        rad = 9
        for lado in ("a", "b"):
            c1, c2 = self.col[lado]
            for p in self._vivos(lado):
                cx, cy = int(px(p.x)), int(py(p.y))
                relleno, borde = self.col_gk[lado] if p.gk else (c1, c2)
                pygame.draw.circle(s, (12, 20, 16), (cx + 1, cy + 2), rad)               # sombra
                pygame.draw.circle(s, relleno, (cx, cy), rad)
                pygame.draw.circle(s, borde, (cx, cy), rad, 2)
                ui.texto(p.numero, (cx, cy), 10, borde, True, "mc")
        # pelota y poseedor
        bx, by = int(px(min(1.0, max(0.0, self.bx)))), int(py(self.by))
        if self.poseedor is not None and self.fase in ("juego",):
            h = self.poseedor
            pygame.draw.circle(s, (255, 235, 90), (int(px(h.x)), int(py(h.y))), rad + 3, 2)
            ui.placa_jugador_corta(int(px(h.x)), int(py(h.y)) + rad + 4, h.nombre)
        pygame.draw.circle(s, (255, 255, 255), (bx, by), 5)
        pygame.draw.circle(s, (25, 25, 25), (bx, by), 5, 1)
        for p, tipo, _ in self.marcas:
            cx, cy = int(px(p.x)), int(py(p.y)) - rad - 12
            if tipo in ("amarilla", "roja"):
                pygame.draw.rect(s, (255, 193, 7) if tipo == "amarilla" else (235, 60, 60), (cx - 6, cy - 9, 12, 17), border_radius=2)
            else:
                pygame.draw.circle(s, (255, 255, 255), (cx, cy), 9)
                pygame.draw.rect(s, (235, 60, 60), (cx - 5, cy - 2, 10, 4))
                pygame.draw.rect(s, (235, 60, 60), (cx - 2, cy - 5, 4, 10))
            ui.placa_jugador_corta(int(px(p.x)), int(py(p.y)) + rad + 4, p.nombre)
        if self.aviso:
            ui.texto(self.aviso[0], (bx, by - 20), 13, (255, 235, 90), True, "mc")
