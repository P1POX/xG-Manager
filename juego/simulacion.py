"""Motor de partidos.

IMPORTANTE: el dataset de Kaggle trae jugadores, equipos y entrenadores, pero NO resultados de
partidos. Por eso el resultado se simula con un modelo de Poisson (goles esperados) alimentado
por el plantel real. Los modelos de minería de datos entran antes y después del partido:
rol de cada jugador, aptitud por posición, valor justo, reglas tácticas y pronóstico.
"""
import numpy as np

from . import tactica as tac

PESO_ATAQUE = {"DEL": 1.0, "MED": 0.45, "DEF": 0.08, "POR": 0.0}
PESO_DEFENSA = {"POR": 1.4, "DEF": 1.0, "MED": 0.40, "DEL": 0.05}
PESO_MEDIO = {"MED": 1.0, "DEL": 0.1, "DEF": 0.1, "POR": 0.0}

GOLES_BASE = 1.22
K_DIF = 0.04          # cada punto de diferencia ataque-defensa cambia ~5 % los goles esperados
K_MEDIO = 0.015
VENTAJA_LOCAL = 1.12


def fuerzas(xi):
    """xi: lista de (grupo_del_puesto, jugador). Devuelve ataque, defensa, medio y overall."""
    def prom(pesos):
        num = sum(pesos[g] * j.rendimiento(g) for g, j in xi)
        den = sum(pesos[g] for g, _ in xi)
        return num / den if den else 0.0

    return {
        "ataque": prom(PESO_ATAQUE), "defensa": prom(PESO_DEFENSA), "medio": prom(PESO_MEDIO),
        "overall": float(np.mean([j.rendimiento(g) for g, j in xi])) if xi else 0.0,
    }


def goles_esperados(fa, fb, ta, tb, a_local, bono_a=0.0, bono_b=0.0):
    """Goles esperados de A y de B."""
    oa, ob = tac.ofensividad(ta), tac.ofensividad(tb)
    base_a = GOLES_BASE * np.exp(K_DIF * (fa["ataque"] - fb["defensa"])
                                 + K_MEDIO * (fa["medio"] - fb["medio"]))
    base_b = GOLES_BASE * np.exp(K_DIF * (fb["ataque"] - fa["defensa"])
                                 + K_MEDIO * (fb["medio"] - fa["medio"]))
    la = base_a * (1 + 0.06 * oa) * (1 + 0.05 * ob) * (1 + bono_a)
    lb = base_b * (1 + 0.06 * ob) * (1 + 0.05 * oa) * (1 + bono_b)
    la *= VENTAJA_LOCAL if a_local else 0.92
    lb *= 0.92 if a_local else VENTAJA_LOCAL
    return float(la), float(lb)


def simular(la, lb, rng):
    return int(rng.poisson(la)), int(rng.poisson(lb))


def monte_carlo(la, lb, rng, n=3000):
    ga = rng.poisson(la, n)
    gb = rng.poisson(lb, n)
    pa, pe, pb = float((ga > gb).mean()), float((ga == gb).mean()), float((ga < gb).mean())
    marc = {}
    for x, y in zip(ga, gb):
        marc[(int(x), int(y))] = marc.get((int(x), int(y)), 0) + 1
    modal = max(marc, key=marc.get)
    return {"gana_a": pa, "empate": pe, "gana_b": pb, "esperado": (float(ga.mean()), float(gb.mean())),
            "marcador": modal}


def minutos_goles(ga, gb, rng):
    """Reparte los goles en minutos y devuelve [(minuto, 'a'|'b')] ordenado."""
    ev = [(int(rng.integers(1, 91)), "a") for _ in range(ga)] + \
         [(int(rng.integers(1, 91)), "b") for _ in range(gb)]
    return sorted(ev)


def goleador(xi, rng):
    """Elige autor del gol con probabilidad proporcional a su peligro ofensivo."""
    pesos = []
    for g, j in xi:
        base = {"DEL": 1.0, "MED": 0.4, "DEF": 0.07, "POR": 0.003}[g]
        pesos.append(base * (j.rasgos["shooting"] / 70.0) ** 2)
    pesos = np.array(pesos)
    return xi[int(rng.choice(len(xi), p=pesos / pesos.sum()))][1]
