import importlib.util
import os
import sys
from pathlib import Path

from waitress import serve

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "orbyta"
APP_FILE = APP_DIR / "app.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

spec = importlib.util.spec_from_file_location("orbyta_app", APP_FILE)
if spec is None or spec.loader is None:
    raise RuntimeError("Não foi possível carregar o app Flask.")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    threads = int(os.getenv("WAITRESS_THREADS", "4"))

    print(f"Orbyta em produção: http://{host}:{port} | threads={threads}")
    serve(app, host=host, port=port, threads=threads)
