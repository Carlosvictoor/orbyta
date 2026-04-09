from datetime import datetime


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


SLOTS_PADRAO_30 = gerar_slots_padrao_30()