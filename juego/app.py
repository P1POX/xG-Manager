"""Aplicación principal (Pygame): menús, gestión del club y partidos."""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pygame

from . import eventos as ev
from . import guardado as G
from . import minijuegos as mj
from . import tactica as tac
from . import ui as U
from .asistente import Asistente
from .cancha import VistaPartido
from .camisetas import color_portero
from .datos import DATA, Mundo
from .modelo import (FORMACIONES, GRUPOS, NOMBRE_GRUPO, Liga, autoalinear, reparar_once)
from .simulacion import fuerzas, goles_esperados

ANCHO, ALTO = 1280, 720
X0 = 224                       # inicio del área de contenido (a la derecha de la barra lateral)
REPORTES = DATA.parent / "reports"
IMG = DATA.parent / "assets" / "img"


def eur(v):
    if v >= 1e6:
        return f"{v / 1e6:.1f} M€"
    if v >= 1e3:
        return f"{v / 1e3:.0f} K€"
    return f"{v:.0f} €"


def color_apt(a):
    return U.VERDE if a >= 0.999 else U.AMARILLO if a >= 0.55 else U.ROJO


class App:
    def __init__(self, seed=None):
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")   # al escalar a 1080p, suaviza en vez de "pixelar"
        pygame.init()
        pygame.display.set_caption("xG Manager · Minería de Datos con FC 24")
        try:
            pygame.display.set_icon(pygame.transform.smoothscale(pygame.image.load(str(IMG / "logo.png")), (64, 64)))
        except (pygame.error, FileNotFoundError):
            pass                                          # sin logo el juego funciona igual
        self.pantalla = pygame.display.set_mode((ANCHO, ALTO), pygame.SCALED | pygame.RESIZABLE)
        self.ui = U.UI(self.pantalla)
        self.reloj = pygame.time.Clock()
        self.seed = seed
        self.mundo = None
        self.asist = Asistente(seed=seed)
        self.rng = np.random.default_rng(seed)
        self.escena = "menu"
        self._pendiente = None
        self.tab = "alineacion"
        self.avisos = []
        self.ayuda = False
        self.fondo = self._crear_fondo()
        self.fondo_menu = self._crear_fondo_menu()
        self.logo = self._cargar_logo()
        self._ml = None
        # estado de partida
        self.liga_nombre = None
        self.club_sel = None
        self.liga = None
        self.club = None
        self.ultimos = []
        self.sel_slot = None
        self.sel_jug = None
        self.scroll_plantel = 0
        self.mercado = {"grupo": None, "orden": "gangas", "ovr_min": 68, "asequibles": True, "texto": "",
                        "pagina": 0, "sel": None, "cache": None, "clave": None, "reemplazo": None}
        self.p = None                    # estado del partido
        self.sugerencia = None
        self._guardada = None            # (datos, error) de la partida guardada, o None si aún no se ha leído
        self._continuar = None
        self._confirmar_nueva = False

    # ------------------------------------------------------------ utilidades
    def _crear_fondo(self):
        s = pygame.Surface((ANCHO, ALTO))
        for y in range(ALTO):
            s.fill(U.mezclar((10, 16, 28), (22, 36, 58), y / ALTO), (0, y, ANCHO, 1))
        return s

    def _crear_fondo_menu(self):
        """Foto del estadio recortada a 16:9 y oscurecida para que se lean los botones. Si falta, el degradado normal."""
        try:
            img = pygame.image.load(str(IMG / "fondo_menu.jpg")).convert()
        except (pygame.error, FileNotFoundError):
            return self.fondo
        k = max(ANCHO / img.get_width(), ALTO / img.get_height())
        img = pygame.transform.smoothscale(img, (round(img.get_width() * k), round(img.get_height() * k)))
        s = pygame.Surface((ANCHO, ALTO))
        s.blit(img, ((ANCHO - img.get_width()) // 2, (ALTO - img.get_height()) // 2))
        velo = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        for y in range(ALTO):                             # más oscuro abajo, donde van los botones y el texto
            velo.fill((6, 10, 20, int(95 + 90 * y / ALTO)), (0, y, ANCHO, 1))
        s.blit(velo, (0, 0))
        return s

    def _cargar_logo(self):
        try:
            return pygame.image.load(str(IMG / "logo.png")).convert_alpha()
        except (pygame.error, FileNotFoundError):
            return None

    def dibujar_logo(self, centro_x, y, alto):
        """Logo del juego con su altura `alto`, centrado en x. Devuelve False si no hay logo."""
        if self.logo is None:
            return False
        w = round(self.logo.get_width() * alto / self.logo.get_height())
        clave = ("logo", alto)
        if clave not in self.ui._cache:
            self.ui._cache[clave] = pygame.transform.smoothscale(self.logo, (w, alto))
        self.pantalla.blit(self.ui._cache[clave], (centro_x - w // 2, y))
        return True

    def aviso(self, texto, color=U.VERDE, ms=3500):
        self.avisos.append([texto, color, pygame.time.get_ticks() + ms])

    def ir(self, escena):
        self._pendiente = escena
        if escena == "menu":
            self._guardada = None        # releer el archivo de guardado
            self._confirmar_nueva = False

    def guardar(self, aviso=False):
        """Guarda la temporada en curso. Los fallos de disco no deben tumbar el juego."""
        if self.club is None or self.liga is None:
            return False
        try:
            G.guardar(self)
        except OSError as e:
            self.aviso(f"No se pudo guardar la partida: {e}", U.ROJO, 5000)
            return False
        if aviso:
            self.aviso("Partida guardada.", U.VERDE)
        return True

    def reiniciar_mundo(self):
        self.mundo = Mundo(seed=self.seed)
        self.rng = np.random.default_rng(self.seed)

    # ------------------------------------------------------------ bucle
    def ejecutar(self):
        while True:
            eventos = pygame.event.get()
            for e in eventos:
                if e.type == pygame.QUIT:
                    if self.escena == "hub":
                        self.guardar()
                    pygame.quit()
                    sys.exit()
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
            self.ui.inicio_frame(eventos)
            self.cuadro()
            self.ui.dibujar_tooltip()
            self.dibujar_avisos()
            pygame.display.flip()
            self.reloj.tick(60)

    def cuadro(self):
        if self._pendiente:
            self.escena, self._pendiente = self._pendiente, None
            self.ui.foco = None
        self.pantalla.blit(self.fondo_menu if self.escena in ("menu", "cargando", "liga") else self.fondo, (0, 0))
        getattr(self, "escena_" + self.escena)()

    def dibujar_avisos(self):
        ahora = pygame.time.get_ticks()
        self.avisos = [a for a in self.avisos if a[2] > ahora]
        for i, (t, c, _) in enumerate(reversed(self.avisos[-4:])):
            w = self.ui.fuente(16, True).size(t)[0] + 28
            r = pygame.Rect(0, 0, w, 34)
            r.midbottom = (ANCHO // 2 + 100, ALTO - 14 - i * 40)
            self.ui.panel(r, (10, 14, 24), 8, c)
            self.ui.texto(t, r.center, 16, c, True, "mc")

    # ================================================================ MENÚ
    def escena_menu(self):
        ui = self.ui
        if not self.dibujar_logo(ANCHO // 2, 14, 236):
            ui.texto("xG MANAGER", (ANCHO // 2, 130), 120, U.TEXTO, anchor="tc", titulo=True)
        ui.texto("Dirige un club con ayuda de la minería de datos", (ANCHO // 2, 258), 24, U.VERDE, True, "tc")
        ui.texto("Datos reales de EA SPORTS FC 24 · clustering · regresión · árboles de decisión · reglas de asociación",
                 (ANCHO // 2, 294), 16, (170, 184, 208), anchor="tc")
        if self._guardada is None:
            self._guardada = G.leer()                 # (datos, error); se relee al volver al menú
        datos, error = self._guardada
        y = 330
        if datos is not None:
            if ui.boton((ANCHO // 2 - 160, y, 320, 56), "Continuar temporada", True, tam=22):
                self._continuar = datos
                self.ir("cargando")
            ui.texto(G.resumen(datos), (ANCHO // 2, y + 62), 14, U.AMARILLO, anchor="tc")
            y += 90
        elif error:
            ui.texto(error, (ANCHO // 2, y + 8), 14, U.ROJO, anchor="tc")
            y += 36
        if ui.boton((ANCHO // 2 - 160, y, 320, 56), "Nueva temporada", datos is None, tam=22):
            if datos is not None and not self._confirmar_nueva:
                self._confirmar_nueva = True          # primer clic: avisa; segundo clic: sobrescribe
                self.aviso("Ya hay una partida guardada. Pulsa otra vez para empezar de cero y reemplazarla.", U.AMARILLO, 5000)
            else:
                self._confirmar_nueva = False
                self.ir("cargando")
        if ui.boton((ANCHO // 2 - 160, y + 70, 320, 48), "¿Cómo se juega?", self.ayuda, tam=18):
            self.ayuda = not self.ayuda
        if ui.boton((ANCHO // 2 - 160, y + 130, 320, 48), "Salir", tam=18):
            pygame.quit()
            sys.exit()
        if self.ayuda:
            r = pygame.Rect(ANCHO // 2 - 380, 545, 760, 150)
            ui.panel(r, (10, 14, 24), 10, U.BORDE)
            ui.parrafo("Elige liga y club. Entre jornadas arma la alineación, ficha jugadores y ajusta la táctica. "
                       "El asistente te muestra qué dicen los modelos: el ROL de cada jugador (K-means), su VALOR JUSTO "
                       "(regresión), su APTITUD por posición (árbol de decisión), el PRONÓSTICO del partido y las REGLAS "
                       "TÁCTICAS (Apriori) asociadas a los equipos de élite. ¡Termina la liga cumpliendo el objetivo!",
                       r.inflate(-28, -20), 15)
        ui.texto("Fuentes: Lato y Bebas Neue (SIL OFL) · Datos: EA SPORTS FC 24 Complete Player Dataset (Kaggle)",
                 (ANCHO // 2, ALTO - 24), 13, U.APAGADO, anchor="tc")

    def escena_cargando(self):
        self.dibujar_logo(ANCHO // 2, 90, 280)
        self.ui.texto("Cargando datos de jugadores y entrenando el asistente…", (ANCHO // 2, ALTO // 2 + 120), 26,
                      U.TEXTO, True, "mc")
        self.ui.texto("(solo la primera vez)", (ANCHO // 2, ALTO // 2 + 156), 16, (170, 184, 208), anchor="mc")
        if getattr(self, "_cargado_frame", False):
            self._cargado_frame = False
            self.reiniciar_mundo()
            datos, self._continuar = self._continuar, None
            if datos is not None:
                try:
                    G.aplicar(self, datos)
                    self.aviso("Partida cargada.", U.VERDE)
                    self.ir("hub")
                except Exception as e:                # archivo dañado: no se pierde nada, se vuelve al menú
                    self.aviso(f"No se pudo cargar la partida: {e}", U.ROJO, 6000)
                    self.reiniciar_mundo()
                    self.ir("menu")
            else:
                self.ir("liga")
        else:
            self._cargado_frame = True

    # ============================================================ LIGA / CLUB
    def escena_liga(self):
        ui = self.ui
        ui.texto("Elige una liga", (ANCHO // 2, 50), 56, anchor="tc", titulo=True)
        ligas = sorted(self.mundo.ligas)
        w, h = 220, 330
        x = (ANCHO - (w * len(ligas) + 20 * (len(ligas) - 1))) // 2
        for nombre in ligas:
            ids = self.mundo.ligas[nombre]
            clubes = [self.mundo.clubes[i] for i in ids]
            r = pygame.Rect(x, 160, w, h)
            hov = ui.hover(r)
            ui.panel(r, U.PANEL2 if hov else U.PANEL, 14, U.VERDE if hov else U.BORDE)
            ui.texto(nombre, (r.centerx, r.y + 24), 30, anchor="tc", titulo=True)
            top = max(clubes, key=lambda c: c.ovr)
            if not ui.logo_liga((r.centerx, r.y + 112), 80, nombre):
                ui.insignia((r.centerx, r.y + 110), 36, top)
            ui.texto(f"{len(clubes)} clubes", (r.centerx, r.y + 165), 17, U.APAGADO, anchor="tc")
            ui.texto(f"OVR medio {np.mean([c.ovr for c in clubes]):.1f}", (r.centerx, r.y + 192), 17, anchor="tc")
            ui.texto(f"Favorito: {top.nombre}", (r.centerx, r.y + 222), 15, U.AMARILLO, anchor="tc", maxw=w - 20)
            if ui.clic_en(r):
                self.liga_nombre = nombre
                self.club_sel = None
                self.ir("club")
            x += w + 20
        if ui.boton((24, ALTO - 64, 140, 40), "← Menú"):
            self.ir("menu")

    def escena_club(self):
        ui = self.ui
        clubes = sorted((self.mundo.clubes[i] for i in self.mundo.ligas[self.liga_nombre]),
                        key=lambda c: (-c.ovr, c.nombre))
        if self.club_sel is None:
            self.club_sel = clubes[len(clubes) // 2]
        ui.texto(self.liga_nombre, (40, 24), 52, titulo=True)
        ui.logo_liga((1170, 56), 56, self.liga_nombre)
        ui.texto("Elige el club que vas a dirigir", (40, 78), 17, U.APAGADO)
        ui.texto("Club", (100, 116), 14, U.APAGADO)
        ui.texto("OVR", (370, 116), 14, U.APAGADO)
        ui.texto("Valor plantel", (472, 116), 14, U.APAGADO)
        ui.texto("Presupuesto", (590, 116), 14, U.APAGADO)
        y = 138
        alto_f = 25
        for c in clubes:
            r = pygame.Rect(40, y, 680, alto_f - 2)
            if c is self.club_sel:
                ui.panel(r, U.PANEL2, 6, U.VERDE)
            elif ui.hover(r):
                ui.panel(r, U.PANEL, 6)
            ui.insignia((62, y + 11), 9, c)
            ui.texto(c.nombre, (100, y + 11), 15, anchor="ml", maxw=255)
            ui.barra((370, y + 6, 50, 10), (c.ovr - 65) / 22, U.VERDE)
            ui.texto(c.ovr, (452, y + 11), 15, U.AMARILLO, True, "mr")
            ui.texto(eur(c.valor_plantel()), (472, y + 11), 15, anchor="ml")
            ui.texto(eur(c.presupuesto), (590, y + 11), 15, anchor="ml")
            if ui.clic_en(r):
                self.club_sel = c
            y += alto_f
        c = self.club_sel
        r = pygame.Rect(750, 120, 490, 520)
        ui.panel(r, U.PANEL, 14, U.BORDE)
        ui.insignia((r.x + 60, r.y + 62), 38, c)
        ui.texto(c.nombre, (r.x + 112, r.y + 30), 36, titulo=True, maxw=360)
        ui.texto(c.estadio, (r.x + 112, r.y + 66), 15, U.APAGADO, maxw=360)
        fil = [("Entrenador (actual)", c.entrenador), ("OVR del equipo", c.ovr),
               ("Valor del plantel", eur(c.valor_plantel())), ("Presupuesto de fichajes", eur(c.presupuesto)),
               ("Formación inicial", c.formacion)]
        yy = r.y + 120
        for k, v in fil:
            ui.texto(k, (r.x + 24, yy), 15, U.APAGADO)
            ui.texto(v, (r.right - 24, yy), 16, U.TEXTO, True, "tr", maxw=260)
            yy += 32
        rk = 1 + sum(1 for x in clubes if x.ovr > c.ovr)
        obj = self.objetivo(c, clubes)
        ui.texto("Objetivo de la directiva", (r.x + 24, yy + 8), 15, U.APAGADO)
        ui.texto(f"Terminar entre los {obj} primeros", (r.x + 24, yy + 32), 22, U.AMARILLO, True)
        ui.texto(f"Hoy eres el nº {rk} de {len(clubes)} por OVR del equipo", (r.x + 24, yy + 66), 14, U.APAGADO)
        if ui.boton((r.x + 24, r.bottom - 76, r.w - 48, 54), f"Dirigir al {c.nombre}", True, tam=20):
            self.iniciar_temporada(c)
        if ui.boton((24, ALTO - 50, 120, 36), "← Ligas"):
            self.ir("liga")

    @staticmethod
    def objetivo(c, clubes):
        rk = 1 + sum(1 for x in clubes if x.ovr > c.ovr)
        return max(1, math.ceil(rk * 0.7))

    def iniciar_temporada(self, club):
        self.club = club
        clubes = [self.mundo.clubes[i] for i in self.mundo.ligas[self.liga_nombre]]
        for c in clubes:
            c.reset_temporada()
        self.liga = Liga(self.liga_nombre, clubes, self.rng)
        self.objetivo_pos = self.objetivo(club, sorted(clubes, key=lambda c: -c.ovr))
        self.ultimos = []
        self.sel_slot = self.sel_jug = None
        self.mercado.update(sel=None, cache=None, clave=None, reemplazo=None, pagina=0)
        self.tab = "alineacion"
        self.ir("hub")

    # ================================================================== HUB
    def escena_hub(self):
        ui = self.ui
        c = self.club
        # ---- barra lateral
        ui.panel((0, 0, X0 - 12, ALTO), (16, 23, 38), 0)
        ui.insignia((60, 62), 34, c)
        ui.texto_fit(c.nombre, (112, 38), 26, 14, 96, titulo=True)
        ui.texto(c.liga, (112, 66), 13, U.APAGADO, maxw=100)
        ui.texto("PRESUPUESTO", (20, 118), 12, U.APAGADO)
        ui.texto(eur(c.presupuesto), (20, 134), 26, U.VERDE, True)
        ui.texto(f"Posición: {self.liga.posicion(c)}º  ·  {c.pts} pts", (20, 172), 15)
        ui.texto(f"Objetivo: top {self.objetivo_pos}", (20, 194), 14, U.AMARILLO)
        tabs = [("alineacion", "Alineación"), ("mercado", "Mercado"), ("tactica", "Táctica"),
                ("liga", "Liga"), ("datos", "Datos y modelos")]
        y = 236
        for k, nombre in tabs:
            if ui.boton((14, y, X0 - 40, 42), nombre, self.tab == k, tam=17):
                self.tab = k
            y += 50
        if self.liga.terminada:
            if ui.boton((14, ALTO - 84, X0 - 40, 60), "Ver resultado final", True, U.AMARILLO, tam=18):
                self.ir("fin")
        else:
            rid, local = self.liga.rival(c)
            if ui.boton((14, ALTO - 84, X0 - 40, 60), f"Jugar jornada {self.liga.jornada + 1}", True, tam=18):
                self.guardar()                        # conserva los cambios de alineación/mercado hechos antes del partido
                self.preparar_partido()
        if ui.boton((14, ALTO - 136, X0 - 40, 40), "Guardar y salir", tam=15,
                    tip="Guarda la temporada y vuelve al menú.\nTambién se guarda sola al cerrar cada jornada."):
            if self.guardar(aviso=False):
                self.aviso("Partida guardada. Puedes continuarla desde el menú.", U.VERDE, 4000)
            self.ir("menu")
        # ---- encabezado
        if not self.liga.terminada:
            rid, local = self.liga.rival(c)
            riv = self.mundo.clubes[rid]
            ui.texto(f"Jornada {self.liga.jornada + 1}/{self.liga.total_jornadas}", (X0, 20), 15, U.APAGADO)
            r = ui.texto("Próximo partido:", (X0 + 150, 20), 15, U.APAGADO, True)
            x0 = r.x
            local_c, visita_c = (c, riv) if local else (riv, c)          # el orden indica quién juega en casa
            for k, club in enumerate((local_c, visita_c)):
                if k == 1:
                    r = ui.texto("vs", (r.right + 12, 20), 15, U.APAGADO)
                ui.insignia((r.right + 22, 29), 11, club)
                r = ui.texto(club.nombre, (r.right + 42, 20), 15, U.VERDE if club is c else U.TEXTO, True)
                r = ui.texto(f"({club.ovr})", (r.right + 6, 20), 15, U.AMARILLO)
            if ui.hover(pygame.Rect(x0, 16, r.right - x0, 26)):
                ui.tip = ("Quien aparece primero juega en casa.\n"
                          "El número entre paréntesis es el OVR del equipo en FC 24\n"
                          f"(la misma escala que los jugadores): tú {c.ovr}, rival {riv.ovr}.\n"
                          "No es la posición en la tabla.")
        getattr(self, "tab_" + self.tab)()

    # ------------------------------------------------------- alineación
    def tab_alineacion(self):
        ui, c = self.ui, self.club
        campo = pygame.Rect(X0 + 8, 52, 430, 640)
        ui.campo(campo)
        slots = FORMACIONES[c.formacion]
        for i, (g, x, y) in enumerate(slots):
            j = c.once[i]
            px, py = ui.pos_campo(campo, x, y)
            rr = pygame.Rect(0, 0, 80, 84)
            rr.center = (px, py + 4)
            if i == self.sel_slot:
                pygame.draw.circle(ui.surf, U.AMARILLO, (px, py), 30, 3)
            if j is not None:
                apt = j.aptitud(g)
                if g == "POR":
                    k1, k2 = color_portero(c.color, c.color2)
                    ui.camiseta((px, py), 46, k1, k2, numero=j.dorsal, apagada=j.lesion > 0)
                else:
                    ui.camiseta((px, py), 46, c.color, c.color2, numero=j.dorsal, apagada=j.lesion > 0, patron=c.patron)
                bx, by = px + 27, py - 25                                  # OVR: círculo en el hombro, no tapa el dorsal
                pygame.draw.circle(ui.surf, color_apt(apt), (bx, by), 13)
                pygame.draw.circle(ui.surf, (12, 22, 16), (bx, by), 13, 2)
                ui.texto(j.ovr, (bx, by), 13, (10, 20, 15), True, "mc")
                ui.placa_jugador(px, py + 28, j.nombre, g)
                if j.lesion:
                    ui.icono_baja(px - 27, py - 24, j.motivo)
                if ui.hover(rr):
                    ui.tip = (f"{j.nombre}" + (f" · #{j.dorsal}" if j.dorsal else "") + f" ({j.pos}) · {j.rol}\nAptitud en {g}: {apt:.0%} (árbol de decisión)"
                              + (f"\n{'Suspendido' if j.motivo == 'sanción' else 'Lesionado'} {j.lesion} jornada(s)" if j.lesion else ""))
            else:
                pygame.draw.circle(ui.surf, (20, 70, 35), (px, py), 24, 3)
                ui.texto(g, (px, py), 13, (200, 230, 210), True, "mc")
            if ui.clic_en(rr):
                if self.sel_jug is not None:
                    self.asignar(i, self.sel_jug)
                else:
                    self.sel_slot = None if self.sel_slot == i else i
        # ---- panel derecho
        px0 = X0 + 456
        pw = ANCHO - px0 - 14
        ui.texto("Formación", (px0, 52), 14, U.APAGADO)
        for k, f in enumerate(FORMACIONES):
            if ui.boton((px0 + 76 + k * 78, 46, 72, 30), f, c.formacion == f, tam=14):
                self.cambiar_formacion(f)
        if ui.boton((px0 + pw - 140, 46, 140, 30), "Autoalinear", color=U.AZUL, tam=14,
                    tip="Algoritmo húngaro: asigna a cada puesto el\njugador con mayor rendimiento (OVR x aptitud)."):
            autoalinear(c, c.formacion)
            self.sel_slot = self.sel_jug = None
            self.aviso("Alineación óptima aplicada.")
        # lista del plantel
        orden = sorted(c.plantel, key=lambda j: (GRUPOS.index(j.grupo), -j.ovr))
        y0 = 92
        ui.texto("Pos", (px0 + 34, y0), 13, U.APAGADO)
        ui.texto("Jugador", (px0 + 80, y0), 13, U.APAGADO)
        ui.texto("Edad", (px0 + 250, y0), 13, U.APAGADO)
        ui.texto("OVR", (px0 + 292, y0), 13, U.APAGADO)
        ui.texto("Rol (K-means)", (px0 + 336, y0), 13, U.APAGADO)
        filas, fh = 13, 25
        lista = pygame.Rect(px0, y0 + 20, pw, filas * fh)
        if lista.collidepoint(ui.mouse):
            self.scroll_plantel -= ui.rueda
        self.scroll_plantel = max(0, min(self.scroll_plantel, max(0, len(orden) - filas)))
        for n, j in enumerate(orden[self.scroll_plantel:self.scroll_plantel + filas]):
            r = pygame.Rect(px0, y0 + 20 + n * fh, pw, fh - 1)
            if j is self.sel_jug:
                ui.panel(r, U.PANEL2, 5, U.AMARILLO)
            elif ui.hover(r):
                ui.panel(r, U.PANEL, 5)
            tit = j in c.once
            if tit:
                ui.texto("XI", (px0 + 8, r.centery), 12, U.VERDE, True, "ml")
            if j.lesion and not tit:
                ui.icono_baja(px0 + 8, r.centery, j.motivo, 7)
                ui.texto(j.lesion, (px0 + 18, r.centery), 12, U.ROJO, True, "ml")
            ui.texto(j.pos, (px0 + 34, r.centery), 14, U.AMARILLO, anchor="ml")
            ui.texto(j.nombre, (px0 + 80, r.centery), 14, U.APAGADO if j.lesion else U.TEXTO, anchor="ml", maxw=165)
            ui.texto(j.edad, (px0 + 250, r.centery), 14, anchor="ml")
            ui.texto(j.ovr, (px0 + 292, r.centery), 14, U.VERDE, True, "ml")
            ui.texto(j.rol, (px0 + 336, r.centery), 13, U.APAGADO, anchor="ml", maxw=pw - 340)
            if ui.clic_en(r):
                if self.sel_slot is not None and j.lesion == 0:
                    self.asignar(self.sel_slot, j)
                else:
                    self.sel_jug = None if self.sel_jug is j else j
        # ficha del jugador seleccionado
        j = self.sel_jug or (c.once[self.sel_slot] if self.sel_slot is not None else None)
        ficha = pygame.Rect(px0, y0 + 20 + filas * fh + 10, pw, 700 - (y0 + 20 + filas * fh + 10))
        ui.panel(ficha, U.PANEL, 12, U.BORDE)
        if j is None:
            ui.texto("Haz clic en un puesto del campo y luego en un jugador de la lista (o al revés) para alinearlo.",
                     (ficha.x + 16, ficha.y + 16), 14, U.APAGADO, maxw=ficha.w - 32)
            ui.texto("Número = dorsal · círculo = OVR · cruz = lesión · tarjeta roja = suspendido.",
                     (ficha.x + 16, ficha.y + 42), 14, U.APAGADO, maxw=ficha.w - 32)
            ui.texto("Círculo verde = posición natural · amarillo/rojo = fuera de posición (rinde menos).",
                     (ficha.x + 16, ficha.y + 66), 14, U.APAGADO, maxw=ficha.w - 32)
            return
        self.ficha_jugador(ficha, j)
        pos_sl = c.once.index(j) if j in c.once else None
        vend_ok, vend_msg = self.mundo.puede_vender(c, j)
        if ui.boton((ficha.right - 330, ficha.bottom - 44, 150, 34), f"Vender {eur(round(j.valor * .9, -5))}",
                    habilitado=vend_ok, color=U.ROJO, tam=14, tip=vend_msg or "Se vende al 90 % del valor de mercado."):
            ok, msg = self.mundo.vender(c, j)
            self.aviso(msg, U.VERDE if ok else U.ROJO)
            self.sel_jug = self.sel_slot = None
            self.mercado["clave"] = None
        if ui.boton((ficha.right - 168, ficha.bottom - 44, 156, 34), "Buscar reemplazo", color=U.AZUL, tam=14,
                    tip="K-means: jugadores más parecidos en el espacio de atributos."):
            self.mercado["reemplazo"] = j
            self.mercado.update(pagina=0, sel=None, clave=None)
            self.tab = "mercado"

    def ficha_jugador(self, r, j):
        ui = self.ui
        ui.texto(j.nombre_largo if len(j.nombre_largo) < 24 else j.nombre, (r.x + 16, r.y + 10), 22, titulo=True)
        ui.texto(f"{'/'.join(j.pos_lista)} · {j.edad} años · {j.nacionalidad}", (r.x + 16, r.y + 38), 13, U.APAGADO)
        ui.texto(f"OVR {j.ovr}", (r.right - 16, r.y + 8), 26, U.VERDE, True, "tr", titulo=True)
        ui.texto(f"POT {j.pot}", (r.right - 16, r.y + 34), 14, U.AMARILLO, True, "tr")
        # atributos principales
        nombres = {"pace": "RIT", "shooting": "TIR", "passing": "PAS", "dribbling": "REG", "defending": "DEF",
                   "physic": "FÍS"}
        if j.grupo == "POR":
            nombres = {"pace": "EST", "shooting": "SAQ", "passing": "MAN", "dribbling": "COL", "defending": "REF",
                       "physic": "FÍS"}
        for n, (k, lab) in enumerate(nombres.items()):
            x = r.x + 16 + (n % 3) * 110
            y = r.y + 64 + (n // 3) * 22
            ui.texto(lab, (x, y), 12, U.APAGADO)
            ui.barra((x + 30, y + 4, 50, 8), j.rasgos[k] / 100,
                     U.VERDE if j.rasgos[k] >= 75 else U.AMARILLO if j.rasgos[k] >= 55 else U.ROJO)
        # modelos
        x = r.x + 360
        ui.texto("Rol (K-means)", (x, r.y + 62), 12, U.APAGADO)
        ui.texto(j.rol, (x, r.y + 78), 14, U.AZUL, True, maxw=r.right - x - 12)
        dif = j.valor_pred / j.valor - 1
        ui.texto(f"Valor real {eur(j.valor)} · valor justo (regresión) {eur(j.valor_pred)}", (r.x + 16, r.y + 116), 13)
        ui.texto("Aptitud por posición (árbol):", (r.x + 16, r.y + 138), 12, U.APAGADO)
        for n, g in enumerate(GRUPOS):
            x = r.x + 180 + n * 95
            ui.texto(g, (x, r.y + 138), 12, U.APAGADO)
            ui.barra((x + 28, r.y + 142, 44, 7), j.aptitud(g), color_apt(j.aptitud(g)))

    def asignar(self, slot, j):
        c = self.club
        if j.lesion:
            self.aviso(f"{j.nombre} está {'suspendido' if j.motivo == 'sanción' else 'lesionado'}.", U.ROJO)
            return
        if j in c.once:
            k = c.once.index(j)
            c.once[k], c.once[slot] = c.once[slot], j
        else:
            c.once[slot] = j
        self.sel_slot = self.sel_jug = None

    def cambiar_formacion(self, f):
        c = self.club
        autoalinear(c, f)
        self.sel_slot = self.sel_jug = None

    # ---------------------------------------------------------- mercado
    def tab_mercado(self):
        ui, c, m = self.ui, self.club, self.mercado
        rep = m["reemplazo"]
        if rep:
            ui.texto(f"Reemplazos para {rep.nombre} (jugadores más parecidos · K-means)", (X0, 52), 18, U.AZUL, True)
            if ui.boton((ANCHO - 170, 46, 150, 30), "Ver todo el mercado", tam=14):
                m["reemplazo"] = None
                m.update(pagina=0, sel=None, clave=None)
        else:
            ui.texto("Grupo", (X0, 55), 13, U.APAGADO)
            for k, g in enumerate([None] + GRUPOS):
                if ui.boton((X0 + 48 + k * 58, 46, 54, 30), g or "Todos", m["grupo"] == g, tam=13):
                    m.update(grupo=g, pagina=0, clave=None)
            ui.texto("Orden", (X0 + 360, 55), 13, U.APAGADO)
            for k, (o, lab) in enumerate([("gangas", "Gangas"), ("ovr", "OVR"), ("pot", "Potencial"),
                                           ("precio", "Precio")]):
                if ui.boton((X0 + 402 + k * 78, 46, 74, 30), lab, m["orden"] == o, color=U.AMARILLO, tam=13,
                            tip="Gangas = valor justo (regresión) / precio pedido." if o == "gangas" else None):
                    m.update(orden=o, pagina=0, clave=None)
            ui.texto("OVR mín.", (X0 + 730, 55), 13, U.APAGADO)
            if ui.boton((X0 + 790, 46, 26, 30), "−", tam=16):
                m.update(ovr_min=max(0, m["ovr_min"] - 2), pagina=0, clave=None)
            ui.texto(m["ovr_min"], (X0 + 830, 61), 15, U.TEXTO, True, "mc")
            if ui.boton((X0 + 846, 46, 26, 30), "+", tam=16):
                m.update(ovr_min=min(90, m["ovr_min"] + 2), pagina=0, clave=None)
            if ui.boton((X0 + 884, 46, 150, 30), "Solo asequibles", m["asequibles"], U.AZUL, tam=13):
                m.update(asequibles=not m["asequibles"], pagina=0, clave=None)
            nuevo = ui.entrada_texto((X0, 84, 300, 28), m["texto"], "buscar", "Buscar jugador o club…")
            if nuevo != m["texto"]:
                m.update(texto=nuevo, pagina=0, clave=None)
        # ---- lista candidata (en caché)
        clave = (m["grupo"], m["orden"], m["ovr_min"], m["asequibles"], m["texto"], rep.id if rep else None,
                 int(c.presupuesto // 100_000), len(c.plantel))
        if m["clave"] != clave:
            m["clave"] = clave
            cand = self.mundo.candidatos_mercado(c)
            if rep:
                lista = [p for p, _ in self.mundo.similares(rep, cand, 40)]
            else:
                t = m["texto"].lower()
                lista = [p for p in cand if (m["grupo"] is None or p.grupo == m["grupo"]) and p.ovr >= m["ovr_min"]
                         and (not t or t in p.nombre.lower() or t in p.nombre_largo.lower()
                              or t in self.nombre_club(p).lower())]
                if m["asequibles"]:
                    lista = [p for p in lista if self.mundo.precio(p) <= c.presupuesto]
                claves = {"gangas": lambda p: -(p.valor_pred / self.mundo.precio(p)), "ovr": lambda p: -p.ovr,
                          "pot": lambda p: -p.pot, "precio": lambda p: self.mundo.precio(p)}
                lista.sort(key=claves[m["orden"]])
            m["cache"] = lista
        lista = m["cache"]
        # ---- tabla
        cols = [("Jugador", 0, 'l'), ("Club", 175, 'l'), ("Pos", 320, 'l'), ("Edad", 362, 'l'), ("OVR", 408, 'l'),
                ("POT", 448, 'l'), ("Rol (K-means)", 492, 'l'), ("Precio", 745, 'r'), ("Valor justo", 840, 'r'),
                ("Dif.", 920, 'r')]
        y0 = 122
        for n, x, al in cols:
            ui.texto(n, (X0 + 14 + x, y0), 12, U.APAGADO, anchor="tl" if al == 'l' else "tr")
        filas, fh = 15, 28
        por_pag = filas
        npag = max(1, math.ceil(len(lista) / por_pag))
        m["pagina"] = min(m["pagina"], npag - 1)
        for n, p in enumerate(lista[m["pagina"] * por_pag:(m["pagina"] + 1) * por_pag]):
            r = pygame.Rect(X0, y0 + 20 + n * fh, 1032, fh - 2)
            if p is m["sel"]:
                ui.panel(r, U.PANEL2, 6, U.VERDE)
            elif ui.hover(r):
                ui.panel(r, U.PANEL, 6)
            precio = self.mundo.precio(p)
            dif = p.valor_pred / precio - 1
            cy = r.centery
            ui.texto(p.nombre, (X0 + 14, cy), 14, anchor="ml", maxw=155)
            ui.texto(self.nombre_club(p), (X0 + 189, cy), 13, U.APAGADO, anchor="ml", maxw=125)
            ui.texto(p.pos, (X0 + 334, cy), 14, U.AMARILLO, anchor="ml")
            ui.texto(p.edad, (X0 + 376, cy), 14, anchor="ml")
            ui.texto(p.ovr, (X0 + 422, cy), 14, U.VERDE, True, "ml")
            ui.texto(p.pot, (X0 + 462, cy), 14, anchor="ml")
            ui.texto(p.rol, (X0 + 506, cy), 13, U.APAGADO, anchor="ml", maxw=225)
            ui.texto(eur(precio), (X0 + 14 + 745, cy), 14, U.TEXTO, True, "mr")
            ui.texto(eur(p.valor_pred), (X0 + 14 + 840, cy), 14, anchor="mr")
            ui.texto(f"{dif:+.0%}", (X0 + 14 + 920, cy), 14, U.VERDE if dif > 0.05 else U.ROJO if dif < -0.05 else U.APAGADO,
                     True, "mr")
            if ui.clic_en(r):
                m["sel"] = p
        if not lista:
            ui.texto("Sin resultados con estos filtros.", (X0 + 14, y0 + 40), 16, U.APAGADO)
        # ---- pie: paginación y compra
        yb = y0 + 20 + filas * fh + 8
        if ui.boton((X0, yb, 36, 30), "‹", habilitado=m["pagina"] > 0):
            m["pagina"] -= 1
        ui.texto(f"{m['pagina'] + 1}/{npag}  ·  {len(lista)} jugadores", (X0 + 130, yb + 15), 14, U.APAGADO, anchor="mc")
        if ui.boton((X0 + 230, yb, 36, 30), "›", habilitado=m["pagina"] < npag - 1):
            m["pagina"] += 1
        if pygame.Rect(X0, y0, 1032, filas * fh).collidepoint(ui.mouse) and ui.rueda:
            m["pagina"] = max(0, min(npag - 1, m["pagina"] - ui.rueda))
        s = m["sel"]
        if s:
            ok, msg = self.mundo.puede_comprar(c, s)
            precio = self.mundo.precio(s)
            ui.texto(f"{s.nombre} · {s.rol}", (X0 + 290, yb + 4), 15, U.TEXTO, True, maxw=330)
            ui.texto(msg or f"Fichaje por {eur(precio)}  ·  te quedarían {eur(c.presupuesto - precio)}",
                     (X0 + 290, yb + 24), 13, U.ROJO if msg else U.APAGADO, maxw=330)
            if ui.boton((X0 + 640, yb - 2, 190, 40), f"Fichar por {eur(precio)}", habilitado=ok, tam=15):
                okc, msgc = self.mundo.comprar(c, s)
                self.aviso(msgc, U.VERDE if okc else U.ROJO)
                m.update(sel=None, clave=None)
            sim = self.mundo.similares(s, c.plantel, 1)
            if sim:
                ui.texto(f"Tu más parecido: {sim[0][0].nombre} ({sim[0][0].ovr})", (X0 + 850, yb + 14), 13, U.APAGADO,
                         anchor="ml", maxw=180)

    def nombre_club(self, p):
        cl = self.mundo.clubes.get(p.club_id)
        return cl.nombre if cl else "Otras ligas"

    # ----------------------------------------------------------- táctica
    def tab_tactica(self):
        ui, c, a = self.ui, self.club, self.asist
        ui.texto("Táctica del equipo", (X0, 48), 40, titulo=True)
        y = 100
        for k in tac.CLAVES:
            ui.texto(tac.ETIQUETAS[k], (X0, y + 12), 16, U.TEXTO, True, "ml")
            ops = tac.OPCIONES[k]
            w = 132 if len(ops) == 4 else 100
            for n, op in enumerate(ops):
                if ui.boton((X0 + 200 + n * (w + 6), y, w, 32), op, c.tactica[k] == op, tam=13):
                    c.tactica[k] = op
            y += 40
        bono = a.bono_tactico(c.tactica)
        ui.texto("Ofensividad táctica", (X0, y + 14), 14, U.APAGADO)
        ui.barra((X0 + 200, y + 18, 220, 10), (tac.ofensividad(c.tactica) + 1) / 2, U.NARANJA)
        ui.texto("Más goles a favor, pero también más ocasiones para el rival (heurístico, no sale de los datos).",
                 (X0, y + 40), 13, U.APAGADO)
        # ---- reglas de asociación
        r = pygame.Rect(X0, y + 66, ANCHO - X0 - 16, ALTO - (y + 66) - 14)
        ui.panel(r, U.PANEL, 12, U.BORDE)
        ui.texto("Asistente de reglas de asociación (Apriori)", (r.x + 16, r.y + 10), 18, U.VERDE, True)
        ui.texto(f"Bono táctico actual: {bono:+.1%} de goles esperados", (r.right - 16, r.y + 12), 16,
                 U.VERDE if bono > 0 else U.ROJO if bono < 0 else U.APAGADO, True, "tr")
        apl = a.reglas_aplicables(c.tactica)
        yy = r.y + 44
        if not apl:
            ui.texto("Ninguna regla significativa aplica a esta combinación.", (r.x + 16, yy), 14, U.APAGADO)
        for rg in apl[:5]:
            niv = rg["entonces"].split("= ")[1]
            col = U.VERDE if niv in ("Alto", "Élite") else U.ROJO if niv == "Bajo" else U.APAGADO
            ui.texto("SI " + "  Y  ".join(rg["si"]), (r.x + 16, yy), 13,
                     U.TEXTO, maxw=r.w - 32)
            ui.texto(f"→ equipos de nivel {niv.upper()} · confianza {rg['confianza']:.0%} · lift {rg['lift']:.2f}"
                     f" · soporte {rg['soporte']:.1%}", (r.x + 34, yy + 17), 13, col, True, maxw=r.w - 50)
            yy += 38
        if ui.boton((r.x + 16, r.bottom - 48, 330, 34), "Aplicar la mejor sugerencia del asistente", color=U.AZUL, tam=14):
            sug, b2 = self.sugerir()
            if sug:
                c.tactica.update(sug)
                self.aviso(f"Táctica ajustada (bono {b2:+.1%}).")
        ui.texto("Las reglas muestran asociación (los equipos fuertes suelen usar estos ajustes), no causalidad.",
                 (r.x + 364, r.bottom - 30), 13, U.APAGADO, anchor="ml", maxw=r.w - 380)

    def sugerir(self):
        a, c = self.asist, self.club
        mejor, bono = None, a.bono_tactico(c.tactica)
        inv = {tac.ETIQUETAS[k]: k for k in tac.CLAVES}
        for rg in a.reglas:
            if rg["entonces"].split("= ")[1] not in ("Alto", "Élite"):
                continue
            cand = dict(c.tactica)
            for it in rg["si"]:
                lab, val = it.split(" = ")
                cand[inv[lab]] = val
            b = a.bono_tactico(cand)
            if b > bono + 1e-9:
                mejor, bono = cand, b
        return mejor, bono

    # -------------------------------------------------------------- liga
    def tab_liga(self):
        ui, c = self.ui, self.club
        ui.texto(f"{self.liga.nombre} · Clasificación", (X0, 44), 40, titulo=True)
        hdr = [("#", 0), ("Club", 40), ("PJ", 330), ("G", 372), ("E", 410), ("P", 448), ("GF", 486), ("GC", 526),
               ("DG", 568), ("PTS", 616)]
        y = 100
        for n, x in hdr:
            ui.texto(n, (X0 + 10 + x, y), 12, U.APAGADO)
        tabla = self.liga.tabla()
        fh = 26 if len(tabla) <= 18 else 24.5
        for i, t in enumerate(tabla):
            r = pygame.Rect(X0, int(y + 20 + i * fh), 670, int(fh) - 1)
            if t is c:
                ui.panel(r, U.PANEL2, 5, U.VERDE)
            elif i < 4:
                pygame.draw.rect(ui.surf, (30, 60, 55), r, border_radius=5)
            elif i >= len(tabla) - 3:
                pygame.draw.rect(ui.surf, (62, 34, 40), r, border_radius=5)
            cy = r.centery
            ui.texto(i + 1, (X0 + 10, cy), 14, anchor="ml")
            ui.insignia((X0 + 58, cy), 9, t)
            ui.texto(t.nombre, (X0 + 80, cy), 14, U.TEXTO, t is c, "ml", maxw=240)
            for v, x in ((t.pj, 330), (t.g, 372), (t.e, 410), (t.p, 448), (t.gf, 486), (t.gc, 526)):
                ui.texto(v, (X0 + 10 + x, cy), 14, anchor="ml")
            ui.texto(f"{t.dg:+d}", (X0 + 10 + 568, cy), 14, anchor="ml")
            ui.texto(t.pts, (X0 + 10 + 616, cy), 15, U.AMARILLO, True, "ml")
        # resultados
        rx = X0 + 700
        ui.panel((rx, 100, ANCHO - rx - 14, 590), U.PANEL, 12, U.BORDE)
        ui.texto("Última jornada", (rx + 16, 112), 18, U.VERDE, True)
        if not self.ultimos:
            ui.texto("Aún no se ha jugado.", (rx + 16, 146), 14, U.APAGADO)
        for i, (h, v, gh, gv) in enumerate(self.ultimos[:10]):
            H, V = self.mundo.clubes[h], self.mundo.clubes[v]
            yy = 146 + i * 30
            mio = c.id in (h, v)
            ui.texto(H.nombre, (rx + 150, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "tr", maxw=130)
            ui.texto(f"{gh} - {gv}", (rx + 170, yy), 14, U.TEXTO, True, "tc")
            ui.texto(V.nombre, (rx + 196, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "tl", maxw=130)
        ui.texto("Verde: zona alta · Rojo: descenso", (rx + 16, 670), 12, U.APAGADO, anchor="bl")

    # --------------------------------------------------- datos y modelos
    def _cargar_ml(self):
        if self._ml is None:
            self._ml = {}
            try:
                self._ml["met"] = json.loads((REPORTES / "metricas.json").read_text(encoding="utf-8"))
                self._ml["pca"] = pd.read_csv(DATA / "pca_roles.csv")
            except Exception:
                self._ml["met"] = {}
                self._ml["pca"] = None
        return self._ml

    def tab_datos(self):
        ui = self.ui
        ml = self._cargar_ml()
        met = ml["met"]
        ui.texto("Datos y modelos", (X0, 44), 40, titulo=True)
        if not met:
            ui.texto("Ejecuta ml/entrenar.py para generar las métricas.", (X0, 100), 16, U.ROJO)
            return
        # ---- scatter PCA
        r = pygame.Rect(X0, 100, 500, 312)
        ui.panel(r, U.PANEL, 12, U.BORDE)
        ui.texto("K-means · roles de jugadores (proyección PCA)", (r.x + 14, r.y + 8), 15, U.VERDE, True)
        pca = ml["pca"]
        if pca is not None:
            if "xy" not in ml:
                x, y = pca.x.values, pca.y.values
                ml["xy"] = ((x - x.min()) / (x.max() - x.min()), (y - y.min()) / (y.max() - y.min()), pca.c.values)
            nx, ny, cc = ml["xy"]
            area = pygame.Rect(r.x + 12, r.y + 34, 330, 254)
            if "surf" not in ml:
                s = pygame.Surface(area.size, pygame.SRCALPHA)
                for a_, b_, c_ in zip(nx, ny, cc):
                    pygame.draw.circle(s, U.COLORES_CLUSTER[int(c_) % 9] + (150,),
                                       (int(a_ * (area.w - 6)) + 3, int((1 - b_) * (area.h - 6)) + 3), 2)
                ml["surf"] = s
            ui.surf.blit(ml["surf"], area)
            roles = met["clustering"]["roles"]
            for k, nom in roles.items():
                yy = r.y + 40 + int(k) * 26
                pygame.draw.circle(ui.surf, U.COLORES_CLUSTER[int(k) % 9], (r.x + 356, yy + 8), 5)
                ui.texto(nom, (r.x + 368, yy), 12, U.TEXTO, maxw=124)
        # ---- tarjetas de métricas
        mx = X0 + 516
        mw = ANCHO - mx - 14
        ui.panel((mx, 100, mw, 312), U.PANEL, 12, U.BORDE)
        ui.texto("Métricas de los modelos (conjunto de prueba)", (mx + 14, 108), 15, U.VERDE, True)
        rg, ap, apar = met["regresion"]["Gradient Boosting"], met["arbol_posicion"], met["arbol_partido"]
        filas = [
            ("Clustering K-means", f"k={met['clustering']['k']} · silueta {met['clustering']['silueta']:.2f}",
             "Roles solapados: la silueta es baja y es normal."),
            ("Regresión (valor justo)", f"R² {rg['R2_log']:.3f} · error medio {rg['MAE_eur'] / 1e6:.2f} M€",
             "Gradient Boosting; la regresión lineal logra R² " + f"{met['regresion']['Regresión lineal']['R2_log']:.3f}."),
            ("Árbol · posición", f"accuracy {ap['accuracy_arbol']:.1%} (RF {ap['accuracy_random_forest']:.1%})",
             "Clasifica POR/DEF/MED/DEL por atributos."),
            ("Árbol · resultado", f"accuracy {apar['accuracy']:.1%} vs base {apar['linea_base']:.1%}",
             "Entrenado con partidos SIMULADOS; los empates son casi impredecibles."),
            ("Reglas de asociación", f"{met['reglas_tacticas']['reglas']} reglas · soporte≥1.5 % · conf≥30 %",
             f"{met['reglas_tacticas']['transacciones']} configuraciones tácticas de FC 22-24."),
        ]
        yy = 136
        for t, v, n in filas:
            ui.texto(t, (mx + 14, yy), 12, U.APAGADO)
            ui.texto(v, (mx + 14, yy + 15), 16, U.TEXTO, True, maxw=mw - 28)
            ui.texto(n, (mx + 14, yy + 37), 12, U.APAGADO, maxw=mw - 28)
            yy += 54
        # ---- matriz de confusión
        r2 = pygame.Rect(X0, 424, 500, 272)
        ui.panel(r2, U.PANEL, 12, U.BORDE)
        ui.texto("Árbol de posición · matriz de confusión", (r2.x + 14, r2.y + 8), 15, U.VERDE, True)
        cm = np.array(ap["matriz_confusion"])
        orden = ap["orden"]
        cell = 40
        ox, oy = r2.x + 110, r2.y + 62
        ui.texto("predicho →", (ox + 2 * cell, oy - 40), 12, U.APAGADO, anchor="tc")
        for i, g in enumerate(orden):
            ui.texto(g, (ox + i * cell + cell // 2, oy - 22), 13, U.TEXTO, True, "tc")
            ui.texto(g, (ox - 10, oy + i * cell + cell // 2), 13, U.TEXTO, True, "mr")
        for i in range(4):
            tot = max(1, cm[i].sum())
            for j in range(4):
                f = cm[i, j] / tot
                col = U.mezclar((28, 38, 58), U.VERDE if i == j else U.ROJO, min(1.0, f * 1.1))
                rc = pygame.Rect(ox + j * cell + 1, oy + i * cell + 1, cell - 2, cell - 2)
                pygame.draw.rect(ui.surf, col, rc, border_radius=5)
                ui.texto(int(cm[i, j]), rc.center, 14, U.TEXTO, True, "mc")
        ui.texto("real ↓", (r2.x + 30, oy + 2 * cell), 12, U.APAGADO, anchor="mc")
        ui.parrafo("Los porteros se distinguen perfecto; los errores están entre posiciones vecinas "
                   "(DEF↔MED, MED↔DEL), igual que en el fútbol real.", pygame.Rect(r2.x + 14, r2.bottom - 50, 472, 40), 12,
                   U.APAGADO)
        # ---- mejores reglas
        r3 = pygame.Rect(mx, 424, mw, 272)
        ui.panel(r3, U.PANEL, 12, U.BORDE)
        ui.texto("Reglas más fuertes (mayor lift) hacia nivel Alto/Élite", (r3.x + 14, r3.y + 8), 15, U.VERDE, True)
        top = [x for x in self.asist.reglas if x["entonces"].split("= ")[1] in ("Alto", "Élite")][:5]
        yy = r3.y + 38
        for rg_ in top:
            ui.texto("SI " + " Y ".join(rg_["si"]), (r3.x + 14, yy), 12, U.TEXTO, maxw=r3.w - 28)
            ui.texto(f"→ {rg_['entonces']} · conf {rg_['confianza']:.0%} · lift {rg_['lift']:.2f}",
                     (r3.x + 28, yy + 16), 12, U.VERDE, True)
            yy += 42
        ui.texto("El dataset no contiene resultados reales de partidos: los partidos del juego se simulan.",
                 (r3.x + 14, r3.bottom - 24), 12, U.AMARILLO, anchor="ml", maxw=r3.w - 28)

    # ============================================================ PARTIDO
    def preparar_partido(self):
        c = self.club
        cambios = reparar_once(c)
        for sale, entra in cambios:
            self.aviso(f"{entra.nombre} sustituye a {sale.nombre if sale else 'una baja'} en el once.", U.AMARILLO, 5000)
        rid, local_user = self.liga.rival(c)
        riv = self.mundo.clubes[rid]
        local, visit = (c, riv) if local_user else (riv, c)
        pron = self.asist.pronostico(local, visit)
        self.p = {"fase": "pre", "local": local, "visit": visit, "user_local": local_user, "pron": pron,
                  "ga": 0, "gb": 0, "eventos": [], "t0": 0, "min": 0}
        self.ir("partido")

    def escena_partido(self):
        p = self.p
        if p["fase"] == "pre":
            self.partido_pre()
        else:
            self.partido_vivo()

    def marcador(self, y=60):
        ui, p = self.ui, self.p
        L, V = p["local"], p["visit"]
        ui.insignia((ANCHO // 2 - 330, y + 40), 44, L)
        ui.insignia((ANCHO // 2 + 330, y + 40), 44, V)
        ui.texto_fit(L.nombre, (ANCHO // 2 - 270, y + 16), 34, 18, 230, titulo=True)
        ui.texto_fit(V.nombre, (ANCHO // 2 + 270, y + 16), 34, 18, 230, anchor="tr", titulo=True)
        ui.texto(f"{L.formacion} · {L.entrenador}", (ANCHO // 2 - 270, y + 52), 13, U.APAGADO, maxw=210)
        ui.texto(f"{V.formacion} · {V.entrenador}", (ANCHO // 2 + 270, y + 52), 13, U.APAGADO, anchor="tr", maxw=210)

    def partido_pre(self):
        ui, p, c = self.ui, self.p, self.club
        pr = p["pron"]
        L, V = p["local"], p["visit"]
        ui.texto("Previa del partido", (ANCHO // 2, 14), 18, U.APAGADO, anchor="tc")
        self.marcador(34)
        ui.texto("VS", (ANCHO // 2, 90), 40, U.AMARILLO, anchor="tc", titulo=True)
        ui.texto(f"{L.estadio}", (ANCHO // 2, 130), 14, U.APAGADO, anchor="tc")
        # comparación de líneas
        r = pygame.Rect(60, 170, 520, 250)
        ui.panel(r, U.PANEL, 12, U.BORDE)
        ui.texto("Comparación de plantillas (once titular)", (r.x + 16, r.y + 10), 16, U.VERDE, True)
        for i, (k, lab) in enumerate([("ataque", "Ataque"), ("medio", "Mediocampo"), ("defensa", "Defensa"),
                                      ("overall", "Nivel general")]):
            y = r.y + 58 + i * 46
            a, b = pr["fa"][k], pr["fb"][k]
            ui.texto(lab, (r.centerx, y - 8), 13, U.APAGADO, anchor="tc")
            tot = a + b
            wl = int((r.w - 140) * a / tot)
            ui.texto(f"{a:.1f}", (r.x + 16, y + 22), 15, U.TEXTO, True, "ml")
            ui.texto(f"{b:.1f}", (r.right - 16, y + 22), 15, U.TEXTO, True, "mr")
            pygame.draw.rect(ui.surf, L.color, (r.x + 70, y + 16, wl, 12), border_radius=6)
            pygame.draw.rect(ui.surf, U.mezclar(V.color, (255, 255, 255), .0), (r.x + 70 + wl, y + 16, r.w - 140 - wl, 12),
                             border_radius=6)
        # pronóstico
        r2 = pygame.Rect(600, 170, 620, 250)
        ui.panel(r2, U.PANEL, 12, U.BORDE)
        ui.texto("Pronóstico del asistente", (r2.x + 16, r2.y + 10), 16, U.VERDE, True)
        mc = pr["mc"]
        ui.texto("Simulación Monte Carlo (3000 partidos, Poisson)", (r2.x + 16, r2.y + 36), 13, U.APAGADO)
        vals = [(f"Gana {L.nombre}", mc["gana_a"], L.color), ("Empate", mc["empate"], (170, 175, 190)),
                (f"Gana {V.nombre}", mc["gana_b"], V.color)]
        for i, (lab, v, col) in enumerate(vals):
            y = r2.y + 62 + i * 30
            ui.texto(lab, (r2.x + 16, y + 9), 14, anchor="ml", maxw=190)
            ui.barra((r2.x + 210, y + 2, 300, 14), v, col)
            ui.texto(f"{v:.0%}", (r2.right - 16, y + 9), 15, U.TEXTO, True, "mr")
        ui.texto(f"Marcador más probable {mc['marcador'][0]}-{mc['marcador'][1]}  ·  goles esperados "
                 f"{mc['esperado'][0]:.1f} - {mc['esperado'][1]:.1f}", (r2.x + 16, r2.y + 158), 14, U.AMARILLO, True)
        if pr.get("arbol"):
            ar = pr["arbol"]
            ui.texto(f"Árbol de decisión: favorece a {pr['arbol_clase'].upper()}  "
                     f"(L {ar.get('Local', 0):.0%} · E {ar.get('Empate', 0):.0%} · V {ar.get('Visitante', 0):.0%})",
                     (r2.x + 16, r2.y + 186), 13, U.TEXTO, maxw=r2.w - 32)
            ui.texto("¿Por qué?  " + " → ".join(pr["arbol_camino"][:3]), (r2.x + 16, r2.y + 208), 12, U.APAGADO,
                     maxw=r2.w - 32)
        # consejos
        r3 = pygame.Rect(60, 436, 1160, 150)
        ui.panel(r3, U.PANEL, 12, U.BORDE)
        mi = c
        bono = pr["ba"] if p["user_local"] else pr["bb"]
        ui.texto(f"Tu bono táctico (reglas Apriori): {bono:+.1%}", (r3.x + 16, r3.y + 10), 15, U.VERDE, True)
        apl = self.asist.reglas_aplicables(mi.tactica)[:2]
        yy = r3.y + 40
        for rg in apl:
            ui.texto("• SI " + " Y ".join(rg["si"]) + f" → {rg['entonces']} (lift {rg['lift']:.2f})",
                     (r3.x + 16, yy), 13, maxw=r3.w - 32)
            yy += 22
        rival = V if p["user_local"] else L
        brv = pr["bb"] if p["user_local"] else pr["ba"]
        ui.texto(f"Táctica rival: {rival.tactica['salida']} · {rival.tactica['creacion']} · {rival.tactica['defensa']}"
                 f"  (bono {brv:+.1%})", (r3.x + 16, yy + 6), 13, U.APAGADO, maxw=r3.w - 32)
        lesionados = [j.nombre for j in c.plantel if j.lesion and j.motivo != "sanción"]
        suspendidos = [j.nombre for j in c.plantel if j.lesion and j.motivo == "sanción"]
        if lesionados or suspendidos:
            partes = ([f"Lesionados: {', '.join(lesionados[:4])}"] if lesionados else []) + \
                     ([f"Suspendidos: {', '.join(suspendidos[:4])}"] if suspendidos else [])
            ui.texto("No disponibles · " + "  |  ".join(partes), (r3.x + 16, r3.bottom - 56), 13, U.ROJO, maxw=r3.w - 32)
        fuera = [j.nombre for (g, j) in c.xi_con_grupo() if j.aptitud(g) < 0.55]
        if fuera:
            ui.texto("Fuera de posición: " + ", ".join(fuera), (r3.x + 16, r3.bottom - 32), 13, U.AMARILLO, maxw=r3.w - 32)
        if ui.boton((60, 620, 180, 54), "← Volver", tam=18):
            self.ir("hub")
        if ui.boton((ANCHO - 340, 620, 280, 54), "Jugar el partido", True, tam=22):
            self.iniciar_partido()

    # ---------------------------------------------------------- partido en vivo
    VEL_MS = 600                     # milisegundos reales por minuto de partido (a velocidad x1): un partido dura ~1 min
    MENTALIDADES = {"atk": ("Atacar", 1.20, 1.15, "Más goles propios (+20 %), pero también del rival (+15 %)."),
                    "eq": ("Equilibrado", 1.0, 1.0, "Sin cambios respecto al plan inicial."),
                    "def": ("Cerrarse", 0.85, 0.78, "Menos goles propios (-15 %) y bastante menos del rival (-22 %).")}

    def iniciar_partido(self):
        p = self.p
        pr = p["pron"]
        lado = "a" if p["user_local"] else "b"
        est = ev.nuevo_estado(p["local"], p["visit"], pr["la"], pr["lb"], lado)
        ev.generar_tramo(est, 1, 45, self.rng)
        med = pr["fa"]["medio"], pr["fb"]["medio"]
        vista = VistaPartido(p["local"], p["visit"], med[0] / (med[0] + med[1]), semilla=p["local"].id * 1000 + p["visit"].id)
        p.update(fase="vivo", est=est, lado=lado, min=0, fin=False, pausa=None, mini=None, ev_mini=None,
                 t_ult=pygame.time.get_ticks(), acum=0.0, vel=1, mentalidad="eq", tramo=1, jugadas=[],
                 banner=None, vista=vista)

    def _pendiente_en(self, minuto):
        for e in self.p["est"]["eventos"]:
            if e["pend"] and e["res"] is None and e["min"] <= minuto:
                return e
        return None

    def _segundo_tiempo(self):
        p = self.p
        est = p["est"]
        _, f_propio, f_rival, _ = self.MENTALIDADES[p["mentalidad"]]
        otro = "b" if p["lado"] == "a" else "a"
        est["f"][p["lado"]], est["f"][otro] = f_propio, f_rival
        ev.generar_tramo(est, 46, 90, self.rng)
        p["tramo"] = 2
        p["pausa"] = None
        p["vista"].reiniciar("b")                                  # saque inicial del 2.º tiempo

    def _anunciar(self, minuto, solo=None):
        """Cartel breve con el evento más importante del minuto; además se actúan en la vista animada."""
        p = self.p
        for e in ([solo] if solo else p["est"]["eventos"]):
            if e["min"] == minuto and (e["res"] is not None or e["tipo"] not in ev.INTERACTIVOS):
                p["vista"].evento(e)
        prio = {"gol": 0, "roja": 1, "lesion": 2, "amarilla": 3}
        cands = [e for e in p["est"]["eventos"] if e["min"] == minuto and not e["oculto"]
                 and (e["tipo"] in prio or e["res"] is not None)]
        if not cands:
            return
        e = min(cands, key=lambda x: prio.get("gol" if ev.es_gol(x) else x["tipo"], 5))
        titulo, _, clave = ev.describir(e, p["est"]["clubes"])
        col = {"gol": U.VERDE, "amarilla": U.AMARILLO, "roja": U.ROJO, "lesion": U.ROJO}.get(clave, U.APAGADO)
        p["banner"] = (titulo, col, pygame.time.get_ticks() + 2200)

    def _avanzar_partido(self):
        p = self.p
        ahora = pygame.time.get_ticks()
        dt = min(ahora - p["t_ult"], 100)
        p["t_ult"] = ahora
        if p["pausa"] or p["fin"]:
            return
        p["vista"].actualizar(dt, p["vel"])
        p["acum"] += dt * p["vel"]
        while p["acum"] >= self.VEL_MS and not p["pausa"] and not p["fin"]:
            e = self._pendiente_en(p["min"])
            if e:
                p["pausa"], p["ev_mini"] = "mini", e
                p["mini"] = mj.crear(e, p["lado"], self.rng)
                return
            if p["min"] >= 90:
                p["fin"] = True
                break
            if p["min"] == 45 and p["tramo"] == 1:
                p["pausa"] = "descanso"
                return
            p["acum"] -= self.VEL_MS
            p["min"] += 1
            self._anunciar(p["min"])

    def omitir_partido(self):
        """Salta hasta el final: las jugadas pendientes se resuelven con la probabilidad del modelo."""
        p = self.p
        p["mini"] = None
        p["pausa"] = None
        while not p["fin"]:
            e = self._pendiente_en(p["min"])
            if e:
                ev.autoresolver(e, self.rng)
                continue
            if p["min"] >= 90:
                p["fin"] = True
            elif p["min"] == 45 and p["tramo"] == 1:
                self._segundo_tiempo()
            else:
                p["min"] += 1
        p["banner"] = None

    def _cerrar_minijuego(self, r):
        p = self.p
        e, mini = p["ev_mini"], p["mini"]
        if r == "auto":
            ev.autoresolver(e, self.rng)
        else:
            e["res"], e["motivo"], e["pend"] = mini.resultado, mini.motivo, False
            suyo = e["lado"] == p["lado"]
            p["jugadas"].append((e["tipo"], (e["res"] == "gol") if suyo else (e["res"] != "gol")))
        p["pausa"], p["mini"], p["ev_mini"] = None, None, None
        p["acum"] = 0.0
        self._anunciar(e["min"], solo=e)

    @staticmethod
    def _icono_evento(surf, clave, cx, cy):
        if clave == "gol":
            pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 9)
            pygame.draw.circle(surf, (20, 20, 20), (cx, cy), 9, 2)
            pygame.draw.circle(surf, (20, 20, 20), (cx, cy), 3)
        elif clave in ("amarilla", "roja"):
            pygame.draw.rect(surf, U.AMARILLO if clave == "amarilla" else U.ROJO, (cx - 6, cy - 9, 12, 18), border_radius=2)
        elif clave == "lesion":
            pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 10)
            pygame.draw.rect(surf, U.ROJO, (cx - 6, cy - 2, 12, 4))
            pygame.draw.rect(surf, U.ROJO, (cx - 2, cy - 6, 4, 12))
        elif clave == "fallo":
            pygame.draw.circle(surf, (90, 100, 120), (cx, cy), 10, 2)
            pygame.draw.line(surf, (160, 170, 190), (cx - 5, cy - 5), (cx + 5, cy + 5), 2)
            pygame.draw.line(surf, (160, 170, 190), (cx - 5, cy + 5), (cx + 5, cy - 5), 2)
        else:
            pygame.draw.circle(surf, U.NARANJA, (cx, cy), 10, 2)
            pygame.draw.circle(surf, U.NARANJA, (cx, cy), 3)

    @staticmethod
    def _icono_omitir(surf, cx, cy, col):
        for dx in (0, 11):
            pygame.draw.polygon(surf, col, [(cx + dx - 6, cy - 8), (cx + dx - 6, cy + 8), (cx + dx + 5, cy)])

    def partido_vivo(self):
        ui, p = self.ui, self.p
        est = p["est"]
        L, V = p["local"], p["visit"]
        self._avanzar_partido()
        ga, gb = ev.marcador(est["eventos"], p["min"])
        self.marcador(34)
        ui.texto(f"{ga} - {gb}", (ANCHO // 2, 80), 110, U.TEXTO, anchor="tc", titulo=True)
        if p["fin"]:
            etiqueta = "FINAL"
        elif p["pausa"] == "descanso":
            etiqueta = "DESCANSO"
        else:
            etiqueta = f"{p['min']}'"
        ui.texto(etiqueta, (ANCHO // 2, 190), 28, U.AMARILLO, True, "tc")
        ui.barra((ANCHO // 2 - 200, 232, 400, 8), p["min"] / 90, U.VERDE)
        # campo animado
        campo = pygame.Rect(ANCHO // 2 - 300, 262, 600, 330)
        p["vista"].dibujar(ui, campo)
        if p["banner"] and p["banner"][2] > pygame.time.get_ticks():
            tx, col, _ = p["banner"]
            w = ui.fuente(26, True).size(tx)[0] + 40
            r = pygame.Rect(0, 0, w, 46)
            r.midtop = (campo.centerx, campo.y + 14)
            ui.panel(r, (10, 14, 24), 10, col)
            ui.texto(tx, r.center, 26, col, True, "mc", maxw=campo.w - 40)
        # crónica
        ui.texto("Crónica", (60, 262), 18, U.VERDE, True)
        visibles = [e for e in est["eventos"] if not e["oculto"] and e["min"] <= p["min"]
                    and (e["res"] is not None or e["tipo"] not in ev.INTERACTIVOS)]
        yy = 294
        for e in reversed(visibles[-7:]):
            titulo, sub, clave = ev.describir(e, est["clubes"])
            self._icono_evento(ui.surf, clave, 74, yy + 14)
            ui.texto(f"{e['min']}'  {titulo}", (96, yy), 14, U.TEXTO, True, maxw=240)
            ui.texto(sub, (96, yy + 18), 12, U.APAGADO, maxw=240)
            yy += 42
        if not visibles:
            ui.texto("Todavía no pasa nada…", (60, 296), 14, U.APAGADO)
        self._panel_stats(pygame.Rect(960, 372, 260, 238), p["min"])
        # controles (no se muestran mientras hay un minijuego o el descanso abiertos)
        if not p["fin"] and not p["pausa"]:
            if ui.boton((ANCHO - 260, 620, 220, 50), "Omitir partido", tam=17,
                        tip="Salta al final del partido.\nLas jugadas clave se simulan solas."):
                self.omitir_partido()
            r = pygame.Rect(ANCHO - 260, 620, 220, 50)
            self._icono_omitir(ui.surf, r.x + 26, r.centery, U.TEXTO)
            ui.texto("Velocidad", (ANCHO - 590, 616), 12, U.APAGADO)
            for i, v in enumerate((1, 2, 4)):
                if ui.boton((ANCHO - 590 + i * 66, 636, 60, 34), f"x{v}", p["vel"] == v, tam=15, color=U.AZUL):
                    p["vel"] = v
        if p["pausa"] == "mini":
            r = p["mini"].dibujar(ui)
            if r:
                self._cerrar_minijuego(r)
        elif p["pausa"] == "descanso":
            self._descanso(ga, gb)
        elif p["fin"]:
            self.resumen_final(ga, gb)

    def _panel_stats(self, r, minuto):
        ui, p = self.ui, self.p
        est = p["est"]
        ui.panel(r, U.PANEL, 10, U.BORDE)
        L, V = p["local"], p["visit"]
        ui.insignia((r.x + 26, r.y + 22), 13, L)
        ui.insignia((r.right - 26, r.y + 22), 13, V)
        ui.texto("Estadísticas", (r.centerx, r.y + 22), 15, U.VERDE, True, "mc")
        st = ev.estadisticas(est["eventos"], minuto)
        pr = p["pron"]["fa"]["medio"], p["pron"]["fb"]["medio"]
        posesion = pr[0] / (pr[0] + pr[1])
        filas = [("Faltas", st["faltas"]["a"], st["faltas"]["b"]), ("Amarillas", st["amarillas"]["a"], st["amarillas"]["b"]),
                 ("Rojas", st["rojas"]["a"], st["rojas"]["b"]), ("Jugadas clave", st["jugadas"]["a"], st["jugadas"]["b"])]
        y = r.y + 44
        for lab, a, b in filas:
            ui.texto(lab, (r.centerx, y + 8), 13, U.APAGADO, anchor="mc")
            ui.texto(a, (r.x + 24, y + 8), 17, U.TEXTO, True, "ml")
            ui.texto(b, (r.right - 24, y + 8), 17, U.TEXTO, True, "mr")
            pygame.draw.line(ui.surf, U.BORDE, (r.x + 16, y + 26), (r.right - 16, y + 26), 1)
            y += 33
        ui.texto("Posesión (estimada)", (r.centerx, y + 6), 13, U.APAGADO, anchor="mc")
        bx0, bw = r.x + 62, r.w - 124
        wl = int(bw * posesion)
        col = p["vista"].col                      # los mismos colores que las camisetas en la cancha (si coinciden, el visitante cambia)
        pygame.draw.rect(ui.surf, col["a"][0], (bx0, y + 22, wl, 10), border_radius=5)
        pygame.draw.rect(ui.surf, col["b"][0], (bx0 + wl, y + 22, bw - wl, 10), border_radius=5)
        pygame.draw.rect(ui.surf, U.BORDE, (bx0, y + 22, bw, 10), 1, border_radius=5)
        ui.texto(f"{posesion:.0%}", (r.x + 24, y + 27), 14, U.TEXTO, True, "ml")
        ui.texto(f"{1 - posesion:.0%}", (r.right - 24, y + 27), 14, U.TEXTO, True, "mr")

    def _descanso(self, ga, gb):
        ui, p = self.ui, self.p
        sombra = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 175))
        ui.surf.blit(sombra, (0, 0))
        r = pygame.Rect(340, 110, 600, 520)
        ui.panel(r, (12, 18, 30), 14, U.BORDE)
        ui.texto("DESCANSO", (r.centerx, r.y + 12), 56, U.AMARILLO, anchor="tc", titulo=True)
        L, V = p["local"], p["visit"]
        ui.texto(f"{L.nombre}  {ga} - {gb}  {V.nombre}", (r.centerx, r.y + 78), 20, U.TEXTO, True, "tc", maxw=r.w - 40)
        st = ev.estadisticas(p["est"]["eventos"], 45)
        y = r.y + 118
        for lab, k in (("Faltas", "faltas"), ("Amarillas", "amarillas"), ("Rojas", "rojas"), ("Jugadas clave", "jugadas")):
            ui.texto(st[k]["a"], (r.x + 150, y), 16, U.TEXTO, True, "tr")
            ui.texto(lab, (r.centerx, y), 14, U.APAGADO, anchor="tc")
            ui.texto(st[k]["b"], (r.right - 150, y), 16, U.TEXTO, True, "tl")
            y += 26
        ui.texto("Mentalidad para el 2.º tiempo", (r.centerx, y + 14), 18, U.VERDE, True, "tc")
        y += 48
        for i, (k, (nombre, _, _, _)) in enumerate(self.MENTALIDADES.items()):
            if ui.boton((r.x + 30 + i * 186, y, 174, 46), nombre, p["mentalidad"] == k, tam=17):
                p["mentalidad"] = k
        ui.texto(self.MENTALIDADES[p["mentalidad"]][3], (r.centerx, y + 58), 14, U.TEXTO, anchor="tc", maxw=r.w - 40)
        dif = (ga - gb) if p["user_local"] else (gb - ga)
        rojas = ev.estadisticas(p["est"]["eventos"], 45)["rojas"]
        mias, suyas = (rojas["a"], rojas["b"]) if p["user_local"] else (rojas["b"], rojas["a"])
        if mias > suyas:
            consejo = "Juegas con un hombre menos: cerrarte limita el daño."
        elif suyas > mias:
            consejo = "El rival tiene un expulsado: atacar puede aprovechar la ventaja."
        elif dif < 0:
            consejo = "Vas perdiendo: atacar sube tus goles esperados, a costa de riesgo."
        elif dif >= 2:
            consejo = "Ventaja cómoda: cerrarte reduce el riesgo."
        else:
            consejo = "Partido parejo: el plan equilibrado es razonable."
        ui.texto("Consejo (regla simple, no es un modelo): " + consejo, (r.centerx, y + 88), 13, U.AMARILLO,
                 anchor="tc", maxw=r.w - 40)
        if ui.boton((r.centerx - 150, r.bottom - 74, 300, 54), "Empezar el 2.º tiempo", True, tam=19) or \
                pygame.K_RETURN in ui.teclas:
            self._segundo_tiempo()

    def resumen_final(self, ga, gb):
        ui, p, c = self.ui, self.p, self.club
        user_goles, riv_goles = (ga, gb) if p["user_local"] else (gb, ga)
        res = "¡VICTORIA!" if user_goles > riv_goles else "EMPATE" if user_goles == riv_goles else "DERROTA"
        col = U.VERDE if user_goles > riv_goles else U.AMARILLO if user_goles == riv_goles else U.ROJO
        ui.texto(res, (1090, 262), 54, col, anchor="tc", titulo=True)
        pr = p["pron"]["mc"]
        pu = (pr["gana_a"] if p["user_local"] else pr["gana_b"])
        ui.texto(f"El asistente te daba {pu:.0%} de ganar.", (1090, 322), 14, U.APAGADO, anchor="tc")
        if p["jugadas"]:
            ok = sum(1 for _, a in p["jugadas"] if a)
            ui.texto(f"Jugadas clave jugadas: {ok}/{len(p['jugadas'])} a tu favor", (1090, 342), 13, U.AMARILLO, anchor="tc")
        if ui.boton((ANCHO - 260, 620, 220, 50), "Continuar", True, tam=18):
            self.cerrar_jornada(ga, gb)

    def cerrar_jornada(self, ga, gb):
        p, c, liga = self.p, self.club, self.liga
        L, V = p["local"], p["visit"]
        self._registrar(L, V, ga, gb)
        resultados = [(L.id, V.id, ga, gb)]
        bajas = list(p["est"]["bajas"])
        for h, v in liga.calendario[liga.jornada]:
            if {h, v} == {L.id, V.id}:
                continue
            H, W = self.mundo.clubes[h], self.mundo.clubes[v]
            fa, fb = fuerzas(H.xi_con_grupo()), fuerzas(W.xi_con_grupo())
            la, lb = goles_esperados(fa, fb, H.tactica, W.tactica, True, self.asist.bono_tactico(H.tactica),
                                     self.asist.bono_tactico(W.tactica))
            g1, g2, bajas_ia, _ = ev.simular_ia(H, W, la, lb, self.rng)
            bajas.extend(bajas_ia)
            self._registrar(H, W, g1, g2)
            resultados.append((h, v, g1, g2))
        # ingresos
        mine = ga if p["user_local"] else gb
        rival = gb if p["user_local"] else ga
        extra = 0.002 if mine > rival else 0.001 if mine == rival else 0
        ingreso = round(c.valor_plantel() * (0.004 + extra), -4)
        c.presupuesto += ingreso
        # recuperación y nuevas bajas (lesiones y sanciones por roja salidas de los partidos)
        for club in liga.clubes:
            for j in club.plantel:
                if j.lesion:
                    j.lesion -= 1
        for club, j, n, motivo in bajas:
            if j.lesion >= n and j.motivo == motivo:
                continue
            j.lesion, j.motivo = n, motivo
            if club is c:
                if motivo == "sanción":
                    self.aviso(f"Roja: {j.nombre} se pierde el próximo partido.", U.ROJO, 5000)
                else:
                    self.aviso(f"Lesión: {j.nombre} estará {n} jornada(s) fuera.", U.ROJO, 5000)
        for club in liga.clubes:
            if club is not c:
                reparar_once(club)
        liga.jornada += 1
        liga.historial.append(resultados)
        self.ultimos = resultados
        self.aviso(f"Ingresos de la jornada: {eur(ingreso)}", U.VERDE)
        self.mercado["clave"] = None
        if liga.terminada:
            G.borrar()                                # temporada acabada: no hay nada que continuar
        else:
            self.guardar()                            # autoguardado al cerrar cada jornada
        self.ir("fin" if liga.terminada else "hub")

    @staticmethod
    def _registrar(H, V, gh, gv):
        H.pj += 1
        V.pj += 1
        H.gf += gh
        H.gc += gv
        V.gf += gv
        V.gc += gh
        if gh > gv:
            H.g += 1
            V.p += 1
        elif gh < gv:
            V.g += 1
            H.p += 1
        else:
            H.e += 1
            V.e += 1

    # ================================================================== FIN
    def escena_fin(self):
        ui, c, liga = self.ui, self.club, self.liga
        tabla = liga.tabla()
        pos = tabla.index(c) + 1
        cumplido = pos <= self.objetivo_pos
        ui.texto("FIN DE TEMPORADA", (ANCHO // 2, 30), 70, anchor="tc", titulo=True)
        ui.texto(f"Campeón: {tabla[0].nombre}", (ANCHO // 2, 112), 26, U.AMARILLO, True, "tc")
        ui.insignia((ANCHO // 2 - 300, 220), 50, c)
        ui.texto(f"{c.nombre}: {pos}º puesto con {c.pts} puntos", (ANCHO // 2 - 220, 190), 30, titulo=True)
        ui.texto(f"Objetivo: top {self.objetivo_pos}  →  {'¡CUMPLIDO!' if cumplido else 'No cumplido'}",
                 (ANCHO // 2 - 220, 230), 24, U.VERDE if cumplido else U.ROJO, True)
        ui.texto(f"{c.g} G · {c.e} E · {c.p} P · goles {c.gf}-{c.gc}", (ANCHO // 2 - 220, 266), 16, U.APAGADO)
        r = pygame.Rect(ANCHO // 2 - 300, 320, 600, 260)
        ui.panel(r, U.PANEL, 12, U.BORDE)
        for i, t in enumerate(tabla[:6]):
            y = r.y + 14 + i * 38
            ui.texto(i + 1, (r.x + 20, y + 14), 17, anchor="ml")
            ui.insignia((r.x + 62, y + 14), 12, t)
            ui.texto(t.nombre, (r.x + 90, y + 14), 17, U.AMARILLO if t is c else U.TEXTO, t is c, "ml", maxw=330)
            ui.texto(f"{t.pts} pts", (r.right - 24, y + 14), 17, U.AMARILLO, True, "mr")
        if ui.boton((ANCHO // 2 - 300, 620, 280, 54), "Ver la tabla completa", tam=18):
            self.tab = "liga"
            self.ir("hub")
        if ui.boton((ANCHO // 2 + 20, 620, 280, 54), "Nueva temporada", True, tam=20):
            self.ir("menu")
