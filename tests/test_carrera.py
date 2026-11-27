"""Prueba del modo carrera: modelo de evolución, paso de temporada y continuidad tras guardar.

Uso:  python tests/test_carrera.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ, App, captura, clic, frame, nueva_app  # noqa: E402

from juego import evolucion as EV  # noqa: E402
from juego import eventos as ev  # noqa: E402
from juego import guardado as G  # noqa: E402
from juego.modelo import GRUPOS  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


app = App(seed=5)
app.ir("cargando")
frame(app, n=4)
m = app.mundo
app.liga_nombre = "La Liga"
club = next(c for c in m.clubes.values() if c.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)

# ------------------------------------------------------------------ 1. el modelo reproduce la curva de edad
todos = [j for c in m.clubes.values() for j in c.plantel] + list(m.externos)
pred = EV.predecir(todos)
mu = np.array([p[0] for p in pred])
edad = np.array([j.edad for j in todos])
assert mu[edad <= 19].mean() > 1.5, "los muy jóvenes deberían mejorar"
assert mu[edad >= 33].mean() < 0, "los veteranos deberían decaer"
assert all(0 <= p[2] <= 1 and 0 <= p[3] <= 1 and p[1] > 0 for p in pred)
joven = max((j for j in todos if j.edad <= 19), key=lambda j: j.pot - j.ovr)
viejo = max((j for j in todos if j.edad >= 34), key=lambda j: j.edad)
assert m.prediccion(joven)[2] > m.prediccion(viejo)[2], "el joven con margen debería tener más prob. de mejorar"
paso("modelo: los jóvenes mejoran, los veteranos decaen, y la prob. de mejorar es mayor en el joven con potencial")

# ------------------------------------------------------------------ 2. paso de temporada sobre el mundo
ids = {j.id: (j.edad, j.ovr) for j in todos}
rng = np.random.default_rng(1)
res = EV.avanzar_temporada(m, rng, club, {c.id: i + 1 for i, c in enumerate(m.clubes.values())})
activos = [j for c in m.clubes.values() for j in c.plantel] + list(m.externos)
assert all(j.edad == ids[j.id][0] + 1 for j in activos), "todos deberían tener un año más"
assert all(EV.OVR_MIN <= j.ovr <= EV.OVR_MAX and j.ovr <= j.pot <= EV.POT_MAX for j in activos)
assert not (m.retirados & {j.id for j in activos}), "un retirado sigue en un club o en el mercado"
assert len(m.retirados) > 300
d = np.array([j.ovr - ids[j.id][1] for j in activos])
e0 = np.array([ids[j.id][0] for j in activos])
joven_m, medio_m, viejo_m = d[e0 <= 19].mean(), d[(e0 >= 29) & (e0 <= 31)].mean(), d[e0 >= 35].mean()
assert 1.5 < joven_m < 4.2 and -0.9 < medio_m < 0.7 and viejo_m < 0, (joven_m, medio_m, viejo_m)
for c in m.clubes.values():
    assert len(c.plantel) >= 18, (c.nombre, len(c.plantel))
    for g in GRUPOS:
        assert sum(1 for j in c.plantel if j.grupo == g) >= 2, (c.nombre, g)
    assert all(j is not None and j in c.plantel for j in c.once), f"once inválido en {c.nombre}"
    assert len({j.id for j in c.once}) == 11
paso(f"temporada: +1 año a todos, curva por edad coherente, {len(m.retirados)} salidas, plantillas y onces válidos")

# ------------------------------------------------------------------ 3. flujo completo en la aplicación
app2 = nueva_app(9)
app2.ir("cargando")
frame(app2, n=4)
app2.liga_nombre = "Serie A"
club2 = next(c for c in app2.mundo.clubes.values() if c.liga == "Serie A")
app2.iniciar_temporada(club2)
frame(app2, n=2)
while not app2.liga.terminada:
    app2.preparar_partido()
    frame(app2)
    app2.iniciar_partido()
    app2.omitir_partido()
    frame(app2, n=2)
    ga, gb = ev.marcador(app2.p["est"]["eventos"])
    app2.cerrar_jornada(ga, gb)
    frame(app2, n=2)
assert app2.escena == "fin" and len(app2.historial_temporadas) == 1
assert G.existe(), "al terminar la temporada la partida debe quedar guardada"
paso("fin de temporada: queda guardada y registrada en el historial")

ovr_antes = {j.id: j.ovr for j in club2.plantel}
clic(app2, "Siguiente temporada")
assert app2.escena == "ascensos"
clic(app2, "Continuar")
for _ in range(6):
    frame(app2, n=2)
assert app2.escena == "evolucion" and app2.temporada == 2024, (app2.escena, app2.temporada)
assert app2.liga.jornada == 0 and app2.liga.total_jornadas in (34, 38, 42, 46)
assert app2.fecha(0).year == 2024, app2.fecha(0)
assert any(j.ovr != ovr_antes.get(j.id) for j in club2.plantel), "ningún jugador cambió de OVR"
app2.avisos.clear()
captura(app2, "17_evolucion")
clic(app2, "Empezar la temporada")
assert app2.escena == "hub"
paso("siguiente temporada: pantalla de evolución, calendario de 2024 y liga nueva")

# ------------------------------------------------------------------ 4. guardar y continuar conserva la evolución
app2.tab = "alineacion"
app2.sel_jug = club2.plantel[0]
app2.avisos.clear()
captura(app2, "17b_ficha_evolucion")
clic(app2, "Guardar y salir")
foto = {j.id: (j.ovr, j.pot, j.edad, round(j.valor)) for j in club2.plantel}
ovr_club = {c.id: c.ovr for c in app2.mundo.clubes.values()}
retirados = set(app2.mundo.retirados)
app3 = nueva_app(77)
clic(app3, "Continuar temporada")
frame(app3, n=8)
assert app3.escena == "hub" and app3.temporada == 2024
club3 = app3.club
assert {j.id: (j.ovr, j.pot, j.edad, round(j.valor)) for j in club3.plantel} == foto, "la evolución no se conservó"
assert {c.id: c.ovr for c in app3.mundo.clubes.values()} == ovr_club
assert app3.mundo.retirados == retirados and len(app3.historial_temporadas) == 1
paso("guardar y continuar conserva edades, OVR, valores, retirados e historial de temporadas")

print(f"\n{len(OK)} comprobaciones OK")
