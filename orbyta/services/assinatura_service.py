from datetime import datetime, timedelta

from core.constants import obter_plano_config
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


def plano_do_dono(u):
    return obter_plano_config((u or {}).get("plano_slug") or "pro")


def limite_funcionarios_do_plano(u):
    limite = (u or {}).get("limite_funcionarios")
    if isinstance(limite, str):
        limite = limite.strip()
        if limite.isdigit():
            return int(limite)
        if not limite:
            return None
    if isinstance(limite, (int, float)):
        return int(limite)
    return plano_do_dono(u).get("limite_funcionarios")


def pode_adicionar_mais_funcionarios(u, quantidade_atual):
    limite = limite_funcionarios_do_plano(u)
    return limite is None or int(quantidade_atual or 0) < int(limite)