from __future__ import annotations

import os
import sys

# Ensure local package import wins over any installed package named 'dashboard'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dashboard.app_factory import create_app


app = create_app()

__all__ = ["app"]


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8050"))
    app.run(debug=False, host=host, port=port)
