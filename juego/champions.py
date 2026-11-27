"""UEFA Champions League: 32 clubes, fase de grupos y eliminatorias (octavos, cuartos y semifinales a doble partido, final única).

Clasifican los 6 primeros de cada una de las 5 ligas (30 clubes) y los 2 mejores del resto por nivel. En la primera
temporada el orden de tu liga es el del nivel (OVR); después, el de la clasificación final de la temporada anterior.

* Fase de grupos: 8 grupos de 4 (bombos por nivel, sin dos clubes de la misma liga si se puede), ida y vuelta: 6 jornadas.
  Pasan los dos primeros (puntos, diferencia de goles, goles a favor).
* Octavos: los primeros de grupo contra los segundos de otro grupo. Cuartos y semifinales: sorteo puro. Todo a doble partido.
* Si el global empata tras el partido de vuelta: prórroga (30 minutos) y tanda de penales.
* La final es a partido único en campo neutral.

Cada jornada de Champions se juega justo antes de una jornada de liga (JORNADA_MD), entre semana. Los partidos entre clubes de
la IA se simulan con el mismo motor que la liga; el del usuario se juega en vivo.
"""
import numpy as np

from . import copa as CP
from . import eventos as ev
from . import simulacion as sim

NOMBRE = "UEFA Champions League"
N_CLUBES = 32
PLAZAS_POR_LIGA = 6
#          grupos                       octavos     cuartos     semis       final
JORNADA_MD = [2, 4, 7, 9, 13, 15, 21, 23, 25, 29, 30, 31, 32]        # se juega antes de esta jornada de liga (0-based)
FASES = ["Fase de grupos"] * 6 + ["Octavos de final"] * 2 + ["Cuartos de final"] * 2 + ["Semifinales"] * 2 + ["Final"]
FASES_CORTAS = ["Grupos"] * 6 + ["Octavos"] * 2 + ["Cuartos"] * 2 + ["Semis"] * 2 + ["Final"]
N_MD = len(JORNADA_MD)
MD_VUELTA = (7, 9, 11)                       # partidos de vuelta
MD_FINAL = 12
PREMIO_PARTICIPAR = 8.0e6
PREMIO_VICTORIA, PREMIO_EMPATE = 2.0e6, 0.7e6
PREMIO_PASE = {5: 6.0e6, 7: 8.0e6, 9: 10.0e6, 11: 14.0e6}     # por pasar de fase (tras la jornada md)
PREMIO_CAMPEON = 20.0e6
LETRAS = "ABCDEFGH"
# calendario de un grupo de 4 (posiciones 0-3 del grupo): (local, visitante) de las 3 primeras jornadas; las otras 3 son la vuelta
IDA = [[(0, 1), (2, 3)], [(3, 0), (1, 2)], [(0, 2), (3, 1)]]


def fase_de(md):
    """Fase de la jornada md: 0 grupos, 1 octavos, 2 cuartos, 3 semifinales, 4 final."""
    return 0 if md < 6 else 4 if md == MD_FINAL else (md - 6) // 2 + 1


def etiqueta_md(md):
    """Texto largo de una jornada de Champions ('Fase de grupos · jornada 3', 'Octavos de final · ida'…)."""
    if md < 6:
        return f"Fase de grupos · jornada {md + 1}"
    if md == MD_FINAL:
        return "Final"
    return f"{FASES[md]} · {'vuelta' if md in MD_VUELTA else 'ida'}"


def corta_md(md):
    if md < 6:
        return f"Grupos J{md + 1}"
    if md == MD_FINAL:
        return "Final"
    return f"{FASES_CORTAS[md]} {'vuelta' if md in MD_VUELTA else 'ida'}"


def simular_partido_ia(H, V, rng, asist, neutral=False, decide=False, previo=(0, 0)):
    """Partido entre dos clubes de la IA. Si `decide`, el global (con el partido de ida) debe tener ganador: prórroga y penales."""
    fa, fb = sim.fuerzas(H.xi_con_grupo()), sim.fuerzas(V.xi_con_grupo())
    la, lb = sim.goles_esperados(fa, fb, H.tactica, V.tactica, True, asist.bono_tactico(H.tactica),
                                 asist.bono_tactico(V.tactica))
    if neutral:
        la, lb = la / sim.VENTAJA_LOCAL, lb / 0.92
    gh, gv, _, est = ev.simular_ia(H, V, la, lb, rng)
    res = {"h": H.id, "v": V.id, "gh": gh, "gv": gv, "prorroga": False, "pen": None, "ganador": None}
    if not decide:
        return res
    if gh + previo[0] == gv + previo[1]:
        res["prorroga"] = True
        gh += int(rng.poisson(la / 3))
        gv += int(rng.poisson(lb / 3))
        res["gh"], res["gv"] = gh, gv
        if gh + previo[0] == gv + previo[1]:
            t = CP.nueva_tanda(est, "a" if rng.random() < 0.5 else "b")
            t.simular_resto(rng)
            res["pen"] = (t.goles["a"], t.goles["b"])
            res["ganador"] = H.id if t.ganador() == "a" else V.id
            return res
    res["ganador"] = H.id if gh + previo[0] > gv + previo[1] else V.id
    return res


class Champions:
    nombre = NOMBRE
    corto = "Champions"

    def __init__(self, inscritos, temporada):
        self.temporada = temporada
        self.inscritos = list(inscritos)
        self.vivos = list(inscritos)             # clubes que siguen en competición (en grupos, todos)
        self.grupos = []                         # 8 listas de 4 ids (se sortean antes de la primera jornada)
        self.llaves = []                         # emparejamientos de la fase de eliminatorias: (local en la ida, visitante)
        self.ronda = 0                           # jornada que toca jugar (13 = terminada); se llama igual que en Copa
        self.pares = []                          # (local, visitante) de la jornada actual
        self.historial = [[] for _ in range(N_MD)]
        self.campeon = None

    # ---------------------------------------------------------------- creación
    @classmethod
    def crear(cls, mundo, liga_usuario, temporada, ordenes=None):
        """Clasificados: los 6 primeros de cada liga según su clasificación final anterior (`ordenes`: {liga: [ids]}; una
        lista se entiende como la de la liga del usuario) y, si no hay, por nivel; más los mejores del resto."""
        if isinstance(ordenes, list):
            ordenes = {liga_usuario: ordenes}
        ordenes = ordenes or {}
        ins, resto = [], []
        for liga, ids in mundo.ligas.items():
            if ordenes.get(liga):
                orden = [i for i in ordenes[liga] if i in ids]
                orden += sorted((i for i in ids if i not in orden), key=lambda i: -mundo.clubes[i].ovr)
            else:
                orden = sorted(ids, key=lambda i: -mundo.clubes[i].ovr)
            ins += orden[:PLAZAS_POR_LIGA]
            resto += orden[PLAZAS_POR_LIGA:]
        resto.sort(key=lambda i: -mundo.clubes[i].ovr)
        ins += resto[:max(0, N_CLUBES - len(ins))]
        c = cls(ins[:N_CLUBES], temporada)
        c.preparar(mundo)
        return c

    # ---------------------------------------------------------------- estado
    @property
    def terminada(self):
        return self.ronda >= N_MD

    @property
    def neutral(self):
        return self.ronda == MD_FINAL

    def participantes(self):
        return set(self.inscritos)

    def toca(self, jornada):
        return (not self.terminada) and jornada >= JORNADA_MD[self.ronda]

    def jornada_de(self, md):
        return JORNADA_MD[md]

    def etiqueta(self, md):
        return etiqueta_md(md)

    def corta(self, md):
        return corta_md(md)

    def decide(self, h=None, v=None):
        """¿La jornada actual tiene que dar un ganador? (vuelta de eliminatoria o final)"""
        return self.ronda in MD_VUELTA or self.ronda == MD_FINAL

    def previo(self, h, v):
        """Goles de la ida para (local, visitante) del partido actual (0, 0 si no es una vuelta)."""
        if self.ronda in MD_VUELTA:
            ida = next((r for r in self.historial[self.ronda - 1] if r["h"] == v and r["v"] == h), None)
            if ida:
                return ida["gv"], ida["gh"]
        return 0, 0

    def grupo_de(self, club_id):
        return next((i for i, g in enumerate(self.grupos) if club_id in g), None)

    def partido_de(self, club_id):
        for h, v in self.pendientes():
            if club_id in (h, v):
                return h, v
        return None

    def pendientes(self):
        hechos = {(r["h"], r["v"]) for r in self.historial[min(self.ronda, N_MD - 1)]}
        return [(h, v) for h, v in self.pares if (h, v) not in hechos]

    def registrar(self, resultado):
        self.historial[self.ronda].append(resultado)

    # ---------------------------------------------------------------- sorteos
    def _sorteo_grupos(self, rng, mundo_ligas):
        """Cuatro bombos por nivel; un club de cada bombo por grupo, sin repetir liga si se puede."""
        orden = sorted(self.inscritos, key=lambda i: -self._nivel[i])
        bombos = [orden[k * 8:(k + 1) * 8] for k in range(4)]
        grupos = [[] for _ in range(8)]
        for b in range(4):                                  # bombo a bombo: la asignación con menos choques de liga
            mejor, malos = None, 99
            for _ in range(400):
                perm = [int(i) for i in rng.permutation(8)]
                malos_ahora = sum(any(mundo_ligas[bombos[b][perm[g]]] == mundo_ligas[x] for x in grupos[g]) for g in range(8))
                if malos_ahora < malos:
                    mejor, malos = perm, malos_ahora
                if malos == 0:
                    break
            for g in range(8):
                grupos[g].append(bombos[b][mejor[g]])
        self.grupos = grupos

    def _sorteo_octavos(self, rng, mundo_ligas):
        primeros = [self._clasificados[g][0] for g in range(8)]
        segundos = [self._clasificados[g][1] for g in range(8)]
        mejor, malos = None, 99
        for _ in range(500):
            perm = [int(i) for i in rng.permutation(8)]
            if any(perm[g] == g for g in range(8)):             # no se cruzan dos del mismo grupo
                continue
            parejas = [(primeros[g], segundos[perm[g]]) for g in range(8)]
            malos_ahora = sum(mundo_ligas[a] == mundo_ligas[b] for a, b in parejas)
            if malos_ahora < malos:
                mejor, malos = parejas, malos_ahora
            if malos == 0:
                break
        # en la ida juega de local el segundo de grupo; la vuelta, el primero
        return [(b, a) for a, b in mejor]

    def sortear(self, rng, mundo=None):
        """Prepara los emparejamientos de la jornada actual (y el sorteo de grupos o de la fase si toca)."""
        ligas = self._ligas
        if not self.grupos:
            self._sorteo_grupos(rng, ligas)
        md = self.ronda
        if md < 6:
            r = md if md < 3 else md - 3
            pares = []
            for g in self.grupos:
                for a, b in IDA[r]:
                    pares.append((g[a], g[b]) if md < 3 else (g[b], g[a]))
            self.pares = pares
        elif md == 6 and not self.llaves:
            self.llaves = self._sorteo_octavos(rng, ligas)
            self.pares = list(self.llaves)
        elif md in MD_VUELTA:
            self.pares = [(v, h) for h, v in self.llaves]
        elif md in (8, 10, MD_FINAL) and not self.llaves:
            orden = [self.vivos[i] for i in rng.permutation(len(self.vivos))]
            self.llaves = [(orden[i], orden[i + 1]) for i in range(0, len(orden) - 1, 2)]
            self.pares = list(self.llaves)
        else:                                                   # ida con sorteo ya hecho
            self.pares = list(self.llaves)
        return self.pares

    # ---------------------------------------------------------------- simulación
    def jugar_ronda_ia(self, mundo, rng, asist, excluir=None):
        for h, v in self.pendientes():
            if excluir is not None and excluir in (h, v):
                continue
            self.registrar(simular_partido_ia(mundo.clubes[h], mundo.clubes[v], rng, asist, self.neutral,
                                              self.decide(), self.previo(h, v)))

    def tabla(self, g):
        """Clasificación del grupo g: [(id, pj, g, e, p, gf, gc, pts)] ordenada."""
        filas = {i: [0, 0, 0, 0, 0, 0, 0] for i in self.grupos[g]}
        for md in range(6):
            for r in self.historial[md]:
                if r["h"] in filas:
                    for club, a, b in ((r["h"], r["gh"], r["gv"]), (r["v"], r["gv"], r["gh"])):
                        f = filas[club]
                        f[0] += 1
                        f[1] += a > b
                        f[2] += a == b
                        f[3] += a < b
                        f[4] += a
                        f[5] += b
                        f[6] += 3 * (a > b) + (a == b)
        orden = sorted(filas, key=lambda i: (-filas[i][6], -(filas[i][4] - filas[i][5]), -filas[i][4], -self._nivel.get(i, 0)))
        return [(i, *filas[i]) for i in orden]

    def cerrar_ronda(self):
        assert not self.pendientes(), "faltan partidos por jugar"
        md = self.ronda
        if md == 5:
            self._clasificados = [[f[0] for f in self.tabla(g)[:2]] for g in range(8)]
            self.vivos = [i for g in self._clasificados for i in g]
        elif md in MD_VUELTA or md == MD_FINAL:
            self.vivos = [r["ganador"] for r in self.historial[md]]
            self.llaves = []
        self.pares = []
        self.ronda += 1
        if self.terminada:
            self.campeon = self.vivos[0]

    # ---------------------------------------------------------------- resumen para el usuario
    def premio_tras(self, club_id, md, resultado):
        """Dinero que cobra `club_id` tras jugar la jornada md con `resultado` = (goles propios, goles rivales) (llamar
        tras cerrar_ronda). Devuelve (monto, texto)."""
        monto, partes = 0.0, []
        if md == 0:
            monto += PREMIO_PARTICIPAR
            partes.append("participación")
        if md < 6:
            gp, gr = resultado
            if gp > gr:
                monto += PREMIO_VICTORIA
                partes.append("victoria")
            elif gp == gr:
                monto += PREMIO_EMPATE
                partes.append("empate")
        if md in PREMIO_PASE and club_id in self.vivos:
            monto += PREMIO_PASE[md]
            partes.append("pase de fase")
        if self.campeon == club_id:
            monto += PREMIO_CAMPEON
            partes.append("título")
        return monto, ", ".join(partes)

    def camino(self, club_id):
        """Partidos jugados por el club: [(md, rival, goles propios, goles rival, prórroga, pen propios, pen rival, gano)]
        con gano True/False/None (None = empate o ida sin decidir)."""
        res = []
        for md, partidos in enumerate(self.historial):
            for p in partidos:
                if club_id in (p["h"], p["v"]):
                    local = p["h"] == club_id
                    gp, gr = (p["gh"], p["gv"]) if local else (p["gv"], p["gh"])
                    pp, pr = (None, None)
                    if p["pen"]:
                        pp, pr = (p["pen"][0], p["pen"][1]) if local else (p["pen"][1], p["pen"][0])
                    if p["ganador"] is not None:
                        gano = p["ganador"] == club_id
                    else:
                        gano = True if gp > gr else None if gp == gr else False
                    res.append((md, p["v"] if local else p["h"], gp, gr, p["prorroga"], pp, pr, gano))
        return res

    def eliminatorias(self, fase):
        """Cruces de la fase 1-4 (octavos…final): [dict(a, b, ida, vuelta, pen, ganador)]. `a` es el local de la ida;
        ida y vuelta son (goles de a, goles de b) o None si aún no se jugó."""
        md0 = 6 + 2 * (fase - 1) if fase < 4 else MD_FINAL
        pares = [(r["h"], r["v"]) for r in self.historial[md0]]
        if fase_de(self.ronda) == fase and not self.terminada:
            pares += [t for t in self.llaves if t not in pares]
        res = []
        for a, b in pares:
            ida = next((r for r in self.historial[md0] if (r["h"], r["v"]) == (a, b)), None)
            vuelta = None
            if fase < 4:
                vuelta = next((r for r in self.historial[md0 + 1] if (r["h"], r["v"]) == (b, a)), None)
            dec = vuelta if fase < 4 else ida
            pen = None
            if dec and dec["pen"]:
                pen = dec["pen"] if dec["h"] == a else (dec["pen"][1], dec["pen"][0])
            res.append({"a": a, "b": b, "ida": (ida["gh"], ida["gv"]) if ida else None,
                        "vuelta": (vuelta["gv"], vuelta["gh"]) if vuelta else None, "pen": pen,
                        "ganador": dec["ganador"] if dec else None})
        return res

    def estado(self, club_id):
        """'campeon' | ('eliminado', md) | ('vivo', md) | None si no participa."""
        if club_id not in self.participantes():
            return None
        if self.campeon == club_id:
            return "campeon"
        if club_id in self.vivos:
            return ("vivo", self.ronda)
        jug = self.camino(club_id)
        return ("eliminado", jug[-1][0] if jug else 0)

    def texto_estado(self, club_id):
        e = self.estado(club_id)
        if e is None:
            return "No participa"
        if e == "campeon":
            return "¡Campeón de Europa!"
        if e[0] == "vivo":
            if self.ronda < 6:
                g = self.grupo_de(club_id)
                if g is not None and self.historial[0]:
                    pos = [f[0] for f in self.tabla(g)].index(club_id) + 1
                    return f"Grupo {LETRAS[g]}: {pos}.º"
                return "Fase de grupos"
            return f"En competición: {FASES[min(e[1], N_MD - 1)]}"
        return f"Eliminado en {FASES[e[1]].lower() if e[1] > 5 else 'la fase de grupos'}"

    # ---------------------------------------------------------------- datos auxiliares (los pone la app al crear/cargar)
    _nivel = {}                                   # id -> nivel (OVR) para bombos y desempates
    _ligas = {}                                   # id -> nombre de la liga
    _clasificados = []

    def preparar(self, mundo):
        """Conecta con el mundo (niveles y ligas de los clubes). Se llama al crear y al cargar la copa."""
        self._nivel = {i: mundo.clubes[i].ovr for i in self.inscritos}
        self._ligas = {i: mundo.clubes[i].liga_madre or mundo.clubes[i].liga for i in self.inscritos}
        if self.ronda >= 6 and not self._clasificados and self.grupos:
            self._clasificados = [[f[0] for f in self.tabla(g)[:2]] for g in range(8)]

    # ---------------------------------------------------------------- guardado
    def a_dict(self):
        return {"temporada": self.temporada, "inscritos": self.inscritos, "vivos": self.vivos, "grupos": self.grupos,
                "llaves": [list(x) for x in self.llaves], "ronda": self.ronda, "pares": [list(p) for p in self.pares],
                "historial": [[dict(r, pen=list(r["pen"]) if r["pen"] else None) for r in md] for md in self.historial],
                "campeon": self.campeon}

    @classmethod
    def de_dict(cls, d):
        c = cls(d["inscritos"], d["temporada"])
        c.vivos = list(d["vivos"])
        c.grupos = [list(g) for g in d["grupos"]]
        c.llaves = [tuple(x) for x in d["llaves"]]
        c.ronda = d["ronda"]
        c.pares = [tuple(p) for p in d["pares"]]
        c.historial = [[dict(r, pen=tuple(r["pen"]) if r["pen"] else None) for r in md] for md in d["historial"]]
        c.campeon = d["campeon"]
        return c
