"""Utilidades de prueba: reloj falso, clics por etiqueta de botón y captura de pantalla."""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
RAIZ = Path(__file__).resolve().parent.parent
os.environ["XG_SAVE_DIR"] = str(RAIZ / "shots" / "_saves")      # las pruebas nunca tocan tu partida real
shutil.rmtree(os.environ["XG_SAVE_DIR"], ignore_errors=True)    # cada ejecución parte sin partida guardada
sys.path.insert(0, str(RAIZ))
import pygame  # noqa: E402

T = [0]
pygame.time.get_ticks = lambda: T[0]          # reloj determinista: avanza solo con frame()

from juego.app import App  # noqa: E402

SHOTS = RAIZ / "shots"
SHOTS.mkdir(exist_ok=True)


def frame(app, click=None, n=1, dt=16, teclas=()):
    """Avanza n cuadros; el clic (si hay) llega en el primero. Devuelve la lista de botones del último."""
    for _ in range(n):
        T[0] += dt
        evs = []
        if click:
            evs.append(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=tuple(click), button=1))
        for k in teclas:
            evs.append(pygame.event.Event(pygame.KEYDOWN, key=k))
        app.ui.inicio_frame(evs)
        app.ui.log = []
        app.cuadro()
        app.ui.dibujar_tooltip()
        app.dibujar_avisos()
        click, teclas = None, ()
    return app.ui.log


def botones(app):
    return frame(app)


def etiquetas(app):
    return [b[1] for b in botones(app)]


def clic(app, etiqueta, nth=0, n=2):
    """Pulsa el botón con esa etiqueta (coincidencia exacta o por prefijo). Falla si no existe o está inhabilitado."""
    log = botones(app)
    cand = [b for b in log if b[1] == etiqueta] or [b for b in log if b[1].startswith(etiqueta)]
    assert len(cand) > nth, f"No hay botón '{etiqueta}'. Botones: {[b[1] for b in log]}"
    rect, _, hab = cand[nth]
    assert hab, f"El botón '{etiqueta}' está inhabilitado"
    frame(app, click=rect.center, n=n)


def clic_xy(app, pos, n=2):
    frame(app, click=pos, n=n)


def captura(app, nombre):
    frame(app)
    pygame.image.save(app.pantalla, str(SHOTS / f"{nombre}.png"))


def inyectar(app, tipo, a_favor=True, minutos=1):
    """Agrega al partido en curso una jugada interactiva (penal/tiro_libre/ocasion) para probar los minijuegos."""
    from juego import eventos as ev
    p = app.p
    est = p["est"]
    lado = p["lado"] if a_favor else ("b" if p["lado"] == "a" else "a")
    rival = "b" if lado == "a" else "a"
    j = ev.elegir_ejecutor(est["xi"][lado], tipo, app.rng)
    e = ev._ev(p["min"] + minutos, tipo, lado, j.nombre, tiro=ev.tiro_de(j, tipo),
               gk=ev.portero_de(est["xi"][rival]), ejecutor=j, clave=j.nombre)
    e["pend"] = True
    est["eventos"].append(e)
    est["eventos"].sort(key=lambda x: x["min"])
    return e


def avanzar_hasta(app, cond, max_cuadros=6000, dt=70):
    """Avanza cuadros hasta que cond() sea cierta. Las jugadas clave aleatorias que aparezcan por el camino se
    simulan solas (salvo que cond() las esté esperando)."""
    for _ in range(max_cuadros):
        if cond():
            return True
        p = app.p
        if p and p.get("pausa") == "mini":
            app._cerrar_minijuego("auto")                 # como el botón "Simular jugada"
        frame(app, dt=dt)
    return cond()


def nueva_app(seed=None):
    """Otra instancia de App en el mismo proceso (cierra la ventana anterior: con SCALED solo cabe una)."""
    pygame.display.quit()
    return App(seed=seed)
