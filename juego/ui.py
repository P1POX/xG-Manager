"""Mini-biblioteca de interfaz en modo inmediato para Pygame (botones, paneles, campo, camisetas)."""
import math
from pathlib import Path

import pygame

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "assets" / "fonts"
LOGOS = RAIZ / "assets" / "logos"

FONDO = (13, 19, 31)
PANEL = (23, 32, 49)
PANEL2 = (33, 45, 68)
BORDE = (52, 68, 98)
TEXTO = (232, 238, 247)
APAGADO = (139, 152, 176)
VERDE = (46, 204, 113)
AMARILLO = (255, 193, 7)
ROJO = (235, 87, 87)
AZUL = (66, 153, 225)
NARANJA = (255, 140, 66)
COLORES_CLUSTER = [(66, 153, 225), (255, 140, 66), (46, 204, 113), (235, 87, 87), (171, 123, 255),
                   (255, 213, 79), (38, 198, 218), (240, 98, 146), (160, 160, 170)]


def mezclar(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


class UI:
    def __init__(self, surf):
        self.surf = surf
        self._fuentes = {}
        self._cache = {}
        self._logos = {}
        self.mouse = (0, 0)
        self.click = None
        self.click_der = None
        self.rueda = 0
        self.tipeo = []
        self.teclas = []
        self.foco = None
        self.tip = None
        self.log = None           # si es una lista, boton() registra (rect, label, habilitado)

    # ------------------------------------------------------------- eventos
    def inicio_frame(self, eventos):
        self.mouse = pygame.mouse.get_pos()
        self.click = self.click_der = None
        self.rueda = 0
        self.tipeo = []
        self.teclas = []
        self.tip = None
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                self.click = e.pos
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 3:
                self.click_der = e.pos
            elif e.type == pygame.MOUSEWHEEL:
                self.rueda += e.y
            elif e.type == pygame.TEXTINPUT:
                self.tipeo.append(e.text)
            elif e.type == pygame.KEYDOWN:
                self.teclas.append(e.key)

    def consumir_click(self):
        self.click = None

    # --------------------------------------------------------------- texto
    def fuente(self, tam, negrita=False, titulo=False):
        k = (tam, negrita, titulo)
        if k not in self._fuentes:
            if titulo:
                f = pygame.font.Font(str(FUENTES / "BebasNeue-Regular.ttf"), tam)
            else:
                f = pygame.font.Font(str(FUENTES / ("Lato-Bold.ttf" if negrita else "Lato-Regular.ttf")), tam)
            self._fuentes[k] = f
        return self._fuentes[k]

    def _render(self, s, tam, color, negrita, titulo):
        k = (s, tam, color, negrita, titulo)
        surf = self._cache.get(k)
        if surf is None:
            if len(self._cache) > 3000:
                self._cache.clear()
            surf = self.fuente(tam, negrita, titulo).render(s, True, color)
            self._cache[k] = surf
        return surf

    def texto(self, s, pos, tam=16, color=TEXTO, negrita=False, anchor="tl", maxw=None, titulo=False):
        s = str(s)
        if maxw:
            f = self.fuente(tam, negrita, titulo)
            if f.size(s)[0] > maxw:
                while s and f.size(s + "…")[0] > maxw:
                    s = s[:-1]
                s += "…"
        img = self._render(s, tam, color, negrita, titulo)
        r = img.get_rect()
        setattr(r, {"tl": "topleft", "tr": "topright", "tc": "midtop", "ml": "midleft", "mr": "midright",
                    "mc": "center", "bl": "bottomleft", "br": "bottomright"}[anchor], pos)
        self.surf.blit(img, r)
        return r

    def texto_fit(self, s, pos, tam, minimo, maxw, color=TEXTO, negrita=False, anchor="tl", titulo=False):
        """Reduce el tamaño de fuente hasta que el texto quepa en maxw."""
        while tam > minimo and self.fuente(tam, negrita, titulo).size(str(s))[0] > maxw:
            tam -= 1
        return self.texto(s, pos, tam, color, negrita, anchor, maxw=maxw, titulo=titulo)

    def parrafo(self, s, rect, tam=15, color=TEXTO, interlinea=4):
        """Texto con salto de línea automático dentro de rect. Devuelve el y final."""
        f = self.fuente(tam)
        x, y = rect.x, rect.y
        for linea in str(s).split("\n"):
            palabras, actual = linea.split(" "), ""
            for p in palabras:
                prueba = (actual + " " + p).strip()
                if f.size(prueba)[0] > rect.w and actual:
                    self.texto(actual, (x, y), tam, color)
                    y += f.get_linesize() + interlinea
                    actual = p
                else:
                    actual = prueba
            self.texto(actual, (x, y), tam, color)
            y += f.get_linesize() + interlinea
        return y

    # ------------------------------------------------------------- formas
    def panel(self, rect, color=PANEL, radio=10, borde=None):
        pygame.draw.rect(self.surf, color, rect, border_radius=radio)
        if borde:
            pygame.draw.rect(self.surf, borde, rect, 1, border_radius=radio)

    def hover(self, rect):
        return pygame.Rect(rect).collidepoint(self.mouse)

    def clic_en(self, rect):
        if self.click and pygame.Rect(rect).collidepoint(self.click):
            self.click = None
            return True
        return False

    def boton(self, rect, label, activo=None, habilitado=True, color=None, tam=16, tip=None, negrita=True):
        """activo=True/False -> botón de selección (color = color al estar activo);
        activo=None -> botón de acción (color = color de fondo)."""
        rect = pygame.Rect(rect)
        if self.log is not None:
            self.log.append((rect.copy(), label, habilitado))
        h = habilitado and rect.collidepoint(self.mouse)
        if not habilitado:
            fondo, tc = (30, 38, 55), (96, 108, 130)
        elif activo:
            fondo, tc = color or VERDE, (10, 20, 15)
        else:
            base = (color if activo is None else None) or PANEL2
            fondo, tc = (mezclar(base, (255, 255, 255), 0.12) if h else base), TEXTO
        pygame.draw.rect(self.surf, fondo, rect, border_radius=8)
        if not activo and habilitado:
            pygame.draw.rect(self.surf, BORDE, rect, 1, border_radius=8)
        self.texto(label, rect.center, tam, tc, negrita, "mc", maxw=rect.w - 8)
        if tip and h:
            self.tip = tip
        if habilitado and self.click and rect.collidepoint(self.click):
            self.click = None
            return True
        return False

    def barra(self, rect, frac, color=VERDE, fondo=(40, 52, 76)):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.surf, fondo, rect, border_radius=rect.h // 2)
        w = int(rect.w * max(0.0, min(1.0, frac)))
        if w > 0:
            pygame.draw.rect(self.surf, color, (rect.x, rect.y, w, rect.h), border_radius=rect.h // 2)

    def entrada_texto(self, rect, valor, clave, placeholder=""):
        rect = pygame.Rect(rect)
        if self.click and rect.collidepoint(self.click):
            self.foco = clave
            self.click = None
        elif self.click and self.foco == clave:
            self.foco = None
        activo = self.foco == clave
        pygame.draw.rect(self.surf, (18, 26, 42), rect, border_radius=8)
        pygame.draw.rect(self.surf, VERDE if activo else BORDE, rect, 1, border_radius=8)
        if activo:
            for t in self.tipeo:
                valor += t
            for k in self.teclas:
                if k == pygame.K_BACKSPACE:
                    valor = valor[:-1]
                elif k in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self.foco = None
        self.texto(valor + ("|" if activo and pygame.time.get_ticks() // 500 % 2 == 0 else "") or placeholder,
                   (rect.x + 10, rect.centery), 15, TEXTO if valor else APAGADO, anchor="ml", maxw=rect.w - 16)
        return valor

    def dibujar_tooltip(self):
        if not self.tip:
            return
        f = self.fuente(14)
        lineas = self.tip.split("\n")
        w = max(f.size(l)[0] for l in lineas) + 18
        h = len(lineas) * (f.get_linesize() + 2) + 12
        x = min(self.mouse[0] + 14, self.surf.get_width() - w - 6)
        y = min(self.mouse[1] + 16, self.surf.get_height() - h - 6)
        pygame.draw.rect(self.surf, (8, 12, 20), (x, y, w, h), border_radius=6)
        pygame.draw.rect(self.surf, BORDE, (x, y, w, h), 1, border_radius=6)
        for i, l in enumerate(lineas):
            self.texto(l, (x + 9, y + 6 + i * (f.get_linesize() + 2)), 14)

    # ------------------------------------------------------- dibujos de juego
    def _logo(self, club_id, alto):
        """Escudo real (assets/logos/<id>.png, ver tools/descargar_logos.py) escalado a `alto` px; None si no existe."""
        clave = (club_id, alto)
        if clave not in self._logos:
            img = None
            ruta = LOGOS / f"{club_id}.png"
            if ruta.exists():
                try:
                    orig = pygame.image.load(str(ruta)).convert_alpha()
                    w = max(1, round(orig.get_width() * alto / orig.get_height()))
                    img = pygame.transform.smoothscale(orig, (w, alto))
                except pygame.error:
                    img = None
            self._logos[clave] = img
        return self._logos[clave]

    def placa_jugador(self, cx, y, nombre, pos, maxw=84):
        """Nombre y posición de un jugador sobre una placa oscura translúcida: se leen sobre cualquier fondo."""
        f = self.fuente(13, True)
        w = min(maxw, f.size(str(nombre))[0]) + 12
        placa = pygame.Surface((w, 33), pygame.SRCALPHA)
        pygame.draw.rect(placa, (6, 14, 10, 165), placa.get_rect(), border_radius=7)
        self.surf.blit(placa, (cx - w // 2, y - 2))
        self.texto(nombre, (cx, y), 13, (255, 255, 255), True, "tc", maxw=maxw)
        self.texto(pos, (cx, y + 16), 11, (214, 232, 220), anchor="tc")

    def icono_baja(self, cx, cy, motivo, r=10):
        """Por qué un jugador no está disponible: cruz roja = lesión; tarjeta roja = sanción por expulsión.
        Sin fondo blanco: solo la figura roja, con un contorno oscuro fino para que se vea sobre cualquier fondo."""
        rojo, borde = (226, 48, 48), (46, 8, 8)
        if motivo == "sanción":
            rect = pygame.Rect(0, 0, int(r * 1.3), int(r * 1.8))
            rect.center = (cx, cy)
            pygame.draw.rect(self.surf, rojo, rect, border_radius=2)
            pygame.draw.rect(self.surf, borde, rect, 1, border_radius=2)
        else:
            largo = r * 1.9                                           # cruz de brazos gruesos
            g = max(2.0, r * 0.62)
            horiz = pygame.Rect(0, 0, int(largo), int(g))
            vert = pygame.Rect(0, 0, int(g), int(largo))
            horiz.center = vert.center = (cx, cy)
            for rect in (horiz, vert):                                # contorno oscuro por debajo
                pygame.draw.rect(self.surf, borde, rect.inflate(2, 2), border_radius=1)
            for rect in (horiz, vert):
                pygame.draw.rect(self.surf, rojo, rect)

    def placa_jugador_corta(self, cx, y, nombre):
        """Nombre pequeño sobre placa oscura (vista animada del partido)."""
        f = self.fuente(11, True)
        w = min(92, f.size(str(nombre))[0]) + 10
        placa = pygame.Surface((w, 17), pygame.SRCALPHA)
        pygame.draw.rect(placa, (6, 14, 10, 175), placa.get_rect(), border_radius=6)
        self.surf.blit(placa, (cx - w // 2, y))
        self.texto(nombre, (cx, y + 2), 11, (255, 255, 255), True, "tc", maxw=92)

    def logo_liga(self, centro, alto, liga):
        """Logo de la liga sobre una placa clara (los logos oficiales no se leen bien sobre fondo oscuro).
        Devuelve False si no está descargado."""
        slug = {"Premier League": "premier", "La Liga": "laliga", "Bundesliga": "bundesliga", "Serie A": "seriea",
                "Ligue 1": "ligue1", "Championship": "championship", "La Liga 2": "laliga2", "2. Bundesliga": "bundesliga2",
                "Serie B": "serieb", "Ligue 2": "ligue2"}.get(liga)
        logo = self._logo(f"liga_{slug}", alto) if slug else None
        if logo is None:
            return False
        if logo.get_width() > 170:                       # logos muy anchos (Premier League): reducir para que quepan
            logo = self._logo(f"liga_{slug}", int(alto * 170 / logo.get_width()))
        placa = logo.get_rect(center=centro).inflate(22, 18)
        pygame.draw.rect(self.surf, (240, 244, 250), placa, border_radius=12)
        self.surf.blit(logo, logo.get_rect(center=centro))
        return True

    LOGOS_COMPETICION = {"UEFA Champions League": "champions", "FA Cup": "copa_facup", "Copa del Rey": "copa_copadelrey",
                         "DFB-Pokal": "copa_dfbpokal", "Coppa Italia": "copa_coppaitalia",
                         "Coupe de France": "copa_coupedefrance"}

    def logo_competicion(self, centro, alto, nombre, ancho_max=130):
        """Logo de una copa o de la Champions sobre una placa clara. Devuelve False si no está descargado."""
        clave = self.LOGOS_COMPETICION.get(nombre)
        logo = self._logo(clave, alto) if clave else None
        if logo is None:
            return False
        if logo.get_width() > ancho_max:
            logo = self._logo(clave, int(alto * ancho_max / logo.get_width()))
        placa = logo.get_rect(center=centro).inflate(18, 14)
        pygame.draw.rect(self.surf, (240, 244, 250), placa, border_radius=10)
        self.surf.blit(logo, logo.get_rect(center=centro))
        return True

    def insignia(self, centro, radio, club):
        logo = self._logo(club.id, int(radio * 2.2))
        if logo is not None:
            self.surf.blit(logo, logo.get_rect(center=centro))
            return
        pygame.draw.circle(self.surf, club.color2, centro, radio)
        pygame.draw.circle(self.surf, club.color, centro, radio - max(2, radio // 8))
        pal = [w for w in club.nombre.replace(".", "").split() if len(w) > 1 or w.isupper()]
        ini = (pal[0][0] + (pal[1][0] if len(pal) > 1 else pal[0][1:2])).upper() if pal else "?"
        self.texto(ini, centro, int(radio * 0.95), club.color2 if sum(club.color) > 380 else (255, 255, 255),
                   True, "mc")

    def camiseta(self, centro, tam, c1, c2, numero=None, apagada=False, patron="liso"):
        """Camiseta con patrón ("liso", "rayas", "aros" o "mitades") recortado a la silueta."""
        cx, cy = centro
        a = tam / 2
        if apagada:
            c1, c2 = mezclar(c1, (60, 60, 60), .6), mezclar(c2, (60, 60, 60), .6)
        lado = int(tam) + 6
        o = lado / 2                                   # centro de la superficie local
        puntos = [(o - a * .38, o - a), (o + a * .38, o - a), (o + a, o - a * .55), (o + a * .72, o - a * .12),
                  (o + a * .5, o - a * .28), (o + a * .5, o + a), (o - a * .5, o + a),
                  (o - a * .5, o - a * .28), (o - a * .72, o - a * .12), (o - a, o - a * .55)]
        loc = pygame.Surface((lado, lado), pygame.SRCALPHA)
        loc.fill(c1)
        ancho = max(2, round(tam / 7))
        if patron == "rayas":
            for x in range(int(o - a) + ancho, int(o + a) + 1, 2 * ancho):
                pygame.draw.rect(loc, c2, (x, 0, ancho, lado))
        elif patron == "aros":
            for y in range(int(o - a) + ancho, int(o + a) + 1, 2 * ancho):
                pygame.draw.rect(loc, c2, (0, y, lado, ancho))
        elif patron == "mitades":
            pygame.draw.rect(loc, c2, (int(o), 0, lado, lado))
        mascara = pygame.Surface((lado, lado), pygame.SRCALPHA)
        pygame.draw.polygon(mascara, (255, 255, 255, 255), puntos)
        loc.blit(mascara, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)    # recorta a la silueta
        if patron == "liso":                                              # cuello y puños en el color secundario
            pygame.draw.polygon(loc, c2, [(o - a * .38, o - a), (o + a * .38, o - a), (o, o - a * .55)])
            pygame.draw.line(loc, c2, (o + a, o - a * .55), (o + a * .72, o - a * .12), 3)
            pygame.draw.line(loc, c2, (o - a, o - a * .55), (o - a * .72, o - a * .12), 3)
        else:                                                             # cuello neutro: se lee bien sobre las rayas
            pygame.draw.polygon(loc, mezclar(c1, c2, .5), [(o - a * .3, o - a), (o + a * .3, o - a), (o, o - a * .62)])
        pygame.draw.polygon(loc, (15, 20, 30), puntos, 2)
        self.surf.blit(loc, (int(cx - o), int(cy - o)))
        if numero is not None:                                            # dorsal en el pecho, con contorno para leerse sobre rayas
            lum = 0.299 * c1[0] + 0.587 * c1[1] + 0.114 * c1[2]
            relleno, contorno = ((255, 255, 255), (12, 18, 30)) if lum < 140 else ((16, 20, 32), (255, 255, 255))
            tam_n = int(tam * (.40 if numero < 10 else .36))
            pos = (cx, cy + a * .22)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                self.texto(str(numero), (pos[0] + dx, pos[1] + dy), tam_n, contorno, True, "mc")
            self.texto(str(numero), pos, tam_n, relleno, True, "mc")

    def campo(self, rect):
        """Cancha completa vertical con proporciones reglamentarias (68×105 m). Arco propio abajo, rival arriba."""
        r = pygame.Rect(rect)
        n = 14
        for i in range(n):
            col = (36, 128, 60) if i % 2 == 0 else (41, 140, 66)
            pygame.draw.rect(self.surf, col, (r.x, r.y + i * r.h // n, r.w, r.h // n + 1))
        blanco = (190, 226, 200)          # un poco atenuado para que no compita con los nombres
        m = 14
        L =pygame.Rect(r.x + m, r.y + m, r.w - 2 * m, r.h - 2 * m)      # líneas de banda y de fondo
        W, H = L.w, L.h
        pygame.draw.rect(self.surf, blanco, L, 2)
        pygame.draw.line(self.surf, blanco, (L.x, L.centery), (L.right, L.centery), 2)
        rc = int(W * 9.15 / 68)
        pygame.draw.circle(self.surf, blanco, L.center, rc, 2)
        pygame.draw.circle(self.surf, blanco, L.center, 3)
        cx = L.centerx
        pw, ph = int(W * 40.3 / 68), int(H * 16.5 / 105)                  # área grande
        gw, gh = int(W * 18.3 / 68), int(H * 5.5 / 105)                   # área chica
        pm = int(H * 11 / 105)                                            # punto penal
        d = ph - pm
        semi = math.acos(max(-1, min(1, d / rc)))                         # tramo del arco que queda fuera del área
        for arriba in (True, False):
            s = 1 if arriba else -1
            y0 = L.y if arriba else L.bottom                              # línea de fondo
            ytope = y0 + s * ph
            pygame.draw.rect(self.surf, blanco, (cx - pw // 2, y0 if arriba else y0 - ph, pw, ph), 2)
            pygame.draw.rect(self.surf, blanco, (cx - gw // 2, y0 if arriba else y0 - gh, gw, gh), 2)
            pygame.draw.circle(self.surf, blanco, (cx, y0 + s * pm), 3)
            a0 = (math.pi * 1.5 if arriba else math.pi / 2) - semi        # el arco mira hacia el medio campo
            pygame.draw.arc(self.surf, blanco, (cx - rc, y0 + s * pm - rc, 2 * rc, 2 * rc), a0, a0 + 2 * semi, 2)
            pygame.draw.rect(self.surf, (200, 210, 220), (cx - gw // 4, y0 - 5 if arriba else y0, gw // 2, 5), 2)  # arco
        return r

    def pos_campo(self, rect, x, y):
        """x, y en 0..1 (y=0 delantera, y=1 portero) → píxeles. Los once ocupan desde el borde del área rival hasta el arco propio."""
        r = pygame.Rect(rect)
        m = 14
        y = 0.11 + 0.82 * y            # de la zona del área rival hasta el área propia: usa todo el largo del campo
        return (int(r.x + m + (r.w - 2 * m) * x), int(r.y + m + (r.h - 2 * m) * y))
