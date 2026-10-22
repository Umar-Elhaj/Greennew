#!/usr/bin/env python3
"""
GREEN — parity between the PyTorch model (.pth, development) and the ONNX
model (.onnx, production), end to end (each with its own preprocessing).

Pass criteria (lot 7.4): on every image, same top-1 class and
max |p_torch - p_onnx| < 1e-3. Also reports time per image and peak memory
of each engine, measured in separate processes.

Usage (from the repository root, needs torch + timm + onnxruntime):
  .venv/bin/python scripts/onnx_parity.py                  # 24 generated images
  .venv/bin/python scripts/onnx_parity.py --images DIR     # + real photos from DIR
Exit code 0 = parity holds.
"""

import argparse
import io
import json
import os
import subprocess
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

ROOT = os.path.abspath(os.path.join(BACKEND, ".."))
PTH = os.path.join(ROOT, "Models", "best_efficientnet.pth")
ONNX = os.path.join(ROOT, "Models", "best_efficientnet.onnx")
TOL = 1e-3


def generated_images(n: int = 24) -> list:
    """Deterministic, varied images: sizes and aspect ratios exercise every resize/crop path."""
    rng = np.random.default_rng(2026)
    sizes = [(224, 224), (640, 480), (480, 640), (1024, 768), (300, 900), (900, 300), (180, 120), (1600, 1200)]
    out = []
    for i in range(n):
        w, h = sizes[i % len(sizes)]
        base = rng.integers(0, 255, size=(h // 8 + 1, w // 8 + 1, 3), dtype=np.uint8)
        img = Image.fromarray(base).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
        d = ImageDraw.Draw(img)
        for _ in range(int(rng.integers(3, 12))):
            x0, y0 = int(rng.integers(0, w)), int(rng.integers(0, h))
            r = int(rng.integers(5, max(6, min(w, h) // 3)))
            colour = tuple(int(c) for c in rng.choice([[40, 140, 50], [120, 90, 40], [200, 200, 60], [90, 60, 30]]))
            d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=colour)
        out.append((f"generated-{i:02d}-{w}x{h}", img.convert("RGB")))
    return out


def folder_images(path: str) -> list:
    out = []
    for name in sorted(os.listdir(path)):
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            with open(os.path.join(path, name), "rb") as f:
                out.append((name, Image.open(io.BytesIO(f.read())).convert("RGB")))
    return out


def bench(backend: str, n_images: int) -> dict:
    """Run in a child process: load one engine, time it, report peak RSS (MB)."""
    env = dict(os.environ, INFERENCE_BACKEND=backend, MODEL_PATH=PTH if backend == "torch" else ONNX)
    code = f"""
import os, sys, time, json, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, {BACKEND!r})
sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r})
from onnx_parity import generated_images
import inference
imgs = [im for _, im in generated_images({n_images})]
t0 = time.perf_counter(); inference.load(); load_s = time.perf_counter() - t0
inference.forward_probs(imgs[0])
times = []
for im in imgs:
    t = time.perf_counter(); inference.forward_probs(im); times.append(time.perf_counter() - t)
times.sort()
# VmHWM: peak RSS of THIS process image (ru_maxrss would include the parent's peak)
hwm = next(int(l.split()[1]) for l in open("/proc/self/status") if l.startswith("VmHWM"))
print(json.dumps({{"load_s": load_s, "median_ms": 1000 * times[len(times) // 2], "max_ms": 1000 * times[-1],
                  "peak_rss_mb": hwm / 1024}}))
"""
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,  # noqa: S603 (fixed code)
                       timeout=900)
    if r.returncode != 0:
        return {"error": r.stderr.strip().splitlines()[-1] if r.stderr else "failed"}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", help="folder of real photos to add")
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--no-bench", action="store_true")
    args = ap.parse_args()

    import inference
    from config import MODEL_PATH  # noqa: F401 (validates the configuration)

    images = generated_images(args.count) + (folder_images(args.images) if args.images else [])
    inference.MODEL_PATH = ONNX
    onnx_probs = [inference.forward_probs(im, "onnx") for _, im in images]
    inference.MODEL_PATH = PTH
    torch_probs = [inference.forward_probs(im, "torch") for _, im in images]

    worst = 0.0
    failures = []
    for (name, _), pt, po in zip(images, torch_probs, onnx_probs, strict=True):
        diff = float(np.max(np.abs(pt - po)))
        worst = max(worst, diff)
        if int(np.argmax(pt)) != int(np.argmax(po)) or diff >= TOL:
            failures.append((name, inference.CLASS_NAMES[int(np.argmax(pt))], inference.CLASS_NAMES[int(np.argmax(po))], diff))
    top1 = sum(int(np.argmax(a)) == int(np.argmax(b)) for a, b in zip(torch_probs, onnx_probs, strict=True))
    print(f"images            : {len(images)}")
    print(f"top-1 identical   : {top1}/{len(images)}")
    print(f"max |Δp|          : {worst:.2e}  (tolerance {TOL:.0e})")
    for f in failures:
        print(f"  FAIL {f[0]}: torch={f[1]} onnx={f[2]} |Δp|={f[3]:.2e}")

    if not args.no_bench:
        for backend in ("onnx", "torch"):
            b = bench(backend, min(len(images), 20))
            if "error" in b:
                print(f"{backend:<6}: benchmark failed ({b['error']})")
            else:
                print(f"{backend:<6}: load {b['load_s']:.2f} s · median {b['median_ms']:.0f} ms/image · "
                      f"max {b['max_ms']:.0f} ms · peak RSS {b['peak_rss_mb']:.0f} MB")
    print("PARITY OK" if not failures else "PARITY FAILED")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
