"""WSGI/gunicorn/gunicorn-compatible entrypoint: `gunicorn wsgi:app`.

Kept deliberately tiny so a Render free instance boots fast; the ML model is lazy-loaded
inside the registry, not here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
