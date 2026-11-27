"""Paso 1 - Limpieza y preparación de los datos (EA SPORTS FC 24, Kaggle).

Uso:
    python ml/preparar_datos.py "C:/ruta/a/archive"

Lee male_players.csv, male_teams.csv y male_coaches.csv y genera en data/:
    jugadores.csv       -> jugadores de FC 24 (última actualización), limpios
    equipos.csv         -> clubes de las 5 grandes ligas con sus datos de plantel
    entrenadores.csv    -> entrenadores
    tacticas_hist.csv   -> configuraciones tácticas de FC 22-24 (para reglas de asociación)
"""
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

# Ligas con las que se juega: Premier League, La Liga, Bundesliga, Serie A y Ligue 1
LIGAS_JUEGO = {13: "Premier League", 53: "La Liga", 19: "Bundesliga", 31: "Serie A", 16: "Ligue 1"}
# Segundas divisiones: no se juegan como liga, pero sus clubes participan en la copa nacional.
# id de liga -> (nombre, liga de primera de ese país)
LIGAS_SEGUNDA = {14: ("Championship", "Premier League"), 54: ("La Liga 2", "La Liga"), 20: ("2. Bundesliga", "Bundesliga"),
                 32: ("Serie B", "Serie A"), 17: ("Ligue 2", "Ligue 1")}

ATRIBUTOS = [
    "pace", "shooting", "passing", "dribbling", "defending", "physic",
    "attacking_crossing", "attacking_finishing", "attacking_heading_accuracy",
    "attacking_short_passing", "attacking_volleys", "skill_dribbling", "skill_curve",
    "skill_fk_accuracy", "skill_long_passing", "skill_ball_control", "movement_acceleration",
    "movement_sprint_speed", "movement_agility", "movement_reactions", "movement_balance",
    "power_shot_power", "power_jumping", "power_stamina", "power_strength", "power_long_shots",
    "mentality_aggression", "mentality_interceptions", "mentality_positioning", "mentality_vision",
    "mentality_penalties", "mentality_composure", "defending_marking_awareness",
    "defending_standing_tackle", "defending_sliding_tackle",
    "goalkeeping_diving", "goalkeeping_handling", "goalkeeping_kicking",
    "goalkeeping_positioning", "goalkeeping_reflexes",
]
COLS_JUGADOR = [
    "player_id", "short_name", "long_name", "player_positions", "overall", "potential",
    "value_eur", "wage_eur", "age", "height_cm", "weight_kg", "club_team_id", "club_name", "club_jersey_number",
    "league_id", "league_name", "club_position", "nationality_name", "preferred_foot",
    "weak_foot", "skill_moves", "international_reputation", "work_rate", "player_traits",
    "player_tags",
] + ATRIBUTOS

COLS_TACTICA = [
    "def_style", "def_team_width", "def_team_depth", "off_build_up_play",
    "off_chance_creation", "off_team_width",
]


def ultima_actualizacion(df, version):
    d = df[df.fifa_version == version]
    return d[d.fifa_update == d.fifa_update.max()]


def main(ruta):
    ruta = Path(ruta)
    DATA.mkdir(exist_ok=True)

    # ---------------------------------------------------------------- jugadores
    jug = pd.read_csv(ruta / "male_players.csv", low_memory=False)
    jug = ultima_actualizacion(jug, 24)[COLS_JUGADOR].copy()
    n0 = len(jug)
    jug = jug.dropna(subset=["value_eur", "club_team_id"])        # sin valor de mercado o sin club
    jug = jug[jug.value_eur > 0]
    jug["wage_eur"] = jug["wage_eur"].fillna(jug["wage_eur"].median())
    for c in ATRIBUTOS:                                           # los porteros no tienen pace, etc.
        jug[c] = jug[c].fillna(jug[c].median() if jug[c].notna().any() else 0)
    jug["club_team_id"] = jug.club_team_id.astype(int)
    jug["league_id"] = jug.league_id.fillna(-1).astype(int)
    jug["pos_principal"] = jug.player_positions.str.split(",").str[0].str.strip()
    jug["player_traits"] = jug.player_traits.fillna("")
    jug["player_tags"] = jug.player_tags.fillna("")
    jug["work_rate"] = jug.work_rate.fillna("Medium/Medium")
    print(f"Jugadores: {n0} -> {len(jug)} tras limpieza (sin valor o club: {n0 - len(jug)})")
    jug.to_csv(DATA / "jugadores.csv", index=False)

    # ------------------------------------------------------------------ equipos
    eq = pd.read_csv(ruta / "male_teams.csv", low_memory=False)
    eq24 = ultima_actualizacion(eq, 24)
    eq24 = eq24[eq24.league_id.isin(list(LIGAS_JUEGO) + list(LIGAS_SEGUNDA))].copy()
    eq24["division"] = eq24.league_id.map(lambda i: 1 if i in LIGAS_JUEGO else 2)
    eq24["liga"] = eq24.league_id.map(lambda i: LIGAS_JUEGO[i] if i in LIGAS_JUEGO else LIGAS_SEGUNDA[i][0])
    eq24["liga_madre"] = eq24.league_id.map(lambda i: LIGAS_JUEGO[i] if i in LIGAS_JUEGO else LIGAS_SEGUNDA[i][1])
    # Solo clubes con plantel suficiente en el dataset de jugadores
    tam = jug.groupby("club_team_id").size()
    eq24 = eq24[eq24.team_id.map(tam).fillna(0) >= 18]
    cols_eq = ["team_id", "team_name", "liga", "division", "liga_madre", "league_id", "overall", "attack", "midfield",
               "defence", "coach_id", "home_stadium", "international_prestige",
               "domestic_prestige"] + COLS_TACTICA
    eq24 = eq24[cols_eq]
    print(f"Equipos: {len(eq24)} -> {eq24.groupby('liga').size().to_dict()}")
    eq24.to_csv(DATA / "equipos.csv", index=False)

    # -------------------------------------------------------------- entrenadores
    ent = pd.read_csv(ruta / "male_coaches.csv", usecols=["coach_id", "short_name", "long_name",
                                                         "nationality_name"])
    ent = ent[ent.coach_id.isin(eq24.coach_id)]
    ent.to_csv(DATA / "entrenadores.csv", index=False)
    print(f"Entrenadores: {len(ent)}")

    # -------------------------------------------------- tácticas históricas (22-24)
    hist = eq[eq.fifa_version.isin([22, 23, 24])].copy()
    hist = hist.dropna(subset=COLS_TACTICA + ["overall"])
    hist = hist[hist.league_name != "Friendly International"]     # selecciones nacionales fuera
    hist = hist[["team_id", "fifa_version", "league_id", "league_level", "overall"] + COLS_TACTICA]
    print(f"Configuraciones tácticas históricas: {len(hist)}")
    hist.to_csv(DATA / "tacticas_hist.csv", index=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
