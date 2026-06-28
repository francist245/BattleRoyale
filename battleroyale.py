"""
STORM ROYALE  --  a 3D battle royale
====================================
Francis & Toby's own battle royale!  Drop into the arena, grab a weapon and
fight an ENORMOUS army of enemies of every difficulty -- from weak grunts all
the way up to giant Juggernaut bosses.  A deadly storm keeps closing in, so
stay in the safe zone and be the LAST ONE STANDING for a VICTORY ROYALE.

Controls
  Mouse           look around
  WASD            move,  Shift sprint,  Space jump
  Left click      shoot  (hold for automatic weapons)
  R               reload
  1 / 2 / 3       switch weapon  (Rifle / Shotgun / Sniper)
  scroll          cycle weapons
  M               mute / unmute music
  Enter / R       restart after the match ends

NOTE on music: real game soundtracks are copyrighted, so STORM ROYALE plays
ORIGINAL chiptune battle music written just for it.

Run:  python battleroyale.py
"""
import math
import os
import random
import wave

import numpy as np
from PIL import Image

from ursina import (
    Ursina, Entity, camera, color, Vec3, Vec2, Text, window, mouse, scene,
    held_keys, destroy, invoke, Texture, clamp, lerp, time as utime,
    DirectionalLight, AmbientLight, raycast,
)
from ursina.prefabs.first_person_controller import FirstPersonController

from panda3d.core import loadPrcFileData
loadPrcFileData('', 'audio-library-name p3openal_audio')

from ursina import color as _ucolor
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets')
os.makedirs(ASSETS, exist_ok=True)


def C(r, g, b, a=255):
    """Ursina Color from 0-255 channel values."""
    return _ucolor.rgba(r / 255, g / 255, b / 255, a / 255)


# ============================================================================
# PROCEDURAL HD TEXTURES  (16px pixel art, nearest-neighbour filtered)
# ============================================================================
def _rng(name):
    return np.random.RandomState(abs(hash(name)) % (2 ** 31))


def _shade(base, d):
    return tuple(int(clamp(base[i] + d, 0, 255)) for i in range(3))


def make_pixels(name, base, kind='noise', accent=None, size=16):
    rng = _rng(name)
    a = np.zeros((size, size, 4), np.uint8)
    a[..., 3] = 255
    accent = accent or _shade(base, -55)

    for y in range(size):
        for x in range(size):
            a[y, x, :3] = _shade(base, rng.randint(-16, 17))

    if kind == 'grass_top':
        for _ in range(size * 4):
            x, y = rng.randint(0, size), rng.randint(0, size)
            a[y, x, :3] = _shade(base, rng.randint(-14, 48))
    elif kind == 'cobble':
        for y in range(size):
            for x in range(size):
                cell = ((x // 4) + (y // 4)) % 2
                a[y, x, :3] = _shade(base, rng.randint(-10, 10) + (8 if cell else -8))
                if x % 4 == 0 or y % 4 == 0:
                    a[y, x, :3] = accent
    elif kind == 'bricks':
        for y in range(size):
            row = y // 4
            off = 2 if row % 2 else 0
            for x in range(size):
                if y % 4 == 0 or (x + off) % 8 == 0:
                    a[y, x, :3] = accent
                else:
                    a[y, x, :3] = _shade(base, rng.randint(-12, 12))
    elif kind == 'planks':
        for y in range(size):
            for x in range(size):
                a[y, x, :3] = _shade(base, rng.randint(-10, 10))
                if y % 4 == 0:
                    a[y, x, :3] = accent
    elif kind == 'bands':
        for y in range(size):
            band = _shade(base, 14 if (y // 3) % 2 else -8)
            for x in range(size):
                a[y, x, :3] = _shade(band, rng.randint(-6, 6))
            if y % 3 == 0:
                a[y, :, :3] = accent
    elif kind == 'vstripe':
        for x in range(size):
            stripe = _shade(base, 12 if (x // 2) % 2 else -12)
            for y in range(size):
                a[y, x, :3] = _shade(stripe, rng.randint(-8, 8))
    elif kind == 'leaves':
        for y in range(size):
            for x in range(size):
                a[y, x, :3] = _shade(base, rng.randint(-25, 30))
                if rng.random() < 0.14:
                    a[y, x, :3] = _shade(base, -45)
    elif kind == 'water':
        for y in range(size):
            for x in range(size):
                w = math.sin((x + y) * 0.9) * 12
                a[y, x, :3] = _shade(base, int(w) + rng.randint(-6, 6))
        a[..., 3] = 205
    elif kind == 'grid':
        for y in range(size):
            for x in range(size):
                a[y, x, :3] = _shade(base, rng.randint(-10, 10))
        a[::5, :, :3] = accent
        a[:, ::5, :3] = accent
    elif kind == 'camo':
        for _ in range(18):
            cx, cy = rng.randint(0, size), rng.randint(0, size)
            r = rng.randint(1, 4)
            sh = _shade(base, rng.randint(-30, 30))
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if 0 <= cy + dy < size and 0 <= cx + dx < size and dx * dx + dy * dy <= r * r:
                        a[cy + dy, cx + dx, :3] = sh
    elif kind == 'plate':
        for y in range(size):
            for x in range(size):
                a[y, x, :3] = _shade(base, rng.randint(-8, 8))
        a[::8, :, :3] = accent
        a[:, ::8, :3] = accent
        for _ in range(6):
            a[rng.randint(0, size), rng.randint(0, size), :3] = _shade(base, 40)
    elif kind == 'glow':
        for y in range(size):
            for x in range(size):
                a[y, x, :3] = _shade(base, rng.randint(-20, 25))
        for _ in range(10):
            a[rng.randint(0, size), rng.randint(0, size), :3] = (255, 250, 180)
    return a


# name -> (base rgb, kind, accent)
BLOCK_TEX = {
    'grass':  ((86, 150, 66), 'grass_top', None),
    'dirt':   ((130, 96, 64), 'noise', None),
    'sand':   ((216, 202, 150), 'bands', None),
    'rock':   ((120, 120, 128), 'cobble', None),
    'crate':  ((176, 132, 80), 'planks', None),
    'metal':  ((150, 156, 168), 'plate', (90, 95, 105)),
    'wall':   ((150, 80, 68), 'bricks', None),
    'water':  ((52, 110, 200), 'water', None),
    'wood':   ((110, 80, 52), 'vstripe', None),
    'leaf':   ((58, 142, 52), 'leaves', None),
    'barrel': ((180, 70, 50), 'plate', (110, 40, 30)),
    'gun':    ((58, 62, 70), 'grid', (28, 30, 36)),
    'gunmetal': ((40, 42, 48), 'plate', (24, 26, 30)),
}

TEX = {}


def build_textures():
    for name, (base, kind, accent) in BLOCK_TEX.items():
        arr = make_pixels(name, base, kind, accent)
        t = Texture(Image.fromarray(arr, 'RGBA'))
        t.filtering = None
        TEX[name] = t


def skin_tex(name, base, kind='noise', accent=None):
    if name in TEX:
        return TEX[name]
    t = Texture(Image.fromarray(make_pixels(name, base, kind, accent), 'RGBA'))
    t.filtering = None
    TEX[name] = t
    return t


# ============================================================================
# ORIGINAL AUDIO  (numpy -> WAV -> Ursina Audio)
# ============================================================================
SR = 22050
NOTE = {
    'C2': 65.4, 'D2': 73.4, 'E2': 82.4, 'F2': 87.3, 'G2': 98.0, 'A2': 110.0, 'B2': 123.5,
    'C3': 130.8, 'D3': 146.8, 'E3': 164.8, 'F3': 174.6, 'G3': 196.0,
    'A3': 220.0, 'B3': 246.9, 'C4': 261.6, 'D4': 293.7, 'E4': 329.6,
    'F4': 349.2, 'G4': 392.0, 'A4': 440.0, 'B4': 493.9, 'C5': 523.3,
    'D5': 587.3, 'E5': 659.3, 'F5': 698.5, 'G5': 784.0, 'A5': 880.0,
    'R': 0.0,
}


def _osc(freq, n, wave_type='square'):
    if freq <= 0:
        return np.zeros(n)
    t = np.arange(n) / SR
    ph = 2 * math.pi * freq * t
    if wave_type == 'square':
        return np.sign(np.sin(ph))
    if wave_type == 'saw':
        return 2 * (t * freq - np.floor(0.5 + t * freq))
    if wave_type == 'noise':
        return np.random.RandomState(int(freq) + n).uniform(-1, 1, n)
    return np.sin(ph)


def _note(freq, dur, vol=0.25, wave_type='square'):
    n = max(1, int(SR * dur))
    s = _osc(freq, n, wave_type) * vol
    env = np.ones(n)
    a = max(1, n // 12)
    env[:a] = np.linspace(0, 1, a)
    env[-a:] = np.linspace(1, 0, a)
    return s * env


def _write_wav(path, samples):
    data = (np.clip(samples, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def build_song(path, lead, bass=None, tempo=1.0, lead_wave='square'):
    beat = 0.18 / tempo
    lead_buf = np.concatenate(
        [_note(NOTE[n], b * beat, 0.20, lead_wave) for n, b in lead])
    if bass:
        bass_buf = np.concatenate(
            [_note(NOTE[n] / 2 if NOTE[n] else 0, b * beat, 0.17, 'saw')
             for n, b in bass])
        if len(bass_buf) < len(lead_buf):
            bass_buf = np.tile(bass_buf, int(np.ceil(len(lead_buf) / len(bass_buf))))
        mix = lead_buf + bass_buf[:len(lead_buf)]
    else:
        mix = lead_buf
    _write_wav(path, mix)


def build_sfx(path, segs):
    _write_wav(path, np.concatenate([_note(f, d, v, w) for f, d, v, w in segs]))


def build_audio():
    # --- DROP / lobby: bouncy, hopeful ---
    build_song(os.path.join(ASSETS, 'm_drop.wav'),
               lead=[('C4', 2), ('E4', 1), ('G4', 1), ('C5', 2), ('B4', 2),
                     ('G4', 1), ('E4', 1), ('F4', 2), ('R', 1), ('G4', 1),
                     ('A4', 2), ('G4', 1), ('E4', 1), ('C4', 4)],
               bass=[('C3', 2), ('G3', 2), ('A3', 2), ('F3', 2)], tempo=1.0)
    # --- BATTLE: driving, energetic ---
    build_song(os.path.join(ASSETS, 'm_battle.wav'),
               lead=[('E4', 1), ('E4', 1), ('G4', 1), ('A4', 1), ('B4', 2),
                     ('A4', 1), ('G4', 1), ('E4', 2), ('D4', 1), ('E4', 1),
                     ('G4', 1), ('B4', 1), ('C5', 2), ('B4', 1), ('A4', 1),
                     ('G4', 2), ('E4', 2), ('A4', 1), ('B4', 1), ('A4', 1),
                     ('G4', 1), ('E4', 4)],
               bass=[('E3', 1), ('E3', 1), ('E3', 1), ('B2', 1),
                     ('C3', 1), ('C3', 1), ('G3', 1), ('B2', 1)], tempo=1.45)
    # --- FINAL CIRCLE: intense, high stakes ---
    build_song(os.path.join(ASSETS, 'm_final.wav'),
               lead=[('A4', 1), ('C5', 1), ('E5', 1), ('A5', 2), ('G5', 1),
                     ('E5', 1), ('A4', 1), ('B4', 1), ('C5', 2), ('R', 1),
                     ('E5', 1), ('D5', 1), ('C5', 1), ('B4', 1), ('A4', 3)],
               bass=[('A3', 1), ('A3', 1), ('F3', 1), ('G3', 1),
                     ('A3', 1), ('E3', 1), ('A3', 1), ('A3', 1)], tempo=1.7)
    # --- VICTORY jingle ---
    build_song(os.path.join(ASSETS, 'm_victory.wav'),
               lead=[('C4', 1), ('E4', 1), ('G4', 1), ('C5', 2), ('G4', 1),
                     ('C5', 1), ('E5', 3)],
               bass=[('C3', 1), ('C3', 1), ('G3', 1), ('C3', 1)], tempo=1.2)

    build_sfx(os.path.join(ASSETS, 's_shoot.wav'),
              [(700, 0.025, 0.32, 'noise'), (320, 0.05, 0.28, 'square'),
               (150, 0.04, 0.2, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_sgun.wav'),
              [(500, 0.04, 0.4, 'noise'), (180, 0.09, 0.34, 'saw'),
               (90, 0.08, 0.28, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_snipe.wav'),
              [(900, 0.03, 0.4, 'noise'), (600, 0.05, 0.34, 'square'),
               (200, 0.12, 0.28, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_reload.wav'),
              [(300, 0.05, 0.22, 'square'), (0, 0.06, 0, 'sine'),
               (420, 0.05, 0.22, 'square')])
    build_sfx(os.path.join(ASSETS, 's_hit.wav'),
              [(820, 0.03, 0.22, 'square'), (560, 0.03, 0.18, 'square')])
    build_sfx(os.path.join(ASSETS, 's_kill.wav'),
              [(660, 0.05, 0.26, 'sine'), (990, 0.06, 0.24, 'sine')])
    build_sfx(os.path.join(ASSETS, 's_hurt.wav'),
              [(180, 0.12, 0.32, 'square'), (90, 0.1, 0.26, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_boom.wav'),
              [(120, 0.05, 0.45, 'noise'), (70, 0.24, 0.4, 'saw'),
               (45, 0.2, 0.34, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_pickup.wav'),
              [(660, 0.05, 0.2, 'sine'), (990, 0.07, 0.2, 'sine')])
    build_sfx(os.path.join(ASSETS, 's_storm.wav'),
              [(70, 0.5, 0.3, 'noise'), (50, 0.5, 0.26, 'saw')])
    build_sfx(os.path.join(ASSETS, 's_click.wav'),
              [(220, 0.03, 0.18, 'square')])


# ============================================================================
# APP
# ============================================================================
app = Ursina(title='Storm Royale', borderless=False, fullscreen=False,
             development_mode=False)
window.color = C(150, 175, 200)
window.fps_counter.enabled = False
window.exit_button.visible = False

build_textures()
build_audio()

from ursina import Audio, application
from pathlib import Path
application.asset_folder = Path(HERE)

MUTED = [False]


class Jukebox:
    def __init__(self):
        self.cur = None
        self.tracks = {}
        for n in ['drop', 'battle', 'final', 'victory']:
            try:
                self.tracks[n] = Audio(f'assets/m_{n}', loop=True,
                                       autoplay=False, volume=0.42)
            except Exception:
                self.tracks[n] = None

    def play(self, name, vol=0.42):
        if name == self.cur:
            return
        prev = self.tracks.get(self.cur)
        if prev:
            prev.stop()
        self.cur = name
        a = self.tracks.get(name)
        if a:
            a.volume = 0 if MUTED[0] else vol
            try:
                a.play()
            except Exception:
                pass

    def set_mute(self, m):
        a = self.tracks.get(self.cur)
        if a:
            a.volume = 0 if m else 0.42


JUKE = Jukebox()
_sfx_cache = {}


def sfx(name, vol=0.6):
    if MUTED[0]:
        return
    try:
        a = _sfx_cache.get(name)
        if a is None:
            a = Audio(f'assets/s_{name}', autoplay=False)
            _sfx_cache[name] = a
        a.volume = vol
        a.play()
    except Exception:
        pass


# ============================================================================
# WORLD
# ============================================================================
ARENA = 170          # ground is ARENA x ARENA, centred on origin
HALF = ARENA / 2
cover = []           # cover entities (have colliders)
enemies = []
tracers = []
pickups = []
sparks = []

light = DirectionalLight(y=3, z=-2, rotation=(45, -30, 0))
light.color = C(255, 250, 235)
amb = AmbientLight(color=C(150, 150, 165))


def _box(parent, pos, scale, col, tex=None, dbl=False):
    e = Entity(parent=parent, model='cube', position=pos, scale=scale,
               color=col, texture=tex, double_sided=dbl)
    return e


def build_world():
    # ground
    Entity(model='cube', scale=(ARENA, 2, ARENA), position=(0, -1, 0),
           texture=TEX['grass'], texture_scale=(ARENA / 4, ARENA / 4),
           collider='box', color=C(255, 255, 255))
    # sandy patches (visual)
    for _ in range(10):
        x = random.uniform(-HALF + 6, HALF - 6)
        z = random.uniform(-HALF + 6, HALF - 6)
        s = random.uniform(6, 14)
        Entity(model='cube', scale=(s, 0.12, s), position=(x, 0.02, z),
               texture=TEX['sand'], texture_scale=(s / 3, s / 3),
               color=C(255, 255, 255))

    # boundary wall so you can't run off the edge
    for sx, sz, sw, sd in [(-HALF, 0, 1, ARENA), (HALF, 0, 1, ARENA),
                           (0, -HALF, ARENA, 1), (0, HALF, ARENA, 1)]:
        w = Entity(model='cube', scale=(sw, 7, sd), position=(sx, 3, sz),
                   texture=TEX['rock'], texture_scale=(max(sw, sd) / 3, 2),
                   collider='box', color=C(200, 200, 205))
        cover.append(w)

    # scattered cover: crates, barrels, rocks, walls, trees
    placed = 0
    attempts = 0
    while placed < 130 and attempts < 1200:
        attempts += 1
        x = random.uniform(-HALF + 8, HALF - 8)
        z = random.uniform(-HALF + 8, HALF - 8)
        if math.hypot(x, z) < 9:
            continue
        kind = random.random()
        if kind < 0.34:                       # crate stack
            n = random.randint(1, 3)
            for i in range(n):
                e = Entity(model='cube', scale=2, position=(x, 1 + i * 2, z),
                           texture=TEX['crate'], collider='box',
                           color=C(255, 255, 255))
                cover.append(e)
        elif kind < 0.5:                      # barrel
            e = Entity(model='cube', scale=(1.4, 2.2, 1.4),
                       position=(x, 1.1, z), texture=TEX['barrel'],
                       collider='box', color=C(255, 255, 255))
            cover.append(e)
        elif kind < 0.68:                     # rock
            s = random.uniform(2.2, 4.2)
            e = Entity(model='cube', scale=(s, s * 0.8, s),
                       position=(x, s * 0.4, z), texture=TEX['rock'],
                       collider='box', color=C(255, 255, 255),
                       rotation=(0, random.uniform(0, 90), 0))
            cover.append(e)
        elif kind < 0.84:                     # short wall (cover)
            ln = random.uniform(4, 8)
            rot = random.choice([0, 90])
            sc = (ln, 3, 1) if rot == 0 else (1, 3, ln)
            e = Entity(model='cube', scale=sc, position=(x, 1.5, z),
                       texture=TEX['wall'], collider='box',
                       texture_scale=(ln / 2, 1.5), color=C(255, 255, 255))
            cover.append(e)
        else:                                 # tree
            trunk = Entity(model='cube', scale=(0.9, 5, 0.9),
                           position=(x, 2.5, z), texture=TEX['wood'],
                           collider='box', color=C(255, 255, 255))
            cover.append(trunk)
            Entity(model='cube', scale=(4.5, 3.5, 4.5), position=(x, 6, z),
                   texture=TEX['leaf'], color=C(255, 255, 255))
        placed += 1

    # a couple of landmark towers
    for (tx, tz) in [(-HALF * 0.55, HALF * 0.55), (HALF * 0.55, -HALF * 0.55)]:
        for i in range(4):
            e = Entity(model='cube', scale=(6, 3, 6),
                       position=(tx, 1.5 + i * 3, tz),
                       texture=TEX['metal'], collider='box',
                       color=C(255, 255, 255))
            cover.append(e)


# ============================================================================
# WEAPONS
# ============================================================================
# name: dmg, rate(s), mag, range, pellets, spread(deg), auto, sfx
WEAPONS = {
    'Rifle':   dict(dmg=15, rate=0.10, mag=30, rng=95, pellets=1,
                    spread=2.6, auto=True, snd='shoot'),
    'Shotgun': dict(dmg=12, rate=0.72, mag=6, rng=34, pellets=7,
                    spread=10.0, auto=False, snd='sgun'),
    'Sniper':  dict(dmg=95, rate=1.05, mag=5, rng=210, pellets=1,
                    spread=0.3, auto=False, snd='snipe'),
}
WEAPON_ORDER = ['Rifle', 'Shotgun', 'Sniper']


# ============================================================================
# ENEMIES  (7 difficulty tiers)
# ============================================================================
# label, hp, speed, dmg, fire(s), range, accuracy, size, color, is_boss
TIERS = {
    'grunt':      dict(label='Grunt',      hp=30,  spd=3.2, dmg=5,  fire=1.2,
                       rng=26, acc=0.40, size=1.0, col=(150, 160, 120), boss=False),
    'soldier':    dict(label='Soldier',    hp=55,  spd=3.6, dmg=7,  fire=0.95,
                       rng=34, acc=0.50, size=1.05, col=(96, 120, 90), boss=False),
    'scout':      dict(label='Scout',      hp=34,  spd=5.4, dmg=6,  fire=0.7,
                       rng=24, acc=0.46, size=0.95, col=(70, 150, 180), boss=False),
    'heavy':      dict(label='Heavy',      hp=140, spd=2.4, dmg=12, fire=1.35,
                       rng=30, acc=0.50, size=1.35, col=(120, 80, 70), boss=False),
    'sniper':     dict(label='Sniper',     hp=46,  spd=2.6, dmg=24, fire=2.2,
                       rng=85, acc=0.78, size=1.05, col=(60, 64, 80), boss=False),
    'elite':      dict(label='Elite',      hp=240, spd=4.4, dmg=15, fire=0.6,
                       rng=42, acc=0.66, size=1.2, col=(170, 70, 170), boss=False),
    'juggernaut': dict(label='JUGGERNAUT', hp=900, spd=2.2, dmg=26, fire=0.8,
                       rng=46, acc=0.64, size=2.1, col=(200, 60, 50), boss=True),
}


def enemy_model(parent, tier):
    cfg = TIERS[tier]
    col = C(*cfg['col'])
    dark = C(*_shade(cfg['col'], -35))
    head_col = C(*_shade(cfg['col'], 35))
    s = cfg['size']
    # solid-coloured cubes -- merged with combine() into ONE mesh per enemy
    _box(parent, (0, 1.1 * s, 0), (0.9 * s, 1.1 * s, 0.5 * s), col)
    _box(parent, (0, 1.95 * s, 0), (0.55 * s, 0.55 * s, 0.55 * s), head_col)
    _box(parent, (-0.62 * s, 1.1 * s, 0.05 * s), (0.28 * s, 1.0 * s, 0.28 * s), col)
    _box(parent, (0.62 * s, 1.1 * s, 0.18 * s), (0.28 * s, 1.0 * s, 0.28 * s), col)
    _box(parent, (-0.26 * s, 0.45 * s, 0), (0.34 * s, 0.95 * s, 0.34 * s), dark)
    _box(parent, (0.26 * s, 0.45 * s, 0), (0.34 * s, 0.95 * s, 0.34 * s), dark)
    _box(parent, (0.62 * s, 1.15 * s, 0.55 * s), (0.16 * s, 0.16 * s, 0.9 * s),
         C(40, 42, 48))
    if cfg['boss']:
        _box(parent, (-0.7 * s, 1.65 * s, 0), (0.5 * s, 0.4 * s, 0.7 * s), dark)
        _box(parent, (0.7 * s, 1.65 * s, 0), (0.5 * s, 0.4 * s, 0.7 * s), dark)
        _box(parent, (0, 1.98 * s, 0.28 * s), (0.5 * s, 0.12 * s, 0.06 * s),
             C(255, 230, 90))


class Enemy:
    def __init__(self, tier, x, z):
        cfg = TIERS[tier]
        self.tier = tier
        self.cfg = cfg
        self.hp = cfg['hp']
        self.maxhp = cfg['hp']
        self.size = cfg['size']
        self.root = Entity(position=(x, 0, z))
        enemy_model(self.root, tier)
        self.root.combine(auto_destroy=True)
        self.root.color = color.white
        self.base_col = color.white
        self.fire_cd = random.uniform(0.3, cfg['fire'])
        self.melee_cd = 0.0
        self.flash = 0.0
        self.walk = random.uniform(0, 6.28)
        self.strafe = random.choice((-1, 1))
        self.strafe_t = random.uniform(1, 3)
        self.is_boss = cfg['boss']
        self.can_shoot = False
        enemies.append(self)

    @property
    def x(self):
        return self.root.x

    @property
    def z(self):
        return self.root.z

    def center(self):
        return Vec3(self.root.x, self.size * 1.3, self.root.z)

    def hurt(self, dmg):
        if self.hp <= 0:
            return
        self.hp -= dmg
        self.flash = 0.12
        self.root.color = color.red
        sfx('hit', 0.4)
        if self.hp <= 0:
            self.die()

    def die(self):
        if self in enemies:
            enemies.remove(self)
        GAME.kills += 1
        sfx('kill', 0.5)
        burst(self.center(), C(*self.cfg['col']), n=8 if not self.is_boss else 22)
        if self.is_boss or random.random() < 0.12:
            spawn_pickup(self.root.x, self.root.z,
                         'health' if random.random() < 0.5 else 'ammo')
        destroy(self.root)

    def die_storm(self):
        if self in enemies:
            enemies.remove(self)
        destroy(self.root)

    def step(self, dt):
        p = GAME.player
        px, pz = p.x, p.z
        dx, dz = px - self.root.x, pz - self.root.z
        dist = math.hypot(dx, dz) or 0.001
        cfg = self.cfg

        # damage flash recover
        if self.flash > 0:
            self.flash -= dt
            if self.flash <= 0:
                self.root.color = self.base_col

        # storm: take damage outside, and run toward the safe centre
        cx, cz, R = GAME.storm_x, GAME.storm_z, GAME.storm_r
        dcx, dcz = cx - self.root.x, cz - self.root.z
        dcenter = math.hypot(dcx, dcz)
        in_storm = dcenter > R
        if in_storm:
            self.hp -= GAME.storm_dps * 1.3 * dt
            if self.hp <= 0:
                self.die_storm()
                return

        # ---- movement ----
        moving = False
        if in_storm and dcenter > 1:
            # flee into the zone
            ux, uz = dcx / dcenter, dcz / dcenter
            sp = cfg['spd'] * 1.15
            self.root.x += ux * sp * dt
            self.root.z += uz * sp * dt
            moving = True
        else:
            ux, uz = dx / dist, dz / dist
            standoff = 1.6 if cfg['rng'] < 28 else cfg['rng'] * 0.45
            if dist > standoff + 1:
                sp = cfg['spd']
                self.root.x += ux * sp * dt
                self.root.z += uz * sp * dt
                moving = True
            elif dist < standoff - 1.5:
                self.root.x -= ux * cfg['spd'] * 0.6 * dt
                self.root.z -= uz * cfg['spd'] * 0.6 * dt
                moving = True
            else:
                # strafe around the player
                self.strafe_t -= dt
                if self.strafe_t <= 0:
                    self.strafe *= -1
                    self.strafe_t = random.uniform(1, 2.5)
                self.root.x += -uz * self.strafe * cfg['spd'] * 0.5 * dt
                self.root.z += ux * self.strafe * cfg['spd'] * 0.5 * dt
                moving = True

        # keep inside the arena
        self.root.x = clamp(self.root.x, -HALF + 2, HALF - 2)
        self.root.z = clamp(self.root.z, -HALF + 2, HALF - 2)

        # face the player
        self.root.rotation_y = math.degrees(math.atan2(dx, dz))

        # walk bob (single combined mesh -> cheap transform)
        if moving:
            self.walk += dt * 9
            self.root.y = abs(math.sin(self.walk)) * 0.06
        elif self.root.y > 0.001:
            self.root.y *= 0.8

        # ---- melee ----
        self.melee_cd -= dt
        if self.can_shoot and dist < 2.1 and self.melee_cd <= 0:
            GAME.hurt_player(max(4, cfg['dmg'] // 2))
            self.melee_cd = 0.9

        # ---- shooting ----
        self.fire_cd -= dt
        if (self.can_shoot and self.fire_cd <= 0 and dist < cfg['rng']
                and not in_storm):
            self.fire_cd = cfg['fire'] * random.uniform(0.8, 1.25)
            origin = self.center()
            target = Vec3(px, 1.4, pz)
            blocked = self._blocked(origin, target)
            tracer(origin, target if not blocked else
                   origin + (target - origin) * 0.6, C(255, 120, 60))
            if not blocked:
                acc = cfg['acc']
                if dist > cfg['rng'] * 0.7:
                    acc *= 0.7
                if random.random() < acc:
                    GAME.hurt_player(cfg['dmg'])

    def _blocked(self, origin, target):
        d = (target - origin)
        ln = d.length()
        if ln < 0.1:
            return False
        try:
            hit = raycast(origin, d.normalized(), distance=ln - 0.6,
                          ignore=(GAME.player, GAME.gun), traverse_target=scene)
            return hit.hit
        except Exception:
            return False


# ============================================================================
# EFFECTS
# ============================================================================
def tracer(a, b, col=C(255, 240, 160)):
    mid = (a + b) * 0.5
    length = (b - a).length()
    if length < 0.05:
        return
    e = Entity(model='cube', position=mid, color=col,
               scale=(0.06, 0.06, length))
    try:
        e.look_at(b)
    except Exception:
        pass
    tracers.append([e, 0.06])
    if len(tracers) > 70:
        old = tracers.pop(0)
        destroy(old[0])


def burst(pos, col, n=8):
    for _ in range(n):
        e = Entity(model='cube', position=pos, color=col,
                   scale=random.uniform(0.12, 0.3))
        vel = Vec3(random.uniform(-1, 1), random.uniform(0.4, 1.6),
                   random.uniform(-1, 1)) * random.uniform(3, 7)
        sparks.append([e, vel, 0.5])
    if len(sparks) > 160:
        old = sparks.pop(0)
        destroy(old[0])


# ============================================================================
# PICKUPS
# ============================================================================
def spawn_pickup(x, z, kind):
    col = C(220, 60, 60) if kind == 'health' else C(70, 200, 90)
    e = Entity(model='cube', position=(x, 1.0, z), scale=0.8, color=col,
               texture=TEX['metal'])
    Entity(parent=e, model='cube', scale=(1.3, 0.34, 0.1),
           color=C(255, 255, 255), z=-0.5)
    Entity(parent=e, model='cube', scale=(0.34, 1.3, 0.1),
           color=C(255, 255, 255), z=-0.5)
    pickups.append([e, kind])


# ============================================================================
# GAME
# ============================================================================
START_ENEMIES = 150
SHOOTER_CAP = 12        # only the nearest few enemies engage at once


class Game:
    def __init__(self):
        self.player = None
        self.gun = None
        self.started = False

    # ---------- setup ----------
    def start(self):
        build_world()
        self.player = FirstPersonController(
            y=3, x=0, z=-HALF * 0.7, speed=8, jump_height=1.6,
            origin_y=-0.5)
        self.player.cursor.visible = False
        self.player.collider = 'box'
        camera.clip_plane_near = 0.05
        self._build_gun()
        self._build_ui()
        self.reset_state()
        self.spawn_army(START_ENEMIES)
        self.started = True
        JUKE.play('drop')

    def reset_state(self):
        self.hp = 100
        self.maxhp = 100
        self.kills = 0
        self.weapon = 'Rifle'
        self.mag = {k: WEAPONS[k]['mag'] for k in WEAPONS}
        self.fire_cd = 0.0
        self.reloading = 0.0
        self.recoil = 0.0
        self.hurt_t = 0.0
        self.hitmark_t = 0.0
        self.over = False
        self.win = False
        self.muzzle_t = 0.0
        self.spawn_protect = 3.0
        self.regen_delay = 0.0
        self.next_dps = 1.0
        self.shrink_speed = 0.0
        # storm
        self.storm_x = 0.0
        self.storm_z = 0.0
        self.storm_r = HALF * 0.92
        self.storm_target = self.storm_r
        self.storm_dps = 1.0
        self.storm_phase = 0
        self.storm_timer = 16.0
        self.storm_state = 'wait'   # wait | shrink
        self.music_mode = 'drop'
        if getattr(self, 'dome', None):
            self.dome.scale = self.storm_r * 2

    # ---------- gun viewmodel ----------
    def _build_gun(self):
        g = Entity(parent=camera, position=(0.34, -0.30, 0.55),
                   rotation=(0, -4, 0))
        _box(g, (0, 0, 0.0), (0.14, 0.14, 0.8), C(255, 255, 255), TEX['gunmetal'])
        _box(g, (0, -0.14, -0.18), (0.12, 0.26, 0.16), C(255, 255, 255), TEX['gun'])
        _box(g, (0, 0.06, 0.35), (0.1, 0.1, 0.35), C(255, 255, 255), TEX['gunmetal'])
        self.muzzle = Entity(parent=g, model='cube', position=(0, 0.06, 0.6),
                             scale=(0.22, 0.22, 0.22), color=C(255, 230, 120),
                             enabled=False)
        self.gun = g

    # ---------- HUD ----------
    def _build_ui(self):
        self.crosshair = Text('+', origin=(0, 0), scale=2, position=(0, 0),
                              color=C(255, 255, 255))
        self.hp_bg = Entity(parent=camera.ui, model='quad', color=C(20, 20, 24),
                            scale=(0.42, 0.045), position=(-0.55, -0.43),
                            origin=(-0.5, 0))
        self.hp_bar = Entity(parent=camera.ui, model='quad', color=C(70, 210, 90),
                             scale=(0.42, 0.045), position=(-0.55, -0.43),
                             origin=(-0.5, 0))
        self.hp_txt = Text('100', position=(-0.55, -0.40), scale=1.0,
                           color=C(255, 255, 255))
        self.ammo_txt = Text('', position=(0.62, -0.40), origin=(0.5, 0),
                             scale=1.6, color=C(255, 255, 255))
        self.weap_txt = Text('', position=(0.62, -0.45), origin=(0.5, 0),
                             scale=1.0, color=C(220, 220, 160))
        self.alive_txt = Text('', position=(0, 0.47), origin=(0, 0),
                              scale=1.4, color=C(255, 255, 255))
        self.kills_txt = Text('', position=(-0.86, 0.47), origin=(-0.5, 0),
                              scale=1.1, color=C(255, 220, 120))
        self.storm_txt = Text('', position=(0.86, 0.47), origin=(0.5, 0),
                              scale=1.0, color=C(200, 150, 255))
        self.warn_txt = Text('', origin=(0, 0), position=(0, 0.30), scale=1.6,
                             color=C(220, 130, 255))
        self.hitmark = Text('x', origin=(0, 0), position=(0, 0), scale=2.4,
                            color=C(255, 80, 80), enabled=False)
        self.center_txt = Text('', origin=(0, 0), position=(0, 0.08),
                               scale=3, color=C(255, 255, 255), enabled=False)
        self.sub_txt = Text('', origin=(0, 0), position=(0, -0.04), scale=1.2,
                            color=C(230, 230, 230), enabled=False)
        # boss bar
        self.boss_bg = Entity(parent=camera.ui, model='quad', color=C(20, 20, 24),
                              scale=(0.6, 0.03), position=(0, 0.40), enabled=False)
        self.boss_bar = Entity(parent=camera.ui, model='quad', color=C(220, 60, 50),
                               scale=(0.6, 0.03), position=(0, 0.40),
                               origin=(-0.5, 0), enabled=False)
        # screen overlays
        self.over_hurt = Entity(parent=camera.ui, model='quad',
                                color=C(200, 30, 30, 0), scale=(2, 2))
        self.over_storm = Entity(parent=camera.ui, model='quad',
                                 color=C(150, 60, 200, 0), scale=(2, 2))
        # storm dome
        self.dome = Entity(model='sphere', double_sided=True,
                           color=C(170, 90, 220, 46),
                           scale=HALF * 0.92 * 2, position=(0, 0, 0))

    # ---------- spawning ----------
    def spawn_army(self, n):
        # weighted difficulty mix
        bag = (['grunt'] * 34 + ['soldier'] * 24 + ['scout'] * 16 +
               ['heavy'] * 10 + ['sniper'] * 9 + ['elite'] * 5 +
               ['juggernaut'] * 2)
        for _ in range(n):
            tier = random.choice(bag)
            x = z = 0.0
            for _try in range(8):
                ang = random.uniform(0, 6.283)
                rad = random.uniform(12, HALF * 0.9)
                x = math.cos(ang) * rad
                z = math.sin(ang) * rad
                if abs(x - self.player.x) + abs(z - self.player.z) > 14:
                    break
            Enemy(tier, x, z)

    # ---------- combat ----------
    def switch_weapon(self, name):
        if name == self.weapon or self.reloading > 0:
            return
        self.weapon = name
        sfx('click', 0.4)

    def cycle_weapon(self, d):
        i = (WEAPON_ORDER.index(self.weapon) + d) % len(WEAPON_ORDER)
        self.switch_weapon(WEAPON_ORDER[i])

    def reload(self):
        w = WEAPONS[self.weapon]
        if self.reloading > 0 or self.mag[self.weapon] >= w['mag']:
            return
        self.reloading = 0.55 if self.weapon != 'Sniper' else 0.9
        sfx('reload', 0.6)

    def fire(self):
        if self.over or self.reloading > 0 or self.fire_cd > 0:
            return
        w = WEAPONS[self.weapon]
        if self.mag[self.weapon] <= 0:
            sfx('click', 0.5)
            self.reload()
            return
        self.mag[self.weapon] -= 1
        self.fire_cd = w['rate']
        self.recoil = min(8, self.recoil + 3)
        self.muzzle_t = 0.04
        self.muzzle.enabled = True
        sfx(w['snd'], 0.55)

        muzzle_pos = camera.world_position + camera.forward * 0.6
        fwd = camera.forward
        cone = math.cos(math.radians(w['spread'] + 2.2))
        rng = w['rng']
        # candidate enemies sorted by alignment to aim
        cands = []
        for e in enemies:
            to = e.center() - muzzle_pos
            d = to.length()
            if d > rng or d < 0.3:
                continue
            dot = (to.normalized()).dot(fwd)
            if dot > cone:
                cands.append((dot, d, e))
        cands.sort(key=lambda c: -c[0])
        hits = w['pellets']
        any_hit = False
        if cands:
            for dot, d, e in cands[:hits]:
                tp = e.center()
                if self._shot_blocked(muzzle_pos, tp):
                    tracer(muzzle_pos, muzzle_pos + (tp - muzzle_pos) * 0.7)
                    continue
                tracer(muzzle_pos, tp)
                e.hurt(w['dmg'])
                burst(tp, C(255, 180, 90), n=4)
                any_hit = True
            for _ in range(max(0, hits - len(cands))):
                tracer(muzzle_pos, muzzle_pos + fwd * rng * 0.8)
        else:
            tracer(muzzle_pos, muzzle_pos + fwd * rng * 0.8)
        if any_hit:
            self.hitmark_t = 0.12

    def _shot_blocked(self, a, b):
        d = b - a
        ln = d.length()
        if ln < 0.2:
            return False
        try:
            hit = raycast(a, d.normalized(), distance=ln - 0.5,
                          ignore=(self.player, self.gun), traverse_target=scene)
            return hit.hit
        except Exception:
            return False

    # ---------- player damage ----------
    def hurt_player(self, dmg):
        if self.over or self.spawn_protect > 0:
            return
        self.hp -= dmg
        self.hurt_t = 0.4
        self.regen_delay = 4.0
        sfx('hurt', 0.45)
        if self.hp <= 0:
            self.hp = 0
            self.lose()

    # ---------- storm ----------
    def update_storm(self, dt):
        phases = [
            (HALF * 0.55, 1.0, 14),
            (HALF * 0.36, 2.5, 12),
            (HALF * 0.22, 5.0, 11),
            (HALF * 0.12, 8.0, 10),
            (6.0, 12.0, 10),
            (3.0, 18.0, 999),
        ]
        self.storm_timer -= dt
        if self.storm_state == 'wait' and self.storm_timer <= 0:
            if self.storm_phase < len(phases):
                tr, dps, _ = phases[self.storm_phase]
                self.storm_target = tr
                self.next_dps = dps
                self.storm_state = 'shrink'
                self.shrink_speed = (self.storm_r - tr) / 9.0
                sfx('storm', 0.5)
        elif self.storm_state == 'shrink':
            self.storm_r = max(self.storm_target,
                               self.storm_r - self.shrink_speed * dt)
            if self.storm_r <= self.storm_target + 0.05:
                self.storm_dps = self.next_dps
                self.storm_phase += 1
                self.storm_state = 'wait'
                if self.storm_phase < len(phases):
                    self.storm_timer = phases[self.storm_phase - 1][2]
        self.dome.scale = self.storm_r * 2

    # ---------- end states ----------
    def lose(self):
        self.over = True
        self.win = False
        placement = len(enemies) + 1
        self.center_txt.text = 'ELIMINATED'
        self.center_txt.color = C(255, 70, 70)
        self.sub_txt.text = (f'You placed #{placement}   Kills: {self.kills}'
                             f'\nPress ENTER to play again')
        self.center_txt.enabled = True
        self.sub_txt.enabled = True
        self.player.enabled = False
        mouse.locked = False
        mouse.visible = True
        JUKE.play('drop', vol=0.3)

    def victory(self):
        self.over = True
        self.win = True
        self.center_txt.text = '#1 VICTORY ROYALE!'
        self.center_txt.color = C(255, 220, 90)
        self.sub_txt.text = (f'You were the last one standing!   Kills: {self.kills}'
                             f'\nPress ENTER to play again')
        self.center_txt.enabled = True
        self.sub_txt.enabled = True
        sfx('kill', 0.7)
        JUKE.play('victory', vol=0.5)
        self.player.enabled = False
        mouse.locked = False
        mouse.visible = True

    def restart(self):
        for e in list(enemies):
            destroy(e.root)
        enemies.clear()
        for t in tracers:
            destroy(t[0])
        tracers.clear()
        for s in sparks:
            destroy(s[0])
        sparks.clear()
        for p in pickups:
            destroy(p[0])
        pickups.clear()
        self.center_txt.enabled = False
        self.sub_txt.enabled = False
        self.boss_bg.enabled = False
        self.boss_bar.enabled = False
        self.player.enabled = True
        self.player.position = Vec3(0, 3, -HALF * 0.7)
        mouse.locked = True
        mouse.visible = False
        self.reset_state()
        self.spawn_army(START_ENEMIES)
        JUKE.play('drop')

    # ---------- main loop ----------
    def update(self, dt):
        if not self.started or self.over:
            return
        dt = min(dt, 0.05)

        # sprint
        self.player.speed = 13 if held_keys['shift'] else 8

        # spawn protection + slow health regen
        if self.spawn_protect > 0:
            self.spawn_protect -= dt
        if self.regen_delay > 0:
            self.regen_delay -= dt
        elif self.hp < self.maxhp:
            self.hp = min(self.maxhp, self.hp + 5 * dt)

        # firing
        self.fire_cd = max(0, self.fire_cd - dt)
        w = WEAPONS[self.weapon]
        if self.reloading > 0:
            self.reloading -= dt
            if self.reloading <= 0:
                self.mag[self.weapon] = w['mag']
        elif held_keys['left mouse'] and w['auto']:
            self.fire()

        # gun recoil / muzzle
        self.recoil = lerp(self.recoil, 0, dt * 12)
        self.gun.rotation_x = -self.recoil
        self.gun.y = -0.30 - self.recoil * 0.004
        if self.muzzle_t > 0:
            self.muzzle_t -= dt
            if self.muzzle_t <= 0:
                self.muzzle.enabled = False

        # storm
        self.update_storm(dt)
        dcx = self.storm_x - self.player.x
        dcz = self.storm_z - self.player.z
        in_storm = math.hypot(dcx, dcz) > self.storm_r
        if in_storm:
            self.hp -= self.storm_dps * dt
            if self.hp <= 0:
                self.hp = 0
                self.lose()
                return

        # enemies -- only the nearest few actively engage (keeps it survivable
        # and cheap even with a huge army on screen)
        px, pz = self.player.x, self.player.z
        dists = sorted(((math.hypot(e.x - px, e.z - pz), e) for e in enemies),
                       key=lambda t: t[0])
        for i, (d, e) in enumerate(dists):
            e.can_shoot = i < SHOOTER_CAP
        boss = None
        for e in list(enemies):
            e.step(dt)
            if e.is_boss and e.hp > 0:
                boss = e

        # tracers fade
        for t in list(tracers):
            t[1] -= dt
            if t[1] <= 0:
                destroy(t[0])
                tracers.remove(t)
            else:
                t[0].scale_x = max(0.01, t[0].scale_x * 0.6)

        # sparks
        for s in list(sparks):
            s[1].y -= 14 * dt
            s[0].position += s[1] * dt
            s[2] -= dt
            if s[2] <= 0:
                destroy(s[0])
                sparks.remove(s)

        # pickups
        for p in list(pickups):
            p[0].rotation_y += 90 * dt
            if abs(p[0].x - self.player.x) + abs(p[0].z - self.player.z) < 2.2:
                if p[1] == 'health':
                    self.hp = min(self.maxhp, self.hp + 40)
                else:
                    for k in self.mag:
                        self.mag[k] = WEAPONS[k]['mag']
                sfx('pickup', 0.6)
                destroy(p[0])
                pickups.remove(p)

        # win check
        if not enemies:
            self.victory()
            return

        # music
        nearest = dists[0][0] if dists else 999
        if len(enemies) <= 12 or self.storm_phase >= 4:
            mode = 'final'
        elif nearest < 45 or self.hurt_t > 0:
            mode = 'battle'
        else:
            mode = 'drop'
        if mode != self.music_mode:
            self.music_mode = mode
            JUKE.play(mode)

        # overlays
        if self.hurt_t > 0:
            self.hurt_t -= dt
        self.over_hurt.color = C(200, 30, 30, int(150 * max(0, self.hurt_t / 0.4)))
        self.over_storm.color = C(150, 60, 200, 70 if in_storm else 0)

        # hud
        self.refresh_hud(in_storm, boss)

    def refresh_hud(self, in_storm, boss):
        frac = clamp(self.hp / self.maxhp, 0, 1)
        self.hp_bar.scale_x = 0.42 * frac
        self.hp_bar.color = (C(70, 210, 90) if frac > 0.5 else
                             C(230, 200, 60) if frac > 0.25 else C(220, 60, 60))
        self.hp_txt.text = str(int(self.hp))
        self.ammo_txt.text = f"{self.mag[self.weapon]} / {WEAPONS[self.weapon]['mag']}"
        self.weap_txt.text = (self.weapon + '  (reloading...)'
                              if self.reloading > 0 else self.weapon)
        self.alive_txt.text = f'ALIVE: {len(enemies) + 1}'
        self.kills_txt.text = f'Kills: {self.kills}'
        ph = min(self.storm_phase + 1, 6)
        if self.storm_state == 'shrink':
            self.storm_txt.text = f'STORM CLOSING!  (zone {ph})'
        else:
            self.storm_txt.text = f'Zone {ph}   next: {int(max(0, self.storm_timer))}s'
        self.warn_txt.text = '!! GET TO THE SAFE ZONE !!' if in_storm else ''
        self.hitmark_t = max(0, self.hitmark_t - utime.dt)
        self.hitmark.enabled = self.hitmark_t > 0
        if boss:
            self.boss_bg.enabled = True
            self.boss_bar.enabled = True
            self.boss_bar.scale_x = 0.6 * clamp(boss.hp / boss.maxhp, 0, 1)
            self.boss_bar.x = -0.3
        else:
            self.boss_bg.enabled = False
            self.boss_bar.enabled = False

    # ---------- input ----------
    def input(self, key):
        if self.over:
            if key in ('enter', 'r'):
                self.restart()
            return
        if key == 'left mouse down':
            self.fire()
        elif key == 'r':
            self.reload()
        elif key in ('1', '2', '3'):
            self.switch_weapon(WEAPON_ORDER[int(key) - 1])
        elif key == 'scroll up':
            self.cycle_weapon(1)
        elif key == 'scroll down':
            self.cycle_weapon(-1)
        elif key == 'm':
            MUTED[0] = not MUTED[0]
            JUKE.set_mute(MUTED[0])


GAME = Game()


def update():
    GAME.update(utime.dt)


def input(key):
    GAME.input(key)


if __name__ == '__main__':
    GAME.start()
    app.run()
