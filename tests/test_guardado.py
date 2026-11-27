"""Prueba de guardado y carga: la partida restaurada debe ser idéntica y seguir igual que la original.

Uso:  python tests/test_guardado.py      (usa shots/_saves, nunca tu partida real)
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ, App, clic, etiquetas, frame, nueva_app  # noqa: E402

from juego import guardado as G  # noqa: E402

shutil.rmtree(RAIZ / "shots" / "_saves", ignore_errors=True)
OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


def foto(app):
    """Resumen comparable de todo lo que cambia durante la partida."""
    m, liga = app.mundo, app.liga
    return {
        "jornada": liga.jornada,
        "tabla": [(c.id, c.pj, c.g, c.e, c.p, c.gf, c.gc, c.presupuesto, c.formacion) for c in liga.tabla()],
        "clubes": {c.id: ([j.id for j in c.plantel], [None if j is None else j.id for j in c.once], dict(c.tactica))
                   for c in m.clubes.values()},
        "externos": sorted(j.id for j in m.externos),
        "lesion": {j.id: (j.lesion, j.motivo) for j in m.jugadores.values() if j.lesion},
        "club": app.club.id, "obj": app.objetivo_pos, "historial": [list(map(list, r)) for r in liga.historial],
    }


def jugar(app, n):
    for _ in range(n):
        clic(app, "Jugar jornada")
        clic(app, "Jugar el partido")
        clic(app, "Omitir partido")
        clic(app, "Continuar")


# ------------------------------------------------------------------ sin partida guardada
app = App(seed=5)
assert "Continuar temporada" not in etiquetas(app)
paso("menú sin partida: no hay 'Continuar temporada'")

# ------------------------------------------------------------------ jugar, cambiar cosas y comprobar el autoguardado
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
club = next(c for c in app.mundo.clubes.values() if c.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)
club.tactica["defensa"] = "Replegar"
ok, _ = app.mundo.vender(club, club.plantel[-1])
assert ok
jugar(app, 3)
assert G.existe(), "el autoguardado no creó el archivo"
datos, err = G.leer()
assert err is None and datos["liga"]["jornada"] == 3 and datos["resumen"]["club"] == "Real Madrid"
paso(f"autoguardado tras 3 jornadas: {G.resumen(datos)}")

clic(app, "Guardar y salir")
assert app.escena == "menu"
paso("'Guardar y salir' vuelve al menú")
ref = foto(app)

# ------------------------------------------------------------------ la original sigue jugando (para comparar después)
copia = RAIZ / "shots" / "partida_copia.json"
shutil.copyfile(G.ruta(), copia)
app.ir("hub")
frame(app, n=2)
jugar(app, 2)
esperado = foto(app)

# ------------------------------------------------------------------ nueva instancia: continuar desde la copia
shutil.copyfile(copia, G.ruta())
app = nueva_app(99)                                       # otra semilla: todo debe venir del archivo
assert "Continuar temporada" in etiquetas(app)
clic(app, "Continuar temporada")
frame(app, n=6)
assert app.escena == "hub", app.escena
assert foto(app) == ref, "la partida restaurada no coincide con la guardada"
paso("'Continuar temporada' restaura exactamente la partida (tabla, plantillas, táctica, lesiones, historial)")

jugar(app, 2)
assert foto(app) == esperado, "tras restaurar, el desarrollo de la liga es distinto al de la partida original"
paso("2 jornadas más: la partida continuada evoluciona igual que la original")

# ------------------------------------------------------------------ 'Nueva temporada' pide confirmación
clic(app, "Guardar y salir")
frame(app, n=2)
clic(app, "Nueva temporada")
assert app.escena == "menu" and app._confirmar_nueva, "el primer clic debía solo avisar"
clic(app, "Nueva temporada", n=6)
assert app.escena in ("cargando", "liga")
paso("'Nueva temporada' con partida guardada pide confirmar antes de empezar de cero")

# ------------------------------------------------------------------ archivo dañado / de otra versión
ruta = G.ruta()
ruta.write_text("{esto no es json", encoding="utf-8")
app3 = nueva_app(1)
et = etiquetas(app3)
assert "Continuar temporada" not in et and "Nueva temporada" in et
paso("archivo dañado: el menú no se rompe y permite empezar de nuevo")
ruta.write_text(json.dumps({"version": 999}), encoding="utf-8")
app4 = nueva_app(1)
assert "Continuar temporada" not in etiquetas(app4)
paso("guardado de otra versión: se ignora con aviso")

# datos válidos pero incoherentes: cargar falla y se vuelve al menú sin tumbar el juego
ruta.write_text(json.dumps({"version": G.VERSION, "resumen": {
    "club": "X", "liga": "Y", "jornada": 1, "total": 38, "posicion": 1, "pts": 0}, "clubes": {"1": {}}}),
    encoding="utf-8")
app5 = nueva_app(1)
clic(app5, "Continuar temporada")
frame(app5, n=8)
assert app5.escena == "menu", app5.escena
paso("guardado incoherente: avisa y vuelve al menú sin cerrarse")

# ------------------------------------------------------------------ al terminar la temporada la partida sigue guardada
G.borrar()
app6 = nueva_app(3)
app6.ir("cargando")
frame(app6, n=4)
app6.liga_nombre = "Serie A"
app6.iniciar_temporada(next(c for c in app6.mundo.clubes.values() if c.liga == "Serie A"))
frame(app6, n=2)
jugar(app6, 1)
assert G.existe()
while not app6.liga.terminada:
    jugar(app6, 1)
assert G.existe(), "al terminar la liga la partida debe seguir guardada (modo carrera)"
assert app6.escena == "fin"
app7 = nueva_app(4)
clic(app7, "Continuar temporada")
frame(app7, n=8)
assert app7.escena == "hub" and app7.liga.terminada, (app7.escena, app7.liga.terminada)
assert "Ver resultado final" in etiquetas(app7)
paso("al terminar la temporada la partida sigue guardada y al continuar se ofrece 'Ver resultado final'")

shutil.rmtree(RAIZ / "shots" / "_saves", ignore_errors=True)
print(f"\n{len(OK)} comprobaciones OK")
