import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, flash, current_app

from core.auth import exigir_funcionario, usuario_atual
from core.constants import AGENDAMENTOS_FILE, FINANCEIRO_FILE
from core.json_db import carregar_json, salvar_json

from core.helpers import clamp_pct, salvar_imagem_upload
from services.negocios_service import get_negocio
from services.profissionais_service import get_profissional, listar_profissionais, salvar_profissionais
from services.servicos_service import servico_preco, servico_nome_by_id, servicos_do_negocio
from services.horarios_service import obter_horarios_disponiveis, obter_horarios_globais
from services.profissionais_service import comissao_pct_profissional
from services.financeiro_service import calcular_valores_comissao
from services.whatsapp_service import normalizar_telefone_e164, telefone_valido_br

funcionario_bp = Blueprint("funcionario", __name__)


def _whatsapp_link(telefone: str) -> str:
    numero = normalizar_telefone_e164(telefone or "")
    return f"https://wa.me/{numero}" if numero else ""


@funcionario_bp.route("/painel-funcionario")
def painel_funcionario():
    if not exigir_funcionario():
        return redirect("/login")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    negocio_id = int(u.get("negocio_id") or 0)
    profissional_id = int(u.get("profissional_id") or 0)

    if not negocio_id or not profissional_id:
        flash("Sua conta de funcionário não está vinculada corretamente.")
        return redirect("/logout")

    negocio = get_negocio(negocio_id)
    profissional = get_profissional(profissional_id)

    if not negocio or not profissional:
        flash("Funcionário ou negócio não encontrado.")
        return redirect("/logout")

    servs = servicos_do_negocio(negocio_id)
    horarios_configurados = obter_horarios_globais(negocio_id)
    data_hoje = datetime.now().strftime("%Y-%m-%d")

    mes = request.args.get("mes", "").strip()
    if not mes:
        mes = datetime.now().strftime("%Y-%m")

    nome_profissional = (profissional.get("nome") or "").strip().lower()
    comissao_pct = clamp_pct(profissional.get("comissao_pct", 50), 50)

    ag_all = carregar_json(AGENDAMENTOS_FILE)
    meus_agendamentos = []
    faturamento_bruto = 0.0

    for a in ag_all:
        if int(a.get("negocio_id", 0)) != negocio_id:
            continue
        if a.get("data", "")[:7] != mes:
            continue

        ag_prof_id = int(a.get("profissional_id", 0) or 0)
        ag_prof_nome = (a.get("barbeiro") or "").strip().lower()

        pertence_ao_funcionario = False
        if ag_prof_id and ag_prof_id == profissional_id:
            pertence_ao_funcionario = True
        elif ag_prof_nome and ag_prof_nome == nome_profissional:
            pertence_ao_funcionario = True

        if not pertence_ao_funcionario:
            continue

        sid = int(a.get("servico_id", 0) or 0)
        valor = servico_preco(negocio_id, sid)
        faturamento_bruto += valor

        pct_item = comissao_pct_profissional(negocio_id, profissional_id, nome_profissional)
        _, valor_profissional_item, valor_salao_item = calcular_valores_comissao(valor, pct_item)

        telefone = a.get("telefone", "")
        meus_agendamentos.append({
            "data": a.get("data", ""),
            "horario": a.get("horario", ""),
            "cliente": a.get("nome", ""),
            "telefone": telefone,
            "whatsapp_link": _whatsapp_link(telefone),
            "servico": a.get("servico") or servico_nome_by_id(negocio_id, sid) or "Serviço",
            "valor": round(valor, 2),
            "comissao_pct": pct_item,
            "valor_profissional": round(valor_profissional_item, 2),
            "valor_salao": round(valor_salao_item, 2)
        })

    meus_agendamentos.sort(key=lambda x: (x.get("data", ""), x.get("horario", "")), reverse=True)

    _, repasse_profissional, parte_salao = calcular_valores_comissao(faturamento_bruto, comissao_pct)

    fin_all = carregar_json(FINANCEIRO_FILE)
    minhas_saidas = []
    saidas = 0.0

    for f in fin_all:
        if int(f.get("negocio_id", 0)) != negocio_id:
            continue
        if f.get("data", "")[:7] != mes:
            continue
        if int(f.get("profissional_id", 0) or 0) != profissional_id:
            continue
        if f.get("tipo") != "saida":
            continue

        valor = float(f.get("valor", 0) or 0)
        saidas += valor
        minhas_saidas.append(f)

    minhas_saidas.sort(key=lambda x: x.get("data", ""), reverse=True)

    saldo_final = repasse_profissional - saidas

    return render_template(
        "painel_funcionario.html",
        negocio=negocio,
        profissional=profissional,
        mes=mes,
        atendimentos=meus_agendamentos,
        minhas_saidas=minhas_saidas,
        faturamento_bruto=round(faturamento_bruto, 2),
        comissao_pct=round(comissao_pct, 2),
        repasse_profissional=round(repasse_profissional, 2),
        parte_salao=round(parte_salao, 2),
        saidas=round(saidas, 2),
        saldo_final=round(saldo_final, 2),
        qtd_atendimentos=len(meus_agendamentos),
        servs=servs,
        horarios_configurados=horarios_configurados,
        data_hoje=data_hoje,
    )


@funcionario_bp.route("/painel-funcionario/agendar-manual", methods=["POST"])
def painel_funcionario_agendar_manual():
    if not exigir_funcionario():
        return redirect("/login")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    negocio_id = int(u.get("negocio_id") or 0)
    profissional_id = int(u.get("profissional_id") or 0)
    if not negocio_id or not profissional_id:
        flash("Sua conta de funcionário não está vinculada corretamente.")
        return redirect("/logout")

    profissional = get_profissional(profissional_id)
    if not profissional or int(profissional.get("negocio_id", 0)) != negocio_id:
        flash("Profissional não encontrado.")
        return redirect("/logout")

    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    data = request.form.get("data", "").strip()
    horario = request.form.get("horario", "").strip()
    servico_id = request.form.get("servico_id", "").strip()
    mes = request.args.get("mes", "").strip() or (data[:7] if data else datetime.now().strftime("%Y-%m"))

    if not nome:
        flash("Informe o nome do cliente.")
        return redirect(f"/painel-funcionario?mes={mes}")

    if telefone and not telefone_valido_br(telefone):
        flash("Informe um telefone/WhatsApp válido com DDD ou deixe em branco.")
        return redirect(f"/painel-funcionario?mes={mes}")

    try:
        datetime.strptime(data, "%Y-%m-%d")
    except Exception:
        flash("Data inválida.")
        return redirect(f"/painel-funcionario?mes={mes}")

    if not servico_id.isdigit():
        flash("Selecione um serviço válido.")
        return redirect(f"/painel-funcionario?mes={mes}")

    horarios_livres = obter_horarios_disponiveis(negocio_id, profissional.get("nome", ""), data, int(servico_id))
    if horario not in horarios_livres:
        flash("Esse horário não está disponível para você. Escolha outro horário.")
        return redirect(f"/painel-funcionario?mes={mes}")

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
        "profissional_id": profissional_id,
        "servico_id": int(servico_id),
        "servico": servico_nome,
        "status_confirmacao": "pendente" if telefone else "sem_whatsapp",
        "confirmacao_token": uuid.uuid4().hex,
        "lembrete_whatsapp_status": "aguardando" if telefone else "não configurado",
        "origem": "manual_funcionario",
        "criado_por": u.get("email") or u.get("usuario") or "funcionario",
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    salvar_json(AGENDAMENTOS_FILE, ag)

    flash(f"Agendamento manual salvo ✅ {nome} • {data} às {horario}")
    return redirect(f"/painel-funcionario?mes={mes}")


@funcionario_bp.route("/painel-funcionario/perfil", methods=["POST"])
def painel_funcionario_perfil():
    if not exigir_funcionario():
        return redirect("/login")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    negocio_id = int(u.get("negocio_id") or 0)
    profissional_id = int(u.get("profissional_id") or 0)
    if not negocio_id or not profissional_id:
        flash("Seu perfil não está vinculado corretamente.")
        return redirect("/logout")

    foto_url = request.form.get("foto_url", "").strip()
    descricao = request.form.get("descricao", "").strip()
    remover_foto = request.form.get("remover_foto") == "1"
    mes = request.args.get("mes", "").strip() or datetime.now().strftime("%Y-%m")

    foto_upload, erro_upload = salvar_imagem_upload(
        request.files.get("foto_arquivo"),
        current_app.static_folder,
        prefix=f"funcionario-{profissional_id}",
    )
    if erro_upload:
        flash(erro_upload)
        return redirect(f"/painel-funcionario?mes={mes}")

    profs = listar_profissionais()
    ok = False
    for p in profs:
        if int(p.get("id", 0)) == profissional_id and int(p.get("negocio_id", 0)) == negocio_id:
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
    flash("Seu perfil foi atualizado ✅" if ok else "Não foi possível atualizar seu perfil.")
    return redirect(f"/painel-funcionario?mes={mes}")