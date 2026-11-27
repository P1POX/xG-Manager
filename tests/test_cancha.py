"""Prueba de la vista animada: juega partidos completos a x4 y revisa que la animación sea coherente con la crónica.

Uso:  python tests/test_cancha.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, avanzar_hasta, clic, frame  # noqa: E402

from juego import eventos as ev  # noqa: E402
from juego.cancha import POSTE, VistaPartido  # noqa: E402

app = App(seed=21)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "Premier League"
club = next(c for c in app.mundo.clubes.values() if c.nombre == "Manchester City")
app.iniciar_temporada(club)
frame(app, n=2)

# se cuentan los remates que terminan en la red y los de juego que caerían dentro de los palos
dentro, cosmeticos_dentro = [], []
orig = VistaPartido._fin_tiro


def espia(self, v):
    (dentro if v["dentro"] else cosmeticos_dentro).append(v)
    return orig(self, v)


VistaPartido._fin_tiro = espia

total_goles = 0
fuera_de_limites = 0
for jornada in range(3):
    dentro.clear()
    cosmeticos_dentro.clear()
    clic(app, "Jugar jornada")
    clic(app, "Jugar el partido")
    p = app.p
    p["vel"] = 4
    vista = p["vista"]

    def sondeo():
        global fuera_de_limites
        for lado in ("a", "b"):
            for j in vista.eq[lado]:
                if not (0 <= j.x <= 1 and 0 <= j.y <= 1):
                    fuera_de_limites += 1
        if not (-0.001 <= vista.bx <= 1.001 and -0.001 <= vista.by <= 1.001):
            fuera_de_limites += 1
        if p["pausa"] == "descanso":
            app.p["mentalidad"] = "eq"
            app._segundo_tiempo()
        return p["fin"]
    assert avanzar_hasta(app, sondeo, max_cuadros=20000, dt=90), "el partido no terminó"
    goles = sum(1 for e in p["est"]["eventos"] if ev.es_gol(e))
    total_goles += goles
    # los goles de los últimos minutos pueden no alcanzar a actuarse antes del pitazo final
    assert goles - 2 <= len(dentro) <= goles, f"goles {goles} vs animados {len(dentro)}"
    for v in cosmeticos_dentro:
        assert not (abs(v["ey"] - 0.5) < POSTE and v["tirador"] and v["ex"] in (0.0, 1.0)), "un tiro de juego entró en la red"
    print("    minutos de gol:", [e["min"] for e in p["est"]["eventos"] if ev.es_gol(e)], "| cola:", len(vista.cola), vista.fase)
    print(f"  ok · partido {jornada + 1}: {goles} goles en la crónica, {len(dentro)} actuados, "
          f"{len(cosmeticos_dentro)} remates sin gol")
    clic(app, "Omitir partido") if not p["fin"] else None
    clic(app, "Continuar")

assert fuera_de_limites == 0, f"{fuera_de_limites} muestreos con jugadores o pelota fuera de la cancha"
print("  ok · jugadores y pelota siempre dentro de la cancha")
VistaPartido._fin_tiro = orig
print("\nvista animada OK")
