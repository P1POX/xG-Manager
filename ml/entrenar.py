"""Paso 2 - Entrenamiento de los modelos de minería de datos.

Uso (después de preparar_datos.py):
    python ml/entrenar.py

Genera:
    data/jugadores_ml.csv   jugadores + rol (cluster), valor justo, probabilidad de posición
    data/vectores.npy       vector estandarizado de atributos (para 'buscar reemplazo')
    models/arbol_partido.joblib, models/reglas.json
    reports/metricas.json y reports/*.txt, *.png
"""
import json
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             mean_absolute_error, r2_score, silhouette_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from juego import tactica as tac  # noqa: E402
from juego.modelo import GRUPO_POS  # noqa: E402

DATA, MODELOS, REPORTES = RAIZ / "data", RAIZ / "models", RAIZ / "reports"
for d in (MODELOS, REPORTES):
    d.mkdir(exist_ok=True)
SEMILLA = 42
metricas = {}

ATR_CAMPO = [
    "pace", "shooting", "passing", "dribbling", "defending", "physic",
    "attacking_crossing", "attacking_finishing", "attacking_heading_accuracy",
    "attacking_short_passing", "attacking_volleys", "skill_dribbling", "skill_curve",
    "skill_fk_accuracy", "skill_long_passing", "skill_ball_control", "movement_acceleration",
    "movement_sprint_speed", "movement_agility", "movement_reactions", "movement_balance",
    "power_shot_power", "power_jumping", "power_stamina", "power_strength", "power_long_shots",
    "mentality_aggression", "mentality_interceptions", "mentality_positioning", "mentality_vision",
    "mentality_penalties", "mentality_composure", "defending_marking_awareness",
    "defending_standing_tackle", "defending_sliding_tackle",
]
ATR_POR = ["goalkeeping_diving", "goalkeeping_handling", "goalkeeping_kicking",
           "goalkeeping_positioning", "goalkeeping_reflexes"]
GRUPOS = ["POR", "DEF", "MED", "DEL"]

ES = {  # traducción de atributos para nombrar clusters y reglas
    "pace": "velocidad", "shooting": "tiro", "passing": "pase", "dribbling": "regate",
    "defending": "defensa", "physic": "físico", "attacking_crossing": "centros",
    "attacking_finishing": "definición", "attacking_heading_accuracy": "juego aéreo",
    "mentality_vision": "visión", "mentality_interceptions": "intercepción",
    "defending_standing_tackle": "entrada", "power_strength": "fuerza", "skill_dribbling": "regate",
    "skill_long_passing": "pase largo", "power_stamina": "resistencia", "movement_agility": "agilidad",
    "attacking_short_passing": "pase corto", "skill_ball_control": "control", "power_long_shots": "tiro lejano",
}


def sec(titulo):
    print(f"\n=== {titulo} " + "=" * (60 - len(titulo)))


# ------------------------------------------------------------------ 1. CLUSTERING
def clustering(jug):
    sec("1. Clustering K-means (roles de jugadores de campo)")
    campo = jug.grupo != "POR"
    X = jug.loc[campo, ATR_CAMPO].values.astype(float)
    esc = StandardScaler().fit(X)
    Z = esc.transform(X)

    res = []
    muestra = np.random.default_rng(SEMILLA).choice(len(Z), 4000, replace=False)
    for k in range(3, 11):
        km = KMeans(n_clusters=k, n_init=5, random_state=SEMILLA).fit(Z)
        sil = silhouette_score(Z[muestra], km.labels_[muestra])
        res.append((k, km.inertia_, sil))
        print(f"  k={k:2d}  inercia={km.inertia_:12.0f}  silueta={sil:.3f}")
    # Se elige k=8: da roles de juego interpretables (la silueta máxima suele ser k pequeño
    # y solo separa defensas / mediocampistas / delanteros, que ya conocemos de antemano).
    K = 8
    km = KMeans(n_clusters=K, n_init=10, random_state=SEMILLA).fit(Z)
    etiquetas = km.labels_
    sil_final = silhouette_score(Z[muestra], etiquetas[muestra])

    # Nombre automático de cada cluster: grupo dominante + atributo más distintivo
    cdf = jug.loc[campo].copy()
    cdf["c"] = etiquetas
    nombres = {}
    zdf = pd.DataFrame(Z, columns=ATR_CAMPO)
    for c in range(K):
        sub = cdf[cdf.c == c]
        dom = sub.grupo.value_counts().idxmax()
        cen = zdf[etiquetas == c].mean()
        # atributos 'legibles' con mayor valor medio estandarizado
        legibles = [a for a in ES if a in cen.index]
        top = cen[legibles].sort_values(ascending=False).index[:2]
        base = {"DEF": "Defensa", "MED": "Medio", "DEL": "Delantero"}[dom]
        nombres[c] = f"{base} · {ES[top[0]]}/{ES[top[1]]}"
        print(f"  cluster {c}: n={len(sub):5d}  {nombres[c]:<36} grupos={sub.grupo.value_counts().to_dict()}")
    # Evitar nombres repetidos
    vistos = {}
    for c in range(K):
        n = nombres[c]
        vistos[n] = vistos.get(n, 0) + 1
        if vistos[n] > 1:
            nombres[c] = f"{n} ({vistos[n]})"

    jug["cluster_id"] = -1
    jug.loc[campo, "cluster_id"] = etiquetas
    jug["rol"] = jug.cluster_id.map(nombres)
    # Porteros: un cluster propio (los atributos de portero separan solo a este grupo)
    jug.loc[~campo, "cluster_id"] = K
    jug.loc[~campo, "rol"] = "Portero"

    # Vectores estandarizados para 'buscar reemplazo' (campo + porteros por separado)
    vec = np.zeros((len(jug), len(ATR_CAMPO) + len(ATR_POR)), dtype=np.float32)
    vec[campo.values, :len(ATR_CAMPO)] = Z
    zp = StandardScaler().fit_transform(jug.loc[~campo, ATR_POR].values.astype(float))
    vec[(~campo).values, len(ATR_CAMPO):] = zp
    np.save(DATA / "vectores.npy", vec)

    # Gráficos: codo/silueta y proyección PCA
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ks = [r[0] for r in res]
    ax[0].plot(ks, [r[1] for r in res], "o-")
    ax[0].set(title="Método del codo", xlabel="k", ylabel="Inercia")
    ax[1].plot(ks, [r[2] for r in res], "o-", color="tab:orange")
    ax[1].set(title="Coeficiente de silueta", xlabel="k")
    fig.tight_layout()
    fig.savefig(REPORTES / "kmeans_codo_silueta.png", dpi=110)
    plt.close(fig)

    pca = PCA(2, random_state=SEMILLA).fit(Z)
    P = pca.transform(Z)
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(P[::3, 0], P[::3, 1], c=etiquetas[::3], cmap="tab10", s=4)
    ax.set(title=f"Roles de jugadores (PCA, var. explicada {pca.explained_variance_ratio_.sum():.0%})")
    fig.savefig(REPORTES / "kmeans_pca.png", dpi=110)
    plt.close(fig)
    pd.DataFrame(P[::2], columns=["x", "y"]).assign(c=etiquetas[::2]).to_csv(DATA / "pca_roles.csv", index=False)

    metricas["clustering"] = {"k": K, "silueta": round(float(sil_final), 3),
                              "curva": [(k, round(i, 0), round(s, 3)) for k, i, s in res],
                              "roles": nombres}
    return jug


# ------------------------------------------------------------------ 2. REGRESIÓN
def regresion(jug):
    sec("2. Regresión: valor de mercado 'justo'")
    d = jug.copy()
    for g in GRUPOS:
        d["g_" + g] = (d.grupo == g).astype(int)
    feats = ["overall", "potential", "age", "international_reputation", "skill_moves", "weak_foot",
             "pace", "shooting", "passing", "dribbling", "defending", "physic"] + ["g_" + g for g in GRUPOS]
    X, y = d[feats], np.log1p(d.value_eur)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEMILLA)

    lin = LinearRegression().fit(Xtr, ytr)
    gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=SEMILLA).fit(Xtr, ytr)
    out = {}
    for nombre, m in (("Regresión lineal", lin), ("Gradient Boosting", gb)):
        p = m.predict(Xte)
        mae_eur = mean_absolute_error(np.expm1(yte), np.expm1(p))
        out[nombre] = {"R2_log": round(r2_score(yte, p), 4), "MAE_eur": round(mae_eur)}
        print(f"  {nombre:<18} R2(log valor)={out[nombre]['R2_log']:.4f}  MAE={mae_eur / 1e6:.2f} M€")
    jug["valor_pred"] = np.expm1(gb.predict(X))
    metricas["regresion"] = out
    joblib.dump({"modelo": gb, "features": feats}, MODELOS / "regresion_valor.joblib")
    return jug


# ------------------------------------------------- 3. ÁRBOL: posición del jugador
def arbol_posicion(jug):
    sec("3. Árbol de decisión: posición (POR/DEF/MED/DEL) a partir de atributos")
    feats = ATR_CAMPO + ATR_POR
    X, y = jug[feats], jug.grupo
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEMILLA, stratify=y)
    arbol = DecisionTreeClassifier(max_depth=6, min_samples_leaf=30, random_state=SEMILLA).fit(Xtr, ytr)
    rf = RandomForestClassifier(n_estimators=150, random_state=SEMILLA, n_jobs=-1).fit(Xtr, ytr)
    acc_a, acc_r = accuracy_score(yte, arbol.predict(Xte)), accuracy_score(yte, rf.predict(Xte))
    print(f"  Árbol (prof. 6): accuracy={acc_a:.3f}   Random Forest: accuracy={acc_r:.3f}")
    print(classification_report(yte, arbol.predict(Xte), digits=3))
    cm = confusion_matrix(yte, arbol.predict(Xte), labels=GRUPOS)
    print("  Matriz de confusión (filas=real, cols=predicho)", GRUPOS, "\n", cm)
    texto = export_text(arbol, feature_names=feats, max_depth=4)
    (REPORTES / "arbol_posicion_reglas.txt").write_text(texto, encoding="utf-8")
    metricas["arbol_posicion"] = {"accuracy_arbol": round(acc_a, 4), "accuracy_random_forest": round(acc_r, 4),
                                  "matriz_confusion": cm.tolist(), "orden": GRUPOS}
    proba = arbol.predict_proba(jug[feats])
    for i, g in enumerate(arbol.classes_):
        jug["p_" + g] = proba[:, i]
    return jug


# ------------------------------------------------------ 4. REGLAS DE ASOCIACIÓN
def reglas_tacticas():
    sec("4. Reglas de asociación (Apriori): tácticas -> nivel del equipo")
    h = pd.read_csv(DATA / "tacticas_hist.csv")
    h["pct"] = h.groupby("fifa_version").overall.rank(pct=True)
    h["nivel"] = pd.cut(h.pct, [0, .40, .75, .93, 1.0], labels=tac.TIERS, include_lowest=True).astype(str)
    trans = []
    for r in h.to_dict("records"):
        items = tac.a_items(tac.tactica_desde_fila(r))
        items.add(f"Nivel = {r['nivel']}")
        trans.append(items)
    todos = sorted({i for t in trans for i in t})
    oh = pd.DataFrame([{i: (i in t) for i in todos} for t in trans])
    freq = apriori(oh, min_support=0.015, use_colnames=True, max_len=4)
    reglas = association_rules(freq, metric="confidence", min_threshold=0.30)
    # Solo reglas  {ajustes tácticos}  ->  {Nivel = X}
    reglas = reglas[reglas.consequents.apply(lambda s: len(s) == 1 and next(iter(s)).startswith("Nivel"))]
    reglas = reglas[reglas.antecedents.apply(lambda s: not any(i.startswith("Nivel") for i in s))]
    reglas = reglas[(reglas.lift > 1.12) | (reglas.lift < 0.80)]
    reglas = reglas.sort_values("lift", ascending=False)
    print(f"  Transacciones: {len(trans)}   itemsets frecuentes: {len(freq)}   reglas útiles: {len(reglas)}")
    lista = []
    for r in reglas.itertuples():
        lista.append({"si": sorted(r.antecedents), "entonces": next(iter(r.consequents)),
                      "soporte": round(r.support, 4), "confianza": round(r.confidence, 3),
                      "lift": round(r.lift, 3)})
    for r in lista[:8]:
        print(f"  {' & '.join(r['si'])}  =>  {r['entonces']}   (sop={r['soporte']:.3f} conf={r['confianza']:.2f} lift={r['lift']:.2f})")
    (MODELOS / "reglas.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    metricas["reglas_tacticas"] = {"transacciones": len(trans), "reglas": len(lista),
                                   "soporte_min": 0.015, "confianza_min": 0.30}
    return lista


def reglas_rasgos(jug):
    sec("4b. Reglas de asociación: rasgos de jugadores (traits)")
    trans = [set(t.split(", ")) for t in jug.player_traits.fillna("") if t]
    todos = sorted({i for t in trans for i in t})
    oh = pd.DataFrame([{i: (i in t) for i in todos} for t in trans])
    freq = apriori(oh, min_support=0.02, use_colnames=True, max_len=3)
    reglas = association_rules(freq, metric="lift", min_threshold=2.0)
    reglas = reglas[reglas.confidence >= 0.5].sort_values("lift", ascending=False)
    print(f"  Jugadores con rasgos: {len(trans)}  reglas: {len(reglas)}")
    lineas = []
    for r in reglas.head(15).itertuples():
        l = f"{{{', '.join(sorted(r.antecedents))}}} => {{{', '.join(sorted(r.consequents))}}}  conf={r.confidence:.2f} lift={r.lift:.1f}"
        lineas.append(l)
        print("  " + l)
    (REPORTES / "reglas_rasgos.txt").write_text("\n".join(lineas), encoding="utf-8")
    metricas["reglas_rasgos"] = {"jugadores": len(trans), "reglas": int(len(reglas))}


# --------------------------------------------- 5. ÁRBOL: resultado del partido
def arbol_partido(reglas):
    """El dataset no tiene partidos, así que el árbol se entrena con partidos simulados
    entre clubes reales (con plantel y tácticas reales). Sirve para explicar qué factores
    pesan en el resultado y para dar un pronóstico rápido en el juego."""
    sec("5. Árbol de decisión: resultado del partido (entrenado con partidos simulados)")
    from juego.asistente import Asistente, features_partido
    from juego.datos import Mundo
    from juego.simulacion import fuerzas, goles_esperados, simular

    mundo = Mundo(seed=SEMILLA)
    asis = Asistente(reglas_lista=reglas)
    rng = np.random.default_rng(SEMILLA)
    ids = list(mundo.clubes)
    filas, ys = [], []
    for _ in range(8000):
        a, b = (mundo.clubes[i] for i in rng.choice(ids, 2, replace=False))
        # variamos las tácticas para que el árbol vea de todo
        ta = {k: rng.choice(tac.OPCIONES[k]) for k in tac.CLAVES} if rng.random() < .5 else a.tactica
        tb = {k: rng.choice(tac.OPCIONES[k]) for k in tac.CLAVES} if rng.random() < .5 else b.tactica
        fa, fb = fuerzas(a.xi_con_grupo()), fuerzas(b.xi_con_grupo())
        ba, bb = asis.bono_tactico(ta), asis.bono_tactico(tb)
        la, lb = goles_esperados(fa, fb, ta, tb, True, ba, bb)
        ga, gb = simular(la, lb, rng)
        filas.append(features_partido(fa, fb, ta, tb, ba, bb))
        ys.append("Local" if ga > gb else "Empate" if ga == gb else "Visitante")
    X = pd.DataFrame(filas)
    y = pd.Series(ys)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEMILLA, stratify=y)
    candidatos = []
    for prof in (3, 4, 5, 6):
        arb = DecisionTreeClassifier(max_depth=prof, min_samples_leaf=40, random_state=SEMILLA).fit(Xtr, ytr)
        acc = accuracy_score(yte, arb.predict(Xte))
        print(f"  prof={prof}  accuracy={acc:.3f}")
        candidatos.append((acc, prof, arb))
    # Se elige el árbol más simple cuya precisión está a menos de 1 punto de la mejor (interpretabilidad)
    top = max(c[0] for c in candidatos)
    mejor = next(c for c in candidatos if c[0] >= top - 0.01)
    acc, prof, arb = mejor
    base = (y == y.mode()[0]).mean()
    print(f"  -> profundidad elegida {prof}, accuracy={acc:.3f} (línea base clase mayoritaria={base:.3f})")
    print(classification_report(yte, arb.predict(Xte), digits=3))
    (REPORTES / "arbol_partido_reglas.txt").write_text(export_text(arb, feature_names=list(X.columns)), encoding="utf-8")
    joblib.dump({"arbol": arb, "features": list(X.columns)}, MODELOS / "arbol_partido.joblib")
    metricas["arbol_partido"] = {"profundidad": prof, "accuracy": round(acc, 4), "linea_base": round(float(base), 4),
                                 "partidos_entrenamiento": len(X), "nota": "datos simulados"}


def main():
    jug = pd.read_csv(DATA / "jugadores.csv", keep_default_na=False, na_values=[""])
    jug["grupo"] = jug.pos_principal.map(GRUPO_POS)
    jug = jug.dropna(subset=["grupo"]).reset_index(drop=True)
    jug = clustering(jug)
    jug = regresion(jug)
    jug = arbol_posicion(jug)
    jug.drop(columns=["grupo"]).to_csv(DATA / "jugadores_ml.csv", index=False)
    reglas = reglas_tacticas()
    reglas_rasgos(jug)
    arbol_partido(reglas)
    (REPORTES / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nListo. Métricas en reports/metricas.json")


if __name__ == "__main__":
    main()
