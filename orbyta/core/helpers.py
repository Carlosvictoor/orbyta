import os
import uuid
from datetime import datetime

from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def parse_money_br(v):
    if v is None:
        return 0.0
    s = str(v).strip().lower().replace("r$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def clamp_pct(v, default=50.0):
    try:
        n = float(v)
    except Exception:
        return float(default)

    if n < 0:
        return 0.0
    if n > 100:
        return 100.0
    return round(n, 2)


def parse_data_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def gerar_slots_padrao_30():
    slots = []
    h, m = 6, 0

    while True:
        slots.append(f"{h:02d}:{m:02d}")
        m += 30

        if m >= 60:
            m = 0
            h += 1

        if h == 24:
            break

    return slots


def salvar_imagem_upload(upload, static_dir: str, prefix: str = "img"):
    if not upload or not getattr(upload, "filename", ""):
        return None, None

    filename = secure_filename(upload.filename or "")
    if not filename or "." not in filename:
        return None, "Escolha uma imagem válida (PNG, JPG, WEBP ou GIF)."

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None, "Formato não permitido. Use PNG, JPG, WEBP ou GIF."

    upload_dir = os.path.join(static_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    nome_final = f"{prefix}-{uuid.uuid4().hex[:12]}.{ext}"
    destino = os.path.join(upload_dir, nome_final)
    upload.save(destino)

    return f"/static/uploads/{nome_final}", None


SLOTS_PADRAO_30 = gerar_slots_padrao_30()