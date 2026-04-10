from core.constants import PROFISSIONAIS_FILE
from core.json_db import carregar_json, salvar_json
from core.helpers import clamp_pct

MAPA_CATEGORIAS_PADRAO = {
    "barbeiro": ["Cabelo", "Barba"],
    "cabeleireiro": ["Cabelo"],
    "cabeleireira": ["Cabelo"],
    "nail": ["Unha"],
    "manicure": ["Unha"],
    "pedicure": ["Unha"],
    "estetica": ["Estética", "Sobrancelha", "Depilação", "Massagem", "Maquiagem"],
    "estética": ["Estética", "Sobrancelha", "Depilação", "Massagem", "Maquiagem"],
}


def _lista_normalizada(valores):
    if isinstance(valores, str):
        valores = [v.strip() for v in valores.split("|") if v.strip()]

    lista = []
    vistos = set()
    for item in valores or []:
        texto = " ".join(str(item or "").strip().split())
        if not texto:
            continue
        chave = texto.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        lista.append(texto.title() if texto.islower() else texto)
    return lista


def categorias_servico_profissional(profissional: dict | None):
    profissional = profissional or {}
    categorias_explicitas = _lista_normalizada(
        profissional.get("categorias_servico") or profissional.get("especialidades")
    )
    if categorias_explicitas:
        return categorias_explicitas

    categoria_base = str(profissional.get("categoria") or "").strip().lower()
    return MAPA_CATEGORIAS_PADRAO.get(categoria_base, [])


def profissional_atende_categoria(profissional: dict | None, categoria_servico: str):
    categoria = str(categoria_servico or "").strip().lower()
    if not categoria:
        return True

    categorias = [c.lower() for c in categorias_servico_profissional(profissional)]
    return True if not categorias else categoria in categorias


def profissional_atende_servico(profissional: dict | None, servico: dict | None):
    return profissional_atende_categoria(profissional, (servico or {}).get("categoria", ""))


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
            p["categorias_servico"] = categorias_servico_profissional(p)
            lista.append(p)
    return lista


def get_profissional(prof_id):
    profs = carregar_json(PROFISSIONAIS_FILE)
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id):
            if "comissao_pct" not in p:
                p["comissao_pct"] = 50
            p["categorias_servico"] = categorias_servico_profissional(p)
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
            p["categorias_servico"] = categorias_servico_profissional(p)
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