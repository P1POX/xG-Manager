"""Modelo del juego: jugadores, clubes, formaciones y liga."""
import random
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

GRUPO_POS = {
    "GK": "POR",
    "CB": "DEF", "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "CDM": "MED", "CM": "MED", "CAM": "MED", "LM": "MED", "RM": "MED",
    "LW": "DEL", "RW": "DEL", "ST": "DEL", "CF": "DEL",
}
GRUPOS = ["POR", "DEF", "MED", "DEL"]
NOMBRE_GRUPO = {"POR": "Portero", "DEF": "Defensa", "MED": "Mediocampista", "DEL": "Delantero"}


def _fila(grupo, y, xs):
    return [(grupo, x, y) for x in xs]


def _formacion(defs, meds, dels):
    return ([("POR", 0.5, 0.92)] + _fila("DEF", 0.74, defs) + meds + dels)


FORMACIONES = {
    "4-4-2": _formacion([.14, .38, .62, .86], _fila("MED", .50, [.14, .38, .62, .86]),
                        _fila("DEL", .24, [.38, .62])),
    "4-3-3": _formacion([.14, .38, .62, .86], _fila("MED", .52, [.28, .5, .72]),
                        _fila("DEL", .24, [.18, .5, .82])),
    "3-5-2": _formacion([.25, .5, .75], _fila("MED", .50, [.1, .3, .5, .7, .9]),
                        _fila("DEL", .24, [.38, .62])),
    "4-2-3-1": _formacion([.14, .38, .62, .86],
                          _fila("MED", .56, [.34, .66]) + _fila("MED", .38, [.18, .5, .82]),   # filas a ≥ .18 (≈ 90 px)
                          _fila("DEL", .20, [.5])),
}

# ------------------------------------------------------------------ jugadores


class Jugador:
    __slots__ = ("id", "idx", "nombre", "nombre_largo", "pos", "pos_lista", "grupo", "grupos_nat",
                 "ovr", "pot", "edad", "valor", "valor_pred", "cluster", "rol", "p", "club_id",
                 "nacionalidad", "lesion", "motivo", "rasgos", "_prima", "dorsal")

    def __init__(self, fila, idx):
        self.id = int(fila["player_id"])
        self.idx = idx
        self.nombre = fila["short_name"]
        self.nombre_largo = fila["long_name"]
        self.pos_lista = [p.strip() for p in str(fila["player_positions"]).split(",")]
        self.pos = self.pos_lista[0]
        self.grupo = GRUPO_POS[self.pos]
        self.grupos_nat = {GRUPO_POS[p] for p in self.pos_lista if p in GRUPO_POS}
        self.ovr = int(fila["overall"])
        self.pot = int(fila["potential"])
        self.edad = int(fila["age"])
        self.valor = float(fila["value_eur"])
        self.valor_pred = float(fila["valor_pred"])
        self.cluster = int(fila["cluster_id"])
        self.rol = fila["rol"]
        self.p = {g: float(fila["p_" + g]) for g in GRUPOS}
        self.club_id = int(fila["club_team_id"])
        d = fila.get("club_jersey_number")                 # dorsal en su club (FC 24); puede faltar
        self.dorsal = int(float(d)) if d not in (None, "") and d == d else None
        self.nacionalidad = fila["nationality_name"]
        self.lesion = 0
        self.motivo = "lesión"        # "lesión" o "sanción" (roja)
        if self.grupo == "POR":     # porteros: estirada, saque, manejo, colocación, reflejos, físico
            claves = ("goalkeeping_diving", "goalkeeping_kicking", "goalkeeping_handling",
                      "goalkeeping_positioning", "goalkeeping_reflexes", "physic")
        else:
            claves = ("pace", "shooting", "passing", "dribbling", "defending", "physic")
        self.rasgos = dict(zip(("pace", "shooting", "passing", "dribbling", "defending", "physic"),
                               (int(fila[k]) for k in claves)))
        self._prima = None

    def aptitud(self, grupo):
        """1.0 si juega en su posición natural; si no, lo que el árbol de decisión cree que encaja."""
        if grupo in self.grupos_nat:
            return 1.0
        return min(1.0, self.p[grupo] / 0.6)

    def rendimiento(self, grupo):
        return self.ovr * (0.72 + 0.28 * self.aptitud(grupo))

    def __repr__(self):
        return f"<{self.nombre} {self.pos} {self.ovr}>"


# --------------------------------------------------------------------- clubes


@dataclass
class Club:
    id: int
    nombre: str
    liga: str
    ovr: int
    estadio: str
    entrenador: str
    tactica: dict
    plantel: list = field(default_factory=list)
    formacion: str = "4-3-3"
    once: list = field(default_factory=list)
    presupuesto: float = 0.0
    pj: int = 0
    g: int = 0
    e: int = 0
    p: int = 0
    gf: int = 0
    gc: int = 0
    color: tuple = (200, 200, 200)
    color2: tuple = (30, 30, 30)
    patron: str = "liso"

    @property
    def pts(self):
        return self.g * 3 + self.e

    @property
    def dg(self):
        return self.gf - self.gc

    def valor_plantel(self):
        return sum(j.valor for j in self.plantel)

    def xi_con_grupo(self):
        slots = FORMACIONES[self.formacion]
        return [(slots[i][0], j) for i, j in enumerate(self.once) if j is not None]

    def reset_temporada(self):
        self.pj = self.g = self.e = self.p = self.gf = self.gc = 0


def mejor_once(plantel, formacion):
    """Asignación óptima (algoritmo húngaro) de jugadores disponibles a las 11 posiciones."""
    slots = FORMACIONES[formacion]
    disp = [j for j in plantel if j.lesion == 0]
    costo = -np.array([[j.rendimiento(s[0]) for j in disp] for s in slots])
    filas, cols = linear_sum_assignment(costo)
    once = [None] * 11
    for f, c in zip(filas, cols):
        once[f] = disp[c]
    return once, float(-costo[filas, cols].sum())


def autoalinear(club, formacion=None):
    """Elige formación (si no se indica) y once titular."""
    if formacion is None:
        mejor = max(((mejor_once(club.plantel, f), f) for f in FORMACIONES),
                    key=lambda t: t[0][1])
        (club.once, _), club.formacion = mejor[0], mejor[1]
    else:
        club.formacion = formacion
        club.once, _ = mejor_once(club.plantel, formacion)


def reparar_once(club):
    """Sustituye titulares lesionados por el mejor suplente. Devuelve [(sale, entra)]."""
    cambios = []
    slots = FORMACIONES[club.formacion]
    for i, j in enumerate(club.once):
        if j is None or j.lesion > 0 or j not in club.plantel:
            usados = {x.id for x in club.once if x is not None and x.lesion == 0 and x in club.plantel}
            cand = [x for x in club.plantel if x.lesion == 0 and x.id not in usados]
            if not cand:
                continue
            nuevo = max(cand, key=lambda x: x.rendimiento(slots[i][0]))
            cambios.append((j, nuevo))
            club.once[i] = nuevo
    return cambios


# ----------------------------------------------------------------------- liga


class Liga:
    def __init__(self, nombre, clubes, rng):
        self.nombre = nombre
        self.clubes = clubes                      # list[Club]
        self.rng = rng
        self.jornada = 0
        self.calendario = self._calendario()
        self.historial = []                       # resultados jugados

    def _calendario(self):
        ids = [c.id for c in self.clubes]
        if len(ids) % 2:
            ids.append(None)
        n = len(ids)
        rondas = []
        arr = ids[:]
        for r in range(n - 1):
            par = []
            for i in range(n // 2):
                a, b = arr[i], arr[n - 1 - i]
                if a is not None and b is not None:
                    par.append((a, b) if (r + i) % 2 == 0 else (b, a))
            rondas.append(par)
            arr = [arr[0]] + [arr[-1]] + arr[1:-1]
        vuelta = [[(b, a) for a, b in r] for r in rondas]
        todo = rondas + vuelta
        self.rng.shuffle(todo)
        return todo

    @property
    def total_jornadas(self):
        return len(self.calendario)

    @property
    def terminada(self):
        return self.jornada >= self.total_jornadas

    def tabla(self):
        return sorted(self.clubes, key=lambda c: (-c.pts, -c.dg, -c.gf, c.nombre))

    def posicion(self, club):
        return self.tabla().index(club) + 1

    def rival(self, club):
        if self.terminada:
            return None, None
        for a, b in self.calendario[self.jornada]:
            if a == club.id:
                return b, True
            if b == club.id:
                return a, False
        return None, None
