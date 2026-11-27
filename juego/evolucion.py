"""Evolución de los jugadores entre temporadas (modo carrera).

Usa models/evolucion.joblib (ver ml/entrenar_evolucion.py), entrenado con 78 mil casos reales de un mismo jugador en
ediciones consecutivas de FIFA/FC (18 a 24):

  * Gradient Boosting: cambio esperado de OVR y de potencial del año siguiente (según edad, OVR, potencial y posición).
  * Ruido: a ese cambio esperado se le suma azar con la desviación típica real de cada tramo de edad.
  * Árbol de decisión: probabilidad de que el jugador mejore (≥ +2), se estanque o decaiga (≤ -2).
  * Regresión logística: probabilidad de retiro / salida del juego (desde los 30 años).
  * Regresión del valor de mercado: reajusta el valor al cambiar OVR, potencial y edad.
"""
import math
from itertools import chain
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .modelo import GRUPOS, autoalinear, reparar_once

RUTA = Path(__file__).resolve().parent.parent / "models" / "evolucion.joblib"
MIN_GRUPO = {"POR": 3, "DEF": 7, "MED": 7, "DEL": 4}         # jugadores mínimos por línea tras los retiros
OVR_MIN, OVR_MAX, POT_MAX = 40, 96, 99

_BUNDLE = None


def bundle():
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = joblib.load(RUTA)
    return _BUNDLE


def disponible():
    return RUTA.exists()


def _matriz(edad, ovr, pot, grupo):
    X = pd.DataFrame({"age": np.asarray(edad, float), "overall": np.asarray(ovr, float),
                      "potential": np.asarray(pot, float)})
    X["gap"] = X.potential - X.overall
    g = np.asarray(grupo)
    for k in GRUPOS:
        X["g_" + k] = (g == k).astype(int)
    return X[bundle()["features"]]


def _sigma(edad):
    b = bundle()
    out = np.empty(len(edad))
    edad = np.asarray(edad)
    for k, (a, z) in enumerate(b["tramos"]):
        out[(edad >= a) & (edad <= z)] = b["sigma_ovr"][k]
    return out


def predecir(jugadores):
    """Para cada jugador: (cambio esperado de OVR, desviación típica, prob. de mejorar, prob. de decaer)."""
    if not jugadores:
        return []
    b = bundle()
    X = _matriz([j.edad for j in jugadores], [j.ovr for j in jugadores], [j.pot for j in jugadores],
                [j.grupo for j in jugadores])
    mu = b["gb_ovr"].predict(X)
    sd = _sigma(X["age"].values)
    pr = b["arbol"].predict_proba(X)                       # columnas: decae, estable, mejora
    return list(zip(mu.tolist(), sd.tolist(), pr[:, 2].tolist(), pr[:, 0].tolist()))


def p_retiro(jugadores):
    """Probabilidad de que cada jugador se retire (0 por debajo de 31 años)."""
    b = bundle()
    X = pd.DataFrame({"age": [float(j.edad) for j in jugadores], "overall": [float(j.ovr) for j in jugadores],
                      "potential": [float(j.pot) for j in jugadores]})
    p = b["retiro"].predict_proba(X)[:, 1]
    return np.where(X["age"].values >= 31, p, 0.0)


def _valor_log(edad, ovr, pot, grupo):
    return np.expm1(bundle()["valor"].predict(_matriz(edad, ovr, pot, grupo)))


def avanzar_temporada(mundo, rng, club_usuario, posiciones=None):
    """Pasa un año: edad +1, nueva valoración de todos los jugadores, retiros y cantera.

    posiciones: {club_id: posición final} de la liga del usuario (para repartir ingresos).
    Devuelve un resumen con lo ocurrido en el club del usuario y en el mundo.
    """
    activos = list(chain(chain.from_iterable(c.plantel for c in mundo.clubes.values()), mundo.externos))
    antes = {j.id: (j.ovr, j.pot, j.edad) for j in activos}
    media_xi0 = {c.id: _media_xi(c) for c in mundo.clubes.values()}

    # ---- 1. retiros (con la valoración y edad de esta temporada)
    pr = p_retiro(activos)
    retirados = {j.id for j, p, u in zip(activos, pr, rng.random(len(activos))) if u < p}

    # ---- 2. evolución del resto
    vivos = [j for j in activos if j.id not in retirados]
    b = bundle()
    edad = np.array([j.edad for j in vivos], float)
    ovr = np.array([j.ovr for j in vivos], float)
    pot = np.array([j.pot for j in vivos], float)
    grupo = [j.grupo for j in vivos]
    X = _matriz(edad, ovr, pot, grupo)
    mu_o, mu_p = b["gb_ovr"].predict(X), b["gb_pot"].predict(X)
    sd = _sigma(edad)
    z = rng.standard_normal(len(vivos))
    d_ovr = mu_o + sd * z
    ovr_n = np.clip(np.round(ovr + d_ovr), OVR_MIN, OVR_MAX)
    pot_n = np.round(pot + mu_p + 0.55 * sd * z + rng.normal(0, 0.8, len(vivos)))
    pot_n = np.clip(pot_n, ovr_n, POT_MAX)
    veteranos = (edad + 1) >= 29                            # a partir de los 29 el potencial casi coincide con el OVR
    pot_n = np.where(veteranos, np.minimum(pot_n, ovr_n + 1), pot_n)
    v_ant = _valor_log(edad, ovr, pot, grupo)
    v_nue = _valor_log(edad + 1, ovr_n, pot_n, grupo)
    factor = np.clip(v_nue / np.maximum(v_ant, 1.0), 0.15, 6.0)
    for j, o, p, f in zip(vivos, ovr_n, pot_n, factor):
        d = int(o) - j.ovr
        j.edad += 1
        j.ovr, j.pot = int(o), int(p)
        j.rasgos = {k: int(min(99, max(15, v + d))) for k, v in j.rasgos.items()}
        j.valor = float(max(50_000.0, j.valor * f))
        j.valor_pred = float(max(50_000.0, j.valor_pred * f))
        j.lesion, j.motivo = 0, "lesión"
        j._prima = None

    # ---- 3. retirados fuera de clubes y mercado
    mundo.retirados = set(getattr(mundo, "retirados", set())) | retirados
    mundo.externos = [j for j in mundo.externos if j.id not in retirados]
    bajas_usuario = [j for j in club_usuario.plantel if j.id in retirados]
    for c in mundo.clubes.values():
        c.plantel = [j for j in c.plantel if j.id not in retirados]
        c.once = [None if (j is not None and j.id in retirados) else j for j in c.once]

    # ---- 4. cantera: cada club completa sus líneas con jóvenes sin equipo
    cantera = {c.id: [] for c in mundo.clubes.values()}
    por_grupo = {g: sorted([j for j in mundo.externos if j.grupo == g and j.edad <= 23],
                           key=lambda j: -(0.7 * j.pot + 0.3 * j.ovr)) for g in GRUPOS}
    for c in mundo.clubes.values():
        for g, minimo in MIN_GRUPO.items():
            falta = minimo - sum(1 for j in c.plantel if j.grupo == g)
            while falta > 0 and por_grupo[g]:
                nuevo = por_grupo[g].pop(0)
                mundo.externos.remove(nuevo)
                nuevo.club_id = c.id
                c.plantel.append(nuevo)
                cantera[c.id].append(nuevo)
                falta -= 1

    # ---- 5. alineaciones, valoración de cada club e ingresos
    n = len(posiciones) if posiciones else 0
    for c in mundo.clubes.values():
        if c is club_usuario:
            reparar_once(c)
            if any(j is None for j in c.once):
                autoalinear(c, c.formacion)
        else:
            autoalinear(c)
        c.ovr = int(round(c.ovr + (_media_xi(c) - media_xi0[c.id])))
        extra = (n - posiciones[c.id]) * 1_000_000 if posiciones and c.id in posiciones else 0
        c.presupuesto += round(c.valor_plantel() * 0.07 + extra, -5)
    mundo.markup = rng.lognormal(mean=0.10, sigma=0.22, size=len(mundo.markup))
    mundo.invalidar_prediccion()

    # ---- 6. resumen para la pantalla de fin de temporada
    cambios = []
    for j in club_usuario.plantel:
        o0, p0, e0 = antes.get(j.id, (j.ovr, j.pot, j.edad - 1))
        cambios.append((j, o0, j.ovr, p0, j.pot))
    dif = [j.ovr - antes[j.id][0] for j in vivos]
    return {
        "cambios": cambios,
        "retirados": [(j, antes[j.id][0], antes[j.id][2]) for j in bajas_usuario],
        "cantera": cantera[club_usuario.id],
        "mundo": {"jugadores": len(vivos), "retirados": len(retirados), "delta_medio": float(np.mean(dif)),
                  "suben": int(sum(1 for x in dif if x > 0)), "bajan": int(sum(1 for x in dif if x < 0))},
        "media_xi": (media_xi0[club_usuario.id], _media_xi(club_usuario)),
    }


def _media_xi(club):
    v = [j.ovr for j in club.once if j is not None]
    return sum(v) / len(v) if v else float(club.ovr)


def etiqueta_tendencia(p_mejora, p_decae):
    if p_mejora >= 0.5:
        return "Mejora probable"
    if p_decae >= 0.4:
        return "Riesgo de bajar"
    return "Estable"
