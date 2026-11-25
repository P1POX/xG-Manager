"""xG Manager - juego de gestión de fútbol con minería de datos (Pygame).

Ejecutar:  python main.py
Antes (una sola vez):  python ml/preparar_datos.py <carpeta_con_csv>  y  python ml/entrenar.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

if not (RAIZ / "data" / "jugadores_ml.csv").exists():
    sys.exit("Faltan los datos procesados. Ejecuta primero:\n"
             "  python ml/preparar_datos.py <carpeta con male_players.csv, male_teams.csv, male_coaches.csv>\n"
             "  python ml/entrenar.py")

from juego.app import App  # noqa: E402

if __name__ == "__main__":
    App().ejecutar()
