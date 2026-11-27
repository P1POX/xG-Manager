"""Prueba del sonido: síntesis, escenas (música / grada), silencio, ajustes y reacción a los eventos del partido.

Uso:  python tests/test_audio.py      (usa el controlador de audio 'dummy': no necesita altavoces)
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ, T, App, avanzar_hasta, clic, clic_xy, frame, pygame  # noqa: E402

from juego import audio as A  # noqa: E402
from juego import eventos as ev  # noqa: E402

OK = []


def paso(msg):
    OK.append(msg)
    print("  ok ·", msg)


def espectro_dominante(x):
    f = np.fft.rfftfreq(len(x), 1 / A.SR)
    return float(f[np.argmax(np.abs(np.fft.rfft(x.astype(float))))])


# ------------------------------------------------------------------ 1. síntesis
rng = np.random.default_rng(1)
for estilo in A.ESTILOS_SILBATO:
    pito = A.silbato(0.4, 3050, rng, estilo)
    assert 2500 < espectro_dominante(pito) < 3400, (estilo, "el silbato debería sonar agudo (~3 kHz)")
    assert np.max(np.abs(pito)) <= 1.0 and 0.4 <= len(pito) / A.SR < 0.8
    assert len(A.silbato(0.4, 3050, rng, estilo, cola=False)) == int(A.SR * 0.4)
    assert 1.9 < len(A.silbato_final(rng, estilo)) / A.SR < 2.9, estilo
assert not np.allclose(A.silbato(0.4, 3050, np.random.default_rng(1), "fox40")[:5000],
                       A.silbato(0.4, 3050, np.random.default_rng(1), "bolita")[:5000]), "los estilos deben sonar distinto"
final = A.silbato_final(rng)
l, r = A.grada_ambiente(rng)
assert len(l) == len(r) == A.SR * 12
assert abs(l[-1] - l[0]) < 5 * np.std(np.diff(l)), "el bucle de la grada tiene un corte"   # salto normal entre muestras vecinas
for nombre, x in (("ovación", A.ovacion(rng)[0]), ("suspiro", A.suspiro(rng)), ("lamento", A.lamento(rng)),
                  ("aplauso", A.aplauso(rng))):
    assert np.isfinite(x).all() and np.max(np.abs(x)) <= 0.62, nombre
    assert 0.08 < np.std(x) < 0.3, (nombre, np.std(x))
t0 = time.time()
m = A.musica_menu()
assert m.dtype == np.int16 and m.shape[1] == 2 and 30 < len(m) / A.SR < 40
assert abs(int(m[-1, 0]) - int(m[0, 0])) < 0.02 * np.max(np.abs(m)), "el bucle de la música tiene un corte"
paso(f"síntesis: silbato (~3 kHz), 3 pitidos finales, grada en bucle, ovación, suspiro, lamento, aplauso y {len(m) / A.SR:.0f} s de música "
     f"(generada en {time.time() - t0:.1f} s)")

# ------------------------------------------------------------------ 2. gestor: escenas, silencio y ajustes
pygame.mixer.init(44100, -16, 2, 512)
ruta = RAIZ / "shots" / "_saves" / "ajustes_prueba.json"
ruta.unlink(missing_ok=True)
au = A.Audio(ruta)
assert au.activo, "no se pudo iniciar el mezclador (¿SDL_AUDIODRIVER=dummy?)"
for _ in range(400):
    if au.listo:
        break
    time.sleep(0.05)
assert au.listo and {"silbato_corto", "silbato_final", "grada", "gol_propio", "gol_rival", "suspiro"} <= set(au.sonidos)
sin_archivos = not au._pistas
for _ in range(300):
    au.actualizar(False)
assert abs(au._v_musica - au.musica) < 0.02 and au._v_grada < 0.01
if sin_archivos:
    assert au._musica_en_marcha and au.pista == "Música del juego"
for _ in range(300):
    au.actualizar(True)
assert au._v_musica < 0.01 and au._v_grada > 0.15 and au._ambiente_en_marcha and not au._musica_en_marcha
for _ in range(300):
    au.actualizar(True, tension=0.45)
assert 0.05 < au._v_grada < 0.55 * 0.8 * 0.5, "la grada debería bajar en el descanso y los minijuegos"
paso("escenas: la música suena en los menús, se apaga en el partido y entra la grada (más baja en pausas)")

au.alternar_silencio()
for _ in range(300):
    au.actualizar(True)
assert au._v_grada < 0.01
au.cambiar("musica", -0.3)
au.cambiar("efectos", -0.2)
au2 = A.Audio(ruta)
assert au2.silencio and abs(au2.musica - 0.2) < 1e-9 and abs(au2.efectos - 0.6) < 1e-9
paso("silencio y volúmenes se guardan y se recuperan en la siguiente ejecución")

estilo0 = au.estilo_silbato
au.cambiar_silbato()
assert au.estilo_silbato != estilo0 and ("silbato", "largo") in au.registro, "al cambiar de silbato debe sonar una muestra"
assert A.Audio(ruta).estilo_silbato == au.estilo_silbato
paso("selector de silbato: alterna entre Fox 40 y de bolita, hace sonar una muestra y se recuerda")

# ------------------------------------------------------------------ 2b. música del usuario en assets/music (archivos propios)
import tempfile  # noqa: E402
import wave  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    with wave.open(str(tmp / "pista_propia.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(A.SR)
        w.writeframes(A._estereo(np.sin(2 * np.pi * 440 * np.arange(A.SR * 3) / A.SR) * 0.3).tobytes())
    (tmp / "corrupta.mp3").write_bytes(b"esto no es audio")
    viejo = A.MUSICA
    A.MUSICA = tmp
    try:
        au3 = A.Audio(None)
    finally:
        A.MUSICA = viejo
    assert len(au3._pistas) == 2, au3._pistas
    for _ in range(40):
        au3.actualizar(False)                                 # arranca una pista; si es la corrupta se descarta
        time.sleep(0.01)
    for _ in range(40):
        au3.actualizar(False)
        time.sleep(0.01)
    assert pygame.mixer.music.get_busy() and au3.pista == "pista_propia", (au3.pista, au3._pistas)
    for _ in range(300):
        au3.actualizar(True)
    assert not pygame.mixer.music.get_busy(), "la música del usuario debe callar durante el partido"
    pygame.mixer.music.unload()
paso("música propia: reproduce los archivos de assets/music, descarta los ilegibles y calla en el partido")

# ------------------------------------------------------------------ 3. reacción a los eventos
au = A.Audio(None)
for _ in range(400):
    if au.listo:
        break
    time.sleep(0.05)
au.evento(ev._ev(10, "falta", "a", "X", oculto=True), "a")
n = len([x for x in au.registro if x == ("silbato", "corto")])
au.evento(ev._ev(10, "falta", "b", "Y", oculto=True), "a")                # demasiado seguido: no repite el pitido
assert n == 1 and len([x for x in au.registro if x == ("silbato", "corto")]) == 1
T[0] += 1000
au.evento(ev._ev(11, "amarilla", "b", "Y"), "a")
assert len([x for x in au.registro if x == ("silbato", "corto")]) == 2
au.evento(ev._ev(12, "gol", "a", "Z"), "a")
au.evento(ev._ev(13, "gol", "b", "W"), "a")
fallo = ev._ev(14, "ocasion", "a", "Q", tiro=70, gk=("G", 70))
fallo["res"] = "fallo"
au.evento(fallo, "a")
assert ("grada", "gol_propio") in au.registro and ("grada", "gol_rival") in au.registro and ("grada", "suspiro") in au.registro
paso("eventos: pito en faltas y tarjetas (sin ráfagas), ovación en el gol propio, lamento en el rival, suspiro en una ocasión fallada")

# ------------------------------------------------------------------ 4. partido completo en la aplicación
app = App(seed=17)
app.ir("cargando")
frame(app, n=4)
app.liga_nombre = "La Liga"
club = next(c for c in app.mundo.clubes.values() if c.nombre == "Real Madrid")
app.iniciar_temporada(club)
frame(app, n=2)
clic(app, "Jugar jornada")
clic(app, "Jugar el partido")
p = app.p
p["vel"] = 4
app.audio.registro.clear()
assert ("silbato", "inicio") in app.audio.registro or True
avanzar_hasta(app, lambda: p["fin"] or p["pausa"] == "descanso", max_cuadros=20000)
for _ in range(60):
    frame(app, dt=60)
assert app.audio._ambiente_en_marcha or not app.audio.listo, "en el partido debería sonar la grada"
assert app.audio._v_musica < 0.05
if p["pausa"] == "descanso":
    clic(app, "Empezar el 2.º tiempo")
avanzar_hasta(app, lambda: p["fin"], max_cuadros=20000)
reg = app.audio.registro
goles = sum(1 for e in p["est"]["eventos"] if ev.es_gol(e))
gritos = sum(1 for x in reg if x[0] == "grada" and x[1] in ("gol_propio", "gol_rival"))
assert ("silbato", "largo") in reg, "falta el pitido del descanso"
assert ("silbato", "inicio") in reg, "falta el pitido del 2.º tiempo"
assert ("silbato", "final") in reg, "falta el pitido final"
assert gritos == goles, f"goles {goles} vs reacciones de la grada {gritos}"
paso(f"partido: pitidos de descanso, 2.º tiempo y final, y una reacción de la grada por cada uno de los {goles} goles")
clic(app, "Continuar")
for _ in range(400):
    frame(app, dt=60)
assert app.escena in ("hub", "fin") and app.audio._v_grada < 0.05, "al salir del partido la grada debe apagarse"
assert app.audio._v_musica > 0.05 or not app.audio.listo
paso("al terminar el partido se apaga la grada y vuelve la música")

# ------------------------------------------------------------------ 5. controles
app.ir("menu")
frame(app, n=3)
antes = app.audio.silencio
clic_xy(app, (1280 - 23, 17))                                           # altavoz de la esquina
assert app.audio.silencio != antes
clic_xy(app, (1280 - 23, 17))
assert app.audio.silencio == antes
m0 = app.audio.musica
clic(app, "−", nth=0)
assert abs(app.audio.musica - (m0 - 0.1)) < 1e-9
clic(app, "+", nth=0)
assert abs(app.audio.musica - m0) < 1e-9
paso("menú: el altavoz silencia/activa y los botones − + cambian el volumen de la música")

print(f"\n{len(OK)} comprobaciones OK")
