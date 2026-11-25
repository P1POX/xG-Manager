"""Prueba de humo sin pantalla: recorre todas las escenas, juega una temporada completa y guarda capturas."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import pygame  # noqa: E402

from juego.app import App  # noqa: E402

SHOTS = RAIZ / "shots"
SHOTS.mkdir(exist_ok=True)


def frame(app, click=None, n=1):
    for _ in range(n):
        ev = [pygame.event.Event(pygame.MOUSEBUTTONUP, pos=click, button=1)] if click else []
        app.ui.inicio_frame(ev)
        app.cuadro()
        app.ui.dibujar_tooltip()
        app.dibujar_avisos()
        click = None


def shot(app, nombre):
    frame(app)
    pygame.image.save(app.pantalla, str(SHOTS / f"{nombre}.png"))


app = App(seed=7)
shot(app, "01_menu")
app.ayuda = True
shot(app, "01b_menu_ayuda")
app.ir("cargando")
frame(app, n=4)
assert app.escena == "liga", app.escena
shot(app, "02_ligas")
app.liga_nombre = "Premier League"
app.ir("club")
shot(app, "03_club")
club = next(c for c in app.mundo.clubes.values() if c.nombre == "Manchester United")
app.iniciar_temporada(club)
shot(app, "04_alineacion")
app.sel_jug = club.plantel[3]
shot(app, "04b_alineacion_sel")
for t in ("mercado", "tactica", "liga", "datos"):
    app.tab = t
    shot(app, "05_" + t)
app.mercado["reemplazo"] = club.once[9]
app.tab = "mercado"
shot(app, "05b_reemplazos")
app.tab = "alineacion"
# temporada completa
jornadas = 0
while not app.liga.terminada:
    app.preparar_partido()
    frame(app)
    if jornadas == 0:
        shot(app, "06_previa")
    app.iniciar_partido()
    app.p["t0"] -= 3000
    frame(app)
    if jornadas == 0:
        shot(app, "07_partido_vivo")
    app.p["t0"] -= 10000
    frame(app, n=2)
    if jornadas == 0:
        shot(app, "08_partido_final")
    ga, gb = app.p["res"]
    app.cerrar_jornada(ga, gb)
    frame(app, n=2)
    if jornadas == 4:
        app.tab = "liga"
        shot(app, "09_liga_j5")
        app.tab = "alineacion"
    jornadas += 1
print("jornadas jugadas:", jornadas, "| pos final:", app.liga.posicion(club), "| pts:", club.pts)
print("presupuesto:", club.presupuesto)
app.ir("fin")
shot(app, "10_fin")
print("OK")
