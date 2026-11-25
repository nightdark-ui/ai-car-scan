# -*- coding: utf-8 -*-
"""合成 GTA 风格的扫描音效（纯 numpy，输出 16bit 单声道 wav）"""
import os
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "android", "app", "src", "main", "res", "raw")
os.makedirs(OUT, exist_ok=True)


def save(name, x):
    x = np.clip(x, -1.0, 1.0)
    data = (x * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, name), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(name, round(len(x) / SR, 3), "s")


def env(n, attack=0.004):
    a = max(1, int(SR * attack))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[a:] = np.exp(-np.linspace(0, 6.5, n - a))
    return e


def tone(freq, dur, harmonics=(1.0, 0.35, 0.12)):
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for i, h in enumerate(harmonics, start=1):
        x += h * np.sin(2 * np.pi * freq * i * t)
    return x * env(n)


# 锁定目标：短促高音“叮”
save("sfx_lock.wav", tone(1320, 0.085, (1.0, 0.45, 0.2)) * 0.85)

# 扫描中：1.2s 的加速 tick 循环
dur = 1.2
n = int(SR * dur)
x = np.zeros(n)
t0, interval, i = 0.0, 0.125, 0
while t0 < dur - 0.06:
    blip = tone(1700 + i * 45, 0.042, (1.0, 0.3, 0.1))
    s = int(t0 * SR)
    e = min(n, s + len(blip))
    x[s:e] += blip[: e - s]
    t0 += interval
    interval *= 0.925
    i += 1
save("sfx_scan.wav", x * 0.75)

# 完成：三连上行确认音
parts = [tone(f, d, (1.0, 0.35, 0.12)) for f, d in
         [(880, 0.10), (1174, 0.10), (1568, 0.17)]]
save("sfx_done.wav", np.concatenate(parts) * 0.85)

# 取消：下滑
n = int(SR * 0.16)
t = np.arange(n) / SR
f = np.linspace(720, 280, n)
ph = 2 * np.pi * np.cumsum(f) / SR
save("sfx_cancel.wav", np.sin(ph) * env(n) * 0.7)
