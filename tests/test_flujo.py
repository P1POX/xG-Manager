"""Prueba de flujo con clics reales (sin ventana): recorre menús, hub, partido, minijuegos y descanso.

Uso:  python tests/test_flujo.py
Cada botón se pulsa por su etiqueta (ui.log) para comprobar que responde. Guarda capturas en shots/.
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

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
                    ("liga", "Liga"), ("calendario", "Calendario"), ("datos", "Datos y modelos")):
    clic(app, nombre)
    assert app.tab == tab, (tab, app.tab)
    pulsados = set()
    for _ in range(40):
        bs = [b for b in botones(app) if b[2] and b[1] not in pulsados and not b[1].startswith(("Jugar jornada", "Ver resultado", "Guardar y salir"))
              and b[1] not in ("Alineación", "Mercado", "Táctica", "Liga", "Calendario", "Datos y modelos")]
        if not bs:
            break
        rect, lab, _ = bs[0]
        pulsados.add(lab)
        frame(app, click=rect.center, n=2)
        assert app.escena == "hub", f"'{lab}' sacó del hub"
        app.tab = tab
    assert len({j.id for j in club.once if j is not None}) == 11, f"once inválido tras pulsar botones en {tab}"
    paso(f"pestaña {nombre}: {len(pulsados)} botones pulsados sin errores")

# ------------------------------------------------------------------ mercado: orden por criterio, ascendente y descendente
clic(app, "Mercado")
m = app.mercado
claves_orden = {"ovr": lambda q: q.ovr, "pot": lambda q: q.pot, "edad": lambda q: q.edad,
                "precio": lambda q: app.mundo.precio(q)}
for o, lab in (("ovr", "OVR"), ("pot", "Potencial"), ("edad", "Edad"), ("precio", "Precio")):
    clic(app, lab)
    frame(app, n=2)
    assert m["orden"] == o and m["asc"] == app.ASC_POR_DEFECTO[o], (o, m["orden"], m["asc"])
    for _ in range(2):
        valores = [claves_orden[o](q) for q in m["cache"][:80]]
        assert valores == sorted(valores, reverse=not m["asc"]), (o, m["asc"])
        clic(app, "Menor a mayor" if m["asc"] else "Mayor a menor")        # el botón muestra el sentido actual
        frame(app, n=2)
paso("mercado: orden por OVR, potencial, edad y precio, ascendente y descendente")

# ------------------------------------------------------------------ alineación: los no disponibles no pueden ser titulares
clic(app, "Alineación")
baja = next(q for q in club.plantel if q not in club.once)
baja.lesion, baja.motivo = 2, "sanción"
app.asignar(0, baja)
assert baja not in club.once, "un suspendido quedó de titular"
app.sel_slot = None
baja.lesion, baja.motivo = 0, "lesión"
paso("alineación: un jugador no disponible no se puede alinear")

# ------------------------------------------------------------------ mercado: ofertas por debajo del precio pedido
clic(app, "Mercado")
mk = app.mercado
frame(app, n=2)
q = next(x for x in mk["cache"] if app.mundo.precio(x) <= club.presupuesto * 0.1 and x not in club.plantel)
pedido = app.mundo.precio(q)
assert app.mundo.prob_oferta(q, pedido) == 1.0, "pagando lo que piden siempre aceptan"
ps = [app.mundo.prob_oferta(q, pedido * r) for r in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99)]
assert ps == sorted(ps) and ps[0] < 0.01 and ps[-1] > 0.5, ps
assert 0.75 <= app.mundo.reserva(q) <= 0.98
presu = club.presupuesto
rng_t = np.random.default_rng(5)
ok_, msg_, acepta = app.mundo.ofrecer(club, q, pedido * 0.5, rng_t)
assert ok_ and not acepta and q not in club.plantel and club.presupuesto == presu, "una oferta de la mitad debe rechazarse"
mk["sel"] = q
frame(app, n=2)
assert any(t.startswith("Fichar por") for t in etiquetas(app)), etiquetas(app)
clic(app, "−5 %")
clic(app, "−5 %")
assert mk["oferta"] < pedido and any(t.startswith("Ofrecer") for t in etiquetas(app))
ronda = app.temporada * 100 + app.liga.jornada
clic(app, "Ofrecer")
if q in club.plantel:                                         # aceptaron: se paga lo ofrecido, no lo pedido
    assert club.presupuesto <= presu - 0.85 * pedido and club.presupuesto >= presu - pedido
    paso_oferta = "aceptada"
else:                                                         # rechazaron: no se reabre la negociación esta jornada
    assert app.rechazos.get(q.id) == ronda
    assert not next(b for b in botones(app) if b[1].startswith("Ofrecer"))[2], "el botón debe quedar inhabilitado"
    paso_oferta = "rechazada"
paso(f"mercado: se puede ofrecer menos del precio (probabilidad creciente con la oferta); esta oferta fue {paso_oferta}")

# ------------------------------------------------------------------ calendario: 38 jornadas y detalle por clic
clic(app, "Calendario")
assert app.tab == "calendario"
total = app.liga.total_jornadas
assert all(app._partido_de(i, club) for i in range(total)), "falta un partido en el calendario"
assert sum(1 for i in range(total) if app._partido_de(i, club)[0] is club) == total // 2, "mitad local, mitad visitante"
frame(app, n=2)
d = app.fecha(app.liga.jornada)
assert d == app.fecha(app.liga.jornada) and all(app.fecha(i) < app.fecha(i + 1) for i in range(total - 1)), "fechas desordenadas"
celda = app._rect_celda(*divmod(dt.date(d.year, d.month, 1).weekday() + d.day - 1, 7))
clic_xy(app, celda.center)                                   # clic en el día del próximo partido
assert app.cal_sel == app.liga.jornada, (app.cal_sel, app.liga.jornada)
mes0 = app.cal_mes
clic(app, "›")
assert app.cal_mes != mes0
clic(app, "‹")
assert app.cal_mes == mes0
clic(app, "›")
clic(app, "Próximo partido")
assert app.cal_mes is None or app.cal_mes == mes0
paso("calendario: 38 partidos (19 de local), fechas crecientes, clic en un día y navegación entre meses")

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

# límite de tiempo: sin tocar nada, el disparo sale solo
for tipo, fav in (("penal", True), ("penal", False), ("tiro_libre", True), ("ocasion", True)):
    e = inyectar(app, tipo, fav)
    assert avanzar_hasta(app, lambda: p["pausa"] == "mini" and p["ev_mini"] is e)
    m = p["mini"]
    frame(app, n=int(m.limite) + 2, dt=1000)
    assert m.tarde and m.fase == "rev" and m.resultado in ("gol", "fallo"), (tipo, fav, m.fase, m.tarde)
    assert m.detalle.startswith("¡Se acabó el tiempo!")
    clic(app, "Continuar")
    assert p["pausa"] is None and e["res"] in ("gol", "fallo")
paso("límite de tiempo: el disparo sale solo en los 4 casos")

# distancia variable del tiro libre: más cerca = más probable; la crónica la muestra
assert ev.prob_conv("tiro_libre", 80, 75, 18) > ev.prob_conv("tiro_libre", 80, 75, 23) > ev.prob_conv("tiro_libre", 80, 75, 28)
libres = [x for x in p["est"]["eventos"] if x["tipo"] == "tiro_libre" and "dist" in x]
assert all(ev.DIST_LIBRE[0] <= x["dist"] <= ev.DIST_LIBRE[1] for x in libres)
if libres:
    assert f"a {libres[0]['dist']} m" in ev.describir(libres[0], p["est"]["clubes"])[0]
paso(f"tiro libre a distancia variable ({len(libres)} en este partido, entre 18 y 28 m)")

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
avanzar_hasta(app, lambda: p["min"] >= 47)
assert p["min"] >= 47 and p["tramo"] == 2
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
