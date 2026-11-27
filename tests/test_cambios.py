"""Prueba de cambios y formación durante el partido (lógica + interfaz) y del motor minuto a minuto.

Uso:  python tests/test_cambios.py
"""
import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import App, avanzar_hasta, captura, clic, clic_xy, frame  # noqa: E402

from juego import cambios as CB  # noqa: E402
from juego import eventos as ev  # noqa: E402
from juego.modelo import FORMACIONES  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


app = App(seed=13)
app.ir("cargando")
frame(app, n=4)
m = app.mundo
app.liga_nombre = "La Liga"
club = next(c for c in m.clubes.values() if c.nombre == "Real Madrid")
rival = next(c for c in m.clubes.values() if c.nombre == "Getafe")
app.iniciar_temporada(club)
frame(app, n=2)
bono = app.asist.bono_tactico


def nuevo():
    return ev.nuevo_estado(club, rival, 1.6, 1.0, "a")


def misma_linea(est, entra_grupo, excluir=()):
    """Un titular de campo y un suplente del mismo grupo."""
    for s, j in CB.en_campo(est, "a"):
        if s[0] == "POR" or j.id in excluir:
            continue
        for b in CB.banquillo(est, "a"):
            if b.grupo == j.grupo and b.id not in excluir:
                return j, b
    raise AssertionError("no hay pareja titular-suplente")


# ------------------------------------------------------------------ 1. estado inicial
est = nuevo()
assert CB.restantes(est, "a") == (5, 3)
ban = CB.banquillo(est, "a")
assert len(ban) == ev.BANCA and sum(1 for j in ban if j.grupo == "POR") >= 1
assert not ({j.id for j in ban} & {j.id for _, j in est["xi"]["a"]})
assert len(CB.en_campo(est, "a")) == 11
paso("estado inicial: 5 cambios, 3 paradas, banquillo de 9 con portero suplente y sin repetidos")

# ------------------------------------------------------------------ 2. un cambio: usa cambio y parada y recalcula los goles esperados
sale, entra = misma_linea(est, None)
la0 = est["la"]
ok, msg, evs = CB.aplicar(est, "a", est["formacion"]["a"], [(sale, entra)], 30, bono)
assert ok, msg
assert est["cambios"]["a"] == 1 and est["ventanas"]["a"] == 1
assert entra.id in {j.id for _, j in est["xi"]["a"]} and sale.id not in {j.id for _, j in est["xi"]["a"]}
assert {sale.id, entra.id} <= est["usados"] and sale.id not in {j.id for j in CB.banquillo(est, "a")}
assert evs[0]["tipo"] == "cambio" and "sale" in ev.describir(evs[0], est["clubes"])[1]
assert est["la"] != la0, "los goles esperados no se recalcularon"
paso("un cambio: se registra, gasta 1 cambio y 1 parada, el once cambia y se recalculan los goles esperados")

# ------------------------------------------------------------------ 3. peor jugador por el mejor => baja el ataque
est = nuevo()
mejor = max((j for s, j in CB.en_campo(est, "a") if s[0] == "DEL"), key=lambda j: j.ovr)
peor = min((b for b in CB.banquillo(est, "a") if b.grupo == "DEL"), key=lambda j: j.ovr, default=None)
if peor is None:
    peor = min((b for b in CB.banquillo(est, "a") if b.grupo != "POR"), key=lambda j: j.ovr)
CB.aplicar(est, "a", est["formacion"]["a"], [(mejor, peor)], 60, bono)
assert est["la"] < 1.6 * 0.999 or est["la"] != 1.6
la_peor = est["la"]
est2 = nuevo()
CB.recalcular(est2, bono)
assert la_peor < est2["la"], (la_peor, est2["la"])
paso("sacar al mejor delantero por un suplente peor baja los goles esperados del equipo")

# ------------------------------------------------------------------ 4. límites: 5 cambios y 3 paradas
est = nuevo()
usados = set()
total = 0
for n_sub in (2, 2, 1):                                    # 3 paradas con 2 + 2 + 1 = 5 cambios
    subs = []
    for _ in range(n_sub):
        s_, e_ = misma_linea(est, None, excluir=usados | {x.id for p_ in subs for x in p_})
        subs.append((s_, e_))
    ok, msg, _ = CB.aplicar(est, "a", est["formacion"]["a"], subs, 50 + total, bono)
    assert ok, msg
    usados |= {x.id for p_ in subs for x in p_}
    total += n_sub
assert CB.restantes(est, "a") == (0, 0)
s_, e_ = misma_linea(est, None, excluir=usados)
ok, msg = CB.validar(est, "a", est["formacion"]["a"], [(s_, e_)])
assert not ok, "no debería permitir un 6.º cambio"
est = nuevo()
for k in range(3):                                         # 3 paradas de 1 cambio
    s_, e_ = misma_linea(est, None, excluir=est["usados"])
    assert CB.aplicar(est, "a", est["formacion"]["a"], [(s_, e_)], 40 + k, bono)[0]
s_, e_ = misma_linea(est, None, excluir=est["usados"])
ok, msg = CB.validar(est, "a", est["formacion"]["a"], [(s_, e_)])
assert not ok and "paradas" in msg, msg
ok, msg = CB.validar(est, "a", est["formacion"]["a"], [(s_, e_)], descanso=True)
assert ok, "el descanso no cuenta como parada"
paso("límites: 5 cambios en 3 paradas como máximo; el descanso no cuenta como parada")

# ------------------------------------------------------------------ 5. portero y formación
est = nuevo()
gk = next(j for s, j in CB.en_campo(est, "a") if s[0] == "POR")
fuera = next(b for b in CB.banquillo(est, "a") if b.grupo != "POR")
ok, msg = CB.validar(est, "a", est["formacion"]["a"], [(gk, fuera)])
assert not ok and "portero" in msg
for f in FORMACIONES:
    nuevo_xi, msg = CB.proponer(est, "a", f, [])
    assert nuevo_xi is not None and len(nuevo_xi) == 11 and len({j.id for _, j in nuevo_xi}) == 11, f
    assert sum(1 for s, _ in nuevo_xi if s[0] == "POR") == 1
ok, msg, evs = CB.aplicar(est, "a", "4-3-3" if est["formacion"]["a"] != "4-3-3" else "4-4-2", [], 45, bono, descanso=True)
assert ok and evs[0]["tipo"] == "formacion" and est["ventanas"]["a"] == 0 and est["cambios"]["a"] == 0
assert len(est["xi"]["a"]) == 11 and len(est["slots"]["a"]) == 11
paso("portero obligatorio; las 4 formaciones reparten a los 11 sin repetir; cambiar de formación es libre")

# ------------------------------------------------------------------ 6. lesión sin cambios disponibles: se juega con uno menos
est = nuevo()
est["cambios"] = {"a": 5, "b": 5}
viejo_p = ev.P_LESION
ev.P_LESION = 1e3
try:
    evs = ev.generar_tramo(est, 10, 10, np.random.default_rng(3))
finally:
    ev.P_LESION = viejo_p
les = [e for e in evs if e["tipo"] == "lesion"]
assert les and all(e["entra"] is None for e in les) and len(est["xi"]["a"]) == 10
paso("una lesión sin cambios disponibles deja al equipo con 10")

# ------------------------------------------------------------------ 7. generar minuto a minuto = generar de golpe (estadísticamente)
rng1, rng2 = np.random.default_rng(1), np.random.default_rng(2)
g_min, g_blk, tarj_min, tarj_blk = [], [], [], []
for _ in range(100):
    e1 = nuevo()
    for mn in range(1, 91):
        ev.generar_tramo(e1, mn, mn, rng1)
    g_min.append(sum(1 for x in e1["eventos"] if ev.es_gol(x) or (x["tipo"] in ev.INTERACTIVOS and x["res"] is None)))
    tarj_min.append(sum(1 for x in e1["eventos"] if x["tipo"] in ("amarilla", "roja")))
    e2 = nuevo()
    ev.generar_tramo(e2, 1, 90, rng2)
    g_blk.append(sum(1 for x in e2["eventos"] if ev.es_gol(x) or (x["tipo"] in ev.INTERACTIVOS and x["res"] is None)))
    tarj_blk.append(sum(1 for x in e2["eventos"] if x["tipo"] in ("amarilla", "roja")))
assert abs(np.mean(g_min) - np.mean(g_blk)) < 0.5, (np.mean(g_min), np.mean(g_blk))
assert abs(np.mean(tarj_min) - np.mean(tarj_blk)) < 0.8, (np.mean(tarj_min), np.mean(tarj_blk))
paso(f"motor minuto a minuto ≈ motor por tramos (jugadas {np.mean(g_min):.2f} vs {np.mean(g_blk):.2f}, "
     f"tarjetas {np.mean(tarj_min):.2f} vs {np.mean(tarj_blk):.2f})")

# ------------------------------------------------------------------ 8. interfaz durante el partido
clic(app, "Jugar jornada")
clic(app, "Jugar el partido")
p = app.p
avanzar_hasta(app, lambda: p["min"] >= 20)
assert p["pausa"] is None
lado = p["lado"]
est = p["est"]
nombres = {j.nombre for _, j in est["xi"][lado]}
clic(app, "Cambios y formación")
assert p["pausa"] == "cambios"
cam = p["cam"]
frame(app, n=2)
captura(app, "18_cambios_vacio")
sale, entra = misma_linea(est, None) if lado == "a" else (None, None)
if lado != "a":                                            # el usuario es visitante: misma búsqueda sobre su lado
    for s, j in CB.en_campo(est, lado):
        if s[0] != "POR":
            for b in CB.banquillo(est, lado):
                if b.grupo == j.grupo:
                    sale, entra = j, b
                    break
        if sale:
            break
slot = est["slots"][lado][sale.id]
campo = pygame.Rect(90 + 24, 44 + 92, 400, 520)
px, py = app.ui.pos_campo(campo, slot[1], slot[2])
clic_xy(app, (px, py + 6))
assert cam["sel"] is not None and cam["sel"].id == sale.id
idx = [b.id for b in CB.banquillo(est, lado)].index(entra.id)
clic_xy(app, (90 + 450 + 170, 44 + 92 + 50 + idx * 43 + 20))
assert [(s_.id, e_.id) for s_, e_ in cam["pend"]] == [(sale.id, entra.id)], cam["pend"]
frame(app, n=2)
captura(app, "18b_cambios_pendiente")
clic(app, "Confirmar cambios")
assert p["pausa"] is None and p["cam"] is None
assert est["cambios"][lado] == 1 and est["ventanas"][lado] == 1
assert any(e["tipo"] == "cambio" and e["jug"] == entra.nombre for e in est["eventos"])
vis = [x.nombre for x in p["vista"].eq[lado]]
assert entra.nombre in vis and sale.nombre not in vis, "la cancha animada no reflejó el cambio"
paso("interfaz: elegir al que sale, elegir al que entra y confirmar; queda en la crónica y en la cancha animada")

# formación durante el juego
otra = next(f for f in FORMACIONES if f != est["formacion"][lado])
clic(app, "Cambios y formación")
clic(app, otra)
assert p["cam"]["form"] == otra
clic(app, "Confirmar cambios")
assert est["formacion"][lado] == otra and p["pausa"] is None
assert any(e["tipo"] == "formacion" for e in est["eventos"])
assert len(p["vista"].eq[lado]) == len(est["xi"][lado])
paso(f"interfaz: cambio de formación a {otra} en pleno partido")

# cancelar no cambia nada
usados_antes = dict(est["cambios"])
clic(app, "Cambios y formación")
clic(app, "Cancelar")
assert p["pausa"] is None and est["cambios"] == usados_antes
paso("cancelar cierra el panel sin cambiar nada")

# descanso: los cambios no usan parada y se vuelve al descanso
assert avanzar_hasta(app, lambda: p["pausa"] == "descanso"), "no llegó el descanso"
paradas = est["ventanas"][lado]
clic(app, "Cambios y formación")
assert p["cam"]["prev"] == "descanso"
s2, e2 = None, None
for s, j in CB.en_campo(est, lado):
    if s[0] != "POR":
        for b in CB.banquillo(est, lado):
            if b.grupo == j.grupo:
                s2, e2 = j, b
                break
    if s2:
        break
px, py = app.ui.pos_campo(campo, est["slots"][lado][s2.id][1], est["slots"][lado][s2.id][2])
clic_xy(app, (px, py + 6))
idx = [b.id for b in CB.banquillo(est, lado)].index(e2.id)
clic_xy(app, (90 + 450 + 170, 44 + 92 + 50 + idx * 43 + 20))
clic(app, "Confirmar cambios")
assert p["pausa"] == "descanso" and est["ventanas"][lado] == paradas and est["cambios"][lado] == 2
captura(app, "18c_descanso_tras_cambio")
clic(app, "Empezar el 2.º tiempo")
paso("descanso: se pueden hacer cambios sin gastar parada y se vuelve a la pantalla de descanso")

# el partido termina sin errores y cierra la jornada
clic(app, "Omitir partido")
assert p["fin"]
clic(app, "Continuar")
assert app.escena in ("hub", "fin")
paso("el partido con cambios y formación nueva termina y se cierra la jornada")

print(f"\n{len(OK)} comprobaciones OK")
