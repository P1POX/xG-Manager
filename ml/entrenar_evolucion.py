"""Paso 3 (modo carrera) - Modelo de evolución de jugadores con datos reales de FIFA 15 a FC 24.

Uso:
    python ml/entrenar_evolucion.py "C:/ruta/a/archive"      (carpeta con male_players.csv, la misma de preparar_datos.py)

Idea: el dataset trae 10 ediciones. Un mismo jugador aparece en ediciones consecutivas, así que cada par
(jugador en la edición v, jugador en la edición v+1) es un ejemplo real de cómo cambia un futbolista en un año
(~114 mil ejemplos). Con eso se entrena:

  1. Regresión del cambio de OVR y de potencial del año siguiente (lineal vs Gradient Boosting vs la media por edad),
     evaluada con partición temporal: se entrena con FIFA 18-22 y se prueba con las ediciones 23 y 24. Se descartan las
     ediciones 15-17: sus jugadores crecían ~+2 OVR al año (frente a ~+0,7 después) por la forma en que EA calibraba las
     valoraciones, y eso sesgaba la predicción hacia arriba (+0,32 OVR de sesgo medio en la prueba).
  2. Ruido: desviación típica de los residuos por tramo de edad (el juego suma ese azar para que no sea determinista).
  3. Árbol de decisión (mejora / estable / decae) con sus reglas, para explicar la tendencia de un jugador.
  4. Regresión logística de retiro / salida del juego a partir de los 30 años.
  5. Regresión del valor de mercado con solo (OVR, potencial, edad, posición), para reajustar el valor al cambiar.

Genera: models/evolucion.joblib, reports/evolucion_metricas.json, reports/evolucion_reglas.txt,
reports/evolucion_curva_edad.png
"""
import json
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from juego.modelo import GRUPO_POS  # noqa: E402

MODELOS, REPORTES = RAIZ / "models", RAIZ / "reports"
SEMILLA = 42
GRUPOS = ["POR", "DEF", "MED", "DEL"]
FEATURES = ["age", "overall", "potential", "gap"] + ["g_" + g for g in GRUPOS]
DESDE = 18                                   # primera edición (par DESDE -> DESDE+1) que se usa para entrenar
TRAMOS_EDAD = [(0, 19), (20, 22), (23, 25), (26, 28), (29, 31), (32, 34), (35, 99)]
ETIQUETAS = ["decae", "estable", "mejora"]


def sec(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def cargar(ruta):
    """Una fila por jugador y edición (se usa la última actualización de cada edición)."""
    d = pd.read_csv(ruta / "male_players.csv",
                    usecols=["player_id", "fifa_version", "fifa_update", "overall", "potential", "age",
                             "player_positions", "value_eur"], low_memory=False)
    d = d.merge(d.groupby("fifa_version").fifa_update.max().rename("umax"), left_on="fifa_version", right_index=True)
    d = d[d.fifa_update == d.umax].drop_duplicates(["player_id", "fifa_version"]).copy()
    d["fifa_version"] = d.fifa_version.astype(int)
    pos = d.player_positions.astype(str).str.split(",").str[0].str.strip()
    d["grupo"] = pos.map(GRUPO_POS).fillna("MED")
    return d.dropna(subset=["overall", "potential", "age"])


def matriz(d):
    X = pd.DataFrame({"age": d.age.astype(float), "overall": d.overall.astype(float),
                      "potential": d.potential.astype(float)})
    X["gap"] = X.potential - X.overall
    for g in GRUPOS:
        X["g_" + g] = (d.grupo == g).astype(int).values
    return X[FEATURES]


def tramo(edad):
    e = np.asarray(edad)
    out = np.zeros(e.shape, dtype=int)
    for k, (a, b) in enumerate(TRAMOS_EDAD):
        out[(e >= a) & (e <= b)] = k
    return out


def main(ruta):
    sec("1. Pares jugador-año (edición v -> v+1)")
    d = cargar(ruta)
    pares = []
    for v in range(15, 24):
        a = d[d.fifa_version == v].set_index("player_id")
        b = d[d.fifa_version == v + 1].set_index("player_id")
        a = a.assign(v=v, sigue=a.index.isin(b.index))
        m = a.join(b[["overall", "potential"]].rename(columns={"overall": "ovr_sig", "potential": "pot_sig"}))
        pares.append(m.reset_index())
    P = pd.concat(pares, ignore_index=True)
    P = P[P.v >= DESDE]
    con = P[P.sigue].copy()
    con["d_ovr"] = con.ovr_sig - con.overall
    con["d_pot"] = con.pot_sig - con.potential
    print(f"  jugadores-año (FIFA {DESDE}-23): {len(P)} · con registro en la edición siguiente: {len(con)}")
    print(con.groupby(pd.cut(con.age, [0, 19, 22, 25, 28, 31, 34, 99])).d_ovr.agg(["mean", "std", "count"]).round(2))

    metricas = {"pares": int(len(con)), "desde_edicion": DESDE}
    Xc = matriz(con)
    train, test = (con.v <= 21).values, (con.v >= 22).values        # partición temporal
    sec("2. Regresión del cambio de OVR y de potencial (entrenar FIFA 18-22, probar FIFA 23-24)")
    modelos = {}
    for objetivo, col in (("ovr", "d_ovr"), ("pot", "d_pot")):
        y = con[col].values
        media_edad = pd.Series(y[train]).groupby(con.age.values[train]).mean()      # línea base: curva media por edad
        base = np.array([media_edad.get(a, 0.0) for a in con.age.values[test]])
        lin = LinearRegression().fit(Xc[train], y[train])
        gb = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, max_depth=5, random_state=SEMILLA)
        gb.fit(Xc[train], y[train])
        res = {}
        for nombre, pred in (("Media por edad (línea base)", base), ("Regresión lineal", lin.predict(Xc[test])),
                             ("Gradient Boosting", gb.predict(Xc[test]))):
            res[nombre] = {"R2": round(r2_score(y[test], pred), 4), "MAE": round(mean_absolute_error(y[test], pred), 3)}
            print(f"  Δ{objetivo.upper():<4} {nombre:<28} R2={res[nombre]['R2']:.4f}  MAE={res[nombre]['MAE']:.3f}")
        metricas["regresion_" + objetivo] = res
        modelos[objetivo] = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, max_depth=5,
                                                           random_state=SEMILLA).fit(Xc, y)      # modelo final con todo
        if objetivo == "ovr":
            resid = y[test] - gb.predict(Xc[test])
            tr = tramo(con.age.values[test])
            sigma = [float(np.std(resid[tr == k])) if (tr == k).sum() > 30 else float(np.std(resid))
                     for k in range(len(TRAMOS_EDAD))]
            sigma_pot = float(np.std(con.d_pot.values[test] - gb.predict(Xc[test]) * 0))
            pred_test, y_test, edad_test = gb.predict(Xc[test]), y[test], con.age.values[test]
    metricas["sigma_ovr_por_tramo"] = {f"{a}-{b}": round(s, 2) for (a, b), s in zip(TRAMOS_EDAD, sigma)}
    print("  σ del ruido por tramo de edad:", metricas["sigma_ovr_por_tramo"])

    sec("3. Árbol de decisión: ¿mejora (≥ +2), estable o decae (≤ -2)?")
    clase = np.where(con.d_ovr >= 2, 2, np.where(con.d_ovr <= -2, 0, 1))
    arbol = DecisionTreeClassifier(max_depth=4, min_samples_leaf=400, random_state=SEMILLA).fit(Xc[train], clase[train])
    acc = accuracy_score(clase[test], arbol.predict(Xc[test]))
    base_acc = float((clase[test] == np.bincount(clase[train]).argmax()).mean())
    auc = roc_auc_score(clase[test] == 2, arbol.predict_proba(Xc[test])[:, 2])
    print(f"  accuracy (prueba): {acc:.3f} · línea base (clase más frecuente): {base_acc:.3f} · AUC de 'mejora': {auc:.3f}")
    arbol = DecisionTreeClassifier(max_depth=4, min_samples_leaf=400, random_state=SEMILLA).fit(Xc, clase)
    reglas = export_text(arbol, feature_names=FEATURES, class_names=ETIQUETAS)
    (REPORTES / "evolucion_reglas.txt").write_text(reglas, encoding="utf-8")
    metricas["arbol_tendencia"] = {"accuracy": round(acc, 4), "linea_base": round(base_acc, 4), "auc_mejora": round(float(auc), 4), "profundidad": 4,
                                   "clases": ETIQUETAS}
    print(reglas)

    sec("4. Regresión logística: ¿sigue en el juego el año siguiente? (a partir de 30 años)")
    vet = P[P.age >= 30].copy()
    Xr = pd.DataFrame({"age": vet.age.astype(float), "overall": vet.overall.astype(float),
                       "potential": vet.potential.astype(float)})
    yr = (~vet.sigue).astype(int).values                   # 1 = ya no aparece en la edición siguiente
    retiro = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)).fit(Xr, yr)
    prob = retiro.predict_proba(Xr)[:, 1]
    print(f"  veteranos: {len(vet)} · salen del juego: {yr.mean():.1%} · probabilidad media predicha: {prob.mean():.1%}")
    for a in (30, 33, 35, 37, 40):
        sub = vet[vet.age == a]
        if len(sub):
            print(f"    edad {a}: real {(~sub.sigue).mean():.1%} · modelo {retiro.predict_proba(Xr.loc[sub.index])[:, 1].mean():.1%}")
    metricas["retiro"] = {"veteranos": int(len(vet)), "tasa_real": round(float(yr.mean()), 4),
                          "tasa_modelo": round(float(prob.mean()), 4)}

    sec("5. Regresión del valor de mercado con (OVR, potencial, edad, posición)")
    v24 = d[(d.fifa_version == 24) & d.value_eur.notna() & (d.value_eur > 0)]
    Xv, yv = matriz(v24), np.log1p(v24.value_eur.values)
    cut = np.random.default_rng(SEMILLA).random(len(v24)) < 0.8
    gbv = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.08, random_state=SEMILLA).fit(Xv[cut], yv[cut])
    r2v = r2_score(yv[~cut], gbv.predict(Xv[~cut]))
    print(f"  R2 (log valor): {r2v:.4f}")
    metricas["valor_simple"] = {"R2_log": round(float(r2v), 4)}
    valor = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.08, random_state=SEMILLA).fit(Xv, yv)

    # curva de evolución real vs predicha por edad (figura para el informe)
    edades = np.arange(16, 40)
    real = [con[(con.age == e)].d_ovr.mean() for e in edades]
    plt.figure(figsize=(8, 4.2))
    plt.plot(edades, real, "o-", label="Real (todas las ediciones)")
    plt.plot(edades, [pred_test[edad_test == e].mean() if (edad_test == e).any() else np.nan for e in edades],
             "s--", label="Modelo (FIFA 23-24, no visto al entrenar)")
    plt.plot(edades, [y_test[edad_test == e].mean() if (edad_test == e).any() else np.nan for e in edades],
             "^:", label="Real FIFA 23-24")
    plt.axhline(0, color="gray", lw=0.8)
    plt.xlabel("Edad")
    plt.ylabel("Cambio de OVR en un año")
    plt.title("Curva de evolución por edad")
    plt.legend()
    plt.tight_layout()
    plt.savefig(REPORTES / "evolucion_curva_edad.png", dpi=130)
    plt.close()

    joblib.dump({"features": FEATURES, "gb_ovr": modelos["ovr"], "gb_pot": modelos["pot"], "arbol": arbol,
                 "etiquetas": ETIQUETAS, "tramos": TRAMOS_EDAD, "sigma_ovr": sigma, "retiro": retiro,
                 "valor": valor}, MODELOS / "evolucion.joblib")
    (REPORTES / "evolucion_metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nListo: models/evolucion.joblib y reports/evolucion_*")


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if ruta is None or not (ruta / "male_players.csv").exists():
        sys.exit('Uso: python ml/entrenar_evolucion.py "C:/ruta/a/archive"  (carpeta con male_players.csv)')
    main(ruta)
