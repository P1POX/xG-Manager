"""Prueba de la copa nacional: sorteo, rondas, prórroga, penales, partido en vivo, calendario y guardado.

Uso:  python tests/test_copa.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, frame  # noqa: E402

from juego import copa as CP  # noqa: E402
from juego import eventos as ev  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


app = App(seed=31)
app.ir("cargando")
frame(app, n=4)
m = app.mundo
rng = np.random.default_rng(4)

# ------------------------------------------------------------------ 1. participantes y datos
assert set(m.segunda) == set(m.ligas), "cada liga de primera debe tener su segunda división"
for liga, ids in m.ligas.items():
    c = CP.Copa.crear(m, liga, rng, 2023)
    assert len(c.inscritos) == len(set(c.inscritos)) == CP.N_PARTICIPANTES, (liga, len(c.inscritos))
    assert set(ids) <= set(c.inscritos), "los clubes de la liga deben estar todos en su copa"
    assert all(m.clubes[i].division in (1, 2) and m.clubes[i].liga_madre == liga for i in c.inscritos)
    assert c.nombre == CP.NOMBRES[liga]
paso("las 5 copas tienen 32 clubes únicos: toda su primera división y el resto de la segunda")

# ------------------------------------------------------------------ 2. una copa completa entre clubes de la IA
c = CP.Copa.crear(m, "La Liga", rng, 2023)
partidos = 0
neutrales = []
for r in range(5):
    assert c.ronda == r and len(c.vivos) == 32 // 2 ** r
    pares = c.sortear(rng)
    assert len(pares) == len(c.vivos) // 2 and len({x for p in pares for x in p}) == len(c.vivos)
    c.jugar_ronda_ia(m, rng, app.asist)
    assert not c.pendientes()
    partidos += len(c.historial[r])
    for res in c.historial[r]:
        assert res["ganador"] in (res["h"], res["v"])
        if res["gh"] != res["gv"]:
            assert res["ganador"] == (res["h"] if res["gh"] > res["gv"] else res["v"])
        else:                                              # empate tras la prórroga: lo decidieron los penales
            assert res["pen"] and res["prorroga"] and res["pen"][0] != res["pen"][1]
            assert res["ganador"] == (res["h"] if res["pen"][0] > res["pen"][1] else res["v"])
    c.cerrar_ronda()
assert partidos == 31 and c.terminada and c.campeon in c.inscritos and len(c.vivos) == 1
assert c.texto_estado(c.campeon) == "¡Campeón!"
paso("copa completa entre clubes de la IA: 31 partidos, un campeón, y los empates se resuelven con prórroga y penales")

# ------------------------------------------------------------------ 3. frecuencia de prórroga y penales (debe parecerse a la realidad)
prorrogas = penales = total = 0
local_gana = 0
for i in range(300):
    a, b = rng.choice(len(m.ligas["La Liga"]), 2, replace=False)
    ids = m.ligas["La Liga"]
    res = CP.simular_partido_ia(m.clubes[ids[a]], m.clubes[ids[b]], rng, app.asist)
    total += 1
    prorrogas += res["prorroga"]
    penales += bool(res["pen"])
assert 0.15 < prorrogas / total < 0.40 and 0.04 < penales / total < 0.22, (prorrogas / total, penales / total)
paso(f"prórrogas {prorrogas / total:.0%} y penales {penales / total:.0%} de los partidos (en una copa real ≈ 25 % y ≈ 10 %)")

# ------------------------------------------------------------------ 4. tanda de penales: reglas
ids = m.ligas["La Liga"]
est = ev.nuevo_estado(m.clubes[ids[0]], m.clubes[ids[1]], 1.4, 1.2, None)
t = CP.nueva_tanda(est, "a")
assert t.proximo()[0] == "a"
for ok in (True, True, True):                              # a anota 3, b falla 3: tras 3 cada uno quedan 2 tiros
    t.registrar(ok)
    t.registrar(False)
assert t.goles == {"a": 3, "b": 0} and t.terminada(), "con 3-0 tras 3 lanzamientos, b ya no puede alcanzar"
t = CP.nueva_tanda(est, "a")
for _ in range(5):                                         # 5-5: muerte súbita
    t.registrar(True)
    t.registrar(True)
assert not t.terminada() and t.tiros == {"a": 5, "b": 5}
t.registrar(True)
assert not t.terminada(), "en la muerte súbita no se decide hasta que lance el otro"
t.registrar(False)
assert t.terminada() and t.ganador() == "a"
for k in range(200):                                       # simulaciones: siempre hay ganador y se acaba
    t = CP.nueva_tanda(est, "a" if k % 2 else "b")
    t.simular_resto(rng)
    assert t.terminada() and t.goles["a"] != t.goles["b"] and len(t.registro) == t.tiros["a"] + t.tiros["b"] < 60
paso("tanda de penales: final anticipado, muerte súbita y siempre hay un ganador")

# ------------------------------------------------------------------ 5. guardado de la copa
c2 = CP.Copa.de_dict(c.a_dict())
assert c2.campeon == c.campeon and c2.ronda == 5 and c2.historial == c.historial and c2.inscritos == c.inscritos
paso("la copa se serializa y se recupera igual")

# ====================================================================== 6. flujo completo por la interfaz
import datetime as dt  # noqa: E402

from _util import avanzar_hasta, captura, clic, clic_xy, etiquetas, jugar_hub, nueva_app  # noqa: E402
from juego import guardado as G  # noqa: E402

app = nueva_app(31)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
club = next(x for x in app.mundo.clubes.values() if x.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)
assert app.copa is not None and club.id in app.copa.vivos and len(app.copa.inscritos) == 32


def jornada_de_liga_omitiendo():
    jugar_hub(app)
    clic(app, "Jugar el partido")
    clic(app, "Omitir partido")
    clic(app, "Continuar")


while app.liga.jornada < CP.JORNADA_RONDA[0]:
    assert not any(t.startswith("Copa:") for t in etiquetas(app)), "la copa no debería tocar todavía"
    jornada_de_liga_omitiendo()
assert app.comp_debida() is app.copa and app.copa.pares and app.copa.partido_de(club.id), "debe haber sorteo al llegar la ronda"
assert any(t.startswith("Copa: Dieciseisavos") for t in etiquetas(app)), etiquetas(app)
par0 = app.copa.partido_de(club.id)
paso("al llegar a la jornada 6 aparece la ronda de copa, ya sorteada, antes del partido de liga")

clic(app, "Copa")                                       # pestaña
assert app.tab == "copa"
app.avisos.clear()
captura(app, "19_copa")
app.tab = "alineacion"

# ---- partido de copa con prórroga forzada (sin goles) y tanda interactiva
viejo_gen = ev.generar_tramo
ev.generar_tramo = lambda est, m0, m1, rng: []           # ningún evento: el partido acaba 0-0
try:
    jugar_hub(app)
    assert app.p["copa"] == 0 and app.p["user_local"] == (par0[0] == club.id)
    clic(app, "Jugar el partido")
    p = app.p
    p["vel"] = 4
    avanzar_hasta(app, lambda: p["fin"] or p["pausa"] == "descanso", max_cuadros=20000)
    if p["pausa"] == "descanso":
        clic(app, "Empezar el 2.º tiempo")
    assert avanzar_hasta(app, lambda: p["prorroga"], max_cuadros=20000), "a los 90' con empate debía empezar la prórroga"
    assert not p["fin"] and p["min"] >= 90
    assert avanzar_hasta(app, lambda: p["fin"], max_cuadros=20000)
    assert p["min"] == 120 and p["tanda_obj"] is None
finally:
    ev.generar_tramo = viejo_gen
assert "Tanda de penales" in etiquetas(app) and "Continuar" not in etiquetas(app)
paso("copa: con empate a los 90' hay prórroga hasta el 120' y luego pide la tanda de penales")

clic(app, "Tanda de penales")
assert p["pausa"] == "tanda" and p["tanda_obj"] is not None
t = p["tanda_obj"]
frame(app, n=2)
captura(app, "19b_tanda")
clic(app, "Lanzar el penal" if t.proximo()[0] == p["lado"] else "Atajar el penal")
assert p["tanda_ui"]["mini"] is not None, "debía abrirse el minijuego del penal"
captura(app, "19c_tanda_minijuego")
clic(app, "Simular jugada")
assert p["tanda_ui"]["mini"] is None and len(t.registro) == 1, "el lanzamiento no se registró"
clic(app, "Simular el resto")
assert t.terminada() and t.goles["a"] != t.goles["b"]
frame(app, n=2)
captura(app, "19d_tanda_final")
clic(app, "Continuar")
assert p["pausa"] is None and "Continuar" in etiquetas(app)
gano_tanda = t.ganador() == p["lado"]
presupuesto0 = club.presupuesto
clic(app, "Continuar")
assert app.escena == "hub" and app.copa.ronda == 1
r0 = app.copa.historial[0]
assert len(r0) == 16 and any(r["pen"] for r in r0), "la ronda debe estar completa y registrar los penales del usuario"
mio = next(r for r in r0 if club.id in (r["h"], r["v"]))
assert mio["ganador"] == (club.id if gano_tanda else (mio["v"] if mio["h"] == club.id else mio["h"]))
assert (club.id in app.copa.vivos) == gano_tanda
assert (club.presupuesto > presupuesto0) == gano_tanda, "solo se cobra el premio si pasas de ronda"
paso(f"tanda de penales por la interfaz (lanzar/atajar, simular) y cierre de la ronda: {'pasas' if gano_tanda else 'eliminado'}, 16 partidos registrados")

# ---- calendario: la ronda aparece en dorado y al hacer clic lleva a la copa
f0 = app.fecha_copa(0)
app.tab = "calendario"
app.cal_mes = (f0.year, f0.month)
frame(app, n=2)
celda = app._rect_celda(*divmod(dt.date(f0.year, f0.month, 1).weekday() + f0.day - 1, 7))
clic_xy(app, celda.center)
assert app.tab == "copa" and app.copa_sel == 0
paso("calendario: la ronda de copa tiene su día (miércoles) y el clic abre la pestaña Copa")

# ---- guardar y continuar conserva la copa
clic(app, "Guardar y salir")
estado = app.copa.a_dict()
app2 = nueva_app(77)
clic(app2, "Continuar temporada")
frame(app2, n=8)
assert app2.escena == "hub" and app2.copa is not None and app2.copa.a_dict() == estado
paso("guardar y continuar conserva la copa (vivos, ronda e historial)")

# ---- si el usuario ya no está en la copa, la ronda se juega sola entre los demás
app = nueva_app(5)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "Bundesliga"
club = next(x for x in app.mundo.clubes.values() if x.liga == "Bundesliga")
app.iniciar_temporada(club)
frame(app, n=2)
otros = [i for i in app.mundo.ligas["Bundesliga"] if i != club.id] + list(app.mundo.segunda["Bundesliga"])
app.copa = CP.Copa("DFB-Pokal", "Bundesliga", otros[:32], 2023)                    # el usuario no participa
assert club.id not in app.copa.vivos
while app.liga.jornada < CP.JORNADA_RONDA[0]:
    jornada_de_liga_omitiendo()
assert not any(t.startswith("Copa:") for t in etiquetas(app))
assert app.copa.ronda == 1 and len(app.copa.historial[0]) == 16, "la ronda debía simularse sola al llegar su fecha"
jugar_hub(app)
assert app.escena == "partido" and app.p["copa"] is None, "y luego se juega el partido de liga normal"
paso("sin tu club en la copa, la ronda se simula sola y sigues con la liga")

print(f"\n{len(OK)} comprobaciones OK")
