"""Prueba de humo sin pantalla: recorre las escenas, juega una temporada completa y guarda capturas en shots/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, captura, frame  # noqa: E402

from juego import eventos as ev  # noqa: E402

app = App(seed=7)
captura(app, "01_menu")
app.ayuda = True
captura(app, "01b_menu_ayuda")
app.ir("cargando")
frame(app, n=4)
assert app.escena == "liga", app.escena
captura(app, "02_ligas")
app.liga_nombre = "Premier League"
app.ir("club")
captura(app, "03_club")
club = next(c for c in app.mundo.clubes.values() if c.nombre == "Manchester United")
app.iniciar_temporada(club)
captura(app, "04_alineacion")
app.sel_jug = club.plantel[3]
captura(app, "04b_alineacion_sel")
for t in ("mercado", "tactica", "liga", "datos"):
    app.tab = t
    captura(app, "05_" + t)
app.mercado["reemplazo"] = club.once[9]
app.tab = "mercado"
captura(app, "05b_reemplazos")
app.tab = "alineacion"

jornadas = 0
goles_tot = 0
tarjetas = 0
while not app.liga.terminada:
    app.preparar_partido()
    frame(app)
    if jornadas == 0:
        captura(app, "06_previa")
    app.iniciar_partido()
    if jornadas == 0:
        for _ in range(45):                 # hasta el descanso, simulando solo las jugadas pendientes
            frame(app, dt=70)
            if app.p["pausa"] == "mini":
                ev.autoresolver(app.p["ev_mini"], app.rng)
                app.p["pausa"] = app.p["mini"] = None
        captura(app, "07_partido_vivo")
    app.omitir_partido()
    frame(app, n=2)
    ga, gb = ev.marcador(app.p["est"]["eventos"])
    goles_tot += ga + gb
    tarjetas += sum(1 for e in app.p["est"]["eventos"] if e["tipo"] in ("amarilla", "roja"))
    if jornadas == 0:
        captura(app, "08_partido_final")
    app.cerrar_jornada(ga, gb)
    frame(app, n=2)
    if jornadas == 4:
        app.tab = "liga"
        captura(app, "09_liga_j5")
        app.tab = "alineacion"
    jornadas += 1
print("jornadas jugadas:", jornadas, "| pos final:", app.liga.posicion(club), "| pts:", club.pts)
print(f"goles por partido (tuyos): {goles_tot / jornadas:.2f} | tarjetas por partido: {tarjetas / jornadas:.2f}")
print("presupuesto:", club.presupuesto)
app.ir("fin")
captura(app, "10_fin")
print("OK")
