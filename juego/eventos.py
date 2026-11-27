"""Eventos de partido: faltas, tarjetas, lesiones, penales, tiros libres y ocasiones.

El resultado sigue saliendo del modelo de Poisson (ver simulacion.py), pero ahora el partido se
genera por tramos (1.º y 2.º tiempo) minuto a minuto. Las jugadas a balón parado y las ocasiones
claras son *interactivas* para el usuario (minijuegos); para los equipos controlados por la IA se
resuelven con una probabilidad que depende de las estadísticas del ejecutor y del portero.

Calibración: OPEN reduce los goles "de juego abierto" para que, sumados los goles de balón parado
y ocasiones, el promedio total siga siendo ~ los goles esperados del modelo.
"""
import numpy as np

from . import simulacion as sim
from .modelo import FORMACIONES

OPEN = 0.75                 # fracción de los goles esperados que llegan por juego abierto
RATE_PENAL = 0.15           # penales por equipo y partido (escala con el ataque)
RATE_TIRO_LIBRE = 0.8
RATE_OCASION = 0.3          # ocasiones claras extra (mano a mano)
FRAC_GOL_JUGABLE = 0.20     # parte de los goles de juego abierto del USUARIO que llegan como ocasión clara jugable
FALTAS = 11.0               # faltas por equipo y partido
P_AMARILLA = 0.14           # prob. de amarilla por falta
P_ROJA_DIRECTA = 0.012      # roja directa por equipo y partido
P_LESION = 0.15             # lesión por equipo y partido
F_ROJA_PROPIA, F_ROJA_RIVAL = 0.72, 1.15

INTERACTIVOS = ("penal", "tiro_libre", "ocasion")


# ---------------------------------------------------------------- probabilidades
DIST_LIBRE = (18, 28)            # distancia (m) de un tiro libre al arco; la media (23 m) no cambia la probabilidad base


def factor_distancia(dist):
    """Más cerca del arco, más fácil: ±4 % de la probabilidad por metro respecto a 23 m (entre 0,6 y 1,4)."""
    return float(np.clip(1 + 0.04 * (23 - dist), 0.6, 1.4)) if dist else 1.0


def prob_conv(tipo, tiro, ovr_portero, dist=None):
    """Probabilidad de gol de una jugada según el tiro del ejecutor y el nivel del portero
    (y, en un tiro libre, la distancia)."""
    if tipo == "penal":
        return float(np.clip(0.78 + 0.004 * (tiro - 75) - 0.004 * (ovr_portero - 75), 0.55, 0.92))
    if tipo == "tiro_libre":
        p = (0.065 + 0.0015 * (tiro - 70) - 0.0012 * (ovr_portero - 75)) * factor_distancia(dist)
        return float(np.clip(p, 0.02, 0.18))
    return float(np.clip(0.33 + 0.007 * (tiro - 70) - 0.007 * (ovr_portero - 75), 0.12, 0.65))


def portero_de(xi):
    """(nombre, overall) del portero titular; un valor por defecto si no hay."""
    for g, j in xi:
        if g == "POR":
            return j.nombre, j.ovr
    return "Portero suplente", 60


def elegir_ejecutor(xi, tipo, rng):
    cand = [(g, j) for g, j in xi if g != "POR"] or list(xi)
    if tipo == "ocasion":
        return sim.goleador(cand, rng)
    if tipo == "tiro_libre":
        pesos = np.array([((j.rasgos["shooting"] + j.rasgos["passing"]) / 140.0) ** 4 for _, j in cand])
    else:
        pesos = np.array([(j.rasgos["shooting"] / 70.0) ** 4 for _, j in cand])
    return cand[int(rng.choice(len(cand), p=pesos / pesos.sum()))][1]


def p_ocasion_media(xi, ovr_portero, tipo="ocasion"):
    """Probabilidad media de convertir una ocasión de este equipo (ponderada por quién suele rematar)."""
    cand = [(g, j) for g, j in xi if g != "POR"]
    if not cand:
        return 0.3
    w = np.array([(j.rasgos["shooting"] / 70.0) ** 4 for _, j in cand])
    p = np.array([prob_conv(tipo, tiro_de(j, tipo), ovr_portero) for _, j in cand])
    return float((w * p).sum() / w.sum())


def tiro_de(j, tipo):
    r = j.rasgos
    return (r["shooting"] + r["passing"]) / 2 if tipo == "tiro_libre" else r["shooting"]


def _infractor(xi, rng):
    cand = [(g, j) for g, j in xi if g != "POR"]
    if not cand:
        return None
    w = np.array([{"DEF": 1.0, "MED": 0.9, "DEL": 0.5}[g] * (j.rasgos["defending"] + 30) / 100 for g, j in cand])
    return cand[int(rng.choice(len(cand), p=w / w.sum()))][1]


MAX_CAMBIOS = 5                  # cambios por partido (regla vigente en las 5 grandes ligas)
MAX_VENTANAS = 3                 # paradas en las que se puede cambiar, sin contar el descanso
BANCA = 9                        # suplentes convocados


def _suplente(club, xi, grupo, usados, banca=None):
    ocupados = {j.id for _, j in xi} | usados
    cand = [j for j in (banca if banca is not None else club.plantel) if j.id not in ocupados and j.lesion == 0]
    return max(cand, key=lambda x: x.rendimiento(grupo)) if cand else None


def elegir_banca(club, xi):
    """Banquillo de 9: el mejor portero suplente y los 8 mejores del resto del plantel disponible."""
    en_campo = {j.id for _, j in xi}
    libres = [j for j in club.plantel if j.id not in en_campo and j.lesion == 0]
    porteros = sorted([j for j in libres if j.grupo == "POR"], key=lambda j: -j.ovr)[:1]
    resto = sorted([j for j in libres if j not in porteros], key=lambda j: -j.ovr)
    return porteros + resto[:BANCA - len(porteros)]


# ---------------------------------------------------------------- generación
def nuevo_estado(L, V, la, lb, usuario=None):
    """usuario: 'a' (local), 'b' (visitante) o None si el partido lo simula la IA."""
    xi = {"a": list(L.xi_con_grupo()), "b": list(V.xi_con_grupo())}
    slots = {}
    for lado, club in (("a", L), ("b", V)):                 # puesto (grupo, x, y) de cada jugador en el campo
        sl = FORMACIONES[club.formacion]
        slots[lado] = {j.id: sl[i] for i, j in enumerate(club.once) if j is not None}
    return {"L": L, "V": V, "clubes": {"a": L, "b": V}, "la": la, "lb": lb, "user": usuario,
            "xi": xi, "slots": slots, "formacion": {"a": L.formacion, "b": V.formacion},
            "banca": {"a": elegir_banca(L, xi["a"]), "b": elegir_banca(V, xi["b"])},
            "cambios": {"a": 0, "b": 0}, "ventanas": {"a": 0, "b": 0},
            "amar": {"a": {}, "b": {}}, "rojas": {"a": [], "b": []}, "f": {"a": 1.0, "b": 1.0},
            "usados": set(), "eventos": [], "bajas": []}


def _ev(m, tipo, lado, jug, **kw):
    e = {"min": int(m), "tipo": tipo, "lado": lado, "jug": jug, "res": None, "pend": False, "oculto": False}
    e.update(kw)
    return e


def autoresolver(e, rng):
    """Resuelve una jugada con la probabilidad del modelo (IA o 'simular automático')."""
    gol = rng.random() < prob_conv(e["tipo"], e["tiro"], e["gk"][1], e.get("dist"))
    e["res"] = "gol" if gol else "fallo"
    e["pend"] = False
    if not gol:
        opciones = {"penal": ["atajado por " + e["gk"][0], "atajado por " + e["gk"][0], "se fue fuera"],
                    "tiro_libre": ["dio en la barrera", "atajado por " + e["gk"][0], "se fue desviado"],
                    "ocasion": ["atajado por " + e["gk"][0], "atajado por " + e["gk"][0], "se fue desviado", "dio en el palo"]}[e["tipo"]]
        e["motivo"] = opciones[int(rng.integers(len(opciones)))]
    return e["res"]


def generar_tramo(est, m0, m1, rng):
    """Genera los eventos de los minutos m0..m1 y los agrega a est['eventos']."""
    n = m1 - m0 + 1
    minutos = np.arange(m0, m1 + 1)
    evs = []
    opuesto = {"a": "b", "b": "a"}
    # ---- faltas, tarjetas y lesiones
    previos = []
    for lado in "ab":
        for m in rng.integers(m0, m1 + 1, rng.poisson(FALTAS * n / 90)):
            previos.append((int(m), lado, "falta"))
        if rng.random() < P_ROJA_DIRECTA * n / 90:
            previos.append((int(rng.integers(m0, m1 + 1)), lado, "roja_directa"))
        if rng.random() < P_LESION * n / 90:
            previos.append((int(rng.integers(m0, m1 + 1)), lado, "lesion"))
    previos.sort()
    salen = {"a": [], "b": []}
    for m, lado, tipo in previos:
        xi, club = est["xi"][lado], est["clubes"][lado]
        if tipo == "lesion":
            j = xi[int(rng.integers(len(xi)))][1] if xi else None
            if j is None or j.id in est["usados"] or any(x.id == j.id for x in salen[lado]):
                continue
            g = next(g for g, x in xi if x.id == j.id)
            sup = _suplente(club, xi, g, est["usados"], est["banca"][lado]) \
                if est["cambios"][lado] < MAX_CAMBIOS else None           # sin cambios disponibles se juega con uno menos
            est["usados"].add(j.id)
            if sup:
                est["usados"].add(sup.id)
                est["cambios"][lado] += 1
            est["bajas"].append((club, j, int(rng.integers(1, 5)), "lesión"))
            slot = est["slots"][lado].pop(j.id, None)
            if sup and slot:
                est["slots"][lado][sup.id] = slot
            evs.append(_ev(m, "lesion", lado, j.nombre, entra=sup.nombre if sup else None, entra_j=sup, slot=slot))
            est["xi"][lado] = [(gg, sup if (x.id == j.id and sup) else x) for gg, x in xi
                               if sup or x.id != j.id]
            continue
        j = _infractor(xi, rng)
        if j is None:
            continue
        if tipo == "falta":
            evs.append(_ev(m, "falta", lado, j.nombre, oculto=True))
            prev = est["amar"][lado].get(j.id, 0)
            if rng.random() < P_AMARILLA * (0.35 if prev else 1.0):     # con amarilla se cuidan más
                est["amar"][lado][j.id] = prev + 1
                if prev >= 1:
                    evs.append(_ev(m, "roja", lado, j.nombre, detalle="doble amarilla"))
                    est["rojas"][lado].append(m)
                    salen[lado].append(j)
                    est["bajas"].append((club, j, 1, "sanción"))
                else:
                    evs.append(_ev(m, "amarilla", lado, j.nombre))
        else:
            evs.append(_ev(m, "roja", lado, j.nombre, detalle="roja directa"))
            est["rojas"][lado].append(m)
            salen[lado].append(j)
            est["bajas"].append((club, j, 1, "sanción"))
    for lado in "ab":                      # los expulsados dejan el campo (sin sustituto)
        if salen[lado]:
            ids = {x.id for x in salen[lado]}
            est["xi"][lado] = [(g, x) for g, x in est["xi"][lado] if x.id not in ids]
    # ---- ritmos por minuto (las rojas cambian la fuerza de cada equipo)
    fac = {lado: np.full(n, est["f"][lado]) for lado in "ab"}
    for lado in "ab":
        for r in est["rojas"][lado]:
            fac[lado][minutos >= r] *= F_ROJA_PROPIA
            fac[opuesto[lado]][minutos >= r] *= F_ROJA_RIVAL
    lam = {"a": est["la"], "b": est["lb"]}
    for lado in "ab":
        att = float(np.clip(lam[lado] / sim.GOLES_BASE, 0.5, 2.0))
        rival = opuesto[lado]
        gk_riv = portero_de(est["xi"][rival])
        tasas = {"gol": lam[lado] * OPEN / 90 * fac[lado],
                 "penal": RATE_PENAL / 90 * att * fac[lado],
                 "tiro_libre": RATE_TIRO_LIBRE / 90 * att * fac[lado],
                 "ocasion": RATE_OCASION / 90 * att * fac[lado]}
        if est["user"] == lado:
            # Parte de los goles de juego abierto del usuario pasa a ser ocasión clara jugable. Se divide por la
            # probabilidad de convertirla para que, en promedio, no cambien los goles esperados.
            movido = FRAC_GOL_JUGABLE * tasas["gol"]
            tasas["gol"] = tasas["gol"] - movido
            tasas["ocasion"] = tasas["ocasion"] + movido / max(0.15, p_ocasion_media(est["xi"][lado], gk_riv[1]))
        for tipo, tasa in tasas.items():
            cuentas = rng.poisson(tasa)
            for idx in np.nonzero(cuentas)[0]:
                for _ in range(int(cuentas[idx])):
                    m = int(minutos[idx])
                    if tipo == "gol":
                        evs.append(_ev(m, "gol", lado, sim.goleador(est["xi"][lado], rng).nombre))
                        continue
                    j = elegir_ejecutor(est["xi"][lado], tipo, rng)
                    e = _ev(m, tipo, lado, j.nombre, tiro=tiro_de(j, tipo), gk=gk_riv,
                            ejecutor=j, clave=j.nombre)
                    if tipo == "tiro_libre":
                        e["dist"] = int(rng.integers(DIST_LIBRE[0], DIST_LIBRE[1] + 1))
                    interactivo = est["user"] is not None and (lado == est["user"] or
                                                               (tipo == "penal" and rival == est["user"]))
                    if interactivo:
                        e["pend"] = True
                    else:
                        autoresolver(e, rng)
                    evs.append(e)
    evs.sort(key=lambda e: e["min"])
    est["eventos"].extend(evs)
    return evs


def simular_ia(L, V, la, lb, rng):
    """Partido completo sin interacción. Devuelve (goles_local, goles_visita, bajas, estado)."""
    est = nuevo_estado(L, V, la, lb, None)
    generar_tramo(est, 1, 90, rng)
    ga, gb = marcador(est["eventos"])
    return ga, gb, est["bajas"], est


# ---------------------------------------------------------------- consultas
def es_gol(e):
    return e["tipo"] == "gol" or e["res"] == "gol"


def marcador(eventos, hasta=90):
    ga = gb = 0
    for e in eventos:
        if e["min"] <= hasta and es_gol(e):
            if e["lado"] == "a":
                ga += 1
            else:
                gb += 1
    return ga, gb


def estadisticas(eventos, hasta=90):
    s = {k: {"a": 0, "b": 0} for k in ("faltas", "amarillas", "rojas", "jugadas")}
    for e in eventos:
        if e["min"] > hasta:
            continue
        lado, t = e["lado"], e["tipo"]
        if t == "falta":
            s["faltas"][lado] += 1
        elif t == "amarilla":
            s["amarillas"][lado] += 1
        elif t == "roja":
            s["rojas"][lado] += 1
        elif t in INTERACTIVOS:
            s["jugadas"][lado] += 1
    return s


def describir(e, clubes):
    """(titulo, subtitulo, clave_icono) para la crónica del partido."""
    club = clubes[e["lado"]].nombre
    t = e["tipo"]
    if t == "gol":
        return f"Gol de {e['jug']}", club, "gol"
    if t == "amarilla":
        return f"Amarilla para {e['jug']}", club, "amarilla"
    if t == "roja":
        return f"Roja para {e['jug']}", f"{club} · {e.get('detalle', '')}", "roja"
    if t == "lesion":
        return f"Lesión de {e['jug']}", f"{club} · " + (f"entra {e['entra']}" if e.get("entra") else "sin cambios"), "lesion"
    if t == "cambio":
        return f"Cambio: entra {e['jug']}", f"{club} · sale {e['sale']}", "cambio"
    if t == "formacion":
        return f"Cambio táctico: {e['jug']}", club, "cambio"
    nombre, fallado = {"penal": ("Penal", "fallado"), "tiro_libre": ("Tiro libre", "fallado"),
                       "ocasion": ("Ocasión", "desperdiciada")}[t]
    if t == "tiro_libre" and e.get("dist"):
        nombre = f"Tiro libre a {e['dist']} m"
    if e["res"] is None:
        return f"{nombre}: {e['jug']}", club, t
    if e["res"] == "gol":
        return f"¡Gol de {e['jug']}! ({nombre.lower()})", club, "gol"
    return f"{nombre} {fallado} por {e['jug']}", f"{club} · {e.get('motivo', 'sin premio')}", "fallo"
