"""scripts/media_report.py: dry run by default, --apply deletes orphan files only."""

import os
import subprocess
import sys

import media
from conftest import jpeg_bytes

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "media_report.py")


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], env=dict(os.environ),
                          capture_output=True, text=True, timeout=60)


def test_report_and_apply(client, user, fake_model):
    client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                headers=user["headers"])
    orphan_dir = os.path.join(media.MEDIA_DIR, "2020", "01")
    os.makedirs(orphan_dir, exist_ok=True)
    orphan = os.path.join(orphan_dir, "0" * 32 + ".jpg")
    open(orphan, "wb").write(b"x" * 10)

    r = _run()
    assert r.returncode == 0, r.stderr
    assert "orphan files   : 1" in r.stdout and "dry run" in r.stdout
    assert os.path.exists(orphan)

    r = _run("--apply")
    assert "deleted        : 1" in r.stdout
    assert not os.path.exists(orphan)
    assert "orphan files   : 0" in _run().stdout
