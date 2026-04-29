import uuid
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, session, flash

from core.auth import exigir_login, exigir_cliente, usuario_atual
from core.constants import AGENDAMENTOS_FILE, SERVICOS_FILE, PROFISSIONAIS_FILE, obter_plano_config
from core.helpers import SLOTS_PADRAO_30, extrair_codigo_curto_do_uuid
from core.json_db import carregar_json, salvar_json

from services.negocios_service import get_negocio, listar_negocios, salvar_negocios
from services.profissionais_service import profissionais_do_negocio, get_profissional_por_nome, profissional_atende_servico
from services.servicos_service import servicos_do_negocio, agrupar_servicos_por_categoria, get_servico
from services.horarios_service import obter_horarios_disponiveis, obter_horarios_globais
from services.usuarios_service import atualizar_usuario
from services.whatsapp_service import telefone_valido_br

cliente_bp = Blueprint("cliente", __name__)


@cliente_bp.route("/cliente")
def cliente_painel():
    if not exigir_login():
        return redirect("/login")
    if not exigir_cliente():
        return redirect("/")

    email = session.get("usuario")

    ag = carregar_json(AGENDAMENTOS_FILE)
    profs = carregar_json(PROFISSIONAIS_FILE)

    meus = [a for a in ag if a.get("cliente") == email]
    meus.sort(key=lambda x: (x.get("data", ""), x.get("horario", "")))

    prof_map = {p.get("nome"): p for p in profs}
    for a in meus:
        a["status_confirmacao"] = a.get("status_confirmacao") or ("pendente" if a.get("telefone") else "sem_whatsapp")
        negocio_nome = "—"
        if a.get("negocio_id"):
            n = get_negocio(a.get("negocio_id"))
            if n:
                negocio_nome = n.get("nome")
        else:
            p = prof_map.get(a.get("barbeiro"))
            if p and p.get("negocio_id"):
                n = get_negocio(p.get("negocio_id"))
                if n:
                    negocio_nome = n.get("nome")
                    a["negocio_id"] = p.get("negocio_id")
        a["negocio_nome"] = negocio_nome

    return render_template("cliente.html", meus=meus)


@cliente_bp.route("/agenda/<int:negocio_id>", methods=["GET", "POST"])
def agenda(negocio_id):
    if not exigir_login():
        return redirect("/login")

    u = usuario_atual() or {}

    negocio = get_negocio(negocio_id)
    if not negocio:
        return "Negócio não encontrado", 404

    profs = profissionais_do_negocio(negocio_id)
    servs = servicos_do_negocio(negocio_id)
    servicos_categoria = agrupar_servicos_por_categoria(servs)

    horarios_lista = obter_horarios_globais(negocio_id)
    horarios_configurados = bool(horarios_lista)
    servico_preselecionado = request.values.get("servico_id", "").strip()

    if request.method == "POST":
        nome = request.form["nome"].strip()
        telefone = request.form.get("telefone", "").strip()
        data = request.form["data"].strip()
        horario = request.form["horario"].strip()
        barbeiro = request.form["barbeiro"].strip()
        servico_id = request.form["servico_id"].strip()

        if not servs or not profs:
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Esse estabelecimento ainda não cadastrou serviços e profissionais para liberar a agenda.")
        if not horarios_configurados:
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="O dono do estabelecimento ainda não configurou os horários de atendimento.")
        if telefone and not telefone_valido_br(telefone):
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Informe um número de WhatsApp válido com DDD.")
        if horario not in SLOTS_PADRAO_30:
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Horário inválido.")
        if not servico_id.isdigit():
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Selecione um serviço válido.")

        servico_escolhido = get_servico(negocio_id, int(servico_id))
        profissional = get_profissional_por_nome(negocio_id, barbeiro)
        if profissional and servico_escolhido and not profissional_atende_servico(profissional, servico_escolhido):
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Esse profissional não atende essa área/serviço.")

        livres = obter_horarios_disponiveis(negocio_id, barbeiro, data, int(servico_id))
        if horario not in livres:
            return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Esse horário não está disponível para esse barbeiro ou já foi reservado.")

        profissional_id = int(profissional.get("id", 0)) if profissional else None

        ag = carregar_json(AGENDAMENTOS_FILE)
        for a in ag:
            if (a.get("status_confirmacao") or "").strip().lower() == "cancelado":
                continue

            mesma_pessoa = False

            a_prof_id = int(a.get("profissional_id", 0) or 0)
            if profissional_id and a_prof_id == profissional_id:
                mesma_pessoa = True
            elif not profissional_id and (a.get("barbeiro") or "").strip().lower() == barbeiro.lower():
                mesma_pessoa = True

            if (
                int(a.get("negocio_id", 0)) == int(negocio_id)
                and a.get("data") == data
                and a.get("horario") == horario
                and mesma_pessoa
            ):
                return render_template("agenda.html", negocio=negocio, profs=profs, servs=servs, servicos_categoria=servicos_categoria, servico_preselecionado=servico_preselecionado, horarios_configurados=horarios_configurados, horarios_lista=horarios_lista, telefone_padrao=telefone, erro="Horário já ocupado para esse barbeiro!")

        servico_nome = ""
        for s in carregar_json(SERVICOS_FILE):
            if int(s.get("id", 0)) == int(servico_id):
                servico_nome = s.get("nome", "")
                break

        novo_id = max([int(a.get("id", 0) or 0) for a in ag], default=0) + 1

        token = uuid.uuid4().hex
        novo_agendamento = {
            "id": novo_id,
            "negocio_id": negocio_id,
            "nome": nome,
            "cliente": session["usuario"],
            "telefone": telefone,
            "data": data,
            "horario": horario,
            "barbeiro": barbeiro,
            "servico_id": int(servico_id),
            "servico": servico_nome,
            "status_confirmacao": "pendente" if telefone else "sem_whatsapp",
            "confirmacao_token": token,
            "confirmacao_codigo": extrair_codigo_curto_do_uuid(token),
            "lembrete_whatsapp_status": "aguardando" if telefone else "não configurado",
            "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if profissional_id:
            novo_agendamento["profissional_id"] = profissional_id

        ag.append(novo_agendamento)
        salvar_json(AGENDAMENTOS_FILE, ag)

        if telefone:
            atualizar_usuario(session["usuario"], {"telefone": telefone})
            flash("Agendamento concluído. Se o WhatsApp automático estiver ativo, você receberá um lembrete 45 minutos antes.")
        else:
            flash("Agendamento concluído com sucesso.")
        return redirect(f"/agenda/{negocio_id}")

    return render_template(
        "agenda.html",
        negocio=negocio,
        profs=profs,
        servs=servs,
        servicos_categoria=servicos_categoria,
        telefone_padrao=u.get("telefone", ""),
        servico_preselecionado=servico_preselecionado,
        horarios_configurados=horarios_configurados,
        horarios_lista=horarios_lista,
    )

@cliente_bp.route("/quero-ser-dono", methods=["GET", "POST"])
def quero_ser_dono():
    if not exigir_login():
        flash("Faça login para criar seu negócio.")
        return redirect("/login")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    if u.get("tipo") == "admin":
        return redirect("/admin")
    if u.get("tipo") == "dono":
        return redirect("/painel")

    if request.method == "POST":
        tipo = request.form.get("tipo", "").strip()
        nome = request.form.get("nome", "").strip()
        cidade = request.form.get("cidade", "").strip()
        bairro = request.form.get("bairro", "").strip()
        endereco = request.form.get("endereco", "").strip()
        whatsapp = request.form.get("whatsapp", "").strip()

        if not all([tipo, nome, cidade, bairro, endereco, whatsapp]):
            flash("Preencha todos os campos do seu negócio.")
            return redirect("/quero-ser-dono")

        negocios = listar_negocios()
        novo_id = max([int(n.get("id", 0)) for n in negocios], default=0) + 1

        negocios.append({
            "id": novo_id,
            "tipo": tipo,
            "nome": nome,
            "cidade": cidade,
            "bairro": bairro,
            "endereco": endereco,
            "whatsapp": whatsapp
        })

        salvar_negocios(negocios)

        plano_inicial = obter_plano_config("pro")
        atualizar_usuario(u["email"], {
            "tipo": "dono",
            "negocio_id": novo_id,
            "assinatura_status": "trial",
            "trial_ate": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "mp_subscription_id": None,
            "mp_pix_payment_id": None,
            "plano_slug": plano_inicial["slug"],
            "plano_nome": plano_inicial["nome"],
            "limite_funcionarios": plano_inicial.get("limite_funcionarios"),
            "valor_plano": plano_inicial["valor"],
        })

        session["tipo"] = "dono"
        session["negocio_id"] = novo_id

        flash("Negócio criado com sucesso. Você recebeu 7 dias de teste e já pode escolher a forma de pagamento.")
        return redirect("/assinar")

    return render_template("quero_ser_dono.html")


@cliente_bp.route("/agendamento/confirmar/<token>")
@cliente_bp.route("/a/c/<token>")
def confirmar_agendamento(token):
    ag = carregar_json(AGENDAMENTOS_FILE)
    
    # Busca por token completo OU por código curto (6 primeiros caracteres)
    alvo = next(
        (a for a in ag if a.get("confirmacao_token") == token or 
                          a.get("confirmacao_codigo") == token.upper()),
        None
    )

    if not alvo:
        return render_template(
            "confirmacao_agendamento.html",
            ok=False,
            titulo="Link inválido",
            mensagem="Esse link não foi encontrado ou já expirou.",
            agendamento=None,
            negocio=None,
        )

    ja_estava_confirmado = (alvo.get("status_confirmacao") or "").strip().lower() == "confirmado"
    alvo["status_confirmacao"] = "confirmado"
    alvo["confirmado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    salvar_json(AGENDAMENTOS_FILE, ag)

    if ja_estava_confirmado:
        flash("Seu agendamento já estava confirmado.")
    else:
        flash("Agendamento confirmado com sucesso.")
    return redirect("/")


@cliente_bp.route("/agendamento/cancelar/<token>")
@cliente_bp.route("/a/x/<token>")
def cancelar_agendamento(token):
    ag = carregar_json(AGENDAMENTOS_FILE)
    
    # Busca por token completo OU por código curto (6 primeiros caracteres)
    alvo = next(
        (a for a in ag if a.get("confirmacao_token") == token or 
                          a.get("confirmacao_codigo") == token.upper()),
        None
    )

    if not alvo:
        return render_template(
            "confirmacao_agendamento.html",
            ok=False,
            titulo="Link inválido",
            mensagem="Esse link não foi encontrado ou já expirou.",
            agendamento=None,
            negocio=None,
        )

    alvo["status_confirmacao"] = "cancelado"
    alvo["cancelado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    salvar_json(AGENDAMENTOS_FILE, ag)

    return render_template(
        "confirmacao_agendamento.html",
        ok=True,
        titulo="Agendamento cancelado",
        mensagem="Tudo certo. Seu horário foi cancelado e liberado no sistema.",
        agendamento=alvo,
        negocio=get_negocio(alvo.get("negocio_id")),
    )