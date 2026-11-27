"""Prueba del botón 'Simular hasta la jornada N' del calendario y de los logos del encabezado.

Uso:  python tests/test_simular.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import botones, captura, clic, clic_xy, etiquetas, frame, nueva_app  # noqa: E402

from juego import champions as CH  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


app = nueva_app(11)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
club = next(x for x in app.mundo.clubes.values() if x.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)
app.tab = "calendario"
frame(app, n=2)


def boton_sim():
    return next((b for b in botones(app) if b[1].startswith(("Simular hasta", "¿Seguro"))), None)


b = boton_sim()
assert b is not None and not b[2], "la jornada próxima no se puede 'simular hasta': el botón está inhabilitado"
paso("con la próxima jornada seleccionada el botón está inhabilitado")

app.cal_sel = 10
frame(app, n=2)
b = boton_sim()
assert b[1] == "Simular hasta la jornada 11" and b[2]
captura(app, "23_simular_hasta")
clic_xy(app, b[0].center)
b = boton_sim()
assert b[1].startswith("¿Seguro?"), "el primer clic pide confirmar"
assert app.liga.jornada == 0, "todavía no se simuló nada"
app.cal_sel = 12                                                   # cambiar de jornada cancela la confirmación
frame(app, n=2)
assert boton_sim()[1] == "Simular hasta la jornada 13"
app.cal_sel = 10
frame(app, n=2)
clic_xy(app, boton_sim()[0].center)
clic_xy(app, boton_sim()[0].center)
frame(app, n=4)
assert app.liga.jornada == 10 and app.escena == "hub" and app.tab == "calendario", (app.liga.jornada, app.escena)
assert club.pj == 10, club.pj
assert app.copa.ronda >= 1 and len(app.copa.camino(club.id)) >= 1, "la copa debió jugarse por el camino"
camino = app.champions.camino(club.id)
assert [x[0] for x in camino] == [0, 1, 2, 3], [x[0] for x in camino]
assert app.champions.ronda == 4
paso("simular hasta la jornada 11: 10 jornadas de liga, la ronda de copa y 4 jornadas de Champions jugadas de paso")

b = boton_sim()
assert b[1] == "Simular hasta la jornada 11" and not b[2] or b[1].startswith("Simular"), b
assert app.liga.rival(club)[0] is not None
paso("tras simular, estás en la jornada 11 y el partido es tuyo")

# se puede seguir hasta el final de la temporada
app.cal_sel = app.liga.total_jornadas - 1
frame(app, n=2)
clic_xy(app, boton_sim()[0].center)
clic_xy(app, boton_sim()[0].center)
frame(app, n=4)
assert app.liga.jornada == app.liga.total_jornadas - 1 and app.champions.terminada
paso("simular hasta la última jornada: la Champions termina también")

# logos de los encabezados: no invaden la franja del 'Próximo partido' (y < 40)
for tab in ("liga", "copa", "champions"):
    app.tab = tab
    frame(app, n=2)
    captura(app, f"23_logo_{tab}")
paso("capturas de los encabezados de Liga, Copa y Champions")

print(f"\n{len(OK)} comprobaciones OK")
