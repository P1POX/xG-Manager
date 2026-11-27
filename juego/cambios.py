"""Cambios de jugadores y de formación durante el partido (solo para el club del usuario).

Reglas (las vigentes en Premier League, La Liga, Bundesliga, Serie A y Ligue 1):
  * máximo 5 cambios por partido (los que hace sola la lesión de un jugador también cuentan);
  * como mucho 3 paradas para cambiar, sin contar el descanso;
  * se elige entre los 9 suplentes convocados; un jugador que sale no puede volver;
  * hace falta un portero en el campo.
El cambio de formación es libre. Tras cualquier cambio se recalculan los goles esperados de ambos equipos con el
once que queda en el campo, así que lo que ocurre en los minutos siguientes ya refleja la decisión.
"""
from . import eventos as ev
from . import simulacion as sim
from .modelo import FORMACIONES, asignar_formacion


def restantes(est, lado):
    """(cambios que quedan, paradas que quedan)."""
    return ev.MAX_CAMBIOS - est["cambios"][lado], ev.MAX_VENTANAS - est["ventanas"][lado]


def banquillo(est, lado):
    """Suplentes que todavía pueden entrar."""
    en_campo = {j.id for _, j in est["xi"][lado]}
    return [j for j in est["banca"][lado] if j.id not in est["usados"] and j.id not in en_campo and j.lesion == 0]


def en_campo(est, lado):
    """[(puesto, jugador)] de los que están jugando, con su puesto (grupo, x, y) en la formación actual."""
    sl = est["slots"][lado]
    return [(sl[j.id], j) for _, j in est["xi"][lado] if j.id in sl]


def proponer(est, lado, formacion, sustituciones):
    """Once resultante si se aplicaran los cambios: [(puesto, jugador)] (o un mensaje de error)."""
    campo = en_campo(est, lado)
    por_id = {j.id: (s, j) for s, j in campo}
    banca = {j.id for j in banquillo(est, lado)}
    vistos = set()
    for sale, entra in sustituciones:
        if sale.id not in por_id:
            return None, f"{sale.nombre} no está en el campo."
        if entra.id not in banca:
            return None, f"{entra.nombre} no está disponible en el banquillo."
        if sale.id in vistos or entra.id in vistos:
            return None, "Un jugador no puede participar en dos cambios."
        vistos.update((sale.id, entra.id))
    nuevo = []
    reemplazo = {sale.id: entra for sale, entra in sustituciones}
    for s, j in campo:
        nuevo.append((s, reemplazo.get(j.id, j)))
    if formacion != est["formacion"][lado]:
        nuevo = asignar_formacion([j for _, j in nuevo], formacion)
    if not any("POR" in j.grupos_nat for _, j in nuevo):
        return None, "Necesitas un portero en el campo."
    return nuevo, ""


def validar(est, lado, formacion, sustituciones, descanso=False):
    """(ok, mensaje). No modifica nada."""
    n_cambios, n_paradas = restantes(est, lado)
    if len(sustituciones) > n_cambios:
        return False, f"Solo quedan {n_cambios} cambios."
    if sustituciones and not descanso and n_paradas <= 0:
        return False, "Ya usaste las 3 paradas para cambiar (el descanso no cuenta)."
    nuevo, msg = proponer(est, lado, formacion, sustituciones)
    return (nuevo is not None), msg


def aplicar(est, lado, formacion, sustituciones, minuto, bono_tactico, descanso=False):
    """Aplica los cambios y/o la formación. Devuelve (ok, mensaje, eventos_creados)."""
    ok, msg = validar(est, lado, formacion, sustituciones, descanso)
    if not ok:
        return False, msg, []
    nuevo, _ = proponer(est, lado, formacion, sustituciones)
    club = est["clubes"][lado]
    eventos = []
    for sale, entra in sustituciones:
        est["usados"].update((sale.id, entra.id))
        eventos.append(ev._ev(minuto, "cambio", lado, entra.nombre, sale=sale.nombre, entra_j=entra, sale_j=sale))
    if sustituciones:
        est["cambios"][lado] += len(sustituciones)
        if not descanso:
            est["ventanas"][lado] += 1
    if formacion != est["formacion"][lado]:
        eventos.append(ev._ev(minuto, "formacion", lado, formacion))
    est["formacion"][lado] = formacion
    est["xi"][lado] = [(s[0], j) for s, j in nuevo]
    est["slots"][lado] = {j.id: s for s, j in nuevo}
    for e in eventos:
        e["pares"] = nuevo
    est["eventos"].extend(eventos)
    est["eventos"].sort(key=lambda e: e["min"])
    recalcular(est, bono_tactico)
    return True, "Cambios realizados.", eventos


def recalcular(est, bono_tactico):
    """Goles esperados de ambos equipos con el once que hay ahora en el campo."""
    L, V = est["clubes"]["a"], est["clubes"]["b"]
    fa, fb = sim.fuerzas(est["xi"]["a"]), sim.fuerzas(est["xi"]["b"])
    est["la"], est["lb"] = sim.goles_esperados(fa, fb, L.tactica, V.tactica, True,
                                               bono_tactico(L.tactica), bono_tactico(V.tactica))
    if est.get("neutral"):                                      # final de copa: sin ventaja de local
        est["la"], est["lb"] = est["la"] / sim.VENTAJA_LOCAL, est["lb"] / 0.92
    return est["la"], est["lb"]


__all__ = ["restantes", "banquillo", "en_campo", "proponer", "validar", "aplicar", "recalcular", "FORMACIONES"]
