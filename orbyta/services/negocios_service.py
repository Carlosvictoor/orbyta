from core.constants import NEGOCIOS_FILE
from core.json_db import carregar_json, salvar_json


def listar_negocios():
    return carregar_json(NEGOCIOS_FILE)


def salvar_negocios(negocios):
    salvar_json(NEGOCIOS_FILE, negocios)


def get_negocio(negocio_id):
    negocios = carregar_json(NEGOCIOS_FILE)
    for n in negocios:
        if int(n.get("id", 0)) == int(negocio_id):
            return n
    return None


def atualizar_negocio(negocio_id, patch: dict):
    negocios = carregar_json(NEGOCIOS_FILE)
    for n in negocios:
        if int(n.get("id", 0)) == int(negocio_id):
            n.update(patch or {})
            salvar_json(NEGOCIOS_FILE, negocios)
            return True
    return False