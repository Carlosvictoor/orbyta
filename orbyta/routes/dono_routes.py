import os
import uuid
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, session, flash, current_app

from core.auth import exigir_dono, usuario_atual, exigir_assinatura_dono
from core.constants import AGENDAMENTOS_FILE, APP_BASE_URL, MP_ACCESS_TOKEN, MP_PUBLIC_KEY, RANKING_RESET_FILE, USUARIOS_FILE
from core.helpers import parse_money_br, SLOTS_PADRAO_30, clamp_pct, salvar_imagem_upload
from core.json_db import carregar_json, salvar_json
from core.security import hash_senha, senha_forte

from services.negocios_service import get_negocio, atualizar_negocio
from services.profissionais_service import (
    profissionais_do_negocio,
    get_profissional,
    listar_profissionais,
    salvar_profissionais,
    categorias_servico_profissional,
    profissional_atende_servico,
)
from services.servicos_service import (
    listar_servicos,
    salvar_servicos,
    servico_preco,
    servico_nome_by_id,
    categorias_sugeridas,
    agrupar_servicos_por_categoria,
    servicos_do_negocio,
)
from services.horarios_service import obter_horarios_globais, salvar_horarios_globais, obter_horarios_disponiveis
from services.financeiro_service import (
    financeiro_do_negocio,
    salvar_lancamento_financeiro,
    remover_lancamento_financeiro,
    zerar_financeiro_mes,
)
from services.whatsapp_service import (
    send_whatsapp_message,
    telefone_valido_br,
    normalizar_telefone_e164,
    renderizar_template_lembrete,
    gerar_link_whatsapp,
)
from services.assinatura_service import plano_do_dono, limite_funcionarios_do_plano, pode_adicionar_mais_funcionarios

dono_bp = Blueprint("dono", __name__)


def _whatsapp_link(telefone: str, mensagem: str = "") -> str:
    return gerar_link_whatsapp(telefone, mensagem)


def _parse_agendamento_datahora(item: dict):
    try:
        return datetime.strptime(
            f"{item.get('data', '')} {item.get('horario', '')}",
            "%Y-%m-%d %H:%M",
        )
    except Exception:
        return None


def _enriquecer_whatsapp_agendamento(item: dict, negocio: dict, now: datetime):
    telefone = (item.get("telefone") or "").strip()
    status = (item.get("status_confirmacao") or "").strip().lower()

    item["whatsapp_link"] = _whatsapp_link(telefone)
    item["lembrete_manual_link"] = ""
    item["faltam_minutos"] = None
    item["pode_enviar_lembrete"] = False

    if not telefone or status == "cancelado":
        return item

    horario_agendado = _parse_agendamento_datahora(item)
    if not horario_agendado:
        return item

    faltam_minutos = int((horario_agendado - now).total_seconds() / 60)
    item["faltam_minutos"] = faltam_minutos

    if 0 < faltam_minutos <= 45:
        mensagem = renderizar_template_lembrete(negocio.get("whatsapp_mensagem_template", ""), item, negocio)
        item["lembrete_manual_link"] = _whatsapp_link(telefone, mensagem)
        item["pode_enviar_lembrete"] = True

    return item


def _categorias_servicos_negocio(servs):
    sugestoes = categorias_sugeridas() + ["Barba", "Sobrancelha", "Depilação", "Massagem", "Maquiagem", "Geral"]
    lista = []
    vistos = set()

    for categoria in sugestoes + [str(s.get("categoria") or "").strip() for s in (servs or [])]:
        nome = " ".join(str(categoria or "").strip().split())
        if not nome:
            continue
        chave = nome.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        lista.append(nome)

    return lista


@dono_bp.route("/painel")
def painel():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    if not exigir_assinatura_dono():
        flash("Seu teste terminou ou sua assinatura não está ativa. Assine para continuar ✅")
        return redirect("/assinar")

    negocio_id = session.get("negocio_id")
    if not negocio_id:
        flash("Seu usuário dono não está vinculado a um negócio ainda.")
        return redirect("/")

    negocio_id = int(negocio_id)
    negocio = get_negocio(negocio_id)

    if not negocio:
        flash("Negócio do dono não encontrado.")
        return redirect("/")

    ag = carregar_json(AGENDAMENTOS_FILE)
    ag_do_negocio = [a for a in ag if int(a.get("negocio_id", 0)) == negocio_id]
    ag_do_negocio.sort(key=lambda x: (x.get("data", ""), x.get("horario", "")), reverse=True)

    now = datetime.now()
    for item in ag_do_negocio:
        _enriquecer_whatsapp_agendamento(item, negocio, now)

    lembretes_manuais = [item for item in ag_do_negocio if item.get("pode_enviar_lembrete")]

    negocio["whatsapp_link"] = _whatsapp_link(negocio.get("whatsapp"))

    times = obter_horarios_globais(negocio_id)
    horarios_funcionamento = [{"dia": "Todos os dias", "times": times}] if times else []
    profs = profissionais_do_negocio(negocio_id)
    servs = servicos_do_negocio(negocio_id)

    hoje = datetime.now().strftime("%Y-%m-%d")
    mes_atual = datetime.now().strftime("%Y-%m")

    hoje_qtd = 0
    faturamento_mes = 0.0
    clientes_unicos_set = set()
    ranking_map = {}
    proximos = []

    for a in ag_do_negocio:
        if (a.get("status_confirmacao") or "").strip().lower() == "cancelado":
            continue

        data_ag = a.get("data", "")
        horario_ag = a.get("horario", "")
        cliente = (a.get("nome") or "").strip()
        barbeiro = (a.get("barbeiro") or "").strip()
        servico = (a.get("servico") or "").strip()
        sid = int(a.get("servico_id", 0) or 0)

        if cliente:
            clientes_unicos_set.add(cliente.lower())

        if data_ag == hoje:
            hoje_qtd += 1
            proximos.append({
                "data": data_ag,
                "horario": horario_ag,
                "nome": cliente or "Cliente",
                "servico": servico or servico_nome_by_id(negocio_id, sid) or "Serviço",
                "barbeiro": barbeiro or "Profissional",
                "telefone": a.get("telefone", ""),
                "whatsapp_link": a.get("whatsapp_link", _whatsapp_link(a.get("telefone", ""))),
                "lembrete_manual_link": a.get("lembrete_manual_link", ""),
                "pode_enviar_lembrete": a.get("pode_enviar_lembrete", False),
                "faltam_minutos": a.get("faltam_minutos"),
            })

        if data_ag[:7] == mes_atual:
            valor = servico_preco(negocio_id, sid)
            faturamento_mes += valor

            nome_prof = barbeiro or "Profissional"
            if nome_prof not in ranking_map:
                ranking_map[nome_prof] = {"nome": nome_prof, "valor": 0.0, "qtd": 0}

            ranking_map[nome_prof]["valor"] += valor
            ranking_map[nome_prof]["qtd"] += 1

    proximos.sort(key=lambda x: (x.get("data", ""), x.get("horario", "")))
    proximos = proximos[:8]

    resets = carregar_json(RANKING_RESET_FILE)
    reset_mes = next((r for r in resets if int(r.get('negocio_id', 0)) == negocio_id and r.get('mes') == mes_atual), None)
    reset_em = reset_mes.get('reset_em') if reset_mes else None

    if reset_em:
        try:
            reset_dt = datetime.strptime(reset_em, "%Y-%m-%d %H:%M:%S")
            ranking = [
                r for r in ranking_map.values()
                if True
            ]
            ranking = []
            ranking_map_filtrado = {}
            for a in ag_do_negocio:
                data_ag = a.get("data", "")
                horario_ag = a.get("horario", "")
                created_raw = a.get("criado_em") or f"{data_ag} {horario_ag}:00"
                try:
                    created_dt = datetime.strptime(created_raw, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        created_dt = datetime.strptime(f"{data_ag} {horario_ag}:00", "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
                if data_ag[:7] != mes_atual or created_dt < reset_dt:
                    continue
                sid = int(a.get("servico_id", 0) or 0)
                valor = servico_preco(negocio_id, sid)
                nome_prof = (a.get("barbeiro") or "Profissional").strip() or "Profissional"
                if nome_prof not in ranking_map_filtrado:
                    ranking_map_filtrado[nome_prof] = {"nome": nome_prof, "valor": 0.0, "qtd": 0}
                ranking_map_filtrado[nome_prof]["valor"] += valor
                ranking_map_filtrado[nome_prof]["qtd"] += 1
            ranking = sorted(ranking_map_filtrado.values(), key=lambda x: (x["valor"], x["qtd"]), reverse=True)[:5]
        except Exception:
            ranking = sorted(ranking_map.values(), key=lambda x: (x["valor"], x["qtd"]), reverse=True)[:5]
    else:
        ranking = sorted(ranking_map.values(), key=lambda x: (x["valor"], x["qtd"]), reverse=True)[:5]

    for r in ranking:
        r["valor"] = round(r["valor"], 2)

    clientes_unicos = len(clientes_unicos_set)

    base_url = (APP_BASE_URL or "").strip()
    whatsapp_provider = (os.getenv("WHATSAPP_PROVIDER", "none") or "none").strip().lower()
    whatsapp_numero = (negocio.get("whatsapp_numero_envio") or negocio.get("whatsapp") or "").strip()
    integracoes = [
        {
            "nome": "Domínio público",
            "ok": bool(base_url and "127.0.0.1" not in base_url and "localhost" not in base_url),
            "detalhe": base_url or "Ainda em ambiente local",
        },
        {
            "nome": "Mercado Pago",
            "ok": bool(MP_ACCESS_TOKEN and MP_PUBLIC_KEY),
            "detalhe": "Chaves configuradas" if (MP_ACCESS_TOKEN and MP_PUBLIC_KEY) else "Faltam as chaves do pagamento",
        },
        {
            "nome": "WhatsApp automático",
            "ok": bool(whatsapp_numero and whatsapp_provider != "none"),
            "detalhe": f"{whatsapp_provider} • {whatsapp_numero}" if (whatsapp_numero and whatsapp_provider != "none") else "Defina o número e o provider",
        },
    ]

    return render_template(
        "painel.html",
        ag=ag_do_negocio[:20],
        negocio=negocio,
        horarios_funcionamento=horarios_funcionamento,
        hoje_qtd=hoje_qtd,
        faturamento_mes=round(faturamento_mes, 2),
        clientes_unicos=clientes_unicos,
        ranking=ranking,
        proximos=proximos,
        ranking_reset_em=reset_em,
        integracoes=integracoes,
        profs=profs,
        servs=servs,
        horarios_configurados=times,
        data_hoje=hoje,
        lembretes_manuais=lembretes_manuais[:8],
    )


@dono_bp.route("/painel/agendar-manual", methods=["POST"])
def painel_agendar_manual():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    data = request.form.get("data", "").strip()
    horario = request.form.get("horario", "").strip()
    servico_id = request.form.get("servico_id", "").strip()
    profissional_id = request.form.get("profissional_id", "").strip()

    if not nome:
        flash("Informe o nome do cliente.")
        return redirect("/painel")

    if telefone and not telefone_valido_br(telefone):
        flash("Informe um telefone/WhatsApp válido com DDD ou deixe em branco.")
        return redirect("/painel")

    try:
        datetime.strptime(data, "%Y-%m-%d")
    except Exception:
        flash("Data inválida.")
        return redirect("/painel")

    if not servico_id.isdigit():
        flash("Selecione um serviço válido.")
        return redirect("/painel")

    if not profissional_id.isdigit():
        flash("Selecione um profissional válido.")
        return redirect("/painel")

    profissional = get_profissional(int(profissional_id))
    if not profissional or int(profissional.get("negocio_id", 0)) != negocio_id:
        flash("Profissional não encontrado.")
        return redirect("/painel")

    servico_escolhido = next((s for s in servicos_do_negocio(negocio_id) if int(s.get("id", 0)) == int(servico_id)), None)
    if servico_escolhido and not profissional_atende_servico(profissional, servico_escolhido):
        flash("Esse profissional não atende essa área/serviço.")
        return redirect("/painel")

    horarios_livres = obter_horarios_disponiveis(negocio_id, profissional.get("nome", ""), data, int(servico_id))
    if horario not in horarios_livres:
        flash("Esse horário não está disponível para o profissional escolhido.")
        return redirect("/painel")

    ag = carregar_json(AGENDAMENTOS_FILE)
    novo_id = max([int(a.get("id", 0) or 0) for a in ag], default=0) + 1
    servico_nome = servico_nome_by_id(negocio_id, int(servico_id)) or "Serviço"

    ag.append({
        "id": novo_id,
        "negocio_id": negocio_id,
        "nome": nome,
        "cliente": "",
        "telefone": telefone,
        "data": data,
        "horario": horario,
        "barbeiro": profissional.get("nome", "Profissional"),
        "profissional_id": int(profissional_id),
        "servico_id": int(servico_id),
        "servico": servico_nome,
        "status_confirmacao": "pendente" if telefone else "sem_whatsapp",
        "confirmacao_token": uuid.uuid4().hex,
        "lembrete_whatsapp_status": "aguardando" if telefone else "não configurado",
        "origem": "manual_dono",
        "criado_por": u.get("email") or "dono",
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    salvar_json(AGENDAMENTOS_FILE, ag)

    flash(f"Agendamento manual salvo ✅ {nome} • {profissional.get('nome')} • {data} às {horario}")
    return redirect("/painel")


@dono_bp.route("/painel/agendamentos/excluir/<path:ag_id>")
def painel_agendamento_excluir(ag_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    ag = carregar_json(AGENDAMENTOS_FILE)
    novo = []
    removido = False

    for item in ag:
        item_id = item.get("id") or f"{item.get('data','')}|{item.get('horario','')}|{item.get('nome','')}|{item.get('barbeiro','')}"
        if int(item.get("negocio_id", 0)) == negocio_id and str(item_id) == str(ag_id):
            removido = True
            continue
        novo.append(item)

    salvar_json(AGENDAMENTOS_FILE, novo)
    flash("Agendamento excluído ✅" if removido else "Agendamento não encontrado.")
    return redirect("/painel")


@dono_bp.route("/painel/agendamentos/cancelar/<path:ag_id>")
def painel_agendamento_cancelar(ag_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    ag = carregar_json(AGENDAMENTOS_FILE)
    ok = False

    for item in ag:
        item_id = item.get("id") or f"{item.get('data','')}|{item.get('horario','')}|{item.get('nome','')}|{item.get('barbeiro','')}"
        if int(item.get("negocio_id", 0)) == negocio_id and str(item_id) == str(ag_id):
            item["status_confirmacao"] = "cancelado"
            item["cancelado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ok = True
            break

    salvar_json(AGENDAMENTOS_FILE, ag)
    flash("Cliente marcado como cancelado ✅" if ok else "Agendamento não encontrado.")
    return redirect("/painel")


@dono_bp.route("/painel/ranking/zerar")
def painel_ranking_zerar():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    mes = datetime.now().strftime("%Y-%m")
    resets = carregar_json(RANKING_RESET_FILE)
    resets = [r for r in resets if not (int(r.get('negocio_id', 0)) == negocio_id and r.get('mes') == mes)]
    resets.append({
        "negocio_id": negocio_id,
        "mes": mes,
        "reset_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    salvar_json(RANKING_RESET_FILE, resets)
    flash("Ranking do mês zerado ✅")
    return redirect("/painel")


@dono_bp.route("/painel/config-whatsapp", methods=["POST"])
def painel_config_whatsapp():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    mensagem = request.form.get("whatsapp_mensagem_template", "").strip()
    ativo = request.form.get("whatsapp_lembrete_ativo") == "on"
    whatsapp_numero_envio = request.form.get("whatsapp_numero_envio", "").strip()

    if not mensagem:
        flash("Escreva a mensagem que será enviada no WhatsApp.")
        return redirect("/painel")

    if whatsapp_numero_envio and not telefone_valido_br(whatsapp_numero_envio):
        flash("Informe um número de WhatsApp válido com DDD para o estabelecimento.")
        return redirect("/painel")

    negocio = get_negocio(negocio_id) or {}
    atualizar_negocio(
        negocio_id,
        {
            "whatsapp_lembrete_ativo": ativo,
            "whatsapp_mensagem_template": mensagem,
            "whatsapp_numero_envio": whatsapp_numero_envio,
            "whatsapp": whatsapp_numero_envio or negocio.get("whatsapp", ""),
        },
    )

    flash("Configuração do WhatsApp salva ✅")
    return redirect("/painel")


@dono_bp.route("/painel/whatsapp/teste", methods=["POST"])
def painel_whatsapp_teste():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    negocio = get_negocio(negocio_id)
    if not negocio:
        flash("Negócio não encontrado.")
        return redirect("/painel")

    numero_destino = request.form.get("whatsapp_numero_teste", "").strip() or negocio.get("whatsapp_numero_envio") or negocio.get("whatsapp") or ""
    if not numero_destino or not telefone_valido_br(numero_destino):
        flash("Informe um WhatsApp válido para enviar o teste.")
        return redirect("/painel")

    mensagem = (
        f"Teste do WhatsApp da {negocio.get('nome', 'Orbyta')} ✅\n"
        f"Se você recebeu esta mensagem, a configuração principal está pronta para produção."
    )

    whatsapp_provider = (os.getenv("WHATSAPP_PROVIDER", "none") or "none").strip().lower()
    if whatsapp_provider in {"", "none"}:
        link_manual = gerar_link_whatsapp(numero_destino, mensagem)
        if link_manual:
            flash("Abrindo WhatsApp Web com a mensagem de teste pronta ✅")
            return redirect(link_manual)
        flash("Não foi possível montar o link manual do WhatsApp.")
        return redirect("/painel")

    ok, detalhe = send_whatsapp_message(numero_destino, mensagem, negocio=negocio)
    flash("Mensagem de teste enviada ✅" if ok else f"Falha no teste do WhatsApp: {detalhe}")
    return redirect("/painel")


@dono_bp.route("/painel/personalizar", methods=["POST"])
def painel_personalizar():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    negocio = get_negocio(negocio_id)
    if not negocio:
        flash("Negócio não encontrado.")
        return redirect("/painel")

    foto_url = request.form.get("foto_url", "").strip()
    descricao_curta = request.form.get("descricao_curta", "").strip()
    instagram = request.form.get("instagram", "").strip()
    remover_foto = request.form.get("remover_foto") == "1"

    foto_upload, erro_upload = salvar_imagem_upload(
        request.files.get("foto_arquivo"),
        current_app.static_folder,
        prefix=f"negocio-{negocio_id}",
    )
    if erro_upload:
        flash(erro_upload)
        return redirect("/painel")

    patch = {
        "descricao_curta": descricao_curta,
        "instagram": instagram,
    }

    if remover_foto:
        patch["foto"] = ""
    elif foto_upload:
        patch["foto"] = foto_upload
    elif foto_url:
        patch["foto"] = foto_url

    atualizar_negocio(negocio_id, patch)
    flash("Página da loja atualizada ✅")
    return redirect("/painel")


@dono_bp.route("/painel/financeiro", methods=["GET", "POST"])
def painel_financeiro():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    negocio = get_negocio(negocio_id)
    if not negocio:
        flash("Negócio não encontrado.")
        return redirect("/painel")

    mes = request.args.get("mes", "").strip()
    try:
        datetime.strptime(mes, "%Y-%m")
    except Exception:
        mes = datetime.now().strftime("%Y-%m")

    if request.method == "POST":
        tipo = request.form.get("tipo", "").strip()
        if tipo not in ["entrada", "saida"]:
            tipo = "saida"

        categoria = request.form.get("categoria", "").strip() or ("Entrada manual" if tipo == "entrada" else "Despesa geral")
        desc = request.form.get("descricao", "").strip()
        valor_raw = request.form.get("valor", "").strip()
        data = request.form.get("data", "").strip() or datetime.now().strftime("%Y-%m-%d")

        v = parse_money_br(valor_raw)
        if v <= 0:
            flash("Valor inválido.")
            return redirect(f"/painel/financeiro?mes={mes}")

        try:
            datetime.strptime(data, "%Y-%m-%d")
        except Exception:
            flash("Data inválida.")
            return redirect(f"/painel/financeiro?mes={mes}")

        itens_existentes = financeiro_do_negocio(negocio_id)
        novo_id = max([int(x.get("id", 0) or 0) for x in itens_existentes], default=0) + 1

        item = {
            "id": novo_id,
            "negocio_id": negocio_id,
            "tipo": tipo,
            "categoria": categoria,
            "descricao": desc,
            "valor": round(v, 2),
            "data": data,
            "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        profissional_id = request.form.get("profissional_id", "").strip()
        if profissional_id.isdigit():
            item["profissional_id"] = int(profissional_id)

        salvar_lancamento_financeiro(item)

        flash(f"Lançamento salvo ✅ {categoria} • R$ {round(v, 2):.2f}")
        return redirect(f"/painel/financeiro?mes={mes}")

    itens = financeiro_do_negocio(negocio_id)
    itens_mes = [x for x in itens if x.get("data", "")[:7] == mes]
    itens_mes.sort(key=lambda x: (x.get("data", ""), x.get("tipo", "")), reverse=True)

    ag_all = carregar_json(AGENDAMENTOS_FILE)
    ag_mes = [
        a for a in ag_all
        if int(a.get("negocio_id", 0)) == int(negocio_id)
        and a.get("data", "")[:7] == mes
        and (a.get("status_confirmacao") or "").strip().lower() != "cancelado"
    ]

    auto_entradas = []
    for a in ag_mes:
        sid = int(a.get("servico_id", 0) or 0)
        preco = servico_preco(negocio_id, sid)
        nome_serv = a.get("servico") or servico_nome_by_id(negocio_id, sid) or "Serviço"

        agendamento_id = a.get("id") or f"{a.get('data','')}|{a.get('horario','')}|{a.get('nome','')}|{a.get('barbeiro','')}"
        auto_item = {
            "id": f"auto-{a.get('data','')}-{a.get('horario','')}-{a.get('barbeiro','')}-{sid}",
            "agendamento_id": agendamento_id,
            "negocio_id": negocio_id,
            "tipo": "entrada",
            "categoria": "Agendamento",
            "descricao": f"{nome_serv} • {a.get('nome','Cliente')} • {a.get('barbeiro','')}",
            "valor": round(float(preco or 0), 2),
            "data": a.get("data", ""),
            "origem": "agendamento"
        }

        if int(a.get("profissional_id", 0) or 0):
            auto_item["profissional_id"] = int(a.get("profissional_id", 0))

        auto_entradas.append(auto_item)

    entradas_auto = sum(float(x.get("valor", 0) or 0) for x in auto_entradas)
    entradas_manual = sum(float(x.get("valor", 0) or 0) for x in itens_mes if x.get("tipo") == "entrada")
    saidas = sum(float(x.get("valor", 0) or 0) for x in itens_mes if x.get("tipo") == "saida")

    entradas = entradas_auto + entradas_manual
    lucro = entradas - saidas

    qtd_vendas = sum(1 for x in auto_entradas if float(x.get("valor", 0) or 0) > 0)
    ticket = (entradas_auto / qtd_vendas) if qtd_vendas else 0

    itens_tabela = []
    itens_tabela.extend(auto_entradas)

    for x in itens_mes:
        x2 = dict(x)
        x2["origem"] = "manual"
        itens_tabela.append(x2)

    itens_tabela.sort(key=lambda x: (x.get("data", ""), x.get("tipo", "")), reverse=True)

    por_dia = {}
    for x in itens_tabela:
        dia = x.get("data", "")
        if not dia:
            continue
        if dia not in por_dia:
            por_dia[dia] = {"entrada": 0.0, "saida": 0.0}
        t = x.get("tipo")
        por_dia[dia][t] += float(x.get("valor", 0) or 0)

    serie = []
    for dia in sorted(por_dia.keys()):
        serie.append({
            "dia": dia,
            "entrada": round(por_dia[dia]["entrada"], 2),
            "saida": round(por_dia[dia]["saida"], 2),
        })

    profs = profissionais_do_negocio(negocio_id)

    return render_template(
        "financeiro.html",
        negocio=negocio,
        mes=mes,
        itens=itens_tabela,
        entradas=round(entradas, 2),
        saidas=round(saidas, 2),
        lucro=round(lucro, 2),
        ticket=round(ticket, 2),
        qtd_vendas=qtd_vendas,
        serie=serie,
        entradas_auto=round(entradas_auto, 2),
        entradas_manual=round(entradas_manual, 2),
        profs=profs,
        data_hoje=datetime.now().strftime("%Y-%m-%d"),
    )


@dono_bp.route("/painel/financeiro/excluir/<lanc_id>")
def painel_financeiro_excluir(lanc_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))

    ok = remover_lancamento_financeiro(negocio_id, lanc_id)
    flash("Lançamento excluído ✅" if ok else "Não encontrado / item automático não pode ser excluído.")
    return redirect(f"/painel/financeiro?mes={mes}")


@dono_bp.route("/painel/servicos")
def painel_servicos():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id"))
    negocio = get_negocio(negocio_id)

    servs = listar_servicos()
    servs = [s for s in servs if int(s.get("negocio_id", 0)) == negocio_id]
    servicos_agrupados = agrupar_servicos_por_categoria(servs)

    return render_template(
        "painel_servicos.html",
        negocio=negocio,
        servs=servs,
        servicos_agrupados=servicos_agrupados,
        categorias_sugeridas=categorias_sugeridas(),
    )

@dono_bp.route("/painel/servicos/novo", methods=["POST"])
def painel_servicos_novo():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id"))
    categoria = request.form.get("categoria", "").strip()
    nome = request.form.get("nome", "").strip()
    foto_url = request.form.get("foto_url", "").strip()
    descricao = request.form.get("descricao", "").strip()
    ordem_raw = request.form.get("ordem", "0").strip()
    duracao_raw = request.form.get("duracao", "30").strip()
    preco = request.form.get("preco", "").strip()

    if not categoria:
        flash("Tipo de serviço é obrigatório.")
        return redirect("/painel/servicos")

    if not nome:
        flash("Nome do serviço é obrigatório.")
        return redirect("/painel/servicos")

    try:
        ordem = max(int(ordem_raw or 0), 0)
    except Exception:
        ordem = 0

    try:
        duracao = int(duracao_raw)
        if duracao <= 0:
            raise ValueError()
    except Exception:
        flash("Duração inválida.")
        return redirect("/painel/servicos")

    if parse_money_br(preco) <= 0:
        flash("Preço inválido.")
        return redirect("/painel/servicos")

    foto_upload, erro_upload = salvar_imagem_upload(
        request.files.get("foto_arquivo"),
        current_app.static_folder,
        prefix=f"servico-{negocio_id}",
    )
    if erro_upload:
        flash(erro_upload)
        return redirect("/painel/servicos")

    servs = listar_servicos()
    novo_id = max([int(s.get("id", 0)) for s in servs], default=0) + 1

    servs.append({
        "id": novo_id,
        "negocio_id": negocio_id,
        "categoria": categoria,
        "nome": nome,
        "foto": foto_upload or foto_url,
        "descricao": descricao,
        "ordem": ordem,
        "duracao_min": duracao,
        "preco": preco,
        "ativo": True
    })

    salvar_servicos(servs)
    flash("Serviço cadastrado ✅")
    return redirect("/painel/servicos")


@dono_bp.route("/painel/servicos/editar", methods=["POST"])
def painel_servicos_editar():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)

    sid = request.form.get("id", "").strip()
    categoria = request.form.get("categoria", "").strip()
    nome = request.form.get("nome", "").strip()
    foto_url = request.form.get("foto_url", "").strip()
    descricao = request.form.get("descricao", "").strip()
    ordem_raw = request.form.get("ordem", "0").strip()
    duracao_raw = request.form.get("duracao", "30").strip()
    preco = request.form.get("preco", "").strip()
    ativo = request.form.get("ativo", "1").strip()
    remover_foto = request.form.get("remover_foto") == "1"

    if not sid.isdigit():
        flash("Serviço inválido.")
        return redirect("/painel/servicos")

    if not categoria:
        flash("Tipo de serviço é obrigatório.")
        return redirect("/painel/servicos")

    if not nome:
        flash("Nome é obrigatório.")
        return redirect("/painel/servicos")

    try:
        ordem = max(int(ordem_raw or 0), 0)
    except Exception:
        ordem = 0

    try:
        dur = int(duracao_raw)
        if dur <= 0:
            raise ValueError()
    except Exception:
        flash("Duração inválida.")
        return redirect("/painel/servicos")

    if parse_money_br(preco) <= 0:
        flash("Preço inválido.")
        return redirect("/painel/servicos")

    foto_upload, erro_upload = salvar_imagem_upload(
        request.files.get("foto_arquivo"),
        current_app.static_folder,
        prefix=f"servico-{sid}",
    )
    if erro_upload:
        flash(erro_upload)
        return redirect("/painel/servicos")

    servs = listar_servicos()
    ok = False
    for s in servs:
        if int(s.get("id", 0)) == int(sid) and int(s.get("negocio_id", 0)) == negocio_id:
            s["categoria"] = categoria
            s["nome"] = nome
            if remover_foto:
                s["foto"] = ""
            elif foto_upload:
                s["foto"] = foto_upload
            elif foto_url:
                s["foto"] = foto_url
            s["descricao"] = descricao
            s["ordem"] = ordem
            s["duracao_min"] = dur
            s["preco"] = preco
            s["ativo"] = (ativo == "1")
            ok = True
            break

    salvar_servicos(servs)
    flash("Serviço atualizado ✅" if ok else "Serviço não encontrado.")
    return redirect("/painel/servicos")


@dono_bp.route("/painel/servicos/desativar/<int:serv_id>")
def painel_servicos_desativar(serv_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id"))
    servs = listar_servicos()

    for s in servs:
        if int(s.get("id", 0)) == serv_id and int(s.get("negocio_id", 0)) == negocio_id:
            s["ativo"] = False

    salvar_servicos(servs)
    flash("Serviço desativado ✅")
    return redirect("/painel/servicos")


@dono_bp.route("/painel/horarios", methods=["GET", "POST"])
def painel_horarios():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id"))
    negocio = get_negocio(negocio_id)

    if request.method == "POST":
        selecionados = request.form.getlist("times")
        selecionados = [t for t in selecionados if t in SLOTS_PADRAO_30]
        salvar_horarios_globais(negocio_id, selecionados)
        flash("Horários salvos para TODOS OS DIAS ✅")
        return redirect("/painel/horarios")

    selecionados = set(obter_horarios_globais(negocio_id))

    return render_template("painel_horarios.html", negocio=negocio, slots=SLOTS_PADRAO_30, selecionados=selecionados)


@dono_bp.route("/painel/profissionais")
def painel_profissionais():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = session.get("negocio_id")
    if not negocio_id:
        flash("Dono sem negócio vinculado.")
        return redirect("/painel")

    negocio = get_negocio(negocio_id)
    profs = profissionais_do_negocio(negocio_id)
    categorias_servicos = _categorias_servicos_negocio(servicos_do_negocio(int(negocio_id)))

    usuarios = carregar_json(USUARIOS_FILE)
    mapa_acessos = {}
    for usr in usuarios:
        if usr.get("tipo") == "funcionario" and int(usr.get("negocio_id", 0) or 0) == int(negocio_id):
            pid = int(usr.get("profissional_id", 0) or 0)
            if pid:
                mapa_acessos[pid] = usr.get("email")

    for p in profs:
        p["login_funcionario"] = mapa_acessos.get(int(p.get("id", 0)))
        p["comissao_pct"] = clamp_pct(p.get("comissao_pct", 50), 50)
        p["categorias_servico"] = categorias_servico_profissional(p)

    plano_info = plano_do_dono(u)
    limite_funcionarios = limite_funcionarios_do_plano(u)
    qtd_profissionais = len(profs)
    qtd_acessos_funcionarios = sum(1 for usr in usuarios if usr.get("tipo") == "funcionario" and int(usr.get("negocio_id", 0) or 0) == int(negocio_id))
    limite_atingido = limite_funcionarios is not None and qtd_profissionais >= int(limite_funcionarios)

    return render_template(
        "painel_profissionais.html",
        negocio=negocio,
        profs=profs,
        categorias_servicos=categorias_servicos,
        plano_info=plano_info,
        limite_funcionarios=limite_funcionarios,
        qtd_profissionais=qtd_profissionais,
        qtd_acessos_funcionarios=qtd_acessos_funcionarios,
        limite_atingido=limite_atingido,
    )


@dono_bp.route("/painel/profissionais/novo", methods=["GET", "POST"])
def painel_profissionais_novo():
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = session.get("negocio_id")
    if not negocio_id:
        flash("Dono sem negócio vinculado.")
        return redirect("/painel")

    negocio = get_negocio(negocio_id)
    categorias_servicos = _categorias_servicos_negocio(servicos_do_negocio(int(negocio_id)))
    plano_info = plano_do_dono(u)
    limite_funcionarios = limite_funcionarios_do_plano(u)
    profs_existentes = profissionais_do_negocio(negocio_id)
    limite_atingido = limite_funcionarios is not None and len(profs_existentes) >= int(limite_funcionarios)

    if request.method == "POST":
        if not pode_adicionar_mais_funcionarios(u, len(profs_existentes)):
            flash(f"O plano {plano_info['nome']} permite apenas {limite_funcionarios} funcionário cadastrado. Faça upgrade para continuar ✅")
            return redirect("/painel/profissionais")
        nome = request.form["nome"].strip()
        categoria = request.form.get("categoria", "").strip().lower()
        descricao = request.form.get("descricao", "").strip()
        foto_url = request.form.get("foto_url", "").strip()
        categorias_servico = [c.strip() for c in request.form.getlist("categorias_servico") if c.strip()]
        comissao_pct = clamp_pct(request.form.get("comissao_pct", 50), 50)

        if not nome:
            flash("Nome é obrigatório.")
            return redirect("/painel/profissionais/novo")

        if not categoria:
            flash("Categoria é obrigatória.")
            return redirect("/painel/profissionais/novo")

        foto_upload, erro_upload = salvar_imagem_upload(
            request.files.get("foto_arquivo"),
            current_app.static_folder,
            prefix=f"profissional-{negocio_id}",
        )
        if erro_upload:
            flash(erro_upload)
            return redirect("/painel/profissionais/novo")

        profs = listar_profissionais()
        novo_id = max([int(p.get("id", 0)) for p in profs], default=0) + 1

        profs.append({
            "id": novo_id,
            "negocio_id": int(negocio_id),
            "nome": nome,
            "categoria": categoria,
            "descricao": descricao,
            "foto": foto_upload or foto_url,
            "categorias_servico": categorias_servico,
            "comissao_pct": comissao_pct
        })

        salvar_profissionais(profs)
        flash("Profissional cadastrado com sucesso! ✅")
        return redirect("/painel/profissionais")

    return render_template(
        "painel_profissionais_novo.html",
        negocio=negocio,
        categorias_servicos=categorias_servicos,
        plano_info=plano_info,
        limite_funcionarios=limite_funcionarios,
        qtd_profissionais=len(profs_existentes),
        limite_atingido=limite_atingido,
    )


@dono_bp.route("/painel/profissionais/perfil/<int:prof_id>", methods=["POST"])
def atualizar_perfil_profissional(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    foto_url = request.form.get("foto_url", "").strip()
    descricao = request.form.get("descricao", "").strip()
    remover_foto = request.form.get("remover_foto") == "1"

    foto_upload, erro_upload = salvar_imagem_upload(
        request.files.get("foto_arquivo"),
        current_app.static_folder,
        prefix=f"profissional-{prof_id}",
    )
    if erro_upload:
        flash(erro_upload)
        return redirect("/painel/profissionais")

    profs = listar_profissionais()
    ok = False
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id) and int(p.get("negocio_id", 0)) == negocio_id:
            p["descricao"] = descricao
            if remover_foto:
                p["foto"] = ""
            elif foto_upload:
                p["foto"] = foto_upload
            elif foto_url:
                p["foto"] = foto_url
            ok = True
            break

    salvar_profissionais(profs)
    flash("Perfil do profissional atualizado ✅" if ok else "Profissional não encontrado.")
    return redirect("/painel/profissionais")


@dono_bp.route("/painel/profissionais/areas/<int:prof_id>", methods=["POST"])
def atualizar_areas_profissional(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    categorias_servico = [c.strip() for c in request.form.getlist("categorias_servico") if c.strip()]

    profs = listar_profissionais()
    ok = False
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id) and int(p.get("negocio_id", 0)) == negocio_id:
            p["categorias_servico"] = categorias_servico
            ok = True
            break

    salvar_profissionais(profs)
    flash("Áreas de atendimento atualizadas ✅" if ok else "Profissional não encontrado.")
    return redirect("/painel/profissionais")


@dono_bp.route("/painel/profissionais/comissao/<int:prof_id>", methods=["POST"])
def atualizar_comissao_profissional(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    nova_comissao = clamp_pct(request.form.get("comissao_pct", 50), 50)

    profs = listar_profissionais()
    ok = False
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id) and int(p.get("negocio_id", 0)) == negocio_id:
            p["comissao_pct"] = nova_comissao
            ok = True
            break

    salvar_profissionais(profs)
    flash("Comissão atualizada ✅" if ok else "Profissional não encontrado.")
    return redirect("/painel/profissionais")


@dono_bp.route("/painel/profissionais/criar-acesso/<int:prof_id>", methods=["POST"])
def criar_acesso_profissional(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    if not negocio_id:
        flash("Negócio não encontrado.")
        return redirect("/painel/profissionais")

    prof = get_profissional(prof_id)
    if not prof or int(prof.get("negocio_id", 0)) != negocio_id:
        flash("Profissional não encontrado.")
        return redirect("/painel/profissionais")

    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()

    if not email or not senha:
        flash("Email e senha são obrigatórios.")
        return redirect("/painel/profissionais")

    if not senha_forte(senha):
        flash("A senha do funcionário precisa ter pelo menos 6 caracteres.")
        return redirect("/painel/profissionais")

    usuarios = carregar_json(USUARIOS_FILE)

    for usr in usuarios:
        if usr.get("email", "").lower() == email:
            flash("Esse email já está cadastrado.")
            return redirect("/painel/profissionais")

    for usr in usuarios:
        if usr.get("tipo") == "funcionario" and int(usr.get("profissional_id", 0) or 0) == int(prof_id):
            flash("Esse profissional já possui acesso criado.")
            return redirect("/painel/profissionais")

    funcionarios_do_negocio = [
        usr for usr in usuarios
        if usr.get("tipo") == "funcionario" and int(usr.get("negocio_id", 0) or 0) == int(negocio_id)
    ]
    if not pode_adicionar_mais_funcionarios(u, len(funcionarios_do_negocio)):
        plano_info = plano_do_dono(u)
        limite = limite_funcionarios_do_plano(u)
        flash(f"O plano {plano_info['nome']} permite apenas {limite} funcionário com acesso. Faça upgrade para liberar mais ✅")
        return redirect("/painel/profissionais")

    usuarios.append({
        "email": email,
        "senha": hash_senha(senha),
        "tipo": "funcionario",
        "negocio_id": negocio_id,
        "profissional_id": prof_id,
        "assinatura_status": None,
        "trial_ate": None,
        "mp_subscription_id": None,
        "mp_pix_payment_id": None
    })

    salvar_json(USUARIOS_FILE, usuarios)
    flash("Conta do funcionário criada ✅")
    return redirect("/painel/profissionais")


@dono_bp.route("/painel/profissionais/excluir-acesso/<int:prof_id>")
def excluir_acesso_profissional(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = int(session.get("negocio_id") or 0)
    usuarios = carregar_json(USUARIOS_FILE)

    novo = []
    removido = False
    for usr in usuarios:
        if (
            usr.get("tipo") == "funcionario"
            and int(usr.get("negocio_id", 0) or 0) == negocio_id
            and int(usr.get("profissional_id", 0) or 0) == int(prof_id)
        ):
            removido = True
            continue
        novo.append(usr)

    salvar_json(USUARIOS_FILE, novo)
    flash("Acesso do funcionário removido ✅" if removido else "Acesso não encontrado.")
    return redirect("/painel/profissionais")


@dono_bp.route("/painel/profissionais/excluir/<int:prof_id>")
def painel_profissionais_excluir(prof_id):
    if not exigir_dono():
        return redirect("/login")

    u = usuario_atual()
    if not u or not exigir_assinatura_dono():
        flash("Assine para acessar esta área ✅")
        return redirect("/assinar")

    negocio_id = session.get("negocio_id")
    if not negocio_id:
        flash("Dono sem negócio vinculado.")
        return redirect("/painel")

    usuarios = carregar_json(USUARIOS_FILE)
    usuarios = [
        usr for usr in usuarios
        if not (
            usr.get("tipo") == "funcionario"
            and int(usr.get("negocio_id", 0) or 0) == int(negocio_id)
            and int(usr.get("profissional_id", 0) or 0) == int(prof_id)
        )
    ]
    salvar_json(USUARIOS_FILE, usuarios)

    profs = listar_profissionais()
    novo = []
    removido = False
    for p in profs:
        if int(p.get("id", 0)) == int(prof_id) and int(p.get("negocio_id", 0)) == int(negocio_id):
            removido = True
            continue
        novo.append(p)

    salvar_profissionais(novo)
    flash("Profissional excluído ✅" if removido else "Profissional não encontrado.")
    return redirect("/painel/profissionais")