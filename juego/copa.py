"""Copa nacional: eliminatoria de 32 clubes a partido único (FA Cup, Copa del Rey, DFB-Pokal, Coppa Italia, Coupe de France).

Participan los clubes de la primera división del usuario y los que hacen falta de su segunda división (al azar) hasta
completar 32. Se juega en cinco rondas (dieciseisavos, octavos, cuartos, semifinales y final), cada una justo antes de
una jornada de liga. El sorteo de cada ronda es puro. Si hay empate a los 90 minutos hay prórroga (30 minutos más) y,
si sigue, tanda de penales. La final se juega en campo neutral (sin ventaja de local).

Los partidos entre clubes de la IA se simulan con el mismo motor que la liga; el partido del usuario se juega en vivo.
"""
import numpy as np

from . import eventos as ev
from . import simulacion as sim

NOMBRES = {"Premier League": "FA Cup", "La Liga": "Copa del Rey", "Bundesliga": "DFB-Pokal", "Serie A": "Coppa Italia",
           "Ligue 1": "Coupe de France"}
RONDAS = ["Dieciseisavos de final", "Octavos de final", "Cuartos de final", "Semifinales", "Final"]
CORTAS = ["Dieciseisavos", "Octavos", "Cuartos", "Semifinales", "Final"]
JORNADA_RONDA = [5, 11, 19, 27, 33]       # la ronda se juega justo antes de esta jornada de liga (índice desde 0)
PREMIOS = [1.0e6, 2.0e6, 4.0e6, 7.0e6, 12.0e6]      # por ganar la ronda
PREMIO_CAMPEON = 8.0e6
N_PARTICIPANTES = 32


# ====================================================================== tanda de penales
def ordenar_tiradores(xi):
    """Orden de los lanzadores: los de campo de mejor tiro primero y el portero al final."""
    campo = sorted([j for g, j in xi if g != "POR"], key=lambda j: -ev.tiro_de(j, "penal"))
    porteros = [j for g, j in xi if g == "POR"]
    return campo + porteros


class Tanda:
    """Tanda de penales: 5 lanzamientos por equipo (con final anticipado) y muerte súbita después."""

    def __init__(self, tiradores, ovr_portero, primero="a"):
        self.tiradores = tiradores                     # {"a": [Jugador, ...], "b": [...]}
        self.gk = ovr_portero                          # {"a": ovr del portero de a, "b": ...}
        self.primero = primero
        self.goles = {"a": 0, "b": 0}
        self.tiros = {"a": 0, "b": 0}
        self.registro = []                             # (lado, nombre del lanzador, convertido)

    def lado_turno(self):
        if self.tiros["a"] == self.tiros["b"]:
            return self.primero
        return "b" if self.primero == "a" else "a"

    def proximo(self):
        lado = self.lado_turno()
        lst = self.tiradores[lado]
        return lado, lst[self.tiros[lado] % len(lst)]

    def prob(self, lado, jugador):
        rival = "b" if lado == "a" else "a"
        return ev.prob_conv("penal", ev.tiro_de(jugador, "penal"), self.gk[rival])

    def registrar(self, convertido):
        lado, j = self.proximo()
        self.tiros[lado] += 1
        self.goles[lado] += int(bool(convertido))
        self.registro.append((lado, j.nombre, bool(convertido)))

    def terminada(self):
        ga, gb, ka, kb = self.goles["a"], self.goles["b"], self.tiros["a"], self.tiros["b"]
        if ka <= 5 and kb <= 5:                        # primeros cinco: se acaba si el otro ya no puede alcanzarlo
            if ga > gb + (5 - kb) or gb > ga + (5 - ka):
                return True
        return ka >= 5 and ka == kb and ga != gb       # muerte súbita: decide la ronda completa

    def ganador(self):
        return "a" if self.goles["a"] > self.goles["b"] else "b"

    def simular_resto(self, rng):
        while not self.terminada():
            lado, j = self.proximo()
            self.registrar(rng.random() < self.prob(lado, j))


def nueva_tanda(est, primero="a"):
    """Tanda con los once que terminaron el partido (los expulsados no lanzan)."""
    return Tanda({l: ordenar_tiradores(est["xi"][l]) for l in "ab"},
                 {l: ev.portero_de(est["xi"][l])[1] for l in "ab"}, primero)


# ====================================================================== partidos de la IA
def simular_partido_ia(H, V, rng, asist, neutral=False):
    """Eliminatoria entre dos clubes de la IA. Devuelve un dict con goles, prórroga, penales y ganador (id)."""
    fa, fb = sim.fuerzas(H.xi_con_grupo()), sim.fuerzas(V.xi_con_grupo())
    la, lb = sim.goles_esperados(fa, fb, H.tactica, V.tactica, True, asist.bono_tactico(H.tactica),
                                 asist.bono_tactico(V.tactica))
    if neutral:                                        # campo neutral: se quita la ventaja de local
        la, lb = la / sim.VENTAJA_LOCAL, lb / 0.92
    gh, gv, _, est = ev.simular_ia(H, V, la, lb, rng)
    prorroga, pen = False, None
    if gh == gv:
        prorroga = True
        gh += int(rng.poisson(la / 3))                 # 30 minutos más
        gv += int(rng.poisson(lb / 3))
        if gh == gv:
            t = nueva_tanda(est, "a" if rng.random() < 0.5 else "b")
            t.simular_resto(rng)
            pen = (t.goles["a"], t.goles["b"])
            ganador = H.id if t.ganador() == "a" else V.id
            return {"h": H.id, "v": V.id, "gh": gh, "gv": gv, "prorroga": True, "pen": pen, "ganador": ganador}
    return {"h": H.id, "v": V.id, "gh": gh, "gv": gv, "prorroga": prorroga, "pen": pen,
            "ganador": H.id if gh > gv else V.id}


# ====================================================================== la copa
class Copa:
    def __init__(self, nombre, liga_madre, participantes, temporada):
        self.nombre = nombre
        self.liga_madre = liga_madre
        self.temporada = temporada
        self.inscritos = list(participantes)           # todos los clubes que empezaron la copa
        self.vivos = list(participantes)               # ids que siguen en competición
        self.ronda = 0                                 # ronda que toca jugar (5 = terminada)
        self.pares = []                                # emparejamientos de la ronda actual [(local, visitante)]
        self.historial = [[] for _ in RONDAS]          # resultados de cada ronda
        self.campeon = None

    @classmethod
    def crear(cls, mundo, liga_nombre, rng, temporada, forzar=None):
        """`forzar`: id de un club que debe jugar la copa aunque sea de segunda (el club del usuario descendido)."""
        propios = list(mundo.ligas[liga_nombre])
        resto = list(mundo.segunda.get(liga_nombre, []))
        faltan = max(0, N_PARTICIPANTES - len(propios))
        extra = [int(x) for x in rng.choice(resto, min(faltan, len(resto)), replace=False)] if resto else []
        if forzar is not None and forzar not in propios and forzar not in extra and extra:
            extra[0] = forzar
        return cls(NOMBRES.get(liga_nombre, "Copa"), liga_nombre, propios + extra, temporada)

    # ---------------------------------------------------------------- estado
    @property
    def terminada(self):
        return self.ronda >= len(RONDAS)

    @property
    def nombre_ronda(self):
        return RONDAS[min(self.ronda, len(RONDAS) - 1)]

    @property
    def neutral(self):
        return self.ronda == len(RONDAS) - 1

    # interfaz común con la Champions (la app trata ambas competiciones igual)
    @property
    def corto(self):
        return self.nombre

    def etiqueta(self, r):
        return RONDAS[r]

    def corta(self, r):
        return CORTAS[r]

    def jornada_de(self, r):
        return JORNADA_RONDA[r]

    def decide(self, h=None, v=None):
        return True                                    # eliminatoria a partido único: siempre hay ganador

    def previo(self, h, v):
        return 0, 0

    def premio_tras(self, club_id, ronda, resultado=None):
        """Dinero que cobra `club_id` tras jugar la ronda (llamar tras cerrar_ronda). Devuelve (monto, texto)."""
        if self.campeon == club_id:
            return PREMIOS[ronda] + PREMIO_CAMPEON, "ronda y título"
        if club_id in self.vivos:
            return PREMIOS[ronda], "pase de ronda"
        return 0.0, ""

    def vence_antes_de(self):
        """Jornada de liga antes de la cual hay que jugar la ronda actual (None si la copa terminó)."""
        return None if self.terminada else JORNADA_RONDA[self.ronda]

    def toca(self, jornada):
        """¿Hay que jugar una ronda de copa antes de la jornada de liga `jornada`?"""
        return (not self.terminada) and jornada >= JORNADA_RONDA[self.ronda]

    def partido_de(self, club_id):
        """(local, visitante) de la ronda actual en el que juega `club_id`, o None."""
        for h, v in self.pendientes():
            if club_id in (h, v):
                return h, v
        return None

    def resultado_de(self, h, v):
        return next((r for r in self.historial[min(self.ronda, len(RONDAS) - 1)] if (r["h"], r["v"]) == (h, v)), None)

    # ---------------------------------------------------------------- sorteo y rondas
    def sortear(self, rng):
        """Sortea la ronda actual entre los clubes que siguen vivos (el primero de cada pareja es el local)."""
        orden = [self.vivos[i] for i in rng.permutation(len(self.vivos))]
        self.pares = [(orden[i], orden[i + 1]) for i in range(0, len(orden) - 1, 2)]
        return self.pares

    def registrar(self, resultado):
        self.historial[self.ronda].append(resultado)

    def pendientes(self):
        hechos = {(r["h"], r["v"]) for r in self.historial[self.ronda]}
        return [(h, v) for h, v in self.pares if (h, v) not in hechos]

    def jugar_ronda_ia(self, mundo, rng, asist, excluir=None):
        """Simula los partidos pendientes de la ronda (salvo el de `excluir`, que se juega en vivo)."""
        for h, v in self.pendientes():
            if excluir in (h, v) and excluir is not None:
                continue
            self.registrar(simular_partido_ia(mundo.clubes[h], mundo.clubes[v], rng, asist, self.neutral))

    def cerrar_ronda(self):
        """Pasa a la siguiente ronda con los ganadores (requiere que todos los partidos estén jugados)."""
        assert not self.pendientes(), "faltan partidos por jugar"
        self.vivos = [r["ganador"] for r in self.historial[self.ronda]]
        self.pares = []
        self.ronda += 1
        if self.terminada:
            self.campeon = self.vivos[0]

    # ---------------------------------------------------------------- resumen para el usuario
    def camino(self, club_id):
        """Partidos jugados por `club_id`: [(ronda, rival_id, goles_propios, goles_rival, prórroga, penales_propios,
        penales_rival, ganó)]."""
        res = []
        for r, partidos in enumerate(self.historial):
            for p in partidos:
                if club_id in (p["h"], p["v"]):
                    local = p["h"] == club_id
                    gp, gr = (p["gh"], p["gv"]) if local else (p["gv"], p["gh"])
                    pp, pr = (None, None)
                    if p["pen"]:
                        pp, pr = (p["pen"][0], p["pen"][1]) if local else (p["pen"][1], p["pen"][0])
                    res.append((r, p["v"] if local else p["h"], gp, gr, p["prorroga"], pp, pr, p["ganador"] == club_id))
        return res

    def estado(self, club_id):
        """'campeon' | ('eliminado', ronda) | ('vivo', ronda) | None si no participa."""
        if club_id not in self.participantes():
            return None
        if self.campeon == club_id:
            return "campeon"
        if club_id in self.vivos:
            return ("vivo", self.ronda)
        jugados = self.camino(club_id)
        return ("eliminado", jugados[-1][0] if jugados else 0)

    def participantes(self):
        return set(self.inscritos)

    def texto_estado(self, club_id):
        e = self.estado(club_id)
        if e is None:
            return "No participa"
        if e == "campeon":
            return "¡Campeón!"
        if e[0] == "vivo":
            return f"En competición: {CORTAS[min(e[1], 4)]}"
        return f"Eliminado en {CORTAS[e[1]].lower()}"

    # ---------------------------------------------------------------- guardado
    def a_dict(self):
        return {"nombre": self.nombre, "liga_madre": self.liga_madre, "temporada": self.temporada,
                "inscritos": self.inscritos, "vivos": self.vivos, "ronda": self.ronda, "pares": [list(p) for p in self.pares],
                "historial": [[dict(r, pen=list(r["pen"]) if r["pen"] else None) for r in ronda] for ronda in self.historial],
                "campeon": self.campeon}

    @classmethod
    def de_dict(cls, d):
        c = cls(d["nombre"], d["liga_madre"], d["inscritos"], d["temporada"])
        c.vivos = list(d["vivos"])
        c.ronda = d["ronda"]
        c.pares = [tuple(p) for p in d["pares"]]
        c.historial = [[dict(r, pen=tuple(r["pen"]) if r["pen"] else None) for r in ronda] for ronda in d["historial"]]
        c.campeon = d["campeon"]
        return c
