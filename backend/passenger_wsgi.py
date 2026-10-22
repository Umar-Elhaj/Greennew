# ============================================================
# GREEN App — entry point for Phusion Passenger (o2switch, cPanel
# "Setup Python App"): startup file passenger_wsgi.py, entry point
# `application`, application root = this backend/ directory.
#
# Passenger speaks WSGI; FastAPI is ASGI: a2wsgi bridges the two.
# a2wsgi does not run the ASGI lifespan, so the model warm-up thread does
# not start; models load lazily on first use, guarded by a lock
# (inference.load). WARMUP=1 loads them when the process starts instead
# (≈180 MB per Passenger process with ONNX — mind the LVE memory limit).
# ============================================================

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from a2wsgi import ASGIMiddleware  # noqa: E402

from main import _warmup_models, app  # noqa: E402

if os.getenv("WARMUP", "").strip() == "1":
    _warmup_models()

application = ASGIMiddleware(app)
