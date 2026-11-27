"""Prueba de ascensos y descensos: simulación de las divisiones, movimientos de clubes, fin de temporada por la interfaz,
club del usuario descendido jugando en segunda (con copa) y guardado.

Uso:  python tests/test_ascensos.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, captura, clic, etiquetas, frame, jugar_liga, nueva_app  # noqa: E402

from juego import ascensos as AS  # noqa: E402
from juego import guardado as G  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


# ====================================================================== 1. lógica con el mundo completo
app = App(seed=3)
app.ir("cargando")
frame(app, n=4)
m = app.mundo
rng = np.random.default_rng(5)

assert {l: AS.n_ascensos(m, l) for l in m.ligas} == {"Premier League": 3, "La Liga": 3, "Bundesliga": 2, "Serie A": 3,
                                                       "Ligue 1": 2}
paso("3 ascensos/descensos en las ligas de 20 clubes y 2 en las de 18")

ids = m.ligas["La Liga"]
orden, tabla = AS.simular_division(m, ids, rng, app.asist)
assert sorted(orden) == sorted(ids) and all(v[0] <= 3 * 2 * (len(ids) - 1) for v in tabla.values())
assert sum(v[1] for v in tabla.values()) == sum(v[2] for v in tabla.values()), "los goles a favor y en contra coinciden"
fuerza = {i: m.clubes[i].ovr for i in ids}
mejores = sorted(ids, key=lambda i: -fuerza[i])[:5]
pos_media = np.mean([orden.index(i) for i in mejores])
assert pos_media < 7, f"los clubes más fuertes deberían acabar arriba (posición media {pos_media:.1f})"
paso(f"simular una división: tabla coherente; los 5 clubes de más nivel acaban de media en el puesto {pos_media + 1:.1f}")

club = next(x for x in m.clubes.values() if x.nombre == "Real Madrid")
orden_user = sorted(m.ligas["La Liga"], key=lambda i: -m.clubes[i].ovr)
res = AS.cerrar_temporada(m, club, orden_user, rng, app.asist)
assert set(res) == set(m.ligas)
for liga, r in res.items():
    n = r["n"]
    assert r["bajan"] == r["primera"][-n:] and r["suben"] == r["segunda"][:n]
assert res["La Liga"]["primera"] == orden_user
paso("el cierre de temporada simula las otras 9 divisiones y respeta la tabla real del usuario")

tam = {l: (len(m.ligas[l]), len(m.segunda[l])) for l in m.ligas}
antes = {l: (set(m.ligas[l]), set(m.segunda[l])) for l in m.ligas}
suben_ids = [i for r in res.values() for i in r["suben"]]
baja_ids = [i for r in res.values() for i in r["bajan"]]
pres0 = {i: m.clubes[i].presupuesto for i in suben_ids + baja_ids}
AS.aplicar(m, res)
for liga, r in res.items():
    assert (len(m.ligas[liga]), len(m.segunda[liga])) == tam[liga], "cada división conserva su tamaño"
    assert set(r["suben"]) <= set(m.ligas[liga]) and not set(r["suben"]) & set(m.segunda[liga])
    assert set(r["bajan"]) <= set(m.segunda[liga]) and not set(r["bajan"]) & set(m.ligas[liga])
    assert all(m.clubes[i].division == 1 and m.clubes[i].liga == liga for i in r["suben"])
    assert all(m.clubes[i].division == 2 and m.clubes[i].liga == AS.nombre_segunda(m, liga) for i in r["bajan"])
assert all(m.clubes[i].presupuesto == pres0[i] + AS.PREMIO_ASCENSO for i in suben_ids)
assert all(m.clubes[i].presupuesto < pres0[i] for i in baja_ids)
paso("aplicar: los clubes cambian de lista, división y nombre de liga; premio por subir y recorte por bajar")

# serialización de las divisiones sobre un mundo nuevo
d = AS.a_dict(m)
app2 = nueva_app(3)
app2.ir("cargando")
frame(app2, n=4)
AS.de_dict(app2.mundo, d)
assert AS.a_dict(app2.mundo) == d
assert all(app2.mundo.clubes[i].division == 2 for i in baja_ids)
paso("las divisiones se guardan y se restauran sobre un mundo recién cargado")


# ====================================================================== 2. fin de temporada por la interfaz: el club desciende
def jugar_temporada(a):
    guard = 0
    while not a.liga.terminada and guard < 400:
        guard += 1
        jugar_liga_o_comp(a)


def jugar_liga_o_comp(a):
    """Una jornada de liga (y las copas o Champions que haya antes) omitiendo los partidos."""
    jugar_liga(a)
    clic(a, "Jugar el partido")
    clic(a, "Omitir partido")
    clic(a, "Continuar")


app = nueva_app(21)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
# el club más flojo de La Liga: casi seguro baja
club = min((x for x in app.mundo.clubes.values() if x.liga == "La Liga" and x.division == 1), key=lambda c: c.ovr)
app.iniciar_temporada(club)
frame(app, n=2)
assert club.division == 1 and app.liga.nombre == "La Liga" and len(app.liga.clubes) == 20
jugar_temporada(app)
assert app.liga.terminada
pos = app.liga.posicion(club)
paso(f"{club.nombre} termina la temporada de La Liga en el puesto {pos}º")

# si no descendió de verdad, se fuerza su clasificación en el último puesto para probar el descenso
if pos <= 17:
    for t in app.liga.clubes:
        t.g, t.e = 10, 0
    club.g, club.e, club.gf, club.gc = 0, 0, 0, 99
assert AS.estado_usuario(app.mundo, club, [t.id for t in app.liga.tabla()]) == "baja"
app.ir("fin")
frame(app, n=2)
captura(app, "22_fin_descenso")
clic(app, "Siguiente temporada")
assert app.escena == "ascensos" and app.res_ascensos["mov"] == "baja"
frame(app, n=2)
captura(app, "22b_ascensos")
assert club.division == 2 and club.id in app.mundo.segunda["La Liga"] and club.id not in app.mundo.ligas["La Liga"]
assert club.id in app.res_ascensos["res"]["La Liga"]["bajan"]
paso("al pulsar 'Siguiente temporada' aparece la pantalla de ascensos y el club del usuario ha descendido")

clic(app, "Continuar")
frame(app, n=10)
assert app.escena == "evolucion", app.escena
clic(app, "Empezar la temporada")
assert app.escena == "hub"
assert app.liga.nombre == "La Liga 2" and club in app.liga.clubes and len(app.liga.clubes) == len(app.mundo.segunda["La Liga"])
assert app.liga.total_jornadas == 2 * (len(app.liga.clubes) - 1)
assert app.champions.estado(club.id) is None, "un club de segunda no juega la Champions"
assert club.id in app.copa.vivos, "pero sí la copa"
assert len(app.copa.inscritos) == 32 and len(set(app.copa.inscritos)) == 32
assert app.temporada == 2024 and app.historial_temporadas[-1]["mov"] == "baja"
paso(f"temporada siguiente: {club.nombre} juega La Liga 2 ({len(app.liga.clubes)} clubes, {app.liga.total_jornadas} jornadas) y la copa")

app.tab = "liga"
frame(app, n=2)
captura(app, "22c_segunda_liga")
app.tab = "calendario"
frame(app, n=2)
captura(app, "22d_segunda_calendario")
app.tab = "champions"
frame(app, n=2)
app.tab = "alineacion"
paso("las pestañas Liga, Calendario y Champions se dibujan con la segunda división")

# ====================================================================== 3. temporada en segunda: ascenso
jugar_temporada(app)
assert app.liga.terminada
others = [t for t in app.liga.clubes if t is not club]
club.g, club.e, club.gf, club.gc = 99, 0, 999, 0           # campeón de segunda: sube
app.ir("fin")
frame(app, n=2)
captura(app, "22e_fin_ascenso")
clic(app, "Siguiente temporada")
assert app.escena == "ascensos" and app.res_ascensos["mov"] == "sube"
frame(app, n=2)
captura(app, "22f_ascensos_sube")
assert club.division == 1 and club.id in app.mundo.ligas["La Liga"] and club.liga == "La Liga"
presupuesto_antes = club.presupuesto
paso("campeón de segunda: el club asciende de nuevo a La Liga")

clic(app, "Continuar")
frame(app, n=10)
clic(app, "Empezar la temporada")
assert app.liga.nombre == "La Liga" and club in app.liga.clubes and len(app.liga.clubes) == 20
# clasifican a la Champions los 6 primeros de la clasificación final de cada primera división (incluida la simulada)
assert app.champions.temporada == 2025 and len(app.champions.inscritos) == 32
paso("vuelve a jugar en primera (20 clubes)")

# ====================================================================== 4. guardado en segunda división
app = nueva_app(22)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "Serie A"
club = next(x for x in app.mundo.clubes.values() if x.liga == "Serie A")
app.iniciar_temporada(club)
frame(app, n=2)
res = AS.cerrar_temporada(app.mundo, club, [t.id for t in app.liga.tabla()], app.rng, app.asist)
res["Serie A"]["bajan"] = [club.id] + [i for i in res["Serie A"]["bajan"] if i != club.id][:2]   # forzamos el descenso
AS.aplicar(app.mundo, res)
app.temporada += 1
app.iniciar_temporada(club)
frame(app, n=2)
assert app.liga.nombre == "Serie B" and club in app.liga.clubes
app.guardar()
estado = AS.a_dict(app.mundo)
copa = app.copa.a_dict()
app2 = nueva_app(77)
clic(app2, "Continuar temporada")
frame(app2, n=8)
assert app2.escena == "hub" and app2.club.id == club.id and app2.club.division == 2
assert app2.liga.nombre == "Serie B" and club.id in [c.id for c in app2.liga.clubes]
assert AS.a_dict(app2.mundo) == estado and app2.copa.a_dict() == copa
paso("guardar y continuar conserva las divisiones y al club del usuario en segunda")

print(f"\n{len(OK)} comprobaciones OK")
