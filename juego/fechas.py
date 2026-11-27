"""Fechas del calendario. El dataset no trae fechas de partidos: se reparten las jornadas de forma verosímil.

Cada liga empieza en agosto (fechas de la temporada 2023-24), juega una jornada por semana (casi siempre el sábado y
cada tres jornadas el domingo) y tiene paradas por selecciones y un parón invernal. Es solo presentación: el motor
de partidos no usa las fechas.
"""
import datetime as dt

INICIO = {"Premier League": (8, 12), "La Liga": (8, 12), "Bundesliga": (8, 19), "Serie A": (8, 19), "Ligue 1": (8, 12),
          "Championship": (8, 5), "La Liga 2": (8, 12), "2. Bundesliga": (7, 29), "Serie B": (8, 19), "Ligue 2": (8, 5)}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
TEMPORADA_BASE = 2023                    # el juego parte de FC 24 (temporada 2023-24)


def fecha_jornada(liga, i, total=38, temporada=TEMPORADA_BASE):
    """Fecha del partido de la jornada i (0-based) en esa liga."""
    mes, dia = INICIO.get(liga, (8, 12))
    pausas = [(7, 1), (17, 2)] if total >= 38 else [(6, 1), (15, 2), (26, 1)]       # semanas de parada (selecciones, invierno)
    semanas = i + sum(w for k, w in pausas if i >= k)
    d = dt.date(temporada, mes, dia) + dt.timedelta(weeks=semanas)
    if i % 3 == 2:
        d += dt.timedelta(days=1)                                                       # algunas jornadas se juegan el domingo
    return d


def texto_fecha(d, con_dia=True):
    s = f"{d.day} {MESES[d.month - 1][:3]}"
    return f"{DIAS[d.weekday()]} {s}" if con_dia else s


def nombre_temporada(temporada=TEMPORADA_BASE):
    return f"{temporada}-{str(temporada + 1)[2:]}"
