"""Sonido del juego: música en los menús, silbato del árbitro y ambiente de las gradas durante el partido.

No hay archivos de audio con derechos en el repositorio: el silbato, el público y la música por defecto se
*sintetizan* con numpy al abrir el juego (en un hilo, para no frenar el arranque).

Música de los menús:
  * si hay archivos (.ogg, .mp3, .wav, .flac) en assets/music/, se reproducen en orden aleatorio (carpeta ignorada por
    Git: ahí cada persona puede poner la música que tenga derecho a usar);
  * si no hay ninguno, suena una pieza instrumental generada por código.

Durante el partido la música se apaga con un fundido y entra el ambiente de la grada, que reacciona a los goles, a
las ocasiones falladas y al silbato. Los volúmenes y el silencio se guardan en ajustes.json (junto a la partida).
"""
import json
import random
import threading
from pathlib import Path

import numpy as np
import pygame

SR = 44100
RAIZ = Path(__file__).resolve().parent.parent
MUSICA = RAIZ / "assets" / "music"
EXT = (".ogg", ".mp3", ".wav", ".flac")


# ====================================================================== síntesis
def _pico(x, v=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * v


def _nivel(x, rms):
    """Lleva la señal a un nivel RMS (volumen percibido) y limita los picos con tanh: el público tiene picos muy altos."""
    return np.tanh(x / (np.std(x) + 1e-9) * rms / 0.6) * 0.6


def _ruido_banda(n, f1, f2, rng, pendiente=0.0):
    """Ruido blanco filtrado entre f1 y f2 Hz mediante FFT. Es periódico en n muestras (sirve para bucles)."""
    f = np.fft.rfftfreq(n, 1 / SR)
    amp = np.where((f >= f1) & (f <= f2), (np.maximum(f, 1.0) / 1000.0) ** (-pendiente), 0.0)
    amp = amp * np.exp(-((np.maximum(f - f2, 0) / 300.0) ** 2))
    x = np.fft.irfft(amp * np.exp(1j * rng.uniform(0, 2 * np.pi, len(f))), n)
    return x / (np.std(x) + 1e-9)


def _estereo(izq, der=None):
    der = izq if der is None else der
    return np.ascontiguousarray((np.stack([izq, der], axis=1) * 32767 * 0.95).astype(np.int16))


ESTILOS_SILBATO = {"fox40": "Fox 40", "bolita": "De bolita"}


def silbato(dur=0.4, f0=3050.0, rng=None, estilo="fox40", cola=True):
    """Pito de árbitro.

    fox40: silbato moderno sin bolita. Varias resonancias muy juntas (se pisan y dan ese timbre áspero y penetrante), un
           pequeño vibrato irregular, el soplido de aire de fondo y un ataque que arranca algo más agudo.
    bolita: silbato clásico; la bolita interrumpe el aire unas 27 veces por segundo y hace oscilar el tono y el volumen.
    Las dos llevan una reverberación corta de estadio (`cola` = dejarla sonar al final)."""
    rng = rng or np.random.default_rng(1)
    n = int(SR * dur)
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / 0.010) * np.minimum(1.0, (dur - t) / 0.06)
    deriva = np.cumsum(rng.standard_normal(n)) * 4e-5
    deriva -= deriva.mean()                                             # el soplido nunca es perfectamente estable
    arranque = 0.05 * np.exp(-t / 0.035)                                # el tono arranca ~5 % más agudo y se asienta
    if estilo == "bolita":
        trino = 0.5 + 0.5 * np.sin(2 * np.pi * 27 * t)
        f = f0 * 0.93 * (1 + arranque + 0.012 * np.sin(2 * np.pi * 27 * t + 0.6) + deriva)
        fase = np.cumsum(2 * np.pi * f / SR)
        tono = (np.sin(fase) + 0.35 * np.sin(2 * fase) + 0.12 * np.sin(3 * fase)) * (0.55 + 0.45 * trino)
        aire = _ruido_banda(n, 2200, 6500, rng) * 0.14 * (0.6 + 0.4 * trino)
    else:
        f = f0 * (1 + arranque + 0.006 * np.sin(2 * np.pi * 6.2 * t) + deriva)
        fase = np.cumsum(2 * np.pi * f / SR)
        tono = (np.sin(fase) + 0.75 * np.sin(1.083 * fase + 0.7) + 0.5 * np.sin(1.171 * fase + 1.9)
                + 0.18 * np.sin(2 * fase)) * (1 + 0.10 * np.sin(2 * np.pi * 11.5 * t + rng.uniform(0, 6.28)))
        aire = _ruido_banda(n, 2200, 6500, rng) * 0.10
    seco = (tono + aire) * env
    ir = rng.standard_normal(int(SR * 0.30)) * np.exp(-np.arange(int(SR * 0.30)) / (SR * 0.07))
    total = n + len(ir)
    eco = np.fft.irfft(np.fft.rfft(seco, total) * np.fft.rfft(ir, total), total)
    eco = eco / (np.max(np.abs(eco)) + 1e-9) * np.max(np.abs(seco))
    mezcla = np.concatenate([seco, np.zeros(len(ir))]) + 0.16 * eco
    return _pico(mezcla if cola else mezcla[:n], 0.6)


def silbato_final(rng=None, estilo="fox40"):
    """Tres pitidos: dos cortos y uno largo."""
    piezas = [silbato(0.42, 3050, rng, estilo, cola=False), np.zeros(int(SR * 0.16)),
              silbato(0.42, 3050, rng, estilo, cola=False), np.zeros(int(SR * 0.16)), silbato(1.0, 3000, rng, estilo)]
    return np.concatenate(piezas)


def grada_ambiente(rng, seg=12.0):
    """Murmullo del estadio, en bucle sin cortes (ruido periódico y modulaciones con ciclos enteros)."""
    n = int(SR * seg)
    t = np.arange(n) / SR
    canales = []
    for _ in range(2):
        base = _ruido_banda(n, 110, 3200, rng, 0.8) + 0.7 * _ruido_banda(n, 350, 1200, rng, 0.0)
        env = (1 + 0.20 * np.sin(2 * np.pi * 3 / seg * t + rng.uniform(0, 6.28))
               + 0.12 * np.sin(2 * np.pi * 7 / seg * t + rng.uniform(0, 6.28))
               + 0.06 * np.sin(2 * np.pi * 19 / seg * t + rng.uniform(0, 6.28)))
        canales.append(base * env)
    return canales[0], canales[1]


def _claps(n, tasa, rng):
    """Aplausos: impulsos aleatorios muy cortos (ruido con caída rápida)."""
    x = np.zeros(n)
    golpe = rng.standard_normal(int(SR * 0.012)) * np.exp(-np.arange(int(SR * 0.012)) / (SR * 0.0025))
    for i in np.nonzero(rng.random(n) < tasa / SR)[0]:
        x[i:i + len(golpe)] += golpe[:max(0, min(len(golpe), n - i))] * rng.uniform(0.4, 1.0)
    return x


def ovacion(rng, dur=5.0):
    """Rugido de gol: sube rápido, se mantiene con oleadas de voces y aplausos, y se apaga despacio."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    salida = []
    for _ in range(2):
        voz = _ruido_banda(n, 160, 5200, rng, 0.35) + 0.8 * _ruido_banda(n, 500, 1600, rng, 0.0)
        oleadas = 1 + 0.28 * np.sin(2 * np.pi * 2.2 * t + rng.uniform(0, 6)) + 0.15 * np.sin(2 * np.pi * 5.1 * t)
        env = (1 - np.exp(-t / 0.18)) * np.exp(-np.maximum(t - dur * 0.35, 0) / (dur * 0.30))
        salida.append(voz * oleadas * env + _claps(n, 140, rng) * 1.6 * env)
    return _nivel(salida[0], 0.22), _nivel(salida[1], 0.22)


def suspiro(rng, dur=1.7):
    """'¡Uuuy!' de la grada: voz grave que sube y baja."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    voz = _ruido_banda(n, 220, 1100, rng, 0.2) + 0.6 * _ruido_banda(n, 100, 400, rng, 0.0)
    env = np.sin(np.pi * np.minimum(t / dur, 1.0)) ** 1.6
    return _nivel(voz * env, 0.17)


def lamento(rng, dur=2.4):
    """Gol del rival: murmullo bajo y abatido, con algún abucheo."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    voz = _ruido_banda(n, 90, 520, rng, 0.0) * (1 + 0.35 * np.sin(2 * np.pi * 3.0 * t)) + 0.5 * _ruido_banda(n, 200, 900, rng, 0.0)
    env = (1 - np.exp(-t / 0.25)) * np.exp(-np.maximum(t - 0.6, 0) / 1.1)
    return _nivel(voz * env, 0.18)


def aplauso(rng, dur=2.4):
    n = int(SR * dur)
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / 0.2) * np.minimum(1.0, (dur - t) / 0.8)
    return _nivel((_claps(n, 95, rng) + 0.15 * _ruido_banda(n, 800, 4000, rng, 0.0)) * env, 0.16)


# ---- música instrumental por defecto
def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _nota(freq, dur, tipo, rng=None):
    n = int(SR * dur)
    t = np.arange(n) / SR
    if tipo == "pad":
        x = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2 * t) + 0.25 * np.sin(2 * np.pi * freq * 3.01 * t)
        env = np.minimum(1.0, t / 0.35) * np.minimum(1.0, (dur - t) / 0.35)
    elif tipo == "arp":
        x = sum(np.sin(2 * np.pi * freq * k * t) / k for k in (1, 3, 5, 7))
        env = np.exp(-t / 0.22) * np.minimum(1.0, t / 0.004)
    elif tipo == "bajo":
        x = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2 * t)
        env = np.minimum(1.0, t / 0.01) * np.exp(-t / 0.55)
    else:                                                   # melodía: sonido tipo sintetizador brillante
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
        fase = 2 * np.pi * freq * vib * t
        x = np.sin(fase) + 0.5 * np.sin(2 * fase) + 0.3 * np.sin(3 * fase) + 0.15 * np.sin(4 * fase)
        env = np.minimum(1.0, t / 0.02) * np.minimum(1.0, (dur - t) / 0.12)
    return x * env


def _sumar(buf, inicio, snd, gan=1.0):
    """Suma `snd` en `buf` desde `inicio`, dando la vuelta al final (así la pieza hace bucle sin cortes)."""
    n = len(buf)
    idx = (inicio + np.arange(len(snd))) % n
    np.add.at(buf, idx, snd * gan)


def musica_menu(seed=3):
    """Pieza instrumental de ~36 s: acordes, bajo, arpegio, percusión y, en la 2.ª mitad, una melodía."""
    rng = np.random.default_rng(seed)
    bpm = 108
    beat = 60 / bpm
    compases = 16
    n = int(SR * beat * 4 * compases)
    izq, der, centro = np.zeros(n), np.zeros(n), np.zeros(n)
    acordes = [([57, 60, 64], 45), ([53, 57, 60], 41), ([55, 60, 64], 48), ([55, 59, 62], 43)]    # Am F C G
    melodia = [[(76, 1.5), (74, 0.5), (72, 1), (69, 1)], [(72, 1.5), (69, 0.5), (72, 1), (77, 1)],
               [(79, 1.5), (76, 0.5), (74, 1), (72, 1)], [(74, 2), (71, 1), (74, 1)],
               [(76, 1.5), (74, 0.5), (72, 1), (69, 1)], [(77, 1), (76, 1), (72, 1), (69, 1)],
               [(79, 1), (81, 1), (79, 1), (76, 1)], [(74, 3), (0, 1)]]
    for c in range(compases):
        notas, raiz = acordes[c % 4]
        t0 = int(SR * beat * 4 * c)
        for m in notas:                                                  # colchón de acordes
            _sumar(centro, t0, _nota(_midi(m), beat * 4, "pad"), 0.07)
        for k, tiempo in enumerate((0, 1.5, 2.5)):                       # bajo sincopado
            _sumar(centro, t0 + int(SR * beat * tiempo), _nota(_midi(raiz), beat * (1.3 if k else 1.4), "bajo"), 0.32)
        orden = [0, 1, 2, 1, 2, 1, 0, 1]
        for k in range(8):                                               # arpegio de corcheas, abierto en estéreo
            m = notas[orden[k]] + 12 * (1 + (k % 4 == 3))
            s = _nota(_midi(m), beat * 0.5, "arp")
            ini = t0 + int(SR * beat * 0.5 * k)
            _sumar(izq, ini, s, 0.07 if k % 2 == 0 else 0.03)
            _sumar(der, ini + int(SR * 0.012), s, 0.03 if k % 2 == 0 else 0.07)
        for b in range(4):                                               # bombo en cada tiempo, caja en el 2 y el 4
            tb = int(SR * beat * 0.2)
            tt = np.arange(tb) / SR
            bombo = np.sin(2 * np.pi * (48 * tt + (140 - 48) * 0.04 * (1 - np.exp(-tt / 0.04)))) * np.exp(-tt / 0.07)
            _sumar(centro, t0 + int(SR * beat * b), bombo, 0.30)
            if b % 2 == 1:
                caja = _ruido_banda(int(SR * 0.14), 900, 7000, rng, 0.0) * np.exp(-np.arange(int(SR * 0.14)) / (SR * 0.04))
                _sumar(centro, t0 + int(SR * beat * b), caja, 0.10)
            hat = _ruido_banda(int(SR * 0.05), 6000, 12000, rng, 0.0) * np.exp(-np.arange(int(SR * 0.05)) / (SR * 0.012))
            _sumar(centro, t0 + int(SR * beat * (b + 0.5)), hat, 0.05)
        if c >= 8:                                                       # melodía en la segunda mitad
            pos = 0.0
            for m, dur in melodia[c - 8]:
                if m:
                    s = _nota(_midi(m), beat * dur, "mel")
                    _sumar(izq, t0 + int(SR * beat * pos), s, 0.085)
                    _sumar(der, t0 + int(SR * beat * pos) + int(SR * 0.008), s, 0.085)
                pos += dur
    L, R = centro + izq, centro + der
    pico = max(np.max(np.abs(L)), np.max(np.abs(R)))
    return _estereo(L / pico * 0.8, R / pico * 0.8)


# ====================================================================== gestor
class Audio:
    """Reproduce música y efectos. Si no hay dispositivo de audio, todo queda en silencio sin fallar."""

    def __init__(self, ruta_ajustes=None):
        self.activo = bool(pygame.mixer.get_init())
        self.ruta = Path(ruta_ajustes) if ruta_ajustes else None
        self.musica, self.efectos, self.silencio = 0.5, 0.8, False
        self.estilo_silbato = "fox40"
        self.cargar_ajustes()
        self.sonidos = {}
        self.listo = False
        self.registro = []                       # (tipo, nombre) de lo reproducido (para pruebas)
        self._v_musica = self._v_grada = 0.0     # volúmenes actuales (con fundidos)
        self._ultimo_silbato = -10_000
        self._pistas = sorted(p for p in MUSICA.glob("*") if p.suffix.lower() in EXT) if MUSICA.exists() else []
        self._pista_actual = None
        self._canal_musica = self._canal_grada = self._canal_sfx = self._canal_ev = None
        self._ambiente_en_marcha = self._musica_en_marcha = False
        if self.activo:
            pygame.mixer.set_num_channels(12)
            pygame.mixer.set_reserved(4)
            self._canal_musica, self._canal_grada, self._canal_sfx, self._canal_ev = (pygame.mixer.Channel(i) for i in range(4))
            threading.Thread(target=self._sintetizar, daemon=True).start()

    # ---------------------------------------------------------------- ajustes
    def cargar_ajustes(self):
        try:
            d = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta and self.ruta.exists() else {}
            self.musica = float(min(1, max(0, d.get("musica", self.musica))))
            self.efectos = float(min(1, max(0, d.get("efectos", self.efectos))))
            self.silencio = bool(d.get("silencio", False))
            self.estilo_silbato = d.get("silbato") if d.get("silbato") in ESTILOS_SILBATO else self.estilo_silbato
        except (OSError, ValueError, TypeError):
            pass

    def guardar_ajustes(self):
        if not self.ruta:
            return
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.ruta.write_text(json.dumps({"musica": round(self.musica, 2), "efectos": round(self.efectos, 2),
                                             "silencio": self.silencio, "silbato": self.estilo_silbato}),
                              encoding="utf-8")
        except OSError:
            pass

    def cambiar(self, que, delta):
        if que == "musica":
            self.musica = round(min(1.0, max(0.0, self.musica + delta)), 2)
        else:
            self.efectos = round(min(1.0, max(0.0, self.efectos + delta)), 2)
        self.guardar_ajustes()

    def alternar_silencio(self):
        self.silencio = not self.silencio
        self.guardar_ajustes()

    # ---------------------------------------------------------------- síntesis
    def _sintetizar(self):
        try:
            rng = np.random.default_rng(11)
            s = {}
            l, r = grada_ambiente(rng)
            s["grada"] = _estereo(_nivel(l, 0.13), _nivel(r, 0.13))
            l, r = ovacion(rng)
            s["gol_propio"] = _estereo(l, r)
            s["gol_rival"] = _estereo(lamento(rng))
            s["suspiro"] = _estereo(suspiro(rng))
            s["aplauso"] = _estereo(aplauso(rng))
            self.sonidos = {k: pygame.sndarray.make_sound(v) for k, v in s.items()}
            self._crear_silbatos()
            if not self._pistas:
                self.sonidos["musica"] = pygame.sndarray.make_sound(musica_menu())
            self.listo = True
        except Exception:                                   # sin audio el juego sigue igual
            self.listo = False

    def _crear_silbatos(self):
        """(Re)crea los cuatro pitidos con el estilo elegido."""
        rng, e = np.random.default_rng(23), self.estilo_silbato
        self.sonidos["silbato_corto"] = pygame.sndarray.make_sound(_estereo(silbato(0.38, 3050, rng, e)))
        self.sonidos["silbato_largo"] = pygame.sndarray.make_sound(_estereo(silbato(0.95, 3000, rng, e)))
        self.sonidos["silbato_inicio"] = pygame.sndarray.make_sound(_estereo(silbato(0.6, 3080, rng, e)))
        self.sonidos["silbato_final"] = pygame.sndarray.make_sound(_estereo(silbato_final(rng, e)))

    def cambiar_silbato(self):
        """Alterna el estilo del pito, lo guarda y hace sonar una muestra."""
        orden = list(ESTILOS_SILBATO)
        self.estilo_silbato = orden[(orden.index(self.estilo_silbato) + 1) % len(orden)]
        self.guardar_ajustes()
        if self.listo:
            self._crear_silbatos()
            self._ultimo_silbato = -10_000
            self.silbato("largo")

    # ---------------------------------------------------------------- efectos
    def _vol_efectos(self):
        return 0.0 if self.silencio else self.efectos

    def silbato(self, tipo="corto"):
        """tipo: corto | largo | inicio | final. Evita ráfagas de pitidos (mínimo 0,7 s entre cortos)."""
        ahora = pygame.time.get_ticks()
        if tipo == "corto" and ahora - self._ultimo_silbato < 700:
            return
        self._ultimo_silbato = ahora
        self._registrar("silbato", tipo)
        self._tocar("silbato_" + tipo, self._canal_sfx, 0.85)

    def grada(self, tipo):
        """tipo: gol_propio | gol_rival | suspiro | aplauso."""
        self._registrar("grada", tipo)
        self._tocar(tipo, self._canal_ev, {"gol_propio": 1.0, "gol_rival": 0.8, "suspiro": 0.8, "aplauso": 0.7}[tipo])

    def evento(self, e, lado_usuario):
        """Reacción de pitos y público a un evento de la crónica."""
        t = e["tipo"]
        if t in ("falta", "amarilla", "roja", "lesion"):
            self.silbato("corto")
        elif t == "gol" or e.get("res") == "gol":
            self.grada("gol_propio" if e["lado"] == lado_usuario else "gol_rival")
        elif t in ("penal", "tiro_libre", "ocasion") and e.get("res") == "fallo":
            self.grada("suspiro")
        elif t == "cambio" and e["lado"] == lado_usuario:
            self.grada("aplauso")

    def _registrar(self, tipo, nombre):
        self.registro.append((tipo, nombre))
        del self.registro[:-300]

    def _tocar(self, nombre, canal, ganancia):
        if not (self.activo and self.listo) or nombre not in self.sonidos or canal is None:
            return
        snd = self.sonidos[nombre]
        snd.set_volume(ganancia)
        canal.set_volume(self._vol_efectos())
        canal.play(snd)

    # ---------------------------------------------------------------- escenas (se llama cada cuadro)
    def actualizar(self, en_partido, tension=1.0):
        """en_partido: True mientras se juega el partido (entra la grada y sale la música).
        tension: 1 = jugando; <1 baja el público (descanso, minijuegos, cambios)."""
        if not self.activo:
            return
        m_obj = 0.0 if (en_partido or self.silencio) else self.musica
        g_obj = (self._vol_efectos() * 0.55 * tension) if en_partido else 0.0
        self._v_musica += (m_obj - self._v_musica) * 0.05
        self._v_grada += (g_obj - self._v_grada) * 0.05
        self._gestionar_musica()
        if self._canal_grada is not None:
            if self.listo and "grada" in self.sonidos and self._v_grada > 0.01 and not self._ambiente_en_marcha:
                self._canal_grada.play(self.sonidos["grada"], loops=-1)
                self._ambiente_en_marcha = True
            elif self._v_grada <= 0.01 and self._ambiente_en_marcha:
                self._canal_grada.stop()
                self._ambiente_en_marcha = False
            if self._ambiente_en_marcha:
                self._canal_grada.set_volume(min(1.0, self._v_grada))

    def _gestionar_musica(self):
        quiere = self._v_musica > 0.01
        if self._pistas:                                    # archivos del usuario: streaming con mixer.music
            if quiere:
                if not pygame.mixer.music.get_busy():
                    self._siguiente_pista()
                pygame.mixer.music.set_volume(min(1.0, self._v_musica))
            elif pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        elif self.listo and "musica" in self.sonidos:        # pieza generada
            if quiere and not self._musica_en_marcha:
                self._canal_musica.play(self.sonidos["musica"], loops=-1)
                self._musica_en_marcha = True
            elif not quiere and self._musica_en_marcha:
                self._canal_musica.stop()
                self._musica_en_marcha = False
            if self._musica_en_marcha:
                self._canal_musica.set_volume(min(1.0, self._v_musica))

    def _siguiente_pista(self):
        opciones = [p for p in self._pistas if p != self._pista_actual] or self._pistas
        self._pista_actual = random.choice(opciones)
        try:
            pygame.mixer.music.load(str(self._pista_actual))
            pygame.mixer.music.play()
        except pygame.error:                                 # archivo ilegible: se descarta
            self._pistas = [p for p in self._pistas if p != self._pista_actual]
            self._pista_actual = None

    @property
    def pista(self):
        if self._pistas:
            return self._pista_actual.stem if self._pista_actual else None
        return "Música del juego" if self._musica_en_marcha else None
