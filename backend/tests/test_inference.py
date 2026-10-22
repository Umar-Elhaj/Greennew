"""Real inference (marked slow): ONNX ⇄ PyTorch parity and the production ONNX path end to end."""

import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.mark.slow
def test_onnx_torch_parity_on_24_images():
    pytest.importorskip("torch")
    pytest.importorskip("onnxruntime")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "onnx_parity.py"), "--no-bench"],
                       capture_output=True, text=True, timeout=900)
    assert "top-1 identical   : 24/24" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 0 and "PARITY OK" in r.stdout


@pytest.mark.slow
def test_onnx_backend_predicts_without_torch_imported():
    """The production path must not import torch (it is not installed on o2switch)."""
    code = (
        "import sys, io; sys.path.insert(0, 'backend');"
        "from PIL import Image; import inference;"
        "buf = io.BytesIO(); Image.new('RGB', (320, 240), (40, 140, 50)).save(buf, 'JPEG');"
        "r = inference.predict(buf.getvalue());"
        "assert 'torch' not in sys.modules, 'torch was imported';"
        "assert r['class_raw'] in inference.CLASS_NAMES and len(r['top3']) == 3;"
        "print('OK', r['class_raw'], r['confidence'])"
    )
    env = dict(os.environ, INFERENCE_BACKEND="onnx", DEBUG="true", MODEL_PATH="")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
