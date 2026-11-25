"""Mini-biblioteca de interfaz en modo inmediato para Pygame (botones, paneles, campo, camisetas)."""
from pathlib import Path

import pygame

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "assets" / "fonts"

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
        self.mouse = (0, 0)
        self.click = None
        self.click_der = None
        self.rueda = 0
        self.tipeo = []
        self.teclas = []
        self.foco = None
        self.tip = None

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
    def insignia(self, centro, radio, club):
        pygame.draw.circle(self.surf, club.color2, centro, radio)
        pygame.draw.circle(self.surf, club.color, centro, radio - max(2, radio // 8))
        pal = [w for w in club.nombre.replace(".", "").split() if len(w) > 1 or w.isupper()]
        ini = (pal[0][0] + (pal[1][0] if len(pal) > 1 else pal[0][1:2])).upper() if pal else "?"
        self.texto(ini, centro, int(radio * 0.95), club.color2 if sum(club.color) > 380 else (255, 255, 255),
                   True, "mc")

    def camiseta(self, centro, tam, c1, c2, numero=None, apagada=False):
        cx, cy = centro
        a = tam / 2
        if apagada:
            c1, c2 = mezclar(c1, (60, 60, 60), .6), mezclar(c2, (60, 60, 60), .6)
        puntos = [(cx - a * .38, cy - a), (cx + a * .38, cy - a), (cx + a, cy - a * .55), (cx + a * .72, cy - a * .12),
                  (cx + a * .5, cy - a * .28), (cx + a * .5, cy + a), (cx - a * .5, cy + a),
                  (cx - a * .5, cy - a * .28), (cx - a * .72, cy - a * .12), (cx - a, cy - a * .55)]
        pygame.draw.polygon(self.surf, c1, puntos)
        pygame.draw.polygon(self.surf, (15, 20, 30), puntos, 2)
        pygame.draw.polygon(self.surf, c2, [(cx - a * .38, cy - a), (cx + a * .38, cy - a),
                                            (cx, cy - a * .55)])
        pygame.draw.line(self.surf, c2, (cx + a, cy - a * .55), (cx + a * .72, cy - a * .12), 3)
        pygame.draw.line(self.surf, c2, (cx - a, cy - a * .55), (cx - a * .72, cy - a * .12), 3)
        if numero is not None:
            self.texto(str(numero), (cx, cy + a * .15), int(tam * .42), c2, True, "mc")

    def campo(self, rect):
        """Media cancha vertical (arco propio abajo)."""
        r = pygame.Rect(rect)
        n = 10
        for i in range(n):
            col = (36, 128, 60) if i % 2 == 0 else (41, 140, 66)
            pygame.draw.rect(self.surf, col, (r.x, r.y + i * r.h // n, r.w, r.h // n + 1))
        blanco = (225, 240, 228)
        m = 14
        pygame.draw.rect(self.surf, blanco, (r.x + m, r.y + m, r.w - 2 * m, r.h - 2 * m), 2)
        cx = r.centerx
        pygame.draw.circle(self.surf, blanco, (cx, r.y + m), int(r.w * .13), 2)
        pw, ph = int(r.w * .56), int(r.h * .16)
        pygame.draw.rect(self.surf, blanco, (cx - pw // 2, r.bottom - m - ph, pw, ph), 2)
        gw, gh = int(r.w * .26), int(r.h * .06)
        pygame.draw.rect(self.surf, blanco, (cx - gw // 2, r.bottom - m - gh, gw, gh), 2)
        pygame.draw.rect(self.surf, (200, 210, 220), (cx - gw // 4, r.bottom - m, gw // 2, 5), 2)
        pygame.draw.arc(self.surf, blanco, (cx - int(r.w * .12), r.bottom - m - ph - int(r.w * .12), int(r.w * .24),
                                            int(r.w * .24)), 0.55, 2.6, 2)
        return r

    def pos_campo(self, rect, x, y):
        r = pygame.Rect(rect)
        m = 14
        return (int(r.x + m + (r.w - 2 * m) * x), int(r.y + m + (r.h - 2 * m) * (y)))
