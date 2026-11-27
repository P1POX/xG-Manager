"""Escudos de las segundas divisiones y logos de la Champions League y de las copas nacionales.

Se usa desde tools/descargar_logos.py (que lo llama al final) o solo:
    python tools/logos_extra.py segunda          escudos de las segundas divisiones
    python tools/logos_extra.py competiciones    Champions y copas nacionales

Fuentes: el repositorio luukhopman/football-logos (temporadas 2021-26: sirve para los clubes de segunda que estuvieron en
primera) y la API pública de Wikipedia (imagen principal del artículo del club o de la competición). Uso educativo y
no comercial; assets/logos/ está en .gitignore.
"""
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from descargar_logos import CARPETAS, DESTINO, RAIZ, REPO, norm  # noqa: E402

TEMPORADAS = ("2023-24", "2022-23", "2021-22", "2024-25", "2025-26")
FORZADOS = {"Norwich City": "Norwich", "Como": "Como 1907", "Spezia": "Spezia Calcio", "Troyes": "ESTAC Troyes",
            "SpVgg Greuther Fürth": "Greuther Fürth", "Parma": "Parma Calcio 1913"}
COMPETICIONES = {           # archivo de salida -> artículo de Wikipedia cuya imagen principal es el logo
    "champions": "UEFA Champions League", "copa_facup": "FA Cup", "copa_copadelrey": "Copa del Rey",
    "copa_dfbpokal": "DFB-Pokal", "copa_coppaitalia": "Coppa Italia", "copa_coupedefrance": "Coupe de France",
    "liga_championship": "EFL Championship", "liga_laliga2": "Segunda División", "liga_bundesliga2": "2. Bundesliga",
    "liga_serieb": "Serie B", "liga_ligue2": "Ligue 2",       # segundas divisiones (ascensos y descensos)
}
ARTICULOS = {               # artículo de Wikipedia de los clubes de segunda cuyo nombre es ambiguo en una búsqueda
    "Paris": "Paris FC", "Pau": "Pau FC", "Laval": "Stade Lavallois", "Caen": "Stade Malherbe Caen",
    "Burgos": "Burgos CF", "Tenerife": "CD Tenerife", "Huesca": "SD Huesca", "Eldense": "CD Eldense",
    "Amorebieta": "SD Amorebieta", "Villarreal II": "Villarreal CF B", "Racing Ferrol": "Racing de Ferrol",
    "Albacete": "Albacete Balompié", "Mirandés": "CD Mirandés", "Alcorcón": "AD Alcorcón", "Elche": "Elche CF",
    "Levante": "Levante UD", "Real Oviedo": "Real Oviedo", "SD Eibar": "SD Eibar", "Real Valladolid": "Real Valladolid",
    "Espanyol": "RCD Espanyol", "Real Zaragoza": "Real Zaragoza", "Sporting Gijón": "Sporting de Gijón",
    "Racing Santander": "Racing de Santander", "FC Andorra": "FC Andorra", "FC Cartagena": "FC Cartagena",
    "Leganés": "CD Leganés", "Hull City": "Hull City A.F.C.", "Millwall": "Millwall F.C.", "Stoke City": "Stoke City F.C.",
    "Bristol City": "Bristol City F.C.", "Swansea City": "Swansea City A.F.C.", "Cardiff City": "Cardiff City F.C.",
    "Preston North End": "Preston North End F.C.", "Sunderland": "Sunderland A.F.C.",
    "Blackburn Rovers": "Blackburn Rovers F.C.", "Birmingham City": "Birmingham City F.C.",
    "Coventry City": "Coventry City F.C.", "Watford": "Watford F.C.", "Plymouth Argyle": "Plymouth Argyle F.C.",
    "Rotherham United": "Rotherham United F.C.", "Sheffield Wednesday": "Sheffield Wednesday F.C.",
    "Huddersfield Town": "Huddersfield Town A.F.C.", "Middlesbrough": "Middlesbrough F.C.",
    "West Bromwich Albion": "West Bromwich Albion F.C.", "Queens Park Rangers": "Queens Park Rangers F.C.",
    "Ipswich Town": "Ipswich Town F.C.", "Leeds United": "Leeds United F.C.", "Leicester City": "Leicester City F.C.",
    "Southampton": "Southampton F.C.", "Norwich City": "Norwich City F.C.", "Hamburger SV": "Hamburger SV",
    "Schalke 04": "FC Schalke 04", "Hertha BSC": "Hertha BSC", "Kaiserslautern": "1. FC Kaiserslautern",
    "Nürnberg": "1. FC Nürnberg", "Karlsruher SC": "Karlsruher SC", "Hannover 96": "Hannover 96",
    "Paderborn": "SC Paderborn 07", "St. Pauli": "FC St. Pauli", "Hansa Rostock": "F.C. Hansa Rostock",
    "Holstein Kiel": "Holstein Kiel", "Fortuna Düsseldorf": "Fortuna Düsseldorf", "Magdeburg": "1. FC Magdeburg",
    "Osnabrück": "VfL Osnabrück", "Eintracht Braunschweig": "Eintracht Braunschweig",
    "Wehen Wiesbaden": "SV Wehen Wiesbaden", "Elversberg": "SV 07 Elversberg", "Cremonese": "U.S. Cremonese",
    "Venezia": "Venezia FC", "Palermo": "Palermo F.C.", "Pisa": "Pisa S.C.", "Sampdoria": "U.C. Sampdoria",
    "Bari 1908": "S.S.C. Bari", "Brescia": "Brescia Calcio", "Ascoli": "Ascoli Calcio 1898 F.C.",
    "Ternana": "Ternana Calcio", "Modena": "Modena F.C.", "Reggiana": "A.C. Reggiana 1919", "Cosenza": "Cosenza Calcio",
    "FeralpiSalò": "FeralpiSalò", "Lecco": "Calcio Lecco 1912", "Catanzaro": "U.S. Catanzaro 1929",
    "Südtirol": "FC Südtirol", "Cittadella": "A.S. Cittadella", "Saint-Étienne": "AS Saint-Étienne",
    "Bordeaux": "FC Girondins de Bordeaux", "Angers SCO": "Angers SCO", "Auxerre": "AJ Auxerre", "Troyes": "ESTAC Troyes",
    "Amiens SC": "Amiens SC", "Ajaccio": "AC Ajaccio", "Guingamp": "En Avant Guingamp",
    "Grenoble Foot 38": "Grenoble Foot 38", "Bastia": "SC Bastia", "Valenciennes": "Valenciennes FC",
    "Quevilly Rouen": "US Quevilly-Rouen Métropole", "Rodez": "Rodez AF", "Annecy": "FC Annecy",
    "Concarneau": "US Concarneau", "Dunkerque": "USL Dunkerque",
}


def _pedir(url, pausa=2.0):
    """GET educado con Wikimedia: pausa entre peticiones y reintentos si responde 429."""
    cab = {"User-Agent": "xg-manager-educational/1.0"}
    for intento in range(4):
        time.sleep(pausa + 5 * intento)
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=30).read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or intento == 3:
                raise
            time.sleep(min(60, int(e.headers.get("Retry-After", "10") or 10)))


def _archivo_infobox(articulo):
    """Nombre del archivo del escudo o logo que usa el infobox del artículo (None si no se encuentra)."""
    q = urllib.parse.urlencode({"action": "parse", "page": articulo, "prop": "wikitext", "section": 0, "redirects": 1,
                                "format": "json"})
    try:
        texto = json.loads(_pedir("https://en.wikipedia.org/w/api.php?" + q))["parse"]["wikitext"]["*"]
    except (KeyError, urllib.error.HTTPError):
        return None
    m = re.search(r"\|\s*(?:logo|logo_image|image_file|image)\s*=\s*(?:\[\[)?(?:File:|Image:|Archivo:)?([^|\]\n<{]+\.(?:svg|png|jpg|jpeg))",
                  texto, re.I)
    return m.group(1).strip() if m else None


def logo_wikipedia(articulo, salida):
    """Logo o escudo del artículo de Wikipedia (archivo del infobox o, si no, su imagen principal), en PNG de hasta 300 px.
    True si se guardó."""
    archivo = _archivo_infobox(articulo)
    if archivo:
        q = urllib.parse.urlencode({"action": "query", "titles": "File:" + archivo, "prop": "imageinfo", "iiprop": "url",
                                    "iiurlwidth": 300, "format": "json"})
        try:
            info = next(iter(json.loads(_pedir("https://en.wikipedia.org/w/api.php?" + q))["query"]["pages"].values()))
            (DESTINO / f"{salida}.png").write_bytes(_pedir(info["imageinfo"][0]["thumburl"]))
            return True
        except (KeyError, IndexError, urllib.error.HTTPError):
            pass
    q = urllib.parse.urlencode({"action": "query", "titles": articulo, "prop": "pageimages", "piprop": "thumbnail",
                                "pithumbsize": 300, "redirects": 1, "format": "json"})
    datos = json.loads(_pedir("https://en.wikipedia.org/w/api.php?" + q))
    pag = next(iter(datos["query"]["pages"].values()))
    if "thumbnail" not in pag:
        return False
    (DESTINO / f"{salida}.png").write_bytes(_pedir(pag["thumbnail"]["source"]))
    return True


def descargar_segunda(equipos, repo):
    """Primero los escudos del repositorio (si el club estuvo en primera en 2021-26) y luego Wikipedia para el resto."""
    del_repo, pendientes, de_wiki = 0, [], 0
    for _, f in equipos[equipos.division == 2].iterrows():
        if (DESTINO / f"{f.team_id}.png").exists():
            continue
        objetivo = FORZADOS.get(f.team_name, f.team_name)
        mejor = (0.0, None)
        for temp in TEMPORADAS:
            for a in (Path(repo) / "history" / temp / CARPETAS[f.liga_madre]).glob("*.png"):
                sim = difflib.SequenceMatcher(None, norm(objetivo), norm(a.stem)).ratio()
                if sim > mejor[0]:
                    mejor = (sim, a)
        if mejor[0] >= 0.85 or (f.team_name in FORZADOS and mejor[0] >= 0.6):
            shutil.copyfile(mejor[1], DESTINO / f"{f.team_id}.png")
            del_repo += 1
        else:
            pendientes.append(f)
    for f in pendientes:
        articulo = ARTICULOS.get(f.team_name, f.team_name + " football club")
        try:
            if logo_wikipedia(articulo, str(f.team_id)):
                de_wiki += 1
            else:
                print(f"  sin imagen: {f.team_name} ({articulo})")
        except Exception as e:
            print(f"  no se pudo bajar {f.team_name}: {e}")
    print(f"Segundas divisiones: {del_repo} del repositorio, {de_wiki} de Wikipedia, "
          f"{len(pendientes) - de_wiki} sin escudo (se dibuja uno genérico).")


def descargar_competiciones():
    """Logos de la Champions League y de las copas nacionales."""
    ok = 0
    for salida, articulo in COMPETICIONES.items():
        try:
            ok += bool(logo_wikipedia(articulo, salida))
        except Exception as e:
            print(f"  no se pudo bajar {articulo}: {e}")
    print(f"Logos de competiciones: {ok}/{len(COMPETICIONES)}")


def descargar_segunda_clonando():
    equipos = pd.read_csv(RAIZ / "data" / "equipos.csv")
    DESTINO.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, tmp],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp, "sparse-checkout", "set", "history"], check=True, capture_output=True)
        descargar_segunda(equipos, tmp)


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    modo = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if modo in ("segunda", "todo"):
        descargar_segunda_clonando()
    if modo in ("competiciones", "todo"):
        descargar_competiciones()
