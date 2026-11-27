"""Guardado y carga de la temporada (un solo archivo JSON por usuario, fuera de la carpeta del proyecto).

Se guarda solo lo que cambia durante la partida (plantillas, alineaciones, presupuestos, tabla, calendario, lesiones,
táctica y semillas aleatorias). Los jugadores y los modelos se vuelven a cargar de data/ y models/, así que el archivo
pesa poco y no depende de la versión de las librerías (a diferencia de pickle).

Ubicación: %APPDATA%\\xG-Manager\\partida.json en Windows, ~/.local/share/xG-Manager/ en Linux y
~/Library/Application Support/xG-Manager/ en macOS. La variable de entorno XG_SAVE_DIR la cambia (la usan las pruebas).
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from . import ascensos as AS
from .champions import Champions
from .copa import Copa
from .fechas import TEMPORADA_BASE
from .modelo import Liga

VERSION = 1


def carpeta():
    if os.environ.get("XG_SAVE_DIR"):
        return Path(os.environ["XG_SAVE_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "xG-Manager"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "xG-Manager"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "xG-Manager"


def ruta():
    return carpeta() / "partida.json"


def existe():
    return ruta().exists()


def borrar():
    try:
        ruta().unlink()
    except FileNotFoundError:
        pass


def _estado_rng(rng):
    return rng.bit_generator.state


def _poner_rng(rng, estado):
    rng.bit_generator.state = estado


def guardar(app):
    """Escribe la partida actual (de forma atómica: primero un archivo temporal y luego se reemplaza)."""
    m, liga, club = app.mundo, app.liga, app.club
    datos = {
        "version": VERSION,
        "guardado": time.strftime("%Y-%m-%d %H:%M:%S"),
        "resumen": {"club": club.nombre, "liga": club.liga, "jornada": liga.jornada,
                    "total": liga.total_jornadas, "posicion": liga.posicion(club), "pts": club.pts},
        "seed": app.seed,
        "temporada": app.temporada,
        "copa": app.copa.a_dict() if app.copa else None,
        "champions": app.champions.a_dict() if app.champions else None,
        "ordenes_prev": app._ordenes_prev,
        "divisiones": AS.a_dict(m),
        "historial": app.historial_temporadas,
        "retirados": sorted(m.retirados),
        "club_id": club.id,
        "liga_nombre": app.liga_nombre,
        "objetivo_pos": app.objetivo_pos,
        "ultimos": [list(r) for r in app.ultimos],
        "rng_app": _estado_rng(app.rng),
        "rng_mundo": _estado_rng(m.rng),
        "markup": [round(float(x), 6) for x in m.markup],
        "externos": [j.id for j in m.externos],
        "lesionados": {str(j.id): [j.lesion, j.motivo] for j in m.jugadores.values() if j.lesion > 0},
        "jugadores": _estadisticas(m) if (app.temporada != TEMPORADA_BASE or m.retirados) else {},
        "clubes": {str(c.id): {
            "ovr": c.ovr,
            "plantel": [j.id for j in c.plantel],
            "once": [None if j is None else j.id for j in c.once],
            "formacion": c.formacion, "presupuesto": c.presupuesto, "tactica": c.tactica,
            "pj": c.pj, "g": c.g, "e": c.e, "p": c.p, "gf": c.gf, "gc": c.gc,
        } for c in m.clubes.values()},
        "liga": {"jornada": liga.jornada,
                 "calendario": [[list(p) for p in r] for r in liga.calendario],
                 "historial": [[list(x) for x in r] for r in liga.historial]},
    }
    destino = ruta()
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destino)


def _estadisticas(m):
    """Lo que cambia con la evolución de los jugadores (solo se guarda si ya pasó alguna temporada)."""
    res = {}
    for c in m.clubes.values():
        for j in c.plantel:
            res[str(j.id)] = _fila(j)
    for j in m.externos:
        res[str(j.id)] = _fila(j)
    return res


def _fila(j):
    return [j.ovr, j.pot, j.edad, round(j.valor), round(j.valor_pred)] + list(j.rasgos.values())


def leer():
    """Devuelve (datos, error). Si no hay partida, ambos son None; si está dañada o es de otra versión, error es texto."""
    if not existe():
        return None, None
    try:
        datos = json.loads(ruta().read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"No se pudo leer la partida guardada ({e})."
    if datos.get("version") != VERSION:
        return None, "La partida guardada es de otra versión del juego y no se puede cargar."
    return datos, None


def resumen(datos):
    r = datos["resumen"]
    return f"{r['club']} · {r['liga']} · jornada {r['jornada']}/{r['total']}"


def aplicar(app, datos):
    """Restaura la partida sobre un mundo recién cargado (app.mundo ya existe, con los datos originales)."""
    m = app.mundo
    por_id = m.jugadores
    m.retirados = set(datos.get("retirados", []))
    if datos.get("divisiones"):                                     # ascensos y descensos de temporadas anteriores
        AS.de_dict(m, datos["divisiones"])
    for i, f in datos.get("jugadores", {}).items():                 # evolución de jugadores de temporadas anteriores
        j = por_id[int(i)]
        j.ovr, j.pot, j.edad, j.valor, j.valor_pred = f[0], f[1], f[2], float(f[3]), float(f[4])
        j.rasgos = dict(zip(j.rasgos.keys(), f[5:]))
    for cid, d in datos["clubes"].items():
        c = m.clubes[int(cid)]
        c.ovr = d.get("ovr", c.ovr)
        c.plantel = [por_id[i] for i in d["plantel"]]
        c.once = [None if i is None else por_id[i] for i in d["once"]]
        c.formacion, c.presupuesto, c.tactica = d["formacion"], d["presupuesto"], d["tactica"]
        c.pj, c.g, c.e, c.p, c.gf, c.gc = d["pj"], d["g"], d["e"], d["p"], d["gf"], d["gc"]
        for j in c.plantel:
            j.club_id = c.id
    m.externos = [por_id[i] for i in datos["externos"]]
    for j in m.externos:
        if j.club_id in m.clubes:                 # lo vendió un club simulado: queda libre
            j.club_id = -1
    for j in por_id.values():
        j.lesion, j.motivo = 0, "lesión"
    for i, (n, motivo) in datos["lesionados"].items():
        por_id[int(i)].lesion, por_id[int(i)].motivo = n, motivo
    m.markup = np.array(datos["markup"], dtype=float)
    _poner_rng(m.rng, datos["rng_mundo"])
    _poner_rng(app.rng, datos["rng_app"])

    club = m.clubes[datos["club_id"]]
    ids = m.ligas[datos["liga_nombre"]] if club.division == 1 else m.segunda[datos["liga_nombre"]]
    clubes = [m.clubes[i] for i in ids]
    liga = Liga(club.liga, clubes, app.rng)
    liga.calendario = [[tuple(p) for p in r] for r in datos["liga"]["calendario"]]
    liga.historial = [[tuple(x) for x in r] for r in datos["liga"]["historial"]]
    liga.jornada = datos["liga"]["jornada"]
    _poner_rng(app.rng, datos["rng_app"])         # Liga() barajó un calendario nuevo con el rng: se restituye el estado guardado

    app.temporada = datos.get("temporada", TEMPORADA_BASE)
    app.copa = Copa.de_dict(datos["copa"]) if datos.get("copa") else None      # partidas antiguas: sin copa
    app.copa_sel = None
    app.champions = Champions.de_dict(datos["champions"]) if datos.get("champions") else None   # partidas antiguas: sin Champions
    if app.champions:
        app.champions.preparar(m)
    app.champ_sel = None
    app._ordenes_prev = datos.get("ordenes_prev")
    app.historial_temporadas = datos.get("historial", [])
    m.invalidar_prediccion()
    app.club, app.liga, app.liga_nombre = club, liga, datos["liga_nombre"]
    app.objetivo_pos = datos["objetivo_pos"]
    app.ultimos = [tuple(r) for r in datos["ultimos"]]
    app.sel_slot = app.sel_jug = None
    app.p = None
    app.mercado.update(sel=None, cache=None, clave=None, reemplazo=None, pagina=0)
    app.tab = "alineacion"
