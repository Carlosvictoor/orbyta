from core.constants import HORARIOS_FILE, AGENDAMENTOS_FILE
from core.json_db import carregar_json, salvar_json
from core.helpers import SLOTS_PADRAO_30
from services.profissionais_service import get_profissional_por_nome, profissional_atende_servico
from services.servicos_service import servico_duracao_min, get_servico


def obter_horarios_globais(negocio_id):
    hs = carregar_json(HORARIOS_FILE)
    for h in hs:
        if int(h.get("negocio_id", 0)) == int(negocio_id) and h.get("modo") == "global":
            times = h.get("times") or []
            return [t for t in times if t in SLOTS_PADRAO_30]
    return []


def salvar_horarios_globais(negocio_id, selecionados):
    hs = carregar_json(HORARIOS_FILE)
    hs = [h for h in hs if not (int(h.get("negocio_id", 0)) == int(negocio_id) and h.get("modo") == "global")]
    hs.append({"negocio_id": int(negocio_id), "modo": "global", "times": selecionados})
    salvar_json(HORARIOS_FILE, hs)


def _slots_intervalo(horario_inicial, duracao_min):
    horario_inicial = (horario_inicial or "").strip()
    if horario_inicial not in SLOTS_PADRAO_30:
        return []

    try:
        duracao = max(int(duracao_min or 30), 30)
    except Exception:
        duracao = 30

    slots_necessarios = max(1, (duracao + 29) // 30)
    idx = SLOTS_PADRAO_30.index(horario_inicial)
    return SLOTS_PADRAO_30[idx: idx + slots_necessarios]


def obter_horarios_disponiveis(negocio_id, barbeiro, data, servico_id=None):
    permitidos = obter_horarios_globais(negocio_id)
    if not permitidos:
        return []

    profissional = get_profissional_por_nome(negocio_id, barbeiro)
    profissional_id = int(profissional.get("id", 0)) if profissional else 0
    servico = get_servico(negocio_id, int(servico_id or 0)) if servico_id else None
    if profissional and servico and not profissional_atende_servico(profissional, servico):
        return []

    duracao_solicitada = servico_duracao_min(negocio_id, int(servico_id or 0))

    ag = carregar_json(AGENDAMENTOS_FILE)
    ocupados = set()

    for a in ag:
        if int(a.get("negocio_id", 0)) != int(negocio_id):
            continue
        if a.get("data") != data:
            continue
        if (a.get("status_confirmacao") or "").strip().lower() == "cancelado":
            continue

        mesma_pessoa = False
        a_prof_id = int(a.get("profissional_id", 0) or 0)

        if profissional_id and a_prof_id == profissional_id:
            mesma_pessoa = True
        elif not profissional_id and (a.get("barbeiro") or "").strip().lower() == (barbeiro or "").strip().lower():
            mesma_pessoa = True

        if mesma_pessoa:
            duracao_agendada = servico_duracao_min(negocio_id, int(a.get("servico_id", 0) or 0))
            for slot in _slots_intervalo(a.get("horario"), duracao_agendada):
                ocupados.add(slot)

    livres = []
    for t in permitidos:
        intervalo = _slots_intervalo(t, duracao_solicitada)
        if not intervalo:
            continue
        if any(slot not in permitidos for slot in intervalo):
            continue
        if any(slot in ocupados for slot in intervalo):
            continue
        livres.append(t)

    return livres