"""Aplicación principal (Pygame): menús, gestión del club y partidos."""
import calendar
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pygame

from . import audio as AU
from . import cambios as CB
from . import ascensos as AS
from . import champions as CH
from . import copa as CP
from . import eventos as ev
from . import evolucion as EV
from . import fechas as F
from . import guardado as G
from . import minijuegos as mj
from . import tactica as tac
from . import ui as U
from .asistente import Asistente
from .cancha import VistaPartido
from .camisetas import color_portero
from .datos import DATA, Mundo
from .modelo import (FORMACIONES, GRUPOS, NOMBRE_GRUPO, Liga, autoalinear, reparar_once)
from .simulacion import VENTAJA_LOCAL, fuerzas, goles_esperados

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
        if sys.platform == "win32":
            # Windows agrupa las ventanas en la barra de tareas por "identidad de aplicación". Sin una propia, el juego
            # hereda la de python.exe (icono de Python); con una propia, la barra muestra el icono del juego.
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xGManager.Educativo.Juego")
            except Exception:
                pass
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")   # al escalar a 1080p, suaviza en vez de "pixelar"
        pygame.mixer.pre_init(44100, -16, 2, 512)                    # latencia baja para los pitidos
        pygame.init()
        pygame.display.set_caption("xG Manager · Minería de Datos con FC 24")
        try:
            pygame.display.set_icon(pygame.transform.smoothscale(pygame.image.load(str(IMG / "logo.png")), (128, 128)))
        except (pygame.error, FileNotFoundError):
            pass                                          # sin logo el juego funciona igual
        self.pantalla = pygame.display.set_mode((ANCHO, ALTO), pygame.SCALED | pygame.RESIZABLE)
        self.ui = U.UI(self.pantalla)
        self.audio = AU.Audio(G.carpeta() / "ajustes.json")
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
        self.rechazos = {}               # {id de jugador: ronda} de ofertas rechazadas (no se reabre hasta la próxima jornada)
        self.cal_sel = None              # jornada elegida en el calendario (None = la próxima)
        self.cal_mes = None              # (año, mes) que muestra el calendario (None = el de la próxima jornada)
        self.temporada = F.TEMPORADA_BASE
        self.historial_temporadas = []   # [{"temporada", "pos", "pts", "objetivo", "cumplido"}] de temporadas ya jugadas
        self.resumen_evol = None         # resultado de la última evolución (pantalla "evolucion")
        self._pasando_frame = False
        self.copa = None                 # copa nacional de la temporada (juego/copa.py)
        self.copa_sel = None             # ronda que muestra la pestaña Copa (None = la actual)
        self.champions = None            # Champions League de la temporada (juego/champions.py)
        self.champ_sel = None            # fase que muestra la pestaña Champions (None = la actual)
        self._ordenes_prev = None        # {liga: ids de primera en orden final} de la temporada anterior (Champions)
        self.res_ascensos = None         # resultado de ascensos y descensos (pantalla "ascensos")
        self._confirmar_sim = None       # jornada para la que se pidió "Simular hasta aquí" (pide confirmar)
        self.mercado = {"grupo": None, "orden": "gangas", "asc": False, "ovr_min": 68, "asequibles": True, "texto": "",
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
        self.temporada = F.TEMPORADA_BASE
        self.historial_temporadas = []
        self.mundo.prediccion(next(iter(self.mundo.jugadores.values())))      # calienta el modelo de evolución

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
                if e.type == pygame.KEYDOWN and e.key == pygame.K_m and self.ui.foco is None:
                    self.audio.alternar_silencio()
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
        self._audio_cuadro()
        self._boton_sonido()

    def _audio_cuadro(self):
        """Música en los menús; en el partido entra la grada (más baja en el descanso, los minijuegos y los cambios)."""
        p = self.p
        en_partido = self.escena == "partido" and bool(p) and p.get("fase") == "vivo"
        tension = 1.0
        if en_partido and (p.get("pausa") in ("descanso", "mini", "cambios") or p.get("fin")):
            tension = 0.45
        self.audio.actualizar(en_partido, tension)

    def _boton_sonido(self):
        """Altavoz en la esquina superior derecha: clic o tecla M para silenciar / activar."""
        ui, au = self.ui, self.audio
        r = pygame.Rect(ANCHO - 40, 4, 34, 26)
        activo = au.activo and not au.silencio
        col = U.TEXTO if activo else U.ROJO
        pygame.draw.rect(ui.surf, (16, 22, 36, 200), r, border_radius=6)
        pygame.draw.rect(ui.surf, U.BORDE, r, 1, border_radius=6)
        cx, cy = r.centerx - 4, r.centery
        pygame.draw.polygon(ui.surf, col, [(cx - 7, cy - 3), (cx - 3, cy - 3), (cx + 2, cy - 8), (cx + 2, cy + 8),
                                           (cx - 3, cy + 3), (cx - 7, cy + 3)])
        if activo:
            for k in (1, 2):
                pygame.draw.arc(ui.surf, col, (cx + 2 - k * 2, cy - 4 - k * 2, 6 + k * 4, 8 + k * 4), -0.9, 0.9, 2)
        else:
            pygame.draw.line(ui.surf, col, (cx + 5, cy - 6), (cx + 12, cy + 6), 2)
            pygame.draw.line(ui.surf, col, (cx + 12, cy - 6), (cx + 5, cy + 6), 2)
        if ui.hover(r):
            ui.tip = ("Sonido silenciado" if not activo else "Sonido activado") + " · clic o tecla M para cambiar" \
                if au.activo else "No se encontró un dispositivo de audio."
        if ui.clic_en(r):
            au.alternar_silencio()

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
        self._ajustes_sonido(24, ALTO - 126)
        ui.texto("Fuentes: Lato y Bebas Neue (SIL OFL) · Datos: EA SPORTS FC 24 Complete Player Dataset (Kaggle)",
                 (ANCHO // 2, ALTO - 24), 13, U.APAGADO, anchor="tc")

    def _ajustes_sonido(self, x, y):
        ui, au = self.ui, self.audio
        ui.panel((x, y - 12, 236, 136), (10, 14, 24), 10, U.BORDE)
        ui.texto("Sonido", (x + 12, y - 4), 14, U.VERDE, True)
        for k, (que, lab, val) in enumerate((("musica", "Música", au.musica), ("efectos", "Efectos", au.efectos))):
            yy = y + 20 + k * 30
            ui.texto(lab, (x + 12, yy + 10), 13, U.APAGADO, anchor="ml")
            if ui.boton((x + 78, yy, 26, 22), "−", tam=14):
                au.cambiar(que, -0.1)
            ui.texto(f"{val:.0%}", (x + 134, yy + 11), 14, U.TEXTO, True, "mc")
            if ui.boton((x + 164, yy, 26, 22), "+", tam=14):
                au.cambiar(que, 0.1)
        ui.texto("Silbato", (x + 12, y + 90), 13, U.APAGADO, anchor="ml")
        if ui.boton((x + 78, y + 79, 112, 22), AU.ESTILOS_SILBATO[au.estilo_silbato], tam=13,
                    tip="Cambia el sonido del pito (Fox 40 o de bolita) y lo hace sonar."):
            au.cambiar_silbato()
        if au.pista:
            ui.texto("♪ " + au.pista, (x + 12, y + 112), 11, U.APAGADO, maxw=210)

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
        ui.logo_liga((1150, 74), 48, self.liga_nombre)
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
        self.liga_nombre = lm = club.liga_madre or club.liga
        ids = self.mundo.ligas[lm] if club.division == 1 else self.mundo.segunda[lm]       # primera o segunda división
        clubes = [self.mundo.clubes[i] for i in ids]
        for c in clubes:
            c.reset_temporada()
        self.liga = Liga(club.liga, clubes, self.rng)
        self.objetivo_pos = self.objetivo(club, sorted(clubes, key=lambda c: -c.ovr))
        self.copa = CP.Copa.crear(self.mundo, lm, self.rng, self.temporada, forzar=club.id if club.division == 2 else None)
        self.copa_sel = None
        self.champions = CH.Champions.crear(self.mundo, lm, self.temporada, self._ordenes_prev)
        self._ordenes_prev = None
        self.champ_sel = None
        self.ultimos = []
        self.sel_slot = self.sel_jug = None
        self.cal_sel = self.cal_mes = None
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
        ui.texto(f"Temp. {F.nombre_temporada(self.temporada)}", (112, 84), 12, U.AMARILLO, maxw=100)
        ui.texto("PRESUPUESTO", (20, 118), 12, U.APAGADO)
        ui.texto(eur(c.presupuesto), (20, 134), 26, U.VERDE, True)
        ui.texto(f"Posición: {self.liga.posicion(c)}º  ·  {c.pts} pts", (20, 172), 15)
        ui.texto(f"Objetivo: top {self.objetivo_pos}", (20, 194), 14, U.AMARILLO)
        tabs = [("alineacion", "Alineación"), ("mercado", "Mercado"), ("tactica", "Táctica"),
                ("liga", "Liga"), ("copa", "Copa"), ("champions", "Champions"), ("calendario", "Calendario"),
                ("datos", "Datos y modelos")]
        y = 222
        for k, nombre in tabs:
            if ui.boton((14, y, X0 - 40, 38), nombre, self.tab == k, tam=16):
                self.tab = k
            y += 43
        if self.liga.terminada:
            if ui.boton((14, ALTO - 84, X0 - 40, 60), "Ver resultado final", True, U.AMARILLO, tam=18):
                self.ir("fin")
        else:
            self.copa_simular_sin_usuario()           # jornadas de competiciones en las que no juegas: se simulan solas
            comp = self.comp_debida()
            if comp is not None:                      # jornada de copa o Champions pendiente: se juega antes de la liga
                self.copa_sorteo()
                champ = comp is self.champions
                if ui.boton((14, ALTO - 84, X0 - 40, 60), f"{'Champions' if champ else 'Copa'}: {comp.corta(comp.ronda)}", True,
                            U.AMARILLO, tam=15 if champ else 17,
                            tip=f"{comp.nombre} · {comp.etiqueta(comp.ronda)}.\n"
                                f"Se juega antes de la jornada {self.liga.jornada + 1} de liga."):
                    self.guardar()
                    self.preparar_partido(comp)
            elif ui.boton((14, ALTO - 84, X0 - 40, 60), f"Jugar jornada {self.liga.jornada + 1}", True, tam=18):
                self.guardar()                        # conserva los cambios de alineación/mercado hechos antes del partido
                self.preparar_partido()
        if ui.boton((14, ALTO - 136, X0 - 40, 40), "Guardar y salir", tam=15,
                    tip="Guarda la temporada y vuelve al menú.\nTambién se guarda sola al cerrar cada jornada."):
            if self.guardar(aviso=False):
                self.aviso("Partida guardada. Puedes continuarla desde el menú.", U.VERDE, 4000)
            self.ir("menu")
        # ---- encabezado
        if not self.liga.terminada:
            comp = self.comp_debida()
            par = comp.partido_de(c.id) if (comp is not None and c.id in comp.vivos) else None
            if par:                                   # próximo partido = jornada de copa o de Champions
                riv = self.mundo.clubes[par[1] if par[0] == c.id else par[0]]
                local = par[0] == c.id
                ui.texto(comp.corto, (X0, 20), 15, U.AMARILLO, True, maxw=140)
                fecha_prox = self.fecha_comp(comp, comp.ronda)
            else:
                rid, local = self.liga.rival(c)
                riv = self.mundo.clubes[rid]
                ui.texto(f"Jornada {self.liga.jornada + 1}/{self.liga.total_jornadas}", (X0, 20), 15, U.APAGADO)
                fecha_prox = self.fecha(self.liga.jornada)
            r = ui.texto("Próximo partido:", (X0 + 150, 20), 15, U.APAGADO, True)
            x0 = r.x
            local_c, visita_c = (c, riv) if local else (riv, c)          # el orden indica quién juega en casa
            for k, club in enumerate((local_c, visita_c)):
                if k == 1:
                    r = ui.texto("vs", (r.right + 12, 20), 15, U.APAGADO)
                ui.insignia((r.right + 22, 29), 11, club)
                r = ui.texto(club.nombre, (r.right + 42, 20), 15, U.VERDE if club is c else U.TEXTO, True)
                r = ui.texto(f"({club.ovr})", (r.right + 6, 20), 15, U.AMARILLO)
            r = ui.texto("· " + F.texto_fecha(fecha_prox, True), (r.right + 10, 20), 15, U.APAGADO)
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
        # lista del plantel en tres secciones: titulares, suplentes y no disponibles (no se pueden alinear)
        titulares = sorted([j for j in c.plantel if j in c.once and not j.lesion], key=lambda j: c.once.index(j))
        suplentes = sorted([j for j in c.plantel if j not in c.once and not j.lesion],
                           key=lambda j: (GRUPOS.index(j.grupo), -j.ovr))
        no_disp = sorted([j for j in c.plantel if j.lesion], key=lambda j: (-j.lesion, GRUPOS.index(j.grupo), -j.ovr))
        orden = [("h", f"TITULARES · {len(titulares)}", U.VERDE)] + [("j", j) for j in titulares]
        orden += [("h", f"SUPLENTES · {len(suplentes)}", U.AMARILLO)] + [("j", j) for j in suplentes]
        if no_disp:
            orden += [("h", f"NO DISPONIBLES · {len(no_disp)}", U.ROJO)] + [("j", j) for j in no_disp]
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
        for n, fila in enumerate(orden[self.scroll_plantel:self.scroll_plantel + filas]):
            r = pygame.Rect(px0, y0 + 20 + n * fh, pw, fh - 1)
            if fila[0] == "h":
                pygame.draw.line(ui.surf, U.BORDE, (px0, r.bottom - 2), (px0 + pw - 10, r.bottom - 2), 1)
                ui.texto(fila[1], (px0 + 8, r.centery - 1), 12, fila[2], True, "ml")
                continue
            j = fila[1]
            if j is self.sel_jug:
                ui.panel(r, U.PANEL2, 5, U.AMARILLO)
            elif ui.hover(r):
                ui.panel(r, U.PANEL, 5)
            if j.lesion:
                ui.icono_baja(px0 + 10, r.centery, j.motivo, 7)
                ui.texto(j.lesion, (px0 + 21, r.centery), 12, U.ROJO, True, "ml")
            ui.texto(j.pos, (px0 + 34, r.centery), 14, U.AMARILLO, anchor="ml")
            ui.texto(j.nombre, (px0 + 80, r.centery), 14, U.APAGADO if j.lesion else U.TEXTO, anchor="ml", maxw=165)
            ui.texto(j.edad, (px0 + 250, r.centery), 14, anchor="ml")
            ui.texto(j.ovr, (px0 + 292, r.centery), 14, U.APAGADO if j.lesion else U.VERDE, True, "ml")
            if j.lesion:
                motivo = "Suspendido" if j.motivo == "sanción" else "Lesionado"
                ui.texto(f"{motivo} · {j.lesion} jornada{'s' if j.lesion > 1 else ''}", (px0 + 336, r.centery), 13,
                         U.ROJO, anchor="ml", maxw=pw - 340)
            else:
                ui.texto(j.rol, (px0 + 336, r.centery), 13, U.APAGADO, anchor="ml", maxw=pw - 340)
            if ui.clic_en(r):
                if self.sel_slot is not None:
                    if j.lesion:                          # un baja no puede ser titular
                        self.aviso(f"{j.nombre} está {'suspendido' if j.motivo == 'sanción' else 'lesionado'}: "
                                   "no puede ser titular.", U.ROJO)
                    else:
                        self.asignar(self.sel_slot, j)
                else:
                    self.sel_jug = None if self.sel_jug is j else j
        if len(orden) > filas:                           # barra de desplazamiento
            alto = lista.h * filas / len(orden)
            top = lista.y + (lista.h - alto) * self.scroll_plantel / max(1, len(orden) - filas)
            pygame.draw.rect(ui.surf, U.BORDE, (lista.right - 5, lista.y, 3, lista.h), border_radius=2)
            pygame.draw.rect(ui.surf, U.APAGADO, (lista.right - 5, top, 3, alto), border_radius=2)
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
        mu, sd, pm, pb = self.mundo.prediccion(j)
        col = U.VERDE if mu >= 1 else U.ROJO if mu <= -1 else U.APAGADO
        ui.texto("Próxima temporada (modelo de evolución):", (r.x + 16, r.y + 166), 12, U.APAGADO)
        ui.texto(f"{mu:+.1f} OVR esperado · {EV.etiqueta_tendencia(pm, pb)}", (r.x + 262, r.y + 165), 13, col, True)
        ui.texto(f"Rango probable {mu - sd:+.0f} a {mu + sd:+.0f} · {pm:.0%} de mejorar · {pb:.0%} de bajar",
                 (r.x + 16, r.y + 186), 12, U.APAGADO)
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
    ORDENES_MERCADO = [("gangas", "Gangas"), ("ovr", "OVR"), ("pot", "Potencial"), ("precio", "Precio"), ("edad", "Edad"),
                       ("evol", "Evol.")]
    ASC_POR_DEFECTO = {"gangas": False, "ovr": False, "pot": False, "precio": True, "edad": True, "evol": False}

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
            for k, (o, lab) in enumerate(self.ORDENES_MERCADO):
                tip = {"gangas": "Gangas = valor justo (regresión) / precio pedido.",
                       "edad": "Edad del jugador.",
                       "evol": "Cambio de OVR esperado el próximo año (modelo de evolución)."}.get(o)
                if ui.boton((X0 + 402 + k * 76, 46, 72, 30), lab, m["orden"] == o, color=U.AMARILLO, tam=13, tip=tip):
                    if m["orden"] != o:                       # cada criterio arranca en su sentido natural
                        m.update(orden=o, asc=self.ASC_POR_DEFECTO[o], pagina=0, clave=None)
            sentido = "Menor a mayor ↑" if m["asc"] else "Mayor a menor ↓"
            if ui.boton((X0 + 402 + len(self.ORDENES_MERCADO) * 76 + 8, 46, 146, 30), sentido, tam=13, color=U.AZUL,
                        tip="Cambia el sentido del orden (ascendente / descendente)."):
                m.update(asc=not m["asc"], pagina=0, clave=None)
            nuevo = ui.entrada_texto((X0, 84, 300, 28), m["texto"], "buscar", "Buscar jugador o club…")
            if nuevo != m["texto"]:
                m.update(texto=nuevo, pagina=0, clave=None)
            ui.texto("OVR mín.", (X0 + 330, 93), 13, U.APAGADO, anchor="ml")
            if ui.boton((X0 + 392, 84, 26, 28), "−", tam=16):
                m.update(ovr_min=max(0, m["ovr_min"] - 2), pagina=0, clave=None)
            ui.texto(m["ovr_min"], (X0 + 432, 98), 15, U.TEXTO, True, "mc")
            if ui.boton((X0 + 448, 84, 26, 28), "+", tam=16):
                m.update(ovr_min=min(90, m["ovr_min"] + 2), pagina=0, clave=None)
            if ui.boton((X0 + 490, 84, 150, 28), "Solo asequibles", m["asequibles"], U.AZUL, tam=13):
                m.update(asequibles=not m["asequibles"], pagina=0, clave=None)
        # ---- lista candidata (en caché)
        clave = (m["grupo"], m["orden"], m["asc"], m["ovr_min"], m["asequibles"], m["texto"], rep.id if rep else None,
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
                claves = {"gangas": lambda p: p.valor_pred / self.mundo.precio(p), "ovr": lambda p: p.ovr,
                          "pot": lambda p: p.pot, "precio": lambda p: self.mundo.precio(p), "edad": lambda p: p.edad,
                          "evol": lambda p: self.mundo.prediccion(p)[0]}
                # desempate estable: a igual valor, el de mayor OVR primero
                lista.sort(key=lambda p: (claves[m["orden"]](p), -p.ovr), reverse=not m["asc"])
            m["cache"] = lista
        lista = m["cache"]
        # ---- tabla
        cols = [("Jugador", 0, 'l'), ("Club", 175, 'l'), ("Pos", 320, 'l'), ("Edad", 362, 'l'), ("OVR", 408, 'l'),
                ("POT", 448, 'l'), ("Evol.", 488, 'l'), ("Rol (K-means)", 540, 'l'), ("Precio", 745, 'r'), ("Valor justo", 840, 'r'),
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
            mu = self.mundo.prediccion(p)[0]
            ui.texto(f"{mu:+.1f}", (X0 + 502, cy), 14, U.VERDE if mu >= 1 else U.ROJO if mu <= -1 else U.APAGADO, True, "ml")
            ui.texto(p.rol, (X0 + 554, cy), 13, U.APAGADO, anchor="ml", maxw=138)           # no debe llegar al precio
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
            precio = self.mundo.precio(s)
            if m.get("oferta_de") != s.id:                        # nueva selección: se parte del precio pedido
                m["oferta"], m["oferta_de"] = precio, s.id
            minimo = round(precio * 0.5, -4)
            paso = max(10_000, round(precio * 0.05, -4))
            m["oferta"] = float(min(precio, max(minimo, m["oferta"])))
            oferta = m["oferta"]
            ronda = self.temporada * 100 + self.liga.jornada
            cerrado = self.rechazos.get(s.id) == ronda
            ok, msg = self.mundo.puede_comprar(c, s, min(oferta, precio))
            ui.texto(f"{s.nombre} · {s.rol}", (X0 + 290, yb + 4), 15, U.TEXTO, True, maxw=250)
            ui.texto(msg or f"Te quedarían {eur(c.presupuesto - oferta)}", (X0 + 290, yb + 24), 13,
                     U.ROJO if msg else U.APAGADO, maxw=250)
            # ---- oferta: se puede pagar menos de lo que piden, con riesgo de que la rechacen
            ui.texto("Oferta", (X0 + 550, yb + 14), 13, U.APAGADO, anchor="ml")
            if ui.boton((X0 + 596, yb + 1, 52, 30), "−5 %", tam=12, habilitado=oferta > minimo):
                m["oferta"] = max(minimo, oferta - paso)
            ui.texto(eur(oferta), (X0 + 704, yb + 16), 16, U.TEXTO, True, "mc")
            if ui.boton((X0 + 760, yb + 1, 52, 30), "+5 %", tam=12, habilitado=oferta < precio):
                m["oferta"] = min(precio, oferta + paso)
            prob = self.mundo.prob_oferta(s, oferta)
            col_p = U.VERDE if prob >= 0.7 else U.AMARILLO if prob >= 0.3 else U.ROJO
            if cerrado:
                ui.texto("Rechazaron tu oferta: no vuelven a negociar hasta la próxima jornada.", (X0 + 550, yb + 44), 13,
                         U.ROJO, maxw=480)
            else:
                ui.texto(f"Prob. de que la acepten: {prob:.0%}" + (f" · piden {eur(precio)}" if oferta < precio else ""),
                         (X0 + 550, yb + 44), 13, col_p, True, maxw=480)
                ui.texto("Piden menos margen si el precio ya es bajo para su valor justo (regresión) y si es titular.",
                         (X0 + 550, yb + 62), 12, U.APAGADO, maxw=480)
            etiqueta = f"Fichar por {eur(precio)}" if oferta >= precio else f"Ofrecer {eur(oferta)}"
            if ui.boton((X0 + 830, yb - 2, 200, 40), etiqueta, habilitado=ok and not cerrado, tam=15):
                if oferta >= precio:
                    okc, msgc = self.mundo.comprar(c, s)
                    self.aviso(msgc, U.VERDE if okc else U.ROJO)
                    m.update(sel=None, clave=None)
                else:
                    okc, msgc, acepta = self.mundo.ofrecer(c, s, oferta, self.rng)
                    self.aviso(msgc, U.VERDE if acepta else U.AMARILLO if okc else U.ROJO, 5000)
                    if acepta:
                        m.update(sel=None, clave=None)
                    elif okc:
                        self.rechazos[s.id] = ronda
            sim = self.mundo.similares(s, c.plantel, 1)
            if sim:
                ui.texto(f"Tu más parecido: {sim[0][0].nombre} ({sim[0][0].ovr})", (X0 + 290, yb + 44), 13, U.APAGADO,
                         anchor="ml", maxw=250)

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
        r0 = ui.texto(f"{self.liga.nombre} · Clasificación", (X0, 44), 40, titulo=True)
        ui.logo_liga((r0.right + 70, 72), 34, self.liga.nombre)
        hdr = [("#", 0), ("Club", 40), ("PJ", 330), ("G", 372), ("E", 410), ("P", 448), ("GF", 486), ("GC", 526),
               ("DG", 568), ("PTS", 616)]
        y = 100
        for n, x in hdr:
            ui.texto(n, (X0 + 10 + x, y), 12, U.APAGADO)
        tabla = self.liga.tabla()
        fh = 26 if len(tabla) <= 18 else 24.5
        n_as = AS.n_ascensos(self.mundo, c.liga_madre)
        zona_alta, zona_baja = (6, n_as) if c.division == 1 else (n_as, 0)       # Champions / descenso, o ascenso
        for i, t in enumerate(tabla):
            r = pygame.Rect(X0, int(y + 20 + i * fh), 670, int(fh) - 1)
            if t is c:
                ui.panel(r, U.PANEL2, 5, U.VERDE)
            elif i < zona_alta:
                pygame.draw.rect(ui.surf, (30, 60, 55), r, border_radius=5)
            elif zona_baja and i >= len(tabla) - zona_baja:
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
        for i, (h, v, gh, gv) in enumerate(self.ultimos[:12]):
            H, V = self.mundo.clubes[h], self.mundo.clubes[v]
            yy = 146 + i * 30
            mio = c.id in (h, v)
            ui.texto(H.nombre, (rx + 150, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "tr", maxw=130)
            ui.texto(f"{gh} - {gv}", (rx + 170, yy), 14, U.TEXTO, True, "tc")
            ui.texto(V.nombre, (rx + 196, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "tl", maxw=130)
        ui.texto("Verde: Champions · Rojo: descenso" if c.division == 1 else "Verde: ascenso a primera (suben "
                 f"{n_as})", (rx + 16, 670), 12, U.APAGADO, anchor="bl")

    # ------------------------------------------------------- calendario
    def _partido_de(self, jornada, club):
        """(local, visitante, resultado | None) del partido de `club` en esa jornada (0-based)."""
        liga = self.liga
        for h, v in liga.calendario[jornada]:
            if club.id in (h, v):
                res = None
                if jornada < len(liga.historial):
                    res = next(((gh, gv) for hh, vv, gh, gv in liga.historial[jornada] if (hh, vv) == (h, v)), None)
                return self.mundo.clubes[h], self.mundo.clubes[v], res
        return None

    def fecha(self, jornada):
        """Fecha (datetime.date) de la jornada 0-based en la liga y temporada actuales."""
        return F.fecha_jornada(self.liga.nombre, jornada, self.liga.total_jornadas, self.temporada)

    def _rect_celda(self, fila, col):
        return pygame.Rect(X0 + col * 100, 124 + fila * 90, 98, 86)

    def _celda_copa(self, ui, r, dia, comp, rc):
        """Día de una jornada de copa (dorado) o de Champions (azul) en el calendario."""
        c = self.club
        champ = comp is self.champions
        pygame.draw.rect(ui.surf, (9, 20, 62) if champ else (112, 84, 18), r, border_radius=6)
        if champ:
            pygame.draw.rect(ui.surf, (110, 160, 255), r, 2, border_radius=6)
        ui.texto(dia, (r.x + 10, r.y + 6), 16, (255, 255, 255), True)
        ui.texto("UCL" if champ else "COPA", (r.right - 8, r.y + 8), 12, (170, 205, 255) if champ else (255, 224, 140),
                 True, "tr")
        ui.texto(comp.corta(rc), (r.x + 10, r.bottom - 8), 11, (190, 215, 255) if champ else (255, 230, 160), anchor="bl")
        mio = [x for x in comp.camino(c.id) if x[0] == rc]
        rival = None
        if mio:
            rival = self.mundo.clubes[mio[0][1]]
            ui.texto(f"{mio[0][2]}-{mio[0][3]}", (r.x + 10, r.bottom - 24), 14, (255, 255, 255), True, "bl")
            gano = mio[0][7]
            pygame.draw.rect(ui.surf, U.AMARILLO if gano is None else U.VERDE if gano else U.ROJO, (r.x, r.y, 6, r.h),
                             border_top_left_radius=6, border_bottom_left_radius=6)
        elif rc == comp.ronda and not comp.terminada and c.id in comp.vivos:
            par = comp.partido_de(c.id)
            if par:
                rival = self.mundo.clubes[par[1] if par[0] == c.id else par[0]]
            pygame.draw.rect(ui.surf, U.AMARILLO, r, 3, border_radius=6)
        if rival is not None:
            ui.insignia((r.right - 26, r.bottom - 26), 15, rival)
        if ui.hover(r):
            ui.tip = f"{comp.nombre} · {comp.etiqueta(rc)}\nClic para ver la competición."

    def tab_calendario(self):
        ui, c, liga = self.ui, self.club, self.liga
        total = liga.total_jornadas
        jug = min(liga.jornada, total - 1)                    # próxima jornada (o la última si ya terminó)
        fechas = {self.fecha(i): i for i in range(total)}
        copas = {}
        for comp in (self.copa, self.champions):
            if comp:
                for r in range(len(comp.historial)):
                    copas[self.fecha_comp(comp, r)] = (comp, r)
        sel = jug if self.cal_sel is None else max(0, min(self.cal_sel, total - 1))
        if self.cal_mes is None:
            d0 = self.fecha(jug)
            self.cal_mes = (d0.year, d0.month)
        anio, mes = self.cal_mes
        primero, ultimo = self.fecha(0), self.fecha(total - 1)
        # ---- cabecera del mes con navegación
        ui.texto(f"{F.MESES[mes - 1].upper()} {anio}", (X0, 40), 40, titulo=True)
        antes = (anio, mes) > (primero.year, primero.month)
        despues = (anio, mes) < (ultimo.year, ultimo.month)
        if ui.boton((X0 + 380, 50, 40, 34), "‹", habilitado=antes, tam=20):
            self.cal_mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
        if ui.boton((X0 + 428, 50, 40, 34), "›", habilitado=despues, tam=20):
            self.cal_mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        if ui.boton((X0 + 476, 50, 150, 34), "Próximo partido", tam=13, tip="Vuelve al mes de tu próximo partido."):
            self.cal_mes = None
        if self._confirmar_sim is not None and self._confirmar_sim != sel:
            self._confirmar_sim = None                             # cambiaste de jornada: se cancela la confirmación
        futura = sel > liga.jornada and not liga.terminada
        confirma = self._confirmar_sim == sel
        if ui.boton((X0 + 716, 50, ANCHO - X0 - 716 - 14, 34),
                    f"¿Seguro? Simular hasta la J{sel + 1}" if confirma else f"Simular hasta la jornada {sel + 1}",
                    confirma, futura, U.AMARILLO, tam=14,
                    tip="Juega solo (sin verlos) todos tus partidos hasta la jornada elegida, incluidas las copas y la\n"
                        "Champions que haya antes. Después paras ahí y juegas ese partido tú.\n"
                        "Elige una jornada futura en el calendario. No se puede deshacer."):
            if confirma:
                self._confirmar_sim = None
                self.simular_hasta(sel)
                return
            self._confirmar_sim = sel
        for k, nombre in enumerate(F.DIAS):
            ui.texto(nombre.upper(), (X0 + k * 100 + 8, 100), 12, U.APAGADO, True)
        # ---- cuadrícula
        offset = dt.date(anio, mes, 1).weekday()
        ndias = calendar.monthrange(anio, mes)[1]
        ganados = empatados = perdidos = 0
        for i in range(total):
            h, v, res = self._partido_de(i, c)
            if res:
                mi, su = (res[0], res[1]) if h is c else (res[1], res[0])
                ganados += mi > su
                empatados += mi == su
                perdidos += mi < su
        for n in range(math.ceil((offset + ndias) / 7) * 7):
            dia = n - offset + 1
            fila, col = divmod(n, 7)
            r = self._rect_celda(fila, col)
            if dia < 1 or dia > ndias:
                pygame.draw.rect(ui.surf, (16, 22, 36), r, border_radius=6)
                continue
            fecha = dt.date(anio, mes, dia)
            i = fechas.get(fecha)
            if i is None and fecha in copas:
                comp, rc = copas[fecha]
                self._celda_copa(ui, r, dia, comp, rc)
                if ui.clic_en(r):
                    if comp is self.champions:
                        self.champ_sel = CH.fase_de(rc)
                        self.tab = "champions"
                    else:
                        self.copa_sel = rc
                        self.tab = "copa"
                continue
            if i is None:
                pygame.draw.rect(ui.surf, (24, 32, 52), r, border_radius=6)
                ui.texto(dia, (r.x + 8, r.y + 6), 16, (120, 134, 164), True)
                continue
            h, v, res = self._partido_de(i, c)
            local = h is c
            rival = v if local else h
            base = (26, 74, 140) if local else (66, 52, 126)
            pygame.draw.rect(ui.surf, base, r, border_radius=6)
            if res:                                           # franja con el resultado para ti
                mi, su = (res[0], res[1]) if local else (res[1], res[0])
                col_res = U.VERDE if mi > su else U.AMARILLO if mi == su else U.ROJO
                pygame.draw.rect(ui.surf, col_res, (r.x, r.y, 6, r.h), border_top_left_radius=6, border_bottom_left_radius=6)
                ui.texto(f"{res[0]} - {res[1]}", (r.x + 10, r.bottom - 8), 15, (255, 255, 255), True, "bl")
            else:
                ui.texto("Local" if local else "Visita", (r.x + 10, r.bottom - 36), 13, (210, 224, 250), True)
                ui.texto("LIGA", (r.x + 10, r.bottom - 8), 11, (170, 190, 230), anchor="bl")
            ui.texto(dia, (r.x + 10, r.y + 6), 16, (255, 255, 255), True)
            ui.texto(f"J{i + 1}", (r.right - 8, r.y + 8), 12, (200, 214, 244), True, "tr")
            ui.insignia((r.right - 26, r.bottom - 26), 15, rival)
            if i == jug and liga.jornada < total:
                pygame.draw.rect(ui.surf, U.AMARILLO, r, 3, border_radius=6)
            elif i == sel:
                pygame.draw.rect(ui.surf, (255, 255, 255), r, 2, border_radius=6)
            if ui.hover(r):
                pygame.draw.rect(ui.surf, (255, 255, 255), r, 1, border_radius=6)
                ui.tip = f"Jornada {i + 1} · {F.texto_fecha(fecha)}\n{h.nombre} vs {v.nombre}"
            if ui.clic_en(r):
                self.cal_sel = i
        # ---- panel de la jornada elegida
        rx = X0 + 716
        panel = pygame.Rect(rx, 96, ANCHO - rx - 14, 392)
        ui.panel(panel, U.PANEL, 12, U.BORDE)
        estado = "próxima" if sel == jug and liga.jornada < total else "jugada" if sel < liga.jornada else "por jugar"
        ui.texto(f"Jornada {sel + 1}", (rx + 16, 106), 22, U.VERDE, True)
        ui.texto(f"{F.texto_fecha(self.fecha(sel))} · {estado}", (panel.right - 16, 112), 13,
                 U.AMARILLO if estado == "próxima" else U.APAGADO, True, "tr")
        paso_y = min(33, 330 / max(1, len(liga.calendario[sel])))
        for k, (h, v) in enumerate(liga.calendario[sel]):
            H, V = self.mundo.clubes[h], self.mundo.clubes[v]
            res = next(((gh, gv) for hh, vv, gh, gv in liga.historial[sel] if (hh, vv) == (h, v)), None) \
                if sel < len(liga.historial) else None
            yy = 152 + k * paso_y
            mio = c.id in (h, v)
            if mio:
                pygame.draw.rect(ui.surf, (30, 44, 66), (rx + 8, yy - 14, panel.w - 16, 28), border_radius=6)
            ui.texto(H.nombre, (rx + 132, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "mr", maxw=112)
            ui.texto(f"{res[0]} - {res[1]}" if res else "vs", (rx + 156, yy), 14, U.TEXTO if res else U.APAGADO,
                     bool(res), "mc")
            ui.texto(V.nombre, (rx + 180, yy), 13, U.AMARILLO if mio else U.TEXTO, mio, "ml", maxw=112)
        # ---- balance de la temporada
        bal = pygame.Rect(rx, 500, panel.w, 190)
        ui.panel(bal, U.PANEL, 12, U.BORDE)
        ui.texto(f"Tu temporada {F.nombre_temporada(self.temporada)}", (rx + 16, 510), 16, U.VERDE, True)
        ui.texto(f"{ganados} V · {empatados} E · {perdidos} D", (rx + 16, 540), 22, U.TEXTO, True)
        ui.texto(f"{c.pts} puntos · {liga.posicion(c)}º · objetivo top {self.objetivo_pos}", (rx + 16, 576), 14,
                 U.AMARILLO)
        ui.texto(f"Quedan {max(0, total - liga.jornada)} jornadas · termina el {F.texto_fecha(ultimo, False)}",
                 (rx + 16, 600), 13, U.APAGADO)
        for k, (col, txt) in enumerate(((U.VERDE, "victoria"), (U.AMARILLO, "empate"), (U.ROJO, "derrota"))):
            pygame.draw.rect(ui.surf, col, (rx + 16 + k * 92, 634, 8, 14), border_radius=2)
            ui.texto(txt, (rx + 30 + k * 92, 641), 12, U.APAGADO, anchor="ml")
        ui.texto("Azul: juegas de local · morado: de visita", (rx + 16, 664), 12, U.APAGADO)

    # ====================================================== COPA NACIONAL
    def comp_debida(self):
        """Competición (Champions o copa) con una jornada pendiente antes de la próxima jornada de liga, o None."""
        if self.liga.terminada:
            return None
        debidas = [x for x in (self.champions, self.copa) if x and x.toca(self.liga.jornada)]
        return min(debidas, key=lambda x: x.jornada_de(x.ronda)) if debidas else None

    def copa_sorteo(self):
        comp = self.comp_debida()
        if comp is not None and not comp.pares:
            comp.sortear(self.rng)

    def copa_simular_sin_usuario(self):
        """Las jornadas de competiciones en las que tu club no juega (no clasificó o ya está eliminado) se juegan solas."""
        while True:
            comp = self.comp_debida()
            if comp is None or self.club.id in comp.vivos:
                return
            self.copa_sorteo()
            comp.jugar_ronda_ia(self.mundo, self.rng, self.asist)
            comp.cerrar_ronda()

    def fecha_comp(self, comp, r):
        """Fecha de la jornada r de la competición: el miércoles (copa) o el martes (Champions) de la semana de la
        jornada de liga antes de la cual se juega."""
        d = self.fecha(comp.jornada_de(r))
        return d - dt.timedelta(days=(d.weekday() - (1 if comp is self.champions else 2)) % 7)

    def fecha_copa(self, r):
        return self.fecha_comp(self.copa, r)

    def iniciar_tanda(self):
        p = self.p
        p["tanda_obj"] = CP.nueva_tanda(p["est"], "a" if self.rng.random() < 0.5 else "b")
        p["tanda_ui"] = {"mini": None, "ev": None}
        p["pausa"] = "tanda"

    def _lanzar_penal(self, lado, j):
        """Abre el minijuego del penal de la tanda (lanzas tú o atajas tú, según el equipo)."""
        p, est = self.p, self.p["est"]
        rival = "b" if lado == "a" else "a"
        e = ev._ev(p["min"], "penal", lado, j.nombre, tiro=ev.tiro_de(j, "penal"), gk=ev.portero_de(est["xi"][rival]),
                   ejecutor=j, clave=j.nombre)
        p["tanda_ui"]["ev"] = e
        p["tanda_ui"]["mini"] = mj.crear(e, p["lado"], self.rng, est["clubes"])

    def _registrar_penal(self, convertido):
        p = self.p
        lado, _ = p["tanda_obj"].proximo()
        p["tanda_obj"].registrar(convertido)
        if convertido:
            self.audio.grada("gol_propio" if lado == p["lado"] else "gol_rival")
        elif lado == p["lado"]:
            self.audio.grada("suspiro")

    def _panel_tanda(self):
        ui, p = self.ui, self.p
        t, st, est = p["tanda_obj"], p["tanda_ui"], p["est"]
        L, V = p["local"], p["visit"]
        if st["mini"] is not None:                              # minijuego del penal en curso
            r = st["mini"].dibujar(ui)
            if r:
                e = st["ev"]
                if r == "auto":
                    ev.autoresolver(e, self.rng)
                    convertido = e["res"] == "gol"
                else:
                    convertido = st["mini"].resultado == "gol"
                st["mini"] = st["ev"] = None
                self._registrar_penal(convertido)
            return
        sombra = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 190))
        ui.surf.blit(sombra, (0, 0))
        M = pygame.Rect(150, 60, 980, 600)
        ui.panel(M, (12, 18, 30), 14, U.BORDE)
        ui.texto("TANDA DE PENALES", (M.centerx, M.y + 14), 52, U.AMARILLO, anchor="tc", titulo=True)
        # marcador
        ui.insignia((M.x + 120, M.y + 140), 40, L)
        ui.insignia((M.right - 120, M.y + 140), 40, V)
        ui.texto_fit(L.nombre, (M.x + 120, M.y + 188), 22, 14, 200, anchor="tc", titulo=True)
        ui.texto_fit(V.nombre, (M.right - 120, M.y + 188), 22, 14, 200, anchor="tc", titulo=True)
        ui.texto(f"{t.goles['a']} - {t.goles['b']}", (M.centerx, M.y + 96), 96, U.TEXTO, anchor="tc", titulo=True)
        # serie de lanzamientos de cada equipo
        for lado, y in (("a", M.y + 250), ("b", M.y + 300)):
            club = L if lado == "a" else V
            ui.insignia((M.x + 60, y), 11, club)
            propios = [x for x in t.registro if x[0] == lado]
            n = max(5, len(propios) + (0 if t.terminada() else 1))
            for k in range(min(n, 14)):
                cx = M.x + 110 + k * 46
                if k < len(propios):
                    ok = propios[k][2]
                    pygame.draw.circle(ui.surf, U.VERDE if ok else U.ROJO, (cx, y), 15)
                    pygame.draw.circle(ui.surf, (10, 20, 15), (cx, y), 15, 2)
                    if ok:
                        pygame.draw.circle(ui.surf, (10, 20, 15), (cx, y), 5)
                    else:
                        pygame.draw.line(ui.surf, (10, 20, 15), (cx - 6, y - 6), (cx + 6, y + 6), 3)
                        pygame.draw.line(ui.surf, (10, 20, 15), (cx - 6, y + 6), (cx + 6, y - 6), 3)
                else:
                    pygame.draw.circle(ui.surf, U.BORDE, (cx, y), 15, 2)
        if t.terminada():
            gano = t.ganador() == p["lado"]
            club = L if t.ganador() == "a" else V
            ui.texto(f"¡{club.nombre} gana la tanda!", (M.centerx, M.y + 380), 34, U.VERDE if gano else U.ROJO,
                     True, "tc", maxw=M.w - 60)
            ui.texto("Pasas de ronda." if gano else f"Quedas eliminado de la {p['comp'].nombre}.", (M.centerx, M.y + 430), 18,
                     U.TEXTO, anchor="tc", maxw=M.w - 60)
            if ui.boton((M.centerx - 120, M.bottom - 90, 240, 56), "Continuar", True, tam=20):
                p["pausa"] = None
            return
        lado, j = t.proximo()
        club = L if lado == "a" else V
        mio = lado == p["lado"]
        ui.texto(f"Turno de {club.nombre}", (M.centerx, M.y + 372), 20, U.APAGADO, anchor="tc")
        ui.texto(f"{'Lanzas tú: ' if mio else 'Lanza '}{j.nombre}", (M.centerx, M.y + 404), 30, U.TEXTO, True, "tc", maxw=M.w - 60)
        ui.texto(f"Probabilidad de gol según el modelo: {t.prob(lado, j):.0%}" if mio else
                 f"Eliges hacia dónde se lanza tu portero ({ev.portero_de(est['xi'][p['lado']])[0]}).",
                 (M.centerx, M.y + 448), 15, U.AMARILLO, anchor="tc")
        if ui.boton((M.centerx - 270, M.bottom - 90, 250, 56), "Lanzar el penal" if mio else "Atajar el penal", True, tam=19):
            self._lanzar_penal(lado, j)
        if ui.boton((M.centerx + 20, M.bottom - 90, 250, 56), "Simular el resto", tam=18,
                    tip="El resto de la tanda se decide con las estadísticas de los lanzadores y porteros."):
            t.simular_resto(self.rng)

    def cerrar_partido_copa(self, ga, gb):
        """Cierra un partido de copa o de Champions: lo registra, juega el resto de la jornada y cobra premios."""
        p, c, comp = self.p, self.club, self.p["comp"]
        L, V = p["local"], p["visit"]
        t, pv = p.get("tanda_obj"), p["previo"]
        pen = ganador = None
        if p["decide"]:                                          # eliminatoria: el global (con la ida) debe tener ganador
            a1, a2 = ga + pv[0], gb + pv[1]
            if a1 != a2:
                ganador = L.id if a1 > a2 else V.id
            else:
                pen = (t.goles["a"], t.goles["b"])
                ganador = L.id if t.ganador() == "a" else V.id
        ronda = comp.ronda
        comp.registrar({"h": L.id, "v": V.id, "gh": ga, "gv": gb, "prorroga": p["prorroga"], "pen": pen, "ganador": ganador})
        comp.jugar_ronda_ia(self.mundo, self.rng, self.asist, excluir=c.id)    # el resto de partidos de la jornada
        comp.cerrar_ronda()
        mios, suyos = (ga, gb) if p["user_local"] else (gb, ga)
        premio, motivo = comp.premio_tras(c.id, ronda, (mios, suyos))
        c.presupuesto += premio
        if comp.campeon == c.id:
            self.aviso(f"¡Campeón de la {comp.nombre}! Premio: {eur(premio)}", U.VERDE, 6000)
        elif c.id not in comp.vivos:
            self.aviso(f"Eliminado de la {comp.nombre} ({comp.etiqueta(ronda)})." +
                       (f" Cobras {eur(premio)}." if premio else ""), U.ROJO, 6000)
        else:
            self.aviso(f"{comp.nombre}: sigues en carrera (siguiente: {comp.etiqueta(comp.ronda).lower()})." +
                       (f" Premio: {eur(premio)} ({motivo})." if premio else ""), U.VERDE, 5000)
        for j in c.plantel:                                                    # un partido oficial más: se recuperan o cumplen sanción
            if j.lesion:
                j.lesion -= 1
        for club, j, n, motivo in p["est"]["bajas"]:
            if club is c and not (j.lesion >= n and j.motivo == motivo):
                j.lesion, j.motivo = n, motivo
                self.aviso(("Roja: " if motivo == "sanción" else "Lesión: ") + j.nombre, U.ROJO, 5000)
        self.mercado["clave"] = None
        self.guardar()
        self.ir("hub")

    def tab_copa(self):
        ui, c, copa = self.ui, self.club, self.copa
        if copa is None:
            ui.texto("La copa no está disponible en esta partida guardada: se crea al empezar una temporada.",
                     (X0, 60), 16, U.APAGADO)
            return
        r = ui.texto(f"{copa.nombre} {F.nombre_temporada(self.temporada)}", (X0, 40), 40, titulo=True)
        ui.logo_competicion((r.right + 64, 72), 38, copa.nombre)
        estado = copa.estado(c.id)
        col = U.VERDE if (estado == "campeon" or (estado and estado[0] == "vivo")) else U.ROJO
        ui.texto(copa.texto_estado(c.id), (X0, 92), 16, col, True)
        sel = copa.ronda if copa.ronda < len(CP.RONDAS) else len(CP.RONDAS) - 1
        if self.copa_sel is not None:
            sel = self.copa_sel
        for i, nombre in enumerate(CP.CORTAS):
            if ui.boton((X0 + i * 124, 120, 118, 32), nombre, sel == i, tam=13,
                        tip=f"{CP.RONDAS[i]} · antes de la jornada {CP.JORNADA_RONDA[i] + 1} de liga"):
                self.copa_sel = i
        jugados = list(copa.historial[sel])
        pendientes = copa.pendientes() if (sel == copa.ronda and not copa.terminada) else []
        filas = [(r["h"], r["v"], r) for r in jugados] + [(h, v, None) for h, v in pendientes]
        y0 = 172
        if not filas:
            if sel > copa.ronda:
                msg = "Todavía no hay sorteo: se hace cuando termina la ronda anterior."
            else:
                msg = f"Sorteo pendiente: se hace antes de la jornada {CP.JORNADA_RONDA[sel] + 1} de liga."
            ui.texto(msg, (X0 + 10, y0 + 10), 15, U.APAGADO)
        for k, (h, v, r) in enumerate(filas[:16]):
            H, W = self.mundo.clubes[h], self.mundo.clubes[v]
            y = y0 + k * 30
            mio = c.id in (h, v)
            rect = pygame.Rect(X0, y, 660, 28)
            if mio:
                ui.panel(rect, U.PANEL2, 6, U.AMARILLO)
            cy = y + 14
            gh = r and r["ganador"] == h
            gv = r and r["ganador"] == v
            ui.texto(H.nombre, (X0 + 290, cy), 14, U.VERDE if H is c else U.TEXTO, bool(gh) or H is c, "mr", maxw=190)
            ui.insignia((X0 + 312, cy), 10, H)
            ui.texto(f"{r['gh']} - {r['gv']}" if r else "vs", (X0 + 372, cy), 14, U.TEXTO if r else U.APAGADO, bool(r), "mc")
            ui.insignia((X0 + 432, cy), 10, W)
            ui.texto(W.nombre, (X0 + 450, cy), 14, U.VERDE if W is c else U.TEXTO, bool(gv) or W is c, "ml", maxw=160)
            if r and r["pen"]:
                ui.texto(f"p. {r['pen'][0]}-{r['pen'][1]}", (X0 + 650, cy), 12, U.AMARILLO, True, "mr")
            elif r and r["prorroga"]:
                ui.texto("pr.", (X0 + 650, cy), 12, U.AMARILLO, True, "mr")
        # ---- tu camino
        rx = X0 + 690
        panel = pygame.Rect(rx, 120, ANCHO - rx - 14, 400)
        ui.panel(panel, U.PANEL, 12, U.BORDE)
        ui.texto("Tu camino", (rx + 16, 130), 18, U.VERDE, True)
        camino = copa.camino(c.id)
        if not camino:
            ui.texto("Todavía no has jugado.", (rx + 16, 166), 14, U.APAGADO)
        for k, (r, rival, gp, gr, prorroga, pp, pr, gano) in enumerate(camino):
            yy = 166 + k * 44
            ui.texto(CP.CORTAS[r], (rx + 16, yy), 12, U.APAGADO, True)
            ui.insignia((rx + 28, yy + 24), 9, self.mundo.clubes[rival])
            ui.texto(self.mundo.clubes[rival].nombre, (rx + 44, yy + 24), 13, U.TEXTO, anchor="ml", maxw=110)
            extra = f" (p. {pp}-{pr})" if pp is not None else " (pr.)" if prorroga else ""
            ui.texto(f"{gp}-{gr}{extra}", (panel.right - 16, yy + 24), 14, U.VERDE if gano else U.ROJO, True, "mr")
        if copa.terminada:
            ui.texto(f"Campeón: {self.mundo.clubes[copa.campeon].nombre}", (rx + 16, panel.bottom - 40), 15, U.AMARILLO,
                     True, maxw=panel.w - 32)
        else:
            ui.texto(f"Próxima ronda: {CP.CORTAS[copa.ronda]} · {F.texto_fecha(self.fecha_copa(copa.ronda), True)}",
                     (rx + 16, panel.bottom - 40), 13, U.APAGADO, maxw=panel.w - 32)
        ui.texto("Premio por ronda ganada: " + " · ".join(f"{p / 1e6:.0f}" for p in CP.PREMIOS) + " M€",
                 (rx, 534), 12, U.APAGADO, maxw=ANCHO - rx - 14)
        ui.texto(f"El campeón cobra {CP.PREMIO_CAMPEON / 1e6:.0f} M€ más.", (rx, 554), 12, U.APAGADO, maxw=ANCHO - rx - 14)

    # ====================================================== CHAMPIONS LEAGUE
    FASES_BOTON = ["Grupos", "Octavos", "Cuartos", "Semifinales", "Final"]

    def tab_champions(self):
        ui, c, ch = self.ui, self.club, self.champions
        if ch is None:
            ui.texto("La Champions no está disponible en esta partida guardada: se crea al empezar una temporada.",
                     (X0, 60), 16, U.APAGADO)
            return
        r = ui.texto(f"{ch.nombre} {F.nombre_temporada(self.temporada)}", (X0, 40), 40, titulo=True)
        ui.logo_competicion((r.right + 70, 72), 38, ch.nombre)
        estado = ch.estado(c.id)
        col = U.VERDE if (estado == "campeon" or (estado and estado[0] == "vivo")) else U.ROJO if estado else U.APAGADO
        ui.texto(ch.texto_estado(c.id) if estado else "Tu club no se ha clasificado esta temporada: la sigues desde aquí.",
                 (X0, 92), 16, col, True)
        sel = CH.fase_de(min(ch.ronda, CH.N_MD - 1)) if self.champ_sel is None else self.champ_sel
        for i, nombre in enumerate(self.FASES_BOTON):
            if ui.boton((X0 + i * 124, 120, 118, 32), nombre, sel == i, tam=13,
                        tip="Se juega antes de la jornada " + (
                            ", ".join(str(CH.JORNADA_MD[m] + 1) for m in range(6)) if i == 0 else
                            " y ".join(str(CH.JORNADA_MD[m] + 1) for m in ((12,) if i == 4 else (6 + 2 * (i - 1), 7 + 2 * (i - 1))))
                        ) + " de liga."):
                self.champ_sel = i
        if sel == 0:
            self._champ_grupos()
        else:
            self._champ_eliminatoria(sel)
        self._champ_pie()

    def _champ_grupos(self):
        ui, c, ch = self.ui, self.club, self.champions
        if not ch.grupos:
            ui.texto(f"El sorteo de grupos se hace antes de la jornada {CH.JORNADA_MD[0] + 1} de liga.", (X0 + 10, 180), 15,
                     U.APAGADO)
            ui.texto("Clasificados: " + ", ".join(self.mundo.clubes[i].nombre for i in ch.inscritos[:8]) + "…", (X0 + 10, 210),
                     13, U.APAGADO, maxw=1000)
            for k, i in enumerate(ch.inscritos):
                ui.insignia((X0 + 24 + (k % 16) * 64, 270 + (k // 16) * 60), 22, self.mundo.clubes[i])
            return
        for g in range(8):
            rect = pygame.Rect(X0 + (g % 4) * 262, 160 + (g // 4) * 146, 254, 138)
            ui.panel(rect, U.PANEL, 8, U.BORDE)
            ui.texto(f"GRUPO {CH.LETRAS[g]}", (rect.x + 10, rect.y + 6), 13, U.AMARILLO, True)
            for txt, dx in (("PJ", 82), ("DG", 50), ("PTS", 14)):
                ui.texto(txt, (rect.right - dx, rect.y + 8), 11, U.APAGADO, True, "mr")
            for k, f in enumerate(ch.tabla(g)):
                y = rect.y + 28 + k * 26
                club = self.mundo.clubes[f[0]]
                if k < 2:
                    pygame.draw.rect(ui.surf, U.VERDE, (rect.x + 3, y + 3, 3, 18), border_radius=2)
                ui.insignia((rect.x + 26, y + 12), 10, club)
                ui.texto(club.nombre, (rect.x + 44, y + 12), 13, U.VERDE if club is c else U.TEXTO, club is c, "ml", maxw=122)
                ui.texto(f[1], (rect.right - 82, y + 12), 13, U.APAGADO, anchor="mr")
                ui.texto(f"{f[5] - f[6]:+d}", (rect.right - 50, y + 12), 13, U.APAGADO, anchor="mr")
                ui.texto(f[7], (rect.right - 14, y + 12), 14, U.TEXTO, True, "mr")

    def _champ_eliminatoria(self, fase):
        ui, c, ch = self.ui, self.club, self.champions
        cruces = ch.eliminatorias(fase)
        if not cruces:
            ui.texto("Todavía no hay sorteo: se hace cuando termina la fase anterior.", (X0 + 10, 190), 15, U.APAGADO)
            return
        doble = fase < 4
        for txt, x in ((("Ida", 420), ("Vuelta", 500), ("Global", 590)) if doble else (("Resultado", 480),)):
            ui.texto(txt, (X0 + x, 164), 12, U.APAGADO, True, "mc")
        for k, t in enumerate(cruces[:8]):
            y = 184 + k * 36
            A, B = self.mundo.clubes[t["a"]], self.mundo.clubes[t["b"]]
            rect = pygame.Rect(X0, y, 900, 32)
            if c.id in (t["a"], t["b"]):
                ui.panel(rect, U.PANEL2, 6, U.AMARILLO)
            cy = y + 16
            ui.texto(A.nombre, (X0 + 310, cy), 15, U.VERDE if A is c else U.TEXTO, t["ganador"] == t["a"] or A is c, "mr", maxw=210)
            ui.insignia((X0 + 334, cy), 11, A)
            ui.insignia((X0 + 668, cy), 11, B)
            ui.texto(B.nombre, (X0 + 688, cy), 15, U.VERDE if B is c else U.TEXTO, t["ganador"] == t["b"] or B is c, "ml", maxw=200)
            if doble:
                for key, x in (("ida", 420), ("vuelta", 500)):
                    ui.texto(f"{t[key][0]}-{t[key][1]}" if t[key] else "—", (X0 + x, cy), 14,
                             U.TEXTO if t[key] else U.APAGADO, bool(t[key]), "mc")
                if t["ida"] and t["vuelta"]:
                    ga, gb = t["ida"][0] + t["vuelta"][0], t["ida"][1] + t["vuelta"][1]
                    ui.texto(f"{ga}-{gb}" + (f" (p. {t['pen'][0]}-{t['pen'][1]})" if t["pen"] else ""), (X0 + 590, cy), 14,
                             U.AMARILLO, True, "mc")
            else:
                res = t["ida"]
                ui.texto(f"{res[0]}-{res[1]}" + (f" (p. {t['pen'][0]}-{t['pen'][1]})" if t["pen"] else "") if res else "vs",
                         (X0 + 480, cy), 15, U.AMARILLO if res else U.APAGADO, True, "mc")
        if fase == 4 and ch.terminada:
            ui.texto(f"Campeón de Europa: {self.mundo.clubes[ch.campeon].nombre}", (X0 + 10, 240), 22, U.AMARILLO, True)
            ui.insignia((X0 + 520, 320), 60, self.mundo.clubes[ch.campeon])

    def _champ_pie(self):
        """Tu camino en la Champions y los premios."""
        ui, c, ch = self.ui, self.club, self.champions
        panel = pygame.Rect(X0, 476, 700, 214)
        ui.panel(panel, U.PANEL, 12, U.BORDE)
        ui.texto("Tu camino", (panel.x + 16, panel.y + 8), 16, U.VERDE, True)
        camino = ch.camino(c.id)
        if not camino:
            ui.texto("Todavía no has jugado." if ch.estado(c.id) else "No participas esta temporada.", (panel.x + 16, panel.y + 40),
                     14, U.APAGADO)
        for k, (md, rival, gp, gr, prorroga, pp, pr, gano) in enumerate(camino[:14]):
            col, fila = divmod(k, 7)
            x, y = panel.x + 16 + col * 340, panel.y + 36 + fila * 25
            ui.texto(ch.corta(md), (x, y), 12, U.APAGADO, True, "ml", maxw=88)
            ui.insignia((x + 104, y), 9, self.mundo.clubes[rival])
            ui.texto(self.mundo.clubes[rival].nombre, (x + 120, y), 13, U.TEXTO, anchor="ml", maxw=110)
            extra = f" (p. {pp}-{pr})" if pp is not None else " (pr.)" if prorroga else ""
            ui.texto(f"{gp}-{gr}{extra}", (x + 318, y), 13, U.AMARILLO if gano is None else U.VERDE if gano else U.ROJO,
                     True, "mr")
        rx = panel.right + 14
        pan2 = pygame.Rect(rx, 476, ANCHO - rx - 14, 214)
        ui.panel(pan2, U.PANEL, 12, U.BORDE)
        if ch.terminada:
            ui.texto("Competición terminada", (rx + 14, pan2.y + 10), 15, U.AMARILLO, True)
        else:
            ui.texto("Próxima jornada", (rx + 14, pan2.y + 10), 15, U.AMARILLO, True)
            ui.texto(ch.etiqueta(ch.ronda), (rx + 14, pan2.y + 34), 13, U.TEXTO, maxw=pan2.w - 28)
            ui.texto(F.texto_fecha(self.fecha_comp(ch, ch.ronda), True), (rx + 14, pan2.y + 54), 13, U.APAGADO)
        ui.texto("Premios: participar 8 M€ · victoria 2 M€ · empate 0,7 M€", (rx + 14, pan2.y + 100), 12, U.APAGADO,
                 maxw=pan2.w - 28)
        ui.texto("Pasar de fase: 6 · 8 · 10 · 14 M€ · campeón +20 M€", (rx + 14, pan2.y + 120), 12, U.APAGADO, maxw=pan2.w - 28)
        ui.texto("Pasan los 2 primeros de cada grupo.", (rx + 14, pan2.y + 148), 12, U.APAGADO, maxw=pan2.w - 28)

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
    def preparar_partido(self, comp=None):
        c = self.club
        cambios = reparar_once(c)
        for sale, entra in cambios:
            self.aviso(f"{entra.nombre} sustituye a {sale.nombre if sale else 'una baja'} en el once.", U.AMARILLO, 5000)
        if comp is not None:
            self.copa_sorteo()
            h, v = comp.partido_de(c.id)
            local, visit = self.mundo.clubes[h], self.mundo.clubes[v]
            local_user = h == c.id
        else:
            rid, local_user = self.liga.rival(c)
            riv = self.mundo.clubes[rid]
            local, visit = (c, riv) if local_user else (riv, c)
        pron = self.asist.pronostico(local, visit)
        neutral = bool(comp is not None and comp.neutral)
        if neutral:                                   # final: campo neutral, sin ventaja de local
            pron["la"], pron["lb"] = pron["la"] / VENTAJA_LOCAL, pron["lb"] / 0.92
        self.p = {"fase": "pre", "local": local, "visit": visit, "user_local": local_user, "pron": pron,
                  "ga": 0, "gb": 0, "eventos": [], "t0": 0, "min": 0,
                  "copa": comp.ronda if comp is not None else None, "neutral": neutral, "comp": comp,
                  "decide": bool(comp is not None and comp.decide(local.id, visit.id)),
                  "previo": comp.previo(local.id, visit.id) if comp is not None else (0, 0)}
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
        est = p.get("est")
        fl, fv = (est["formacion"]["a"], est["formacion"]["b"]) if est else (L.formacion, V.formacion)
        ui.texto(f"{fl} · {L.entrenador}", (ANCHO // 2 - 270, y + 52), 13, U.APAGADO, maxw=210)
        ui.texto(f"{fv} · {V.entrenador}", (ANCHO // 2 + 270, y + 52), 13, U.APAGADO, anchor="tr", maxw=210)

    def partido_pre(self):
        ui, p, c = self.ui, self.p, self.club
        pr = p["pron"]
        L, V = p["local"], p["visit"]
        if p.get("copa") is not None:
            ui.texto(f"{p['comp'].nombre} · {p['comp'].etiqueta(p['copa'])}", (ANCHO // 2, 14), 18, U.AMARILLO, True, "tc")
            ui.logo_competicion((90, 70), 60, p["comp"].nombre)
            if p["previo"] != (0, 0):
                ui.texto(f"Ida: {V.nombre} {p['previo'][1]} - {p['previo'][0]} {L.nombre}", (ANCHO // 2, 150), 15, U.AMARILLO,
                         True, "tc", maxw=620)
        else:
            ui.texto("Previa del partido", (ANCHO // 2, 14), 18, U.APAGADO, anchor="tc")
        self.marcador(34)
        ui.texto("VS", (ANCHO // 2, 90), 40, U.AMARILLO, anchor="tc", titulo=True)
        ui.texto("Campo neutral" if p.get("neutral") else f"{L.estadio}", (ANCHO // 2, 130), 14, U.APAGADO, anchor="tc")
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
        r3 = pygame.Rect(60, 436, 1160, 172)
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
        yy += 6
        ui.texto(f"Táctica rival: {rival.tactica['salida']} · {rival.tactica['creacion']} · {rival.tactica['defensa']}"
                 f"  (bono {brv:+.1%})", (r3.x + 16, yy), 13, U.APAGADO, maxw=r3.w - 32)
        yy += 26                                  # las líneas siguientes se apilan: no se pisan entre sí
        lesionados = [j.nombre for j in c.plantel if j.lesion and j.motivo != "sanción"]
        suspendidos = [j.nombre for j in c.plantel if j.lesion and j.motivo == "sanción"]
        if lesionados or suspendidos:
            partes = ([f"Lesionados: {', '.join(lesionados[:4])}"] if lesionados else []) + \
                     ([f"Suspendidos: {', '.join(suspendidos[:4])}"] if suspendidos else [])
            ui.texto("No disponibles · " + "  |  ".join(partes), (r3.x + 16, yy), 13, U.ROJO, maxw=r3.w - 32)
            yy += 24
        fuera = [j.nombre for (g, j) in c.xi_con_grupo() if j.aptitud(g) < 0.55]
        if fuera:
            ui.texto("Fuera de posición: " + ", ".join(fuera), (r3.x + 16, yy), 13, U.AMARILLO, maxw=r3.w - 32)
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
        est = ev.nuevo_estado(p["local"], p["visit"], pr["la"], pr["lb"], lado)      # las jugadas se generan minuto a minuto
        self.audio.silbato("inicio")
        med = pr["fa"]["medio"], pr["fb"]["medio"]
        vista = VistaPartido(p["local"], p["visit"], med[0] / (med[0] + med[1]), semilla=p["local"].id * 1000 + p["visit"].id)
        if p.get("neutral"):
            est["neutral"] = True                                  # la final no tiene ventaja de local
        p.update(fase="vivo", est=est, lado=lado, min=0, fin=False, pausa=None, mini=None, ev_mini=None,
                 t_ult=pygame.time.get_ticks(), acum=0.0, vel=1, mentalidad="eq", tramo=1, jugadas=[],
                 banner=None, vista=vista, cam=None, prorroga=False, tanda_obj=None, tanda_ui=None)

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
        self.audio.silbato("inicio")
        p["tramo"] = 2
        p["pausa"] = None
        p["vista"].reiniciar("b")                                  # saque inicial del 2.º tiempo

    def _anunciar(self, minuto, solo=None):
        """Cartel breve con el evento más importante del minuto; además se actúan en la vista animada."""
        p = self.p
        for e in ([solo] if solo else p["est"]["eventos"]):
            if e["min"] == minuto and (e["res"] is not None or e["tipo"] not in ev.INTERACTIVOS):
                p["vista"].evento(e)
                self.audio.evento(e, p["lado"])
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
                p["mini"] = mj.crear(e, p["lado"], self.rng, p["est"]["clubes"])
                if e["tipo"] in ("penal", "tiro_libre"):
                    self.audio.silbato("largo" if e["tipo"] == "penal" else "corto")
                return
            if p["min"] >= (120 if p["prorroga"] else 90):
                if self._fin_de_tiempo():
                    break
            if p["min"] == 45 and p["tramo"] == 1:
                p["pausa"] = "descanso"
                self.audio.silbato("largo")
                return
            p["acum"] -= self.VEL_MS
            p["min"] += 1
            ev.generar_tramo(p["est"], p["min"], p["min"], self.rng)       # así los cambios del usuario afectan lo que viene
            self._anunciar(p["min"])

    def _fin_de_tiempo(self):
        """Pasa por aquí al llegar a los 90' (o a los 120'). En la copa, un empate a los 90' lleva a la prórroga.
        Devuelve True si el partido terminó."""
        p = self.p
        if p.get("copa") is not None and p["decide"] and not p["prorroga"]:
            ga, gb = ev.marcador(p["est"]["eventos"], 90)
            if ga + p["previo"][0] == gb + p["previo"][1]:
                p["prorroga"] = True
                self.audio.silbato("largo")
                self.aviso("¡Empate! Se juega la prórroga (30 minutos más).", U.AMARILLO, 5000)
                return False
        p["fin"] = True
        self.audio.silbato("final")
        return True

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
            if p["min"] >= (120 if p["prorroga"] else 90):
                if self._fin_de_tiempo():
                    break
            if p["min"] == 45 and p["tramo"] == 1:
                self._segundo_tiempo()
            else:
                p["min"] += 1
                ev.generar_tramo(p["est"], p["min"], p["min"], self.rng)
        p["banner"] = None
        if p.get("copa") is not None and p["decide"] and p["tanda_obj"] is None:
            ga, gb = ev.marcador(p["est"]["eventos"], p["min"])
            if ga + p["previo"][0] == gb + p["previo"][1]:         # empate global tras la prórroga: la tanda se simula sola
                t = CP.nueva_tanda(p["est"], "a" if self.rng.random() < 0.5 else "b")
                t.simular_resto(self.rng)
                p["tanda_obj"] = t

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
        elif clave == "cambio":
            pygame.draw.circle(surf, U.VERDE, (cx, cy), 10)
            pygame.draw.polygon(surf, (255, 255, 255), [(cx - 6, cy - 6), (cx + 6, cy - 3), (cx - 6, cy)])
            pygame.draw.polygon(surf, (255, 255, 255), [(cx + 6, cy), (cx - 6, cy + 3), (cx + 6, cy + 6)])
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
        if p["prorroga"] and not p["fin"] and p["pausa"] is None:
            etiqueta = f"{p['min']}' · prórroga"
        ui.texto(etiqueta, (ANCHO // 2, 190), 28, U.AMARILLO, True, "tc")
        ui.barra((ANCHO // 2 - 200, 232, 400, 8), p["min"] / (120 if p["prorroga"] else 90), U.VERDE)
        if p.get("copa") is not None and p["previo"] != (0, 0):
            ui.texto(f"Global: {ga + p['previo'][0]} - {gb + p['previo'][1]}", (ANCHO // 2 + 230, 186), 15, U.AMARILLO, True, "tl")
        # campo animado
        campo = pygame.Rect(ANCHO // 2 - 300, 262, 600, 330)
        p["vista"].dibujar(ui, campo)
        if p["banner"] and p["banner"][2] > pygame.time.get_ticks():
            tx, col, _ = p["banner"]
            w = ui.fuente(26, True).size(tx)[0] + 40
            r = pygame.Rect(0, 0, w, 46)
            r.midtop = (campo.centerx, campo.bottom + 14)             # fuera del campo, justo debajo
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
            n_c, n_v = CB.restantes(est, p["lado"])
            if ui.boton((60, 620, 250, 50), f"Cambios y formación ({n_c})", tam=15,
                        tip=f"Haz cambios (máx. {ev.MAX_CAMBIOS} por partido, {ev.MAX_VENTANAS} paradas) o cambia de formación.\n"
                            "El partido se detiene mientras decides."):
                self.abrir_cambios()
            ui.texto("Velocidad", (960, 340), 13, U.APAGADO, anchor="ml")        # arriba de las estadísticas
            for i, v in enumerate((1, 2, 4)):
                if ui.boton((1048 + i * 58, 324, 52, 32), f"x{v}", p["vel"] == v, tam=15, color=U.AZUL):
                    p["vel"] = v
        if p["pausa"] == "mini":
            r = p["mini"].dibujar(ui)
            if r:
                self._cerrar_minijuego(r)
        elif p["pausa"] == "descanso":
            self._descanso(ga, gb)
        elif p["pausa"] == "cambios":
            self._panel_cambios()
        elif p["pausa"] == "tanda":
            self._panel_tanda()
        elif p["fin"]:
            self.resumen_final(ga, gb)

    # ------------------------------------------------ cambios y formación durante el partido
    def abrir_cambios(self):
        p = self.p
        p["cam"] = {"form": p["est"]["formacion"][p["lado"]], "pend": [], "sel": None, "prev": p["pausa"], "msg": ""}
        p["pausa"] = "cambios"

    def _cerrar_cambios(self):
        p = self.p
        p["pausa"] = p["cam"]["prev"]
        p["cam"] = None
        p["acum"] = 0.0

    def _panel_cambios(self):
        ui, p = self.ui, self.p
        est, lado, cam = p["est"], p["lado"], p["cam"]
        club = est["clubes"][lado]
        descanso = cam["prev"] == "descanso"
        sombra = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 185))
        ui.surf.blit(sombra, (0, 0))
        M = pygame.Rect(90, 44, 1100, 632)
        ui.panel(M, (12, 18, 30), 14, U.BORDE)
        ui.texto("CAMBIOS Y FORMACIÓN", (M.x + 24, M.y + 12), 40, U.AMARILLO, titulo=True)
        n_c, n_v = CB.restantes(est, lado)
        pend = cam["pend"]
        ui.texto(f"Minuto {p['min']}' · cambios usados {ev.MAX_CAMBIOS - n_c}/{ev.MAX_CAMBIOS} "
                 f"(con los pendientes {ev.MAX_CAMBIOS - n_c + len(pend)}/{ev.MAX_CAMBIOS}) · "
                 + ("descanso: no usa una parada" if descanso else f"paradas usadas {ev.MAX_VENTANAS - n_v}/{ev.MAX_VENTANAS}"),
                 (M.x + 26, M.y + 62), 14, U.APAGADO, maxw=M.w - 52)
        nuevo, err = CB.proponer(est, lado, cam["form"], pend)
        base = nuevo or CB.en_campo(est, lado)
        entran = {e.id for _, e in pend}
        # ---- campo con el once (y los cambios pendientes)
        campo = pygame.Rect(M.x + 24, M.y + 92, 400, 520)
        ui.campo(campo)
        c1, c2, patron = club.color, club.color2, club.patron
        for slot, j in base:
            px, py = ui.pos_campo(campo, slot[1], slot[2])
            entrante = j.id in entran
            if cam["sel"] is not None and cam["sel"].id == j.id:
                pygame.draw.circle(ui.surf, U.AMARILLO, (px, py), 26, 3)
            elif entrante:
                pygame.draw.circle(ui.surf, U.VERDE, (px, py), 26, 3)
            if slot[0] == "POR":
                k1, k2 = color_portero(c1, c2)
                ui.camiseta((px, py), 36, k1, k2, numero=j.dorsal)
            else:
                ui.camiseta((px, py), 36, c1, c2, numero=j.dorsal, patron=patron)
            pygame.draw.circle(ui.surf, color_apt(j.aptitud(slot[0])), (px + 20, py - 19), 10)
            ui.texto(j.ovr, (px + 20, py - 19), 10, (10, 20, 15), True, "mc")
            apellido = [t for t in j.nombre.split() if not t.endswith(".")]
            ui.placa_jugador_corta(px, py + 20, apellido[-1] if apellido else j.nombre)
            rr = pygame.Rect(0, 0, 58, 62)
            rr.center = (px, py + 6)
            if ui.hover(rr):
                ui.tip = f"{j.nombre} ({j.pos}) · OVR {j.ovr}" + ("\nEntra en este puesto (clic para deshacer)." if entrante
                                                                  else "\nClic para elegir a quién sacar.")
            if ui.clic_en(rr):
                if entrante:
                    cam["pend"] = [(s_, e_) for s_, e_ in pend if e_.id != j.id]
                    cam["msg"] = ""
                else:
                    cam["sel"] = None if (cam["sel"] is not None and cam["sel"].id == j.id) else j
        # ---- banquillo
        bx, by = M.x + 450, M.y + 92
        ui.texto("Banquillo", (bx, by), 18, U.VERDE, True)
        ui.texto("Elige primero a quién sacar (campo) y luego quién entra.", (bx, by + 24), 12, U.APAGADO)
        for i, j in enumerate(CB.banquillo(est, lado)):
            r = pygame.Rect(bx, by + 50 + i * 43, 340, 40)
            dentro = j.id in entran
            if dentro:
                ui.panel(r, (24, 52, 40), 8, U.VERDE)
            elif ui.hover(r):
                ui.panel(r, U.PANEL2, 8, U.AMARILLO if cam["sel"] is not None else U.BORDE)
            else:
                ui.panel(r, U.PANEL, 8)
            ui.texto(j.pos, (r.x + 12, r.centery), 14, U.AMARILLO, True, "ml")
            ui.texto(j.nombre, (r.x + 58, r.centery), 14, U.TEXTO, True, "ml", maxw=170)
            ui.texto(f"OVR {j.ovr}", (r.x + 238, r.centery), 14, U.VERDE, True, "ml")
            ui.texto(f"{j.edad}", (r.right - 14, r.centery), 13, U.APAGADO, anchor="mr")
            if ui.clic_en(r) and not dentro:
                if cam["sel"] is None:
                    cam["msg"] = "Primero toca en el campo al jugador que sale."
                elif len(pend) - sum(1 for s_, _ in pend if s_.id == cam["sel"].id) >= n_c:
                    cam["msg"] = f"No quedan más cambios (máx. {ev.MAX_CAMBIOS})."
                else:
                    cam["pend"] = [(s_, e_) for s_, e_ in pend if s_.id != cam["sel"].id] + [(cam["sel"], j)]
                    cam["sel"], cam["msg"] = None, ""
        if not CB.banquillo(est, lado):
            ui.texto("No quedan suplentes disponibles.", (bx, by + 54), 14, U.APAGADO)
        # ---- formación y resumen
        rx = M.x + 820
        ui.texto("Formación", (rx, by), 18, U.VERDE, True)
        for k, f in enumerate(FORMACIONES):
            if ui.boton((rx + (k % 2) * 136, by + 30 + (k // 2) * 46, 128, 38), f, cam["form"] == f, tam=15):
                cam["form"], cam["msg"] = f, ""
        ui.texto("El cambio de formación es libre.", (rx, by + 126), 12, U.APAGADO)
        ui.texto("Cambios pendientes", (rx, by + 158), 16, U.VERDE, True)
        if not pend:
            ui.texto("Ninguno.", (rx, by + 186), 13, U.APAGADO)
        for i, (sale, entra) in enumerate(pend):
            ui.texto(f"{sale.nombre} → {entra.nombre}", (rx, by + 186 + i * 22), 13, U.TEXTO, maxw=262)
        if cam["form"] != est["formacion"][lado]:
            ui.texto(f"Formación: {est['formacion'][lado]} → {cam['form']}", (rx, by + 186 + max(1, len(pend)) * 22 + 6), 13,
                     U.AMARILLO, True, maxw=262)
        if cam["sel"] is not None:
            ui.texto(f"Sale: {cam['sel'].nombre}", (rx, by + 330), 14, U.AMARILLO, True, maxw=262)
        mensaje = err or cam["msg"]
        ok, motivo = CB.validar(est, lado, cam["form"], pend, descanso)
        if not ok and not err:
            mensaje = motivo
        if mensaje:
            ui.parrafo(mensaje, pygame.Rect(rx, by + 360, 262, 70), 13, U.ROJO)
        # ---- botones
        hay = bool(pend) or cam["form"] != est["formacion"][lado]
        if ui.boton((M.x + 450, M.bottom - 62, 150, 46), "Deshacer todo", tam=15, habilitado=hay):
            cam.update(pend=[], sel=None, form=est["formacion"][lado], msg="")
        if ui.boton((M.right - 360, M.bottom - 62, 150, 46), "Cancelar", tam=16):
            self._cerrar_cambios()
        elif ui.boton((M.right - 200, M.bottom - 62, 176, 46), "Confirmar cambios", True, habilitado=hay and ok, tam=16):
            ok2, msg, evs = CB.aplicar(est, lado, cam["form"], pend, p["min"], self.asist.bono_tactico, descanso)
            if ok2:
                for e in evs:
                    self._anunciar(p["min"], solo=e)
                self.aviso("Cambios realizados." if any(e["tipo"] == "cambio" for e in evs) else "Formación cambiada.")
                self._cerrar_cambios()
            else:
                cam["msg"] = msg

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
        n_c, _ = CB.restantes(p["est"], p["lado"])
        if ui.boton((r.x + 20, r.bottom - 74, 262, 54), f"Cambios y formación ({n_c})", tam=16,
                    tip="En el descanso los cambios no usan una de las 3 paradas."):
            self.abrir_cambios()
        elif ui.boton((r.right - 320, r.bottom - 74, 300, 54), "Empezar el 2.º tiempo", True, tam=19) or \
                pygame.K_RETURN in ui.teclas:
            self._segundo_tiempo()

    def resumen_final(self, ga, gb):
        ui, p, c = self.ui, self.p, self.club
        user_goles, riv_goles = (ga, gb) if p["user_local"] else (gb, ga)
        res = "¡VICTORIA!" if user_goles > riv_goles else "EMPATE" if user_goles == riv_goles else "DERROTA"
        col = U.VERDE if user_goles > riv_goles else U.AMARILLO if user_goles == riv_goles else U.ROJO
        copa = p.get("copa") is not None
        t = p.get("tanda_obj")
        decide = copa and p["decide"]
        pv = p["previo"] if copa else (0, 0)
        A, B = ga + pv[0], gb + pv[1]                         # global (con la ida, si la hubo)
        falta_tanda = decide and A == B and t is None
        if copa:
            glob = f"Global: {A if p['user_local'] else B}-{B if p['user_local'] else A}. " if pv != (0, 0) else ""
            if decide:
                if A != B:
                    gano = (A > B) == p["user_local"]
                elif t is not None:
                    gano = t.ganador() == p["lado"]
                else:
                    gano = None
                titulo_ok = "¡CAMPEÓN!" if p["comp"].neutral else "¡PASAS DE RONDA!"
                res, col = ((titulo_ok, U.VERDE) if gano else ("ELIMINADO", U.ROJO)) if gano is not None else \
                    ("EMPATE", U.AMARILLO)
                if falta_tanda:
                    nota = glob + "Empate tras la prórroga: hay tanda de penales."
                elif t is not None and A == B:
                    nota = f"Tanda de penales: {t.goles['a']}-{t.goles['b']}"
                else:
                    nota = glob + ("Tras la prórroga." if p["prorroga"] else "")
            else:
                nota = "Eliminatoria abierta: se decide en la vuelta." if p["copa"] in (6, 8, 10) else ""
            ui.texto(nota, (1090, 300), 13, U.APAGADO, anchor="tc", maxw=250)
        ui.texto_fit(res, (1090, 262), 54, 22, 250, col, anchor="tc", titulo=True)
        pr = p["pron"]["mc"]
        pu = (pr["gana_a"] if p["user_local"] else pr["gana_b"])
        ui.texto(f"El asistente te daba {pu:.0%} de ganar.", (1090, 322), 14, U.APAGADO, anchor="tc")
        if p["jugadas"]:
            ok = sum(1 for _, a in p["jugadas"] if a)
            ui.texto(f"Jugadas clave jugadas: {ok}/{len(p['jugadas'])} a tu favor", (1090, 342), 13, U.AMARILLO, anchor="tc")
        if falta_tanda:
            if ui.boton((ANCHO - 260, 620, 220, 50), "Tanda de penales", True, U.AMARILLO, tam=18):
                self.iniciar_tanda()
        elif ui.boton((ANCHO - 260, 620, 220, 50), "Continuar", True, tam=18):
            if copa:
                self.cerrar_partido_copa(ga, gb)
            else:
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
        if liga.terminada:                            # se guarda también al terminar: se puede seguir con la siguiente temporada
            pos = liga.posicion(c)
            self.historial_temporadas.append({"temporada": self.temporada, "pos": pos, "pts": c.pts, "division": c.division,
                                              "objetivo": self.objetivo_pos, "cumplido": pos <= self.objetivo_pos})
        self.copa_sorteo()                            # si ahora toca una ronda de copa, se sortea
        self.guardar()                                # autoguardado al cerrar cada jornada
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

    # ======================================================= MODO CARRERA: paso de temporada
    def escena_pasando(self):
        self.dibujar_logo(ANCHO // 2, 90, 240)
        self.ui.texto("Pasa el tiempo…", (ANCHO // 2, ALTO // 2 + 90), 34, U.TEXTO, True, "mc")
        self.ui.texto("Evolucionando a todos los jugadores con el modelo entrenado con FIFA 18-24",
                      (ANCHO // 2, ALTO // 2 + 130), 16, (170, 184, 208), anchor="mc")
        if self._pasando_frame:
            self._pasando_frame = False
            self.siguiente_temporada()
        else:
            self._pasando_frame = True

    def jugar_auto(self, comp=None):
        """Juega tu partido (de liga, copa o Champions) sin verlo, como al pulsar 'Omitir partido'."""
        self.preparar_partido(comp)
        self.iniciar_partido()
        self.omitir_partido()
        p = self.p
        ga, gb = ev.marcador(p["est"]["eventos"], p["min"])
        if comp is not None:
            self.cerrar_partido_copa(ga, gb)
        else:
            self.cerrar_jornada(ga, gb)

    def simular_hasta(self, objetivo):
        """Juega todos tus partidos (liga, copas y Champions) hasta llegar a la jornada `objetivo` (0-based) de liga."""
        jugados = 0
        while not self.liga.terminada and self.liga.jornada < objetivo:
            self.copa_simular_sin_usuario()
            comp = self.comp_debida()
            if comp is not None:
                self.copa_sorteo()
            self.jugar_auto(comp)
            jugados += 1
            if self.escena == "fin":
                break
        self.avisos.clear()
        if self.escena == "hub":
            self.tab = "calendario"
            self.cal_sel = None
            self.cal_mes = None
        self.aviso(f"Simulados {jugados} partidos. Próximo: jornada {self.liga.jornada + 1}.", U.VERDE, 5000)

    def cerrar_division(self):
        """Fin de temporada: se simulan las demás divisiones y suben y bajan los clubes (antes de la evolución)."""
        c = self.club
        orden = [t.id for t in self.liga.tabla()]
        res = AS.cerrar_temporada(self.mundo, c, orden, self.rng, self.asist)
        mov = AS.estado_usuario(self.mundo, c, orden)
        self._ordenes_prev = {liga: r["primera"] for liga, r in res.items()}
        if self.historial_temporadas:
            self.historial_temporadas[-1]["mov"] = mov
        self.res_ascensos = {"res": res, "mov": mov, "liga": c.liga_madre, "division": c.division}
        AS.aplicar(self.mundo, res)

    def escena_ascensos(self):
        ui, a, c = self.ui, self.res_ascensos, self.club
        ui.texto("ASCENSOS Y DESCENSOS", (ANCHO // 2, 12), 58, anchor="tc", titulo=True)
        mov = a["mov"]
        nom2 = AS.nombre_segunda(self.mundo, a["liga"])
        txt, col = {"sube": (f"¡{c.nombre} ASCIENDE a {a['liga']}!", U.VERDE),
                    "baja": (f"{c.nombre} DESCIENDE a {nom2}", U.ROJO),
                    "sigue": (f"{c.nombre} se mantiene en {a['liga'] if a['division'] == 1 else nom2}", U.AMARILLO)}[mov]
        ui.texto(txt, (ANCHO // 2, 84), 30, col, True, "tc")
        if mov == "baja":
            ui.texto("La temporada que viene juegas en la segunda división. Si terminas entre los primeros, vuelves a subir.",
                     (ANCHO // 2, 124), 15, U.APAGADO, anchor="tc")
        elif mov == "sube":
            ui.texto(f"Cobras {eur(AS.PREMIO_ASCENSO)} de premio por el ascenso.", (ANCHO // 2, 124), 15, U.APAGADO, anchor="tc")
        for k, (liga, r) in enumerate(a["res"].items()):
            rect = pygame.Rect(18 + k * 248, 156, 240, 456)
            ui.panel(rect, U.PANEL, 12, U.AMARILLO if liga == a["liga"] else U.BORDE)
            if not ui.logo_liga((rect.centerx, rect.y + 36), 34, liga):
                ui.texto(liga, (rect.centerx, rect.y + 24), 18, anchor="tc", titulo=True)
            ui.texto(liga, (rect.centerx, rect.y + 68), 15, U.APAGADO, True, "tc")
            y = rect.y + 98
            ui.texto("CAMPEÓN", (rect.x + 14, y), 11, U.AMARILLO, True)
            y += 20
            filas = [("c", r["primera"][0])]
            filas_s = [(("↑", U.VERDE), i) for i in r["suben"]]
            filas_b = [(("↓", U.ROJO), i) for i in r["bajan"]]

            def fila(yy, marca, cid):
                club = self.mundo.clubes[cid]
                if marca:
                    ui.texto(marca[0], (rect.x + 14, yy + 13), 17, marca[1], True, "ml")
                ui.insignia((rect.x + 46, yy + 13), 11, club)
                ui.texto(club.nombre, (rect.x + 66, yy + 13), 14, U.AMARILLO if club is c else U.TEXTO, club is c, "ml",
                         maxw=164)
            fila(y, None, filas[0][1])
            y += 40
            ui.texto("SUBEN A PRIMERA", (rect.x + 14, y), 11, U.VERDE, True)
            y += 22
            for marca, cid in filas_s:
                fila(y, marca, cid)
                y += 30
            y += 14
            ui.texto("BAJAN A SEGUNDA", (rect.x + 14, y), 11, U.ROJO, True)
            y += 22
            for marca, cid in filas_b:
                fila(y, marca, cid)
                y += 30
            ui.texto(f"Campeón de segunda: {self.mundo.clubes[r['segunda'][0]].nombre}", (rect.x + 14, rect.bottom - 22), 11,
                     U.APAGADO, maxw=rect.w - 28)
        if ui.boton((ANCHO // 2 - 150, 634, 300, 56), "Continuar", True, tam=21):
            self._pasando_frame = False
            self.ir("pasando")

    def siguiente_temporada(self):
        c, liga = self.club, self.liga
        posiciones = {t.id: i + 1 for i, t in enumerate(liga.tabla())}
        presupuesto0 = c.presupuesto
        if self.copa and self.historial_temporadas:
            self.historial_temporadas[-1]["copa"] = f"{self.copa.nombre}: {self.copa.texto_estado(c.id)}"
        if self.champions and self.historial_temporadas and self.champions.estado(c.id) is not None:
            self.historial_temporadas[-1]["champions"] = f"{self.champions.nombre}: {self.champions.texto_estado(c.id)}"
        self.resumen_evol = EV.avanzar_temporada(self.mundo, self.rng, c, posiciones)
        self.resumen_evol["presupuesto"] = (presupuesto0, c.presupuesto)
        self.temporada += 1
        self.iniciar_temporada(c)                               # liga y calendario nuevos
        self.guardar()
        self.ir("evolucion")

    def escena_evolucion(self):
        ui, r, c = self.ui, self.resumen_evol, self.club
        ui.texto(f"TEMPORADA {F.nombre_temporada(self.temporada)}", (ANCHO // 2, 14), 62, anchor="tc", titulo=True)
        ui.texto("Así cambió tu plantilla en un año (modelo de evolución entrenado con datos reales de FIFA 18-24)",
                 (ANCHO // 2, 84), 15, U.APAGADO, anchor="tc")
        cambios = sorted(r["cambios"], key=lambda t: (t[2] - t[1], t[2]), reverse=True)
        suben = [t for t in cambios if t[2] > t[1]][:7]
        bajan = [t for t in reversed(cambios) if t[2] < t[1]][:7]

        def lista(rect, titulo, color, filas):
            ui.panel(rect, U.PANEL, 12, U.BORDE)
            ui.texto(titulo, (rect.x + 16, rect.y + 10), 18, color, True)
            if not filas:
                ui.texto("Nadie.", (rect.x + 16, rect.y + 46), 14, U.APAGADO)
            for i, (j, o0, o1, p0, p1) in enumerate(filas):
                y = rect.y + 50 + i * 36
                ui.texto(j.nombre, (rect.x + 16, y), 14, U.TEXTO, True, "ml", maxw=150)
                ui.texto(f"{j.edad} años", (rect.x + 172, y), 12, U.APAGADO, anchor="ml")
                ui.texto(f"{o0} → {o1}", (rect.x + 240, y), 14, U.TEXTO, anchor="ml")
                ui.texto(f"{o1 - o0:+d}", (rect.right - 16, y), 16, U.VERDE if o1 > o0 else U.ROJO, True, "mr")
        lista(pygame.Rect(40, 118, 390, 308), "Mejoran", U.VERDE, suben)
        lista(pygame.Rect(445, 118, 390, 308), "Bajan", U.ROJO, bajan)
        rr = pygame.Rect(850, 118, 390, 308)
        ui.panel(rr, U.PANEL, 12, U.BORDE)
        ui.texto("Salidas y cantera", (rr.x + 16, rr.y + 10), 18, U.AMARILLO, True)
        y = rr.y + 48
        if r["retirados"]:
            ui.texto("Dejan el club (retiro o salida a otras ligas)", (rr.x + 16, y), 12, U.APAGADO, True)
            for j, o, e in r["retirados"][:4]:
                y += 24
                ui.texto(f"{j.nombre} · {e} años · OVR {o}", (rr.x + 16, y), 13, U.ROJO, anchor="ml", maxw=rr.w - 32)
            y += 30
        else:
            ui.texto("Nadie de tu plantilla se va.", (rr.x + 16, y), 13, U.APAGADO, anchor="ml")
            y += 34
        if r["cantera"]:
            ui.texto("Llegan de la cantera", (rr.x + 16, y), 12, U.APAGADO, True)
            for j in r["cantera"][:5]:
                y += 24
                ui.texto(f"{j.nombre} · {j.edad} años · OVR {j.ovr} · POT {j.pot}", (rr.x + 16, y), 13, U.VERDE,
                         anchor="ml", maxw=rr.w - 32)
        else:
            ui.texto("No hizo falta fichar de la cantera.", (rr.x + 16, y), 13, U.APAGADO, anchor="ml")
        # ---- resumen
        m = r["mundo"]
        pan = pygame.Rect(40, 440, 1200, 160)
        ui.panel(pan, U.PANEL, 12, U.BORDE)
        x0, x1 = r["media_xi"]
        p0, p1 = r["presupuesto"]
        ui.texto(f"Valoración media de tu once: {x0:.1f} → {x1:.1f}", (pan.x + 20, pan.y + 14), 17, U.TEXTO, True)
        ui.texto(f"Presupuesto: {eur(p0)} → {eur(p1)} (ingresos según el valor del plantel y tu posición final)",
                 (pan.x + 20, pan.y + 44), 15, U.TEXTO)
        ui.texto(f"En todo el mundo: {m['jugadores']:,} jugadores · {m['suben']:,} suben · {m['bajan']:,} bajan · "
                 f"{m['retirados']:,} dejan el juego · cambio medio {m['delta_medio']:+.1f} OVR".replace(",", " "),
                 (pan.x + 20, pan.y + 72), 14, U.APAGADO)
        ui.texto(f"Objetivo de la directiva para esta temporada: top {self.objetivo_pos}", (pan.x + 20, pan.y + 100), 15,
                 U.AMARILLO, True)
        if self.historial_temporadas:
            hist = "   ".join(f"{F.nombre_temporada(h['temporada'])}: {h['pos']}º ({h['pts']} pts) "
                             f"{'cumplido' if h['cumplido'] else 'no cumplido'}" for h in self.historial_temporadas[-4:])
            ui.texto("Temporadas anteriores:  " + hist, (pan.x + 20, pan.y + 128), 13, U.APAGADO, maxw=pan.w - 40)
        if ui.boton((ANCHO // 2 - 170, 626, 340, 56), "Empezar la temporada", True, tam=21):
            self.tab = "alineacion"
            self.ir("hub")

    # ==================================================================== FIN
    def escena_fin(self):
        ui, c, liga = self.ui, self.club, self.liga
        tabla = liga.tabla()
        pos = tabla.index(c) + 1
        cumplido = pos <= self.objetivo_pos
        ui.texto("FIN DE TEMPORADA", (ANCHO // 2, 30), 70, anchor="tc", titulo=True)
        ui.texto(f"Campeón: {tabla[0].nombre}", (ANCHO // 2, 108), 26, U.AMARILLO, True, "tc")
        mov = AS.estado_usuario(self.mundo, c, [t.id for t in tabla])
        if mov != "sigue":
            ui.texto("¡ASCENSO! Subes a primera." if mov == "sube" else "DESCENSO: bajas a segunda división.",
                     (ANCHO // 2, 142), 22, U.VERDE if mov == "sube" else U.ROJO, True, "tc")
        ui.insignia((ANCHO // 2 - 300, 220), 50, c)
        ui.texto(f"{c.nombre}: {pos}º puesto con {c.pts} puntos", (ANCHO // 2 - 220, 190), 30, titulo=True)
        ui.texto(f"Objetivo: top {self.objetivo_pos}  →  {'¡CUMPLIDO!' if cumplido else 'No cumplido'}",
                 (ANCHO // 2 - 220, 230), 24, U.VERDE if cumplido else U.ROJO, True)
        ui.texto(f"{c.g} G · {c.e} E · {c.p} P · goles {c.gf}-{c.gc}", (ANCHO // 2 - 220, 266), 16, U.APAGADO)
        if self.copa:
            ui.texto(f"{self.copa.nombre}: {self.copa.texto_estado(c.id)}", (ANCHO // 2 - 220, 288), 16, U.AMARILLO, True)
        if self.champions and self.champions.estado(c.id) is not None:
            ui.texto(f"{self.champions.nombre}: {self.champions.texto_estado(c.id)}", (ANCHO // 2 - 220, 310), 16,
                     (150, 190, 255), True)
        r = pygame.Rect(ANCHO // 2 - 300, 340, 600, 250)
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
        if ui.boton((ANCHO // 2 + 20, 620, 280, 54), "Siguiente temporada", True, tam=20,
                    tip="Pasa un año: los jugadores cambian de nivel (modelo entrenado con FIFA 18-24),\n"
                        "algunos jugadores se van del club y llega la cantera."):
            self.cerrar_division()
            self.ir("ascensos")
        if ui.boton((24, ALTO - 64, 140, 40), "← Menú", tam=16, tip="La partida queda guardada: puedes continuarla."):
            self.ir("menu")
