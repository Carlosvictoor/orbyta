from core.constants import PROFISSIONAIS_FILE
from core.json_db import carregar_json, salvar_json
from core.helpers import clamp_pct


def listar_profissionais():
    return carregar_json(PROFISSIONAIS_FILE)


def salvar_profissionais(profs):
    salvar_json(PROFISSIONAIS_FILE, profs)


def profissionais_do_negocio(negocio_id):
    profs = carregar_json(PROFISSIONAIS_FILE)
    lista = []
    for p in profs:
        if int(p.get("negocio_id", 0)) == int(negocio_id):
            if "comissao_pct" not in p:
                p["comissao_pct"] = 50
            lista.append(p)
    return lista


def get_profissional(prof_id):
    profs = carregar_json(PROFISSIONAIS_FILE)
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id):
            if "comissao_pct" not in p:
                p["comissao_pct"] = 50
            return p
    return None


def get_profissional_por_nome(negocio_id, nome):
    nome = (nome or "").strip().lower()
    if not nome:
        return None

    profs = carregar_json(PROFISSIONAIS_FILE)
    for p in profs:
        if int(p.get("negocio_id", 0)) == int(negocio_id) and p.get("nome", "").strip().lower() == nome:
            if "comissao_pct" not in p:
                p["comissao_pct"] = 50
            return p
    return None


def comissao_pct_profissional(negocio_id, profissional_id=None, nome=None):
    profs = carregar_json(PROFISSIONAIS_FILE)

    if profissional_id:
        for p in profs:
            if int(p.get("negocio_id", 0)) == int(negocio_id) and int(p.get("id", 0)) == int(profissional_id):
                return clamp_pct(p.get("comissao_pct", 50), 50)

    nome = (nome or "").strip().lower()
    if nome:
        for p in profs:
            if int(p.get("negocio_id", 0)) == int(negocio_id) and p.get("nome", "").strip().lower() == nome:
                return clamp_pct(p.get("comissao_pct", 50), 50)

    return 50.0