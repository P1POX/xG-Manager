"""Carga del 'mundo' del juego a partir de los CSV procesados."""
import colorsys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from . import camisetas, evolucion
from . import tactica as tac
from .modelo import Club, Jugador, autoalinear, reparar_once

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

MIN_PLANTEL = 18


def colores_club(nombre):
    h = zlib.crc32(nombre.encode()) % 360 / 360
    s = 0.55 + (zlib.crc32(nombre[::-1].encode()) % 30) / 100
    c1 = tuple(int(255 * v) for v in colorsys.hsv_to_rgb(h, s, 0.85))
    c2 = (245, 245, 245) if (zlib.crc32(nombre.encode()) >> 3) % 2 else (25, 28, 40)
    return c1, c2


class Mundo:
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.retirados = set()                 # ids de jugadores retirados en temporadas anteriores (modo carrera)
        self._pred = None                      # caché de la predicción de evolución
        jug = pd.read_csv(DATA / "jugadores_ml.csv")
        self.vectores = np.load(DATA / "vectores.npy")
        self.jugadores = {}
        for i, fila in enumerate(jug.to_dict("records")):
            j = Jugador(fila, i)
            self.jugadores[j.id] = j
        self.markup = self.rng.lognormal(mean=0.10, sigma=0.22, size=len(jug))

        eq = pd.read_csv(DATA / "equipos.csv")
        ent = pd.read_csv(DATA / "entrenadores.csv").set_index("coach_id")
        self.clubes = {}
        self.ligas = {}
        for r in eq.to_dict("records"):
            k = camisetas.kit(r["team_name"])
            c1, c2 = k[:2] if k else colores_club(r["team_name"])
            nom_ent = ent.loc[r["coach_id"], "long_name"] if r["coach_id"] in ent.index else "Sin entrenador"
            club = Club(id=int(r["team_id"]), nombre=r["team_name"], liga=r["liga"], ovr=int(r["overall"]),
                        estadio=r["home_stadium"] if isinstance(r["home_stadium"], str) else "Estadio municipal",
                        entrenador=nom_ent, tactica=tac.tactica_desde_fila(r), color=c1, color2=c2,
                        patron=k[2] if k else "liso")
            self.clubes[club.id] = club
            self.ligas.setdefault(r["liga"], []).append(club.id)
        self.externos = []                     # jugadores sin club simulado (otras ligas o sin equipo)
        for j in self.jugadores.values():
            club = self.clubes.get(j.club_id)
            if club:
                club.plantel.append(j)
            else:
                self.externos.append(j)
        for club in self.clubes.values():
            autoalinear(club)
            club.presupuesto = round(club.valor_plantel() * 0.10, -5)

    # ---------------------------------------------------- evolución (modo carrera)
    def prediccion(self, j):
        """(cambio esperado de OVR, desviación típica, prob. de mejorar, prob. de decaer) para el año siguiente."""
        if not evolucion.disponible():
            return (0.0, 0.0, 0.0, 0.0)
        if self._pred is None:
            activos = [x for x in self.jugadores.values() if x.id not in self.retirados]
            self._pred = {x.id: p for x, p in zip(activos, evolucion.predecir(activos))}
        return self._pred.get(j.id) or evolucion.predecir([j])[0]

    def invalidar_prediccion(self):
        self._pred = None

    # -------------------------------------------------------------- mercado
    def precio(self, jugador):
        """Precio que pide el club vendedor: valor real x un margen aleatorio (hay gangas y abusos)."""
        extra = 1.0
        club = self.clubes.get(jugador.club_id)
        if club and jugador in club.once:
            extra = 1.25
        return max(100_000.0, round(jugador.valor * self.markup[jugador.idx] * extra, -5))

    def reserva(self, jugador):
        """Fracción del precio pedido por debajo de la cual el club casi no negocia (su 'precio mínimo').

        Se apoya en la regresión del valor justo: si piden mucho más de lo que vale el jugador (valor justo / precio bajo)
        aceptan descuentos grandes; si ya piden poco, apenas rebajan. Los titulares se venden más caros y los clubes
        se desprenden con más facilidad de los veteranos y de los jugadores sin equipo."""
        pedido = self.precio(jugador)
        r = float(np.clip(1.05 * jugador.valor_pred / pedido, 0.80, 0.97))
        club = self.clubes.get(jugador.club_id)
        if club is None:
            r -= 0.04
        elif jugador in club.once:
            r += 0.03
        if jugador.edad >= 32:
            r -= 0.02
        return float(np.clip(r, 0.75, 0.98))

    def prob_oferta(self, jugador, oferta):
        """Probabilidad de que acepten una oferta (1 si se paga lo que piden; 50 % justo en la reserva del club)."""
        pedido = self.precio(jugador)
        if oferta >= pedido:
            return 1.0
        z = (oferta / pedido - self.reserva(jugador)) / 0.035
        return float(1 / (1 + np.exp(-z)))

    def ofrecer(self, comprador, jugador, oferta, rng):
        """Ofrece `oferta` (< precio pedido). Devuelve (ok, mensaje, aceptada)."""
        pedido = self.precio(jugador)
        ok, msg = self.puede_comprar(comprador, jugador, min(oferta, pedido))
        if not ok:
            return False, msg, False
        if oferta >= pedido or rng.random() < self.prob_oferta(jugador, oferta):
            ok, msg = self.comprar(comprador, jugador, min(oferta, pedido))
            return ok, msg, ok
        cerca = oferta / pedido >= self.reserva(jugador) - 0.04
        return True, ("Rechazaron tu oferta, pero estuvo cerca." if cerca
                      else "Rechazaron tu oferta: quedó lejos de lo que piden."), False

    def puede_comprar(self, comprador, jugador, precio=None):
        if jugador in comprador.plantel:
            return False, "Ya está en tu plantel."
        precio = self.precio(jugador) if precio is None else precio
        if precio > comprador.presupuesto:
            return False, "Presupuesto insuficiente."
        vend = self.clubes.get(jugador.club_id)
        if vend and len(vend.plantel) <= MIN_PLANTEL:
            return False, f"{vend.nombre} no quiere quedarse sin plantel."
        if vend and sum(1 for x in vend.plantel if x.grupo == jugador.grupo) <= (2 if jugador.grupo == "POR" else 4):
            return False, f"{vend.nombre} se queda sin {jugador.grupo}s."
        if len(comprador.plantel) >= 34:
            return False, "Plantel lleno (máx. 34)."
        return True, ""

    def comprar(self, comprador, jugador, precio=None):
        precio = self.precio(jugador) if precio is None else precio
        ok, msg = self.puede_comprar(comprador, jugador, precio)
        if not ok:
            return False, msg
        vend = self.clubes.get(jugador.club_id)
        if vend:
            vend.plantel.remove(jugador)
            vend.presupuesto += precio
            vend.once = [None if x is jugador else x for x in vend.once]
            reparar_once(vend)
        else:
            self.externos.remove(jugador)
        jugador.club_id = comprador.id
        comprador.plantel.append(jugador)
        comprador.presupuesto -= precio
        return True, f"Fichaste a {jugador.nombre} por {precio / 1e6:.1f} M€."

    def puede_vender(self, club, jugador):
        if len(club.plantel) <= MIN_PLANTEL:
            return False, f"Necesitas al menos {MIN_PLANTEL} jugadores."
        if jugador.grupo == "POR" and sum(1 for x in club.plantel if x.grupo == "POR") <= 2:
            return False, "Necesitas al menos 2 porteros."
        return True, ""

    def vender(self, club, jugador):
        ok, msg = self.puede_vender(club, jugador)
        if not ok:
            return False, msg
        ingreso = round(jugador.valor * 0.90, -5)
        club.plantel.remove(jugador)
        club.once = [None if x is jugador else x for x in club.once]
        club.presupuesto += ingreso
        jugador.club_id = -1
        self.externos.append(jugador)
        reparar_once(club)
        return True, f"Vendiste a {jugador.nombre} por {ingreso / 1e6:.1f} M€."

    def candidatos_mercado(self, club):
        """Todos los jugadores del mundo que no están en el club (externos + otros clubes)."""
        res = list(self.externos)
        for c in self.clubes.values():
            if c is not club:
                res.extend(c.plantel)
        return res

    def similares(self, jugador, pool, n=5):
        """Jugadores más parecidos (distancia en el espacio de atributos que usa K-means)."""
        pool = [p for p in pool if p.id != jugador.id and p.grupo == jugador.grupo]
        if not pool:
            return []
        idx = np.array([p.idx for p in pool])
        d = np.linalg.norm(self.vectores[idx] - self.vectores[jugador.idx], axis=1)
        orden = np.argsort(d)[:n]
        return [(pool[i], float(d[i])) for i in orden]
