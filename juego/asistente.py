"""'Asistente de datos': conecta los modelos entrenados con el juego."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import tactica as tac
from .simulacion import fuerzas, goles_esperados, monte_carlo

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = RAIZ / "models"
REPORTES = RAIZ / "reports"

NOMBRE_FEATURE = {
    "dif_ataque": "Diferencia de ataque", "dif_defensa": "Diferencia de defensa",
    "dif_medio": "Diferencia de mediocampo", "dif_overall": "Diferencia de nivel general",
    "dif_ofensividad": "Diferencia de ofensividad táctica", "dif_bono": "Diferencia de bono táctico",
}


def features_partido(fa, fb, ta, tb, ba=0.0, bb=0.0):
    return {
        "dif_ataque": fa["ataque"] - fb["ataque"],
        "dif_defensa": fa["defensa"] - fb["defensa"],
        "dif_medio": fa["medio"] - fb["medio"],
        "dif_overall": fa["overall"] - fb["overall"],
        "dif_ofensividad": tac.ofensividad(ta) - tac.ofensividad(tb),
        "dif_bono": ba - bb,
    }


class Asistente:
    def __init__(self, reglas_lista=None, seed=None):
        self.rng = np.random.default_rng(seed)
        if reglas_lista is None:
            f = MODELOS / "reglas.json"
            reglas_lista = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        self.reglas = reglas_lista
        self._arbol = None
        self.metricas = {}
        mf = REPORTES / "metricas.json"
        if mf.exists():
            self.metricas = json.loads(mf.read_text(encoding="utf-8"))

    # ---------------------------------------------------- reglas de asociación
    def reglas_aplicables(self, tactica):
        """Reglas {ajustes tácticos} -> Nivel cuyo antecedente cumple la táctica elegida."""
        items = tac.a_items(tactica)
        res = [r for r in self.reglas if set(r["si"]) <= items]
        return sorted(res, key=lambda r: abs(r["lift"] - 1) * r["confianza"], reverse=True)

    def bono_tactico(self, tactica):
        """Bonus de goles esperados (-6 % .. +6 %) según las reglas que cumple la táctica.

        Nivel Alto/Élite con lift > 1 suma; Nivel Bajo con lift > 1 resta (y al revés)."""
        total = 0.0
        for r in self.reglas_aplicables(tactica)[:4]:
            nivel = r["entonces"].split("= ")[1]
            signo = {"Élite": 1.0, "Alto": 0.6, "Medio": 0.0, "Bajo": -0.8}[nivel]
            total += signo * 0.03 * (r["lift"] - 1) * r["confianza"] * 2
        return float(max(-0.06, min(0.06, total)))

    # ---------------------------------------------------- árbol de partido
    def _cargar_arbol(self):
        if self._arbol is None:
            import joblib
            self._arbol = joblib.load(MODELOS / "arbol_partido.joblib")
        return self._arbol

    def pronostico(self, local, visitante, usuario_es_local=True, n=3000):
        """Pronóstico para local-visitante con Monte Carlo (Poisson) + árbol de decisión."""
        fa, fb = fuerzas(local.xi_con_grupo()), fuerzas(visitante.xi_con_grupo())
        ba, bb = self.bono_tactico(local.tactica), self.bono_tactico(visitante.tactica)
        la, lb = goles_esperados(fa, fb, local.tactica, visitante.tactica, True, ba, bb)
        mc = monte_carlo(la, lb, self.rng, n)
        out = {"mc": mc, "la": la, "lb": lb, "fa": fa, "fb": fb, "ba": ba, "bb": bb}
        try:
            d = self._cargar_arbol()
            f = features_partido(fa, fb, local.tactica, visitante.tactica, ba, bb)
            x = pd.DataFrame([f])[d["features"]]
            arb = d["arbol"]
            proba = dict(zip(arb.classes_, arb.predict_proba(x)[0]))
            out["arbol"] = proba
            out["arbol_clase"] = arb.predict(x)[0]
            out["arbol_camino"] = self._camino(arb, x, d["features"])
        except Exception:                                  # si el árbol no existe, el juego sigue
            out["arbol"] = None
        return out

    @staticmethod
    def _camino(arb, x, feats):
        """Reglas (condiciones) que recorrió el árbol para esta predicción."""
        nodos = arb.decision_path(x).indices
        t = arb.tree_
        pasos = []
        for n in nodos:
            if t.children_left[n] == t.children_right[n]:
                continue
            f = feats[t.feature[n]]
            val = float(x.iloc[0][f])
            sentido = "≤" if val <= t.threshold[n] else ">"
            pasos.append(f"{NOMBRE_FEATURE.get(f, f)} = {val:+.1f} {sentido} {t.threshold[n]:+.1f}")
        return pasos
