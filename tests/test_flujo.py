"""Prueba de flujo con clics reales (sin ventana): recorre menús, hub, partido, minijuegos y descanso.

Uso:  python tests/test_flujo.py
Cada botón se pulsa por su etiqueta (ui.log) para comprobar que responde. Guarda capturas en shots/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import (App, avanzar_hasta, botones, captura, clic, clic_xy, etiquetas, frame, inyectar,  # noqa: E402
                   pygame)

from juego import eventos as ev  # noqa: E402
from juego.minijuegos import PORTERIA  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


def centro_zona(c, f):
    return (PORTERIA.x + PORTERIA.w // 6 + c * PORTERIA.w // 3, PORTERIA.y + PORTERIA.h // 4 + f * PORTERIA.h // 2)


app = App(seed=11)

# ------------------------------------------------------------------ menú
assert set(etiquetas(app)) >= {"Nueva temporada", "¿Cómo se juega?", "Salir"}
clic(app, "¿Cómo se juega?")
assert app.ayuda is True
clic(app, "¿Cómo se juega?")
assert app.ayuda is False
paso("menú: ayuda se abre y se cierra")
clic(app, "Nueva temporada", n=6)
assert app.escena == "liga", app.escena
clic(app, "← Menú")
assert app.escena == "menu"
clic(app, "Nueva temporada", n=6)
clic_xy(app, (160, 325))                     # primera liga
assert app.escena == "club", app.escena
clic(app, "← Ligas")
assert app.escena == "liga"
clic_xy(app, (160, 325))
clic_xy(app, (300, 148 + 25 * 3))            # cuarto club de la lista
assert app.club_sel is not None
clic(app, "Dirigir al")
assert app.escena == "hub", app.escena
paso("menú → liga → club → hub")

# ------------------------------------------------------------------ hub: cada pestaña y cada botón
club = app.club
for tab, nombre in (("alineacion", "Alineación"), ("mercado", "Mercado"), ("tactica", "Táctica"),
                    ("liga", "Liga"), ("datos", "Datos y modelos")):
    clic(app, nombre)
    assert app.tab == tab, (tab, app.tab)
    pulsados = set()
    for _ in range(40):
        bs = [b for b in botones(app) if b[2] and b[1] not in pulsados and not b[1].startswith(("Jugar jornada", "Ver resultado", "Guardar y salir"))
              and b[1] not in ("Alineación", "Mercado", "Táctica", "Liga", "Datos y modelos")]
        if not bs:
            break
        rect, lab, _ = bs[0]
        pulsados.add(lab)
        frame(app, click=rect.center, n=2)
        assert app.escena == "hub", f"'{lab}' sacó del hub"
        app.tab = tab
    assert len({j.id for j in club.once if j is not None}) == 11, f"once inválido tras pulsar botones en {tab}"
    paso(f"pestaña {nombre}: {len(pulsados)} botones pulsados sin errores")

# ------------------------------------------------------------------ previa
clic(app, "Alineación")
clic(app, "Jugar jornada")
assert app.escena == "partido" and app.p["fase"] == "pre"
captura(app, "06_previa")
clic(app, "← Volver")
assert app.escena == "hub"
clic(app, "Jugar jornada")
paso("previa: Volver y Jugar jornada")
clic(app, "Jugar el partido")
assert app.p["fase"] == "vivo"

# ------------------------------------------------------------------ partido en vivo
p = app.p
assert {"Omitir partido", "x1", "x2", "x4"} <= set(etiquetas(app)), etiquetas(app)
clic(app, "x2")
assert p["vel"] == 2
clic(app, "x4")
assert p["vel"] == 4
while p["pausa"] == "mini":              # a veces ya salió una jugada interactiva: se simula
    clic(app, "Simular jugada")
clic(app, "x1")
assert p["vel"] == 1
paso("velocidad x1/x2/x4")
avanzar_hasta(app, lambda: p["min"] >= 12)
captura(app, "07_partido_vivo")

# minijuego: penal a favor (jugado a mano)
e = inyectar(app, "penal", True)
assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e), "no apareció el minijuego"
captura(app, "11_penal_elegir_zona")
clic_xy(app, centro_zona(0, 1))
captura(app, "11b_penal_barra")
clic_xy(app, (640, 300))
frame(app, n=12, dt=100)
captura(app, "11c_penal_resultado")
assert p["mini"].resultado in ("gol", "fallo")
clic(app, "Continuar")
assert p["pausa"] is None and e["res"] in ("gol", "fallo") and not e["pend"], (p["pausa"], e["res"], e["pend"], p["min"], p["vel"])
paso(f"penal a favor jugado a mano → {e['res']}")

# minijuego: penal en contra
e = inyectar(app, "penal", False)
assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e)
captura(app, "12_penal_contra")
clic_xy(app, centro_zona(2, 1))
frame(app, n=12, dt=100)
captura(app, "12b_penal_contra_resultado")
clic(app, "Continuar")
assert p["pausa"] is None and e["res"] in ("gol", "fallo")
paso(f"penal en contra (atajar) → {e['res']}")

# minijuego: tiro libre y ocasión (clic para disparar)
for tipo, nombre in (("tiro_libre", "13_tiro_libre"), ("ocasion", "14_ocasion")):
    e = inyectar(app, tipo, True)
    assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e)
    frame(app, n=5, dt=40)
    captura(app, nombre)
    clic_xy(app, (640, 300))
    frame(app, n=12, dt=100)
    captura(app, nombre + "_resultado")
    clic(app, "Continuar")
    assert p["pausa"] is None and e["res"] in ("gol", "fallo")
    paso(f"{tipo} jugado a mano → {e['res']}")

# 'Simular jugada' en cada tipo
for tipo, fav in (("penal", True), ("penal", False), ("tiro_libre", True), ("ocasion", True)):
    e = inyectar(app, tipo, fav)
    assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e)
    clic(app, "Simular jugada")
    assert p["pausa"] is None and e["res"] in ("gol", "fallo"), (tipo, fav)
paso("'Simular jugada' en los 4 casos")

# barra de espacio / Enter como atajo
e = inyectar(app, "ocasion", True)
assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e)
frame(app, teclas=(pygame.K_SPACE,), n=2)
frame(app, n=12, dt=100)
frame(app, teclas=(pygame.K_RETURN,), n=2)
assert p["pausa"] is None and e["res"] in ("gol", "fallo")
paso("atajos de teclado ESPACIO / ENTER")

# ------------------------------------------------------------------ descanso
assert avanzar_hasta(app, lambda: p["pausa"] == "descanso"), "no llegó el descanso"
captura(app, "15_descanso")
for nombre, clave in (("Atacar", "atk"), ("Cerrarse", "def"), ("Equilibrado", "eq")):
    clic(app, nombre)
    assert p["mentalidad"] == clave, (nombre, p["mentalidad"])
clic(app, "Atacar")
clic(app, "Empezar el 2.º tiempo")
assert p["tramo"] == 2 and p["pausa"] is None
assert any(e["min"] > 45 for e in p["est"]["eventos"])
paso("descanso: mentalidades y 2.º tiempo")

# ------------------------------------------------------------------ Omitir (con minijuego pendiente)
inyectar(app, "penal", True)
assert avanzar_hasta(app, lambda: p["pausa"] == "mini" or p["fin"])
clic(app, "Omitir partido") if p["pausa"] is None else app.omitir_partido()
frame(app, n=2)
assert p["fin"] and p["min"] == 90 and p["pausa"] is None
assert all(not x["pend"] or x["res"] is not None for x in p["est"]["eventos"]), "quedó una jugada sin resolver"
captura(app, "16_partido_final")
paso("Omitir partido llega al final y resuelve las jugadas pendientes")

j0 = app.liga.jornada
pts0 = club.pj
clic(app, "Continuar")
assert app.escena in ("hub", "fin") and app.liga.jornada == j0 + 1 and club.pj == pts0 + 1
paso("Continuar cierra la jornada y actualiza la tabla")

# ------------------------------------------------------------------ Omitir directo desde el inicio, varias jornadas
for _ in range(6):
    clic(app, "Jugar jornada")
    clic(app, "Jugar el partido")
    clic(app, "Omitir partido")
    assert app.p["fin"]
    clic(app, "Continuar")
assert app.escena == "hub"
paso("6 jornadas seguidas con Omitir")

# Omitir pulsado en pleno primer tiempo: el botón tiene el icono (comprobado visualmente en la captura)
clic(app, "Jugar jornada")
clic(app, "Jugar el partido")
avanzar_hasta(app, lambda: app.p["min"] >= 5)
captura(app, "07b_boton_omitir")
clic(app, "Omitir partido")
assert app.p["fin"]
clic(app, "Continuar")

print(f"\n{len(OK)} comprobaciones OK")
