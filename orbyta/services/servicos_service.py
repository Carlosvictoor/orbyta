from core.constants import SERVICOS_FILE
from core.json_db import carregar_json, salvar_json
from core.helpers import parse_money_br


CATEGORIAS_PADRAO = [
    "Cabelo",
    "Barba",
    "Unha",
    "Sobrancelha",
    "Estética",
    "Depilação",
    "Massagem",
    "Maquiagem",
]

CATEGORIA_POR_PALAVRA = {
    "Cabelo": ["corte", "escova", "selagem", "hidrata", "colora", "mecha", "luzes", "penteado", "progressiva", "cabelo"],
    "Barba": ["barba", "bigode", "navalha", "toalha quente"],
    "Unha": ["unha", "manicure", "pedicure", "gel", "fibra", "blindagem", "esmalta", "nail"],
    "Sobrancelha": ["sobrancelha", "henna", "design"],
    "Estética": ["limpeza de pele", "pele", "botox", "micropigment", "estetica", "estética"],
    "Depilação": ["depil", "cera"],
    "Massagem": ["massagem", "drenagem", "relaxante"],
    "Maquiagem": ["maquiagem", "make"],
}

ICONE_CATEGORIA = {
    "Cabelo": "✂️",
    "Barba": "🧔",
    "Unha": "💅",
    "Sobrancelha": "✨",
    "Estética": "🌿",
    "Depilação": "🪒",
    "Massagem": "💆",
    "Maquiagem": "💄",
    "Geral": "⭐",
}


def _texto_limpo(valor, padrao=""):
    return str(valor or padrao).strip()


def _normalizar_categoria(valor):
    categoria = _texto_limpo(valor, "Geral") or "Geral"
    return " ".join(parte.capitalize() for parte in categoria.split())


def _inferir_categoria(nome="", descricao=""):
    base = f"{_texto_limpo(nome).lower()} {_texto_limpo(descricao).lower()}"
    for categoria, palavras in CATEGORIA_POR_PALAVRA.items():
        if any(palavra in base for palavra in palavras):
            return categoria
    return "Geral"


def icone_categoria(categoria):
    categoria = _normalizar_categoria(categoria)
    return ICONE_CATEGORIA.get(categoria, "⭐")


def ordem_categoria(categoria):
    categoria = _normalizar_categoria(categoria)
    if categoria in CATEGORIAS_PADRAO:
        return CATEGORIAS_PADRAO.index(categoria)
    return len(CATEGORIAS_PADRAO) + 1


def normalizar_servico(item):
    servico = dict(item or {})
    servico["descricao"] = _texto_limpo(servico.get("descricao"))
    servico["nome"] = _texto_limpo(servico.get("nome"))
    servico["foto"] = _texto_limpo(servico.get("foto"))

    categoria_informada = _texto_limpo(servico.get("categoria") or servico.get("tipo_servico"))
    categoria_inferida = _inferir_categoria(servico.get("nome"), servico.get("descricao"))
    categoria_base = categoria_informada

    if not categoria_base or categoria_base.lower() == "geral":
        categoria_base = categoria_inferida or "Geral"

    servico["categoria"] = _normalizar_categoria(categoria_base)

    try:
        servico["duracao_min"] = max(int(servico.get("duracao_min", 30) or 30), 5)
    except Exception:
        servico["duracao_min"] = 30

    try:
        servico["ordem"] = max(int(servico.get("ordem", 0) or 0), 0)
    except Exception:
        servico["ordem"] = 0

    servico["icone_categoria"] = icone_categoria(servico.get("categoria"))
    servico["preco"] = _texto_limpo(servico.get("preco"))
    servico["ativo"] = bool(servico.get("ativo", True))
    return servico


def listar_servicos():
    servs = [normalizar_servico(s) for s in carregar_json(SERVICOS_FILE)]
    return sorted(
        servs,
        key=lambda s: (
            int(s.get("negocio_id", 0) or 0),
            ordem_categoria(s.get("categoria", "Geral")),
            s.get("categoria", "Geral"),
            int(s.get("ordem", 0) or 0),
            s.get("nome", ""),
        ),
    )


def salvar_servicos(servs):
    salvar_json(SERVICOS_FILE, [normalizar_servico(s) for s in servs])


def categorias_sugeridas():
    return CATEGORIAS_PADRAO[:]


def agrupar_servicos_por_categoria(servs):
    grupos = {}
    for s in servs or []:
        item = normalizar_servico(s)
        categoria = item.get("categoria") or "Geral"
        grupos.setdefault(categoria, []).append(item)

    categorias_ordenadas = sorted(grupos.keys(), key=lambda cat: (ordem_categoria(cat), cat))
    return [
        {
            "categoria": categoria,
            "icone": icone_categoria(categoria),
            "itens": sorted(itens, key=lambda s: (int(s.get("ordem", 0) or 0), s.get("nome", ""))),
        }
        for categoria in categorias_ordenadas
        for itens in [grupos[categoria]]
    ]


def servico_preco(negocio_id: int, servico_id: int) -> float:
    servs = listar_servicos()
    for s in servs:
        if int(s.get("negocio_id", 0)) == int(negocio_id) and int(s.get("id", 0)) == int(servico_id):
            return parse_money_br(s.get("preco"))
    return 0.0


def servico_nome_by_id(negocio_id: int, servico_id: int) -> str:
    servs = listar_servicos()
    for s in servs:
        if int(s.get("negocio_id", 0)) == int(negocio_id) and int(s.get("id", 0)) == int(servico_id):
            return (s.get("nome") or "").strip()
    return ""


def get_servico(negocio_id: int, servico_id: int):
    servs = listar_servicos()
    for s in servs:
        if int(s.get("negocio_id", 0)) == int(negocio_id) and int(s.get("id", 0)) == int(servico_id):
            return s
    return None


def servico_duracao_min(negocio_id: int, servico_id: int) -> int:
    servs = listar_servicos()
    for s in servs:
        if int(s.get("negocio_id", 0)) == int(negocio_id) and int(s.get("id", 0)) == int(servico_id):
            try:
                return max(int(s.get("duracao_min", 30) or 30), 30)
            except Exception:
                return 30
    return 30


def servicos_do_negocio(negocio_id):
    servs = listar_servicos()
    return [s for s in servs if int(s.get("negocio_id", 0)) == int(negocio_id) and s.get("ativo", True)]