"""Prueba de la Champions League: clasificación, sorteo, fase de grupos, eliminatorias, interfaz, calendario y guardado.

Uso:  python tests/test_champions.py
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, avanzar_hasta, botones, captura, clic, clic_xy, etiquetas, frame, jugar_hub, jugar_liga, nueva_app  # noqa: E402

from juego import champions as CH  # noqa: E402
from juego import copa as CP  # noqa: E402
from juego import eventos as ev  # noqa: E402
from juego import guardado as G  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


# ====================================================================== 1. lógica pura con el mundo completo
app = App(seed=3)
app.ir("cargando")
frame(app, n=4)
mundo = app.mundo
rng = np.random.default_rng(1)

ch = CH.Champions.crear(mundo, "La Liga", 2023)
assert len(ch.inscritos) == 32 == len(set(ch.inscritos))
por_liga = {}
for i in ch.inscritos:
    por_liga.setdefault(mundo.clubes[i].liga, []).append(i)
assert all(len(v) >= 6 for v in por_liga.values()) and set(por_liga) == set(mundo.ligas), por_liga.keys()
for liga, ids in mundo.ligas.items():                                   # los 6 de más nivel de cada liga entran
    mejores = sorted(ids, key=lambda i: -mundo.clubes[i].ovr)[:6]
    assert all(i in ch.inscritos for i in mejores), liga
paso("clasifican 32 clubes: los 6 mejores de cada liga y 2 más; todos con su liga")

# con el orden final de la temporada anterior de tu liga clasifican los 6 primeros de esa tabla
orden = list(mundo.ligas["La Liga"])[::-1]
ch_b = CH.Champions.crear(mundo, "La Liga", 2024, {"La Liga": orden})
assert all(i in ch_b.inscritos for i in orden[:6])
paso("la clasificación de tu liga sigue la tabla de la temporada anterior")

ch.sortear(rng)
assert len(ch.grupos) == 8 and all(len(g) == 4 for g in ch.grupos)
assert sorted(i for g in ch.grupos for i in g) == sorted(ch.inscritos)
repetidos = sum(4 - len({mundo.clubes[i].liga for i in g}) for g in ch.grupos)
assert repetidos <= 2, f"demasiados clubes de la misma liga en un grupo: {repetidos}"
assert len(ch.pares) == 16
paso(f"sorteo de 8 grupos de 4, con {repetidos} coincidencias de liga y bombos por nivel")

# cada club juega 6 partidos de grupo: 3 de local y 3 de visita, contra los otros 3 dos veces
partidos = {i: [] for i in ch.inscritos}
for md in range(6):
    ch.ronda = md
    ch.pares = []
    ch.sortear(rng)
    jugadores = [x for p in ch.pares for x in p]
    assert sorted(jugadores) == sorted(ch.inscritos), f"jornada {md}: todos juegan una vez"
    for h, v in ch.pares:
        partidos[h].append(("H", v))
        partidos[v].append(("V", h))
for i, lst in partidos.items():
    assert sum(1 for l, _ in lst if l == "H") == 3 and len(lst) == 6
    rivales = sorted(r for _, r in lst)
    assert len(set(rivales)) == 3 and all(rivales.count(r) == 2 for r in set(rivales)), "ida y vuelta contra los 3 rivales"
paso("calendario de grupos: 6 jornadas, 3 de local y 3 de visita, ida y vuelta contra los 3 rivales")

# competición completa entre clubes de la IA
ch = CH.Champions.crear(mundo, "La Liga", 2023)
rng = np.random.default_rng(7)
mds_vistos = []
while not ch.terminada:
    ch.sortear(rng)
    mds_vistos.append(ch.ronda)
    ch.jugar_ronda_ia(mundo, rng, app.asist)
    ch.cerrar_ronda()
    if ch.ronda == 6:
        assert len(ch.vivos) == 16
        tops = {i for g in range(8) for i in [f[0] for f in ch.tabla(g)[:2]]}
        assert set(ch.vivos) == tops
        pasan = {g: [f[0] for f in ch.tabla(g)] for g in range(8)}
assert mds_vistos == list(range(13)) and ch.campeon is not None and len(ch.vivos) == 1
n_ganadores = sum(1 for md in (7, 9, 11, 12) for r in ch.historial[md] if r["ganador"] is None)
assert n_ganadores == 0, "toda vuelta y la final tienen ganador"
for md in (6, 8, 10):
    assert all(r["ganador"] is None for r in ch.historial[md]), "la ida no decide"
assert len(ch.historial[12]) == 1 and all(len(ch.historial[md]) == 4 for md in (8, 9)) and len(ch.historial[10]) == 2
paso("Champions completa entre clubes de la IA: 13 jornadas, 8 grupos, octavos (16), cuartos (8), semis (4) y final; un campeón")

# la vuelta tiene en cuenta el global
h, v = ch.historial[7][0]["h"], ch.historial[7][0]["v"]
ida = next(r for r in ch.historial[6] if r["h"] == v and r["v"] == h)
vuelta = ch.historial[7][0]
glob_h, glob_v = vuelta["gh"] + ida["gv"], vuelta["gv"] + ida["gh"]
if glob_h != glob_v:
    assert vuelta["ganador"] == (h if glob_h > glob_v else v)
paso("el ganador de una eliminatoria sale del global de ida y vuelta")

# prórroga y penales en la vuelta cuando el global empata
rng2 = np.random.default_rng(0)
H, V = mundo.clubes[ch.inscritos[0]], mundo.clubes[ch.inscritos[1]]
n_pr = n_pen = 0
for _ in range(400):
    r = CH.simular_partido_ia(H, V, rng2, app.asist, decide=True, previo=(1, 1))
    assert r["ganador"] in (H.id, V.id)
    n_pr += r["prorroga"]
    n_pen += r["pen"] is not None
    if r["pen"]:
        assert r["prorroga"] and r["gh"] + 1 == r["gv"] + 1 and r["pen"][0] != r["pen"][1]
assert 0 < n_pen < n_pr < 400
paso(f"vuelta con global empatado: prórroga {n_pr / 4:.0f}% y penales {n_pen / 4:.0f}% de los partidos; siempre hay ganador")

# serialización
ch2 = CH.Champions.de_dict(ch.a_dict())
ch2.preparar(mundo)
assert ch2.a_dict() == ch.a_dict() and ch2.campeon == ch.campeon
assert ch2.eliminatorias(4)[0]["ganador"] == ch.campeon
paso("la Champions se serializa y se recupera igual")

# ====================================================================== 2. temporada completa con tu club en la Champions
app = nueva_app(31)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
club = next(x for x in app.mundo.clubes.values() if x.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)
ch = app.champions
assert ch is not None and club.id in ch.vivos and ch.estado(club.id) is not None
assert [t for t in etiquetas(app) if t.startswith("Champions:")] == [], "todavía no toca"
paso("Real Madrid está clasificado y el hub no muestra la Champions antes de su fecha")


def jugar_partido_omitiendo():
    clic(app, "Jugar el partido")
    clic(app, "Omitir partido")
    if "Tanda de penales" in etiquetas(app):
        clic(app, "Tanda de penales")
        clic(app, "Simular el resto")
        clic(app, "Continuar")
    clic(app, "Continuar")


secuencia = []
cap = {"hub": False, "previa": False, "tab": False, "elim": False}
while not app.liga.terminada:
    etiq = [t for t in etiquetas(app) if t.startswith(("Champions:", "Copa:"))]
    if etiq:
        secuencia.append(etiq[0])
    if etiq and etiq[0].startswith("Champions:") and not cap["hub"]:
        cap["hub"] = True
        assert etiq[0] == "Champions: Grupos J1", etiq
        assert app.liga.jornada == CH.JORNADA_MD[0]
        app.tab = "alineacion"
        captura(app, "20_hub_champions")
        f = app.fecha_comp(ch, 0)
        assert f.weekday() == 1 and f < app.fecha(app.liga.jornada), "la Champions se juega el martes anterior a la jornada"
        jugar_hub(app)
        assert app.escena == "partido" and app.p["comp"] is ch and app.p["decide"] is False
        frame(app, n=2)
        captura(app, "20b_previa_champions")
        jugar_partido_omitiendo()
        presupuesto = club.presupuesto
        assert ch.ronda == 1 and len(ch.historial[0]) == 16 and ch.grupos
        app.tab = "champions"
        frame(app, n=2)
        captura(app, "20c_champions_grupos")
        paso("al llegar la jornada 3 de liga aparece 'Champions: Grupos J1' (martes), sorteo de grupos y 16 partidos jugados")
        continue
    if etiq and etiq[0].startswith("Champions:") and ch.ronda == 6 and not cap["elim"]:
        cap["elim"] = True
        app.champ_sel = 1
        app.tab = "champions"
        frame(app, n=2)
        captura(app, "20d_champions_octavos")
        assert len(ch.llaves) == 8 and len(ch.vivos) == 16
        app.tab = "alineacion"
    if etiq:
        jugar_hub(app)
        jugar_partido_omitiendo()
        assert app.escena == "hub"
    else:
        jugar_hub(app)
        jugar_partido_omitiendo()
mis_comp = [t for t in secuencia if t.startswith("Champions:")]
camino = ch.camino(club.id)
assert len(camino) == len({x for x in secuencia if x.startswith("Champions")}) or len(camino) >= 6
assert len(camino) >= 6 and [x[0] for x in camino[:6]] == [0, 1, 2, 3, 4, 5], "jugó los seis partidos de grupo"
assert all(x[0] < 6 for x in camino) or club.id in ch.vivos or ch.estado(club.id)[0] == "eliminado"
paso(f"temporada completa: {len(camino)} partidos de Champions jugados por Real Madrid ({ch.texto_estado(club.id)})")

# al terminar la liga, todas las jornadas de la Champions se han jugado (también las de otros clubes)
assert ch.terminada and ch.campeon is not None
assert len(ch.historial[12]) == 1
paso("al terminar la liga la Champions está terminada, con campeón")

# calendario: aparecen días de Champions en azul y el clic abre la pestaña
f0 = app.fecha_comp(ch, 0)
app.ir("hub")
app.tab = "calendario"
app.cal_mes = (f0.year, f0.month)
frame(app, n=2)
celda = app._rect_celda(*divmod(dt.date(f0.year, f0.month, 1).weekday() + f0.day - 1, 7))
captura(app, "20e_calendario_champions")
clic_xy(app, celda.center)
assert app.tab == "champions" and app.champ_sel == 0, (app.tab, app.champ_sel, f0, [str(app.fecha(i)) for i in range(0, 6)])
paso("calendario: la jornada de Champions tiene su día (martes) y el clic abre la pestaña Champions")

# pestañas de fase y final
for fase in range(5):
    app.champ_sel = fase
    frame(app, n=2)
app.champ_sel = 4
frame(app, n=2)
captura(app, "20f_champions_final")
paso("las cinco pestañas de fase se dibujan sin errores")

# guardar y continuar conserva la Champions
estado = ch.a_dict()
app.guardar()
app2 = nueva_app(77)
clic(app2, "Continuar temporada")
frame(app2, n=8)
assert app2.champions is not None and app2.champions.a_dict() == estado
assert app2.champions.eliminatorias(4)[0]["ganador"] == ch.campeon
paso("guardar y continuar conserva la Champions (grupos, llaves, historial y campeón)")

# siguiente temporada: clasifican los primeros de la tabla final de tu liga
tabla = [t.id for t in app2.liga.tabla()]
app2.ir("fin")
frame(app2, n=2)
captura(app2, "20g_fin_champions")
app2.cerrar_division()
app2.siguiente_temporada()
frame(app2, n=2)
nuevo = app2.champions
assert nuevo is not ch and not nuevo.grupos and nuevo.temporada == app2.temporada
assert all(i in nuevo.inscritos for i in tabla[:6]), "los 6 primeros de la liga clasifican"
assert app2.historial_temporadas[-1].get("champions")
paso("temporada siguiente: nueva Champions con los 6 primeros de la tabla final de tu liga")

# ====================================================================== 3. vuelta de eliminatoria con el global en juego
def preparar_vuelta(ida_club, ida_rival, semilla):
    """Real Madrid juega la vuelta de octavos en casa; en la ida el marcador fue ida_club-ida_rival a su favor/contra."""
    a = nueva_app(semilla)
    a.ir("cargando")
    frame(a, n=4)
    a.liga_nombre = "La Liga"
    c = next(x for x in a.mundo.clubes.values() if x.nombre == "Real Madrid")
    a.iniciar_temporada(c)
    frame(a, n=2)
    rival = next(i for i in a.champions.inscritos if i != c.id)
    k = a.champions
    k.vivos, k.llaves, k.ronda = [c.id, rival], [(rival, c.id)], 7
    k.pares = [(c.id, rival)]
    k.historial[6] = [{"h": rival, "v": c.id, "gh": ida_rival, "gv": ida_club, "prorroga": False, "pen": None, "ganador": None}]
    a.copa.ronda = 5                                      # sin copa pendiente
    a.liga.jornada = CH.JORNADA_MD[7]
    return a, c, k, rival


def jugar_hasta(app, cond):
    p = app.p
    p["vel"] = 4
    avanzar_hasta(app, lambda: p["fin"] or p["pausa"] == "descanso" or cond(), max_cuadros=20000)
    if p["pausa"] == "descanso":
        clic(app, "Empezar el 2.º tiempo")
    return avanzar_hasta(app, cond, max_cuadros=20000)


viejo = ev.generar_tramo
ev.generar_tramo = lambda est, m0, m1, rng: []             # 0-0 en el tiempo reglamentario
try:
    # A) ida 1-1: el global sigue empatado -> prórroga y penales
    app, club, ch, rival = preparar_vuelta(1, 1, 41)
    assert ch.previo(club.id, rival) == (1, 1) and ch.decide()
    p0 = club.presupuesto
    frame(app, n=2)
    assert any(t.startswith("Champions: Octavos vuelta") for t in etiquetas(app)), etiquetas(app)
    jugar_hub(app)
    assert app.p["previo"] == (1, 1) and app.p["decide"]
    frame(app, n=2)
    captura(app, "21_previa_vuelta")
    clic(app, "Jugar el partido")
    p = app.p
    assert jugar_hasta(app, lambda: p["prorroga"]), "global empatado a los 90': debe haber prórroga"
    frame(app, n=2)
    captura(app, "21b_vuelta_global")
    assert avanzar_hasta(app, lambda: p["fin"], max_cuadros=20000) and p["min"] == 120
    assert "Tanda de penales" in etiquetas(app)
    clic(app, "Tanda de penales")
    clic(app, "Simular el resto")
    t = p["tanda_obj"]
    gano = t.ganador() == p["lado"]
    clic(app, "Continuar")
    clic(app, "Continuar")
    r = ch.historial[7][0]
    assert r["pen"] is not None and r["prorroga"] and r["ganador"] == (club.id if gano else rival)
    assert ch.ronda == 8 and (club.id in ch.vivos) == gano
    assert (club.presupuesto - p0 >= CH.PREMIO_PASE[7]) == gano
    paso(f"vuelta con global 1-1: prórroga y tanda de penales por la interfaz ({'pasas' if gano else 'eliminado'})")

    # B) ida perdida 0-2 y 0-0 en la vuelta: el global no empata -> sin prórroga, eliminado
    app, club, ch, rival = preparar_vuelta(0, 2, 42)
    jugar_hub(app)
    clic(app, "Jugar el partido")
    p = app.p
    assert jugar_hasta(app, lambda: p["fin"])
    assert not p["prorroga"] and p["min"] == 90 and "Tanda de penales" not in etiquetas(app)
    frame(app, n=2)
    captura(app, "21c_vuelta_eliminado")
    clic(app, "Continuar")
    assert ch.historial[7][0]["ganador"] == rival and club.id not in ch.vivos and ch.estado(club.id)[0] == "eliminado"
    paso("vuelta con global 0-2 y 0-0: sin prórroga y eliminado")

    # C) ida ganada 2-0 y 0-0 en la vuelta: pasas sin prórroga y cobras el premio de la fase
    app, club, ch, rival = preparar_vuelta(2, 0, 43)
    p0 = club.presupuesto
    jugar_hub(app)
    clic(app, "Jugar el partido")
    clic(app, "Omitir partido")
    assert "Tanda de penales" not in etiquetas(app) and not app.p["prorroga"]
    clic(app, "Continuar")
    assert ch.historial[7][0]["ganador"] == club.id and club.id in ch.vivos
    assert club.presupuesto - p0 >= CH.PREMIO_PASE[7]
    paso("vuelta con ventaja de la ida: pasas sin prórroga y cobras el premio de la fase")
finally:
    ev.generar_tramo = viejo

print(f"\n{len(OK)} comprobaciones OK")
