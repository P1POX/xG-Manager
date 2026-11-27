"""Ascensos y descensos entre la primera y la segunda división de cada país.

Al terminar la temporada:
  * la división del usuario ya se jugó partido a partido; su clasificación final es la real;
  * las demás divisiones (la otra división de tu país y las 5 divisiones de los demás países) se simulan enteras con el
    mismo modelo de goles esperados (Poisson) que usa la liga: es una simulación rápida, sin crónica de eventos;
  * bajan los últimos de primera y suben los primeros de segunda (3 en las ligas de 20 clubes, 2 en las de 18, para que
    cada división conserve su tamaño).

El club que sube cobra un premio y el que baja pierde parte del presupuesto (los ingresos de televisión son menores).
Si el club del usuario baja, la temporada siguiente juega en la segunda división de su país (y puede volver a subir).
"""
from . import simulacion as sim

PREMIO_ASCENSO = 10.0e6
FACTOR_DESCENSO = 0.85                 # el presupuesto de un club que baja se queda en el 85 %


def n_ascensos(mundo, liga):
    """Cuántos clubes suben y bajan en esa liga (según el tamaño de su primera división)."""
    return 3 if len(mundo.ligas[liga]) >= 20 else 2


def nombre_segunda(mundo, liga):
    """Nombre de la segunda división de esa liga (Championship, La Liga 2…)."""
    return mundo.clubes[mundo.segunda[liga][0]].liga


def simular_division(mundo, ids, rng, asist):
    """Temporada completa (todos contra todos, ida y vuelta) entre los clubes `ids`. Devuelve los ids ordenados por
    clasificación (puntos, diferencia de goles, goles a favor, nombre) y la tabla {id: (pts, gf, gc)}."""
    clubes = [mundo.clubes[i] for i in ids]
    fuerza = {c.id: sim.fuerzas(c.xi_con_grupo()) for c in clubes}
    bono = {c.id: asist.bono_tactico(c.tactica) for c in clubes}
    tabla = {c.id: [0, 0, 0] for c in clubes}
    for a in clubes:
        for b in clubes:
            if a is b:
                continue
            la, lb = sim.goles_esperados(fuerza[a.id], fuerza[b.id], a.tactica, b.tactica, True, bono[a.id], bono[b.id])
            ga, gb = int(rng.poisson(la)), int(rng.poisson(lb))
            ta, tb = tabla[a.id], tabla[b.id]
            ta[1] += ga
            ta[2] += gb
            tb[1] += gb
            tb[2] += ga
            ta[0] += 3 * (ga > gb) + (ga == gb)
            tb[0] += 3 * (gb > ga) + (ga == gb)
    orden = sorted(ids, key=lambda i: (-tabla[i][0], -(tabla[i][1] - tabla[i][2]), -tabla[i][1], mundo.clubes[i].nombre))
    return orden, {i: tuple(v) for i, v in tabla.items()}


def cerrar_temporada(mundo, club_usuario, orden_usuario, rng, asist):
    """Calcula (sin aplicar todavía) cómo terminan todas las divisiones.

    orden_usuario: ids de la división del usuario en orden de clasificación final.
    Devuelve {liga: {"primera": [ids], "segunda": [ids], "suben": [ids], "bajan": [ids], "n": N}}."""
    res = {}
    for liga in mundo.ligas:
        n = n_ascensos(mundo, liga)
        prim, seg = list(mundo.ligas[liga]), list(mundo.segunda[liga])
        if club_usuario.liga_madre == liga:
            if club_usuario.division == 1:
                o1, o2 = list(orden_usuario), simular_division(mundo, seg, rng, asist)[0]
            else:
                o1, o2 = simular_division(mundo, prim, rng, asist)[0], list(orden_usuario)
        else:
            o1, o2 = simular_division(mundo, prim, rng, asist)[0], simular_division(mundo, seg, rng, asist)[0]
        res[liga] = {"primera": o1, "segunda": o2, "suben": o2[:n], "bajan": o1[-n:], "n": n}
    return res


def aplicar(mundo, res):
    """Mueve los clubes de división (listas del mundo, división y nombre de liga de cada club) y reparte premios y recortes."""
    for liga, r in res.items():
        nom2 = nombre_segunda(mundo, liga)
        suben, bajan = set(r["suben"]), set(r["bajan"])
        mundo.ligas[liga] = [i for i in mundo.ligas[liga] if i not in bajan] + list(r["suben"])
        mundo.segunda[liga] = [i for i in mundo.segunda[liga] if i not in suben] + list(r["bajan"])
        for i in r["suben"]:
            c = mundo.clubes[i]
            c.division, c.liga = 1, liga
            c.presupuesto += PREMIO_ASCENSO
        for i in r["bajan"]:
            c = mundo.clubes[i]
            c.division, c.liga = 2, nom2
            c.presupuesto = round(c.presupuesto * FACTOR_DESCENSO, -5)


def estado_usuario(mundo, club, orden_usuario):
    """'sube' | 'baja' | 'sigue' para el club del usuario según su clasificación final."""
    n = n_ascensos(mundo, club.liga_madre)
    pos = orden_usuario.index(club.id)
    if club.division == 1 and pos >= len(orden_usuario) - n:
        return "baja"
    if club.division == 2 and pos < n:
        return "sube"
    return "sigue"


def a_dict(mundo):
    """Pertenencia a cada división (para el guardado)."""
    return {liga: {"primera": list(mundo.ligas[liga]), "segunda": list(mundo.segunda[liga])} for liga in mundo.ligas}


def de_dict(mundo, datos):
    """Restaura la pertenencia a divisiones guardada sobre un mundo recién cargado."""
    for liga, d in datos.items():
        nom2 = nombre_segunda(mundo, liga)
        mundo.ligas[liga] = list(d["primera"])
        mundo.segunda[liga] = list(d["segunda"])
        for i in d["primera"]:
            c = mundo.clubes[i]
            c.division, c.liga = 1, liga
        for i in d["segunda"]:
            c = mundo.clubes[i]
            c.division, c.liga = 2, nom2
