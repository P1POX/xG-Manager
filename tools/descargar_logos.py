"""Descarga los escudos de los clubes (temporada 2023-24) y los guarda en assets/logos/<team_id>.png.

Fuentes: https://github.com/luukhopman/football-logos (escudos de clubes) y la API pública de Wikipedia (logos de ligas).
Uso educativo y no comercial: los escudos pertenecen a sus clubes, por eso assets/logos/ está en .gitignore y
cada persona ejecuta este script una vez. Si la carpeta no existe, el juego dibuja un escudo genérico.

Requiere git en el PATH.   Uso:  python tools/descargar_logos.py
"""
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from scipy.optimize import linear_sum_assignment

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "assets" / "logos"
REPO = "https://github.com/luukhopman/football-logos.git"
TEMPORADA = "history/2023-24"
CARPETAS = {"Premier League": "England - Premier League", "La Liga": "Spain - LaLiga",
            "Bundesliga": "Germany - Bundesliga", "Serie A": "Italy - Serie A", "Ligue 1": "France - Ligue 1"}
RUIDO = r"\b(fc|cf|afc|sc|ac|as|ssc|rc|fsv|vfl|vfb|tsg|sv|us|ud|cd|1|rb|sd|ca|rcd|ogc|losc|stade|real)\b"


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(RUIDO, "", s.replace(".", " "))
    return re.sub(r"[^a-z0-9]", "", s)


def emparejar(clubes, archivos):
    """Asignación uno a uno (algoritmo húngaro) entre nombres del juego y archivos de la carpeta de la liga."""
    sim = [[difflib.SequenceMatcher(None, norm(c), norm(a)).ratio() for a in archivos] for c in clubes]
    filas, cols = linear_sum_assignment([[-v for v in f] for f in sim])
    return [(clubes[i], archivos[j], sim[i][j]) for i, j in zip(filas, cols)]


ARCHIVOS_LIGAS = {          # liga -> (nombre del archivo en Wikipedia, nombre de salida)
    "Premier League": ("Premier League Logo.svg", "liga_premier"),
    "La Liga": ("LaLiga EA Sports 2023 Vertical Logo.svg", "liga_laliga"),
    "Bundesliga": ("Bundesliga logo (2017).svg", "liga_bundesliga"),
    "Serie A": ("Serie A ENILIVE logo.svg", "liga_seriea"),
    "Ligue 1": ("Logo Ligue 1 McDonald's 2024.svg", "liga_ligue1"),
}


def descargar_ligas():
    """Logos de las ligas desde la API pública de Wikipedia (miniatura PNG de 300 px de ancho)."""
    api = "https://en.wikipedia.org/w/api.php"
    cab = {"User-Agent": "xg-manager-educational/1.0"}
    ok = 0

    def pedir(url):
        """GET con pausas y reintentos: respeta el límite de peticiones de Wikimedia (HTTP 429 + Retry-After)."""
        for intento in range(4):
            time.sleep(3 + 5 * intento)
            try:
                return urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=30).read()
            except urllib.error.HTTPError as e:
                if e.code != 429 or intento == 3:
                    raise
                time.sleep(min(60, int(e.headers.get("Retry-After", "10") or 10)))

    for liga, (archivo, salida) in ARCHIVOS_LIGAS.items():
        try:
            q = urllib.parse.urlencode({"action": "query", "titles": "File:" + archivo, "prop": "imageinfo",
                                        "iiprop": "url", "iiurlwidth": 300, "format": "json"})
            datos = json.loads(pedir(f"{api}?{q}"))
            url = next(iter(datos["query"]["pages"].values()))["imageinfo"][0]["thumburl"]
            (DESTINO / f"{salida}.png").write_bytes(pedir(url))
            ok += 1
        except Exception as e:                       # sin red o archivo renombrado: el juego usa su alternativa
            print(f"  no se pudo bajar el logo de {liga}: {e}")
    print(f"Logos de ligas: {ok}/{len(ARCHIVOS_LIGAS)}")


def main():
    equipos = pd.read_csv(RAIZ / "data" / "equipos.csv")
    DESTINO.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        print("Descargando escudos (≈17 MB)…")
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, tmp],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp, "sparse-checkout", "set", TEMPORADA], check=True, capture_output=True)
        total = dudosos = 0
        for liga, carpeta in CARPETAS.items():
            archivos = sorted((Path(tmp) / TEMPORADA / carpeta).glob("*.png"))
            filas = equipos[equipos.liga == liga]
            nombres = filas.team_name.tolist()
            ids = dict(zip(filas.team_name, filas.team_id))
            por_nombre = {a.stem: a for a in archivos}
            for club, arch, s in emparejar(nombres, [a.stem for a in archivos]):
                shutil.copyfile(por_nombre[arch], DESTINO / f"{ids[club]}.png")
                total += 1
                if s < 0.5:
                    dudosos += 1
                    print(f"  revisar: {club!r} -> {arch!r} ({s:.2f})")
    print(f"Listo: {total} escudos en {DESTINO} ({dudosos} con coincidencia baja, revisa los de arriba).")
    descargar_ligas()


if __name__ == "__main__":
    sys.exit(main())
