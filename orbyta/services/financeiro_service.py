from core.constants import FINANCEIRO_FILE
from core.json_db import carregar_json, salvar_json
from core.helpers import clamp_pct


def calcular_valores_comissao(valor_bruto: float, comissao_pct: float):
    pct = clamp_pct(comissao_pct)
    repasse_profissional = round(float(valor_bruto) * (pct / 100.0), 2)
    parte_salao = round(float(valor_bruto) - repasse_profissional, 2)
    return pct, repasse_profissional, parte_salao


def financeiro_do_negocio(negocio_id: int):
    itens = carregar_json(FINANCEIRO_FILE)
    return [x for x in itens if int(x.get("negocio_id", 0)) == int(negocio_id)]


def salvar_lancamento_financeiro(item: dict):
    itens = carregar_json(FINANCEIRO_FILE)
    itens.append(item)
    salvar_json(FINANCEIRO_FILE, itens)


def remover_lancamento_financeiro(negocio_id: int, lanc_id: str):
    if str(lanc_id).startswith("auto-"):
        return False

    itens = carregar_json(FINANCEIRO_FILE)
    novo = []
    removido = False

    for x in itens:
        if int(x.get("negocio_id", 0)) == int(negocio_id) and str(x.get("id")) == str(lanc_id):
            removido = True
            continue
        novo.append(x)

    salvar_json(FINANCEIRO_FILE, novo)
    return removido


def zerar_financeiro_mes(negocio_id: int, mes: str):
    itens = carregar_json(FINANCEIRO_FILE)
    novo = []
    removidos = 0

    for x in itens:
        if int(x.get("negocio_id", 0)) == int(negocio_id) and str(x.get("data", "")).startswith(mes):
            removidos += 1
            continue
        novo.append(x)

    salvar_json(FINANCEIRO_FILE, novo)
    return removidos