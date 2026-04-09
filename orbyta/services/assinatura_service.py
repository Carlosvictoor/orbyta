from datetime import datetime, timedelta
from core.helpers import parse_data_iso


def dono_tem_acesso(u):
    status = (u.get("assinatura_status") or "").lower()

    if status == "ativa":
        return True

    if status == "trial":
        trial_ate = parse_data_iso(u.get("trial_ate", ""))
        if trial_ate and datetime.now() <= (trial_ate + timedelta(hours=23, minutes=59)):
            return True

    return False