"""Vocabulario táctico compartido entre el entrenamiento (reglas de asociación) y el juego."""

SALIDA = {"balanced": "Equilibrada", "fast build up": "Salida rápida",
          "slow build up": "Salida lenta", "long ball": "Balón largo"}
CREACION = {"balanced": "Equilibrada", "possession": "Posesión",
            "forward runs": "Desmarques", "direct passing": "Pase directo"}
DEFENSA = {"balanced": "Equilibrada", "pressure on heavy touch": "Presión al mal control",
           "press after possession loss": "Presión tras pérdida", "drop back": "Replegar"}

OPC_SALIDA = list(SALIDA.values())
OPC_CREACION = list(CREACION.values())
OPC_DEFENSA = list(DEFENSA.values())
NIVELES3_ANCHO = ["Estrecha", "Media", "Ancha"]
NIVELES3_PROF = ["Baja", "Media", "Alta"]

CLAVES = ["salida", "creacion", "defensa", "ancho_def", "prof", "ancho_of"]
ETIQUETAS = {
    "salida": "Salida de balón", "creacion": "Creación de ocasiones", "defensa": "Estilo defensivo",
    "ancho_def": "Anchura defensiva", "prof": "Profundidad defensiva", "ancho_of": "Anchura ofensiva",
}
OPCIONES = {
    "salida": OPC_SALIDA, "creacion": OPC_CREACION, "defensa": OPC_DEFENSA,
    "ancho_def": NIVELES3_ANCHO, "prof": NIVELES3_PROF, "ancho_of": NIVELES3_ANCHO,
}

TIERS = ["Bajo", "Medio", "Alto", "Élite"]


def bin3(valor, nombres):
    """Discretiza una escala 0-100 de FC en tres categorías."""
    if valor <= 50:
        return nombres[0]
    if valor <= 60:
        return nombres[1]
    return nombres[2]


def tactica_desde_fila(fila):
    """Convierte una fila del CSV (en inglés, con mayúsculas inconsistentes) a un dict en español."""
    return {
        "salida": SALIDA[str(fila["off_build_up_play"]).lower()],
        "creacion": CREACION[str(fila["off_chance_creation"]).lower()],
        "defensa": DEFENSA[str(fila["def_style"]).lower()],
        "ancho_def": bin3(float(fila["def_team_width"]), NIVELES3_ANCHO),
        "prof": bin3(float(fila["def_team_depth"]), NIVELES3_PROF),
        "ancho_of": bin3(float(fila["off_team_width"]), NIVELES3_ANCHO),
    }


def a_items(tactica):
    """Una táctica -> conjunto de 'ítems' (la 'transacción' de las reglas de asociación)."""
    return {f"{ETIQUETAS[k]} = {tactica[k]}" for k in CLAVES}


def ofensividad(t):
    """Índice heurístico entre -1 (muy conservador) y 1 (muy ofensivo). No sale de los datos."""
    v = {"Desmarques": 0.6, "Pase directo": 0.4, "Posesión": 0.1}.get(t["creacion"], 0)
    v += {"Salida rápida": 0.3, "Balón largo": 0.2, "Salida lenta": -0.1}.get(t["salida"], 0)
    v += {"Presión tras pérdida": 0.4, "Presión al mal control": 0.2, "Replegar": -0.5}.get(t["defensa"], 0)
    v += {"Alta": 0.3, "Baja": -0.3}.get(t["prof"], 0)
    v += 0.1 if t["ancho_of"] == "Ancha" else 0
    return max(-1.0, min(1.0, v))


TACTICA_BASE = {"salida": "Equilibrada", "creacion": "Equilibrada", "defensa": "Equilibrada",
                "ancho_def": "Media", "prof": "Media", "ancho_of": "Media"}
