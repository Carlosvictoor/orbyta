from datetime import datetime, timedelta
from urllib.parse import unquote

from flask import Blueprint, render_template, request, redirect, flash

from core.json_db import carregar_json, salvar_json
from core.auth import exigir_admin
from core.constants import HORARIOS_FILE, AGENDAMENTOS_FILE, FINANCEIRO_FILE
from core.security import hash_senha, senha_forte

from services.negocios_service import listar_negocios, salvar_negocios, get_negocio
from services.profissionais_service import listar_profissionais, salvar_profissionais
from services.servicos_service import listar_servicos, salvar_servicos
from services.usuarios_service import listar_usuarios, salvar_usuarios

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
def admin():
    if not exigir_admin():
        return redirect("/login")

    negocios = listar_negocios()
    usuarios = listar_usuarios()
    donos = [u for u in usuarios if u.get("tipo") == "dono"]

    return render_template("admin.html", negocios=negocios, donos=donos)


@admin_bp.route("/admin/criar_negocio", methods=["POST"])
def admin_criar_negocio():
    if not exigir_admin():
        return redirect("/login")

    tipo = request.form.get("tipo", "").strip()
    nome = request.form.get("nome", "").strip()
    cidade = request.form.get("cidade", "").strip()
    bairro = request.form.get("bairro", "").strip()
    endereco = request.form.get("endereco", "").strip()
    whatsapp = request.form.get("whatsapp", "").strip()

    if not all([tipo, nome, cidade, bairro, endereco, whatsapp]):
        flash("Preencha todos os campos do negócio.")
        return redirect("/admin")

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
    flash(f"Negócio criado com sucesso! ✅ (ID {novo_id})")
    return redirect("/admin")


@admin_bp.route("/admin/criar_dono", methods=["POST"])
def admin_criar_dono():
    if not exigir_admin():
        return redirect("/login")

    email = request.form["email"].strip().lower()
    senha = request.form["senha"].strip()
    negocio_id = request.form["negocio_id"].strip()

    if not senha_forte(senha):
        flash("A senha do dono precisa ter pelo menos 6 caracteres.")
        return redirect("/admin")

    if not negocio_id.isdigit():
        flash("Selecione um negócio válido.")
        return redirect("/admin")

    negocio_id = int(negocio_id)

    if not get_negocio(negocio_id):
        flash("Negócio não encontrado.")
        return redirect("/admin")

    usuarios = listar_usuarios()
    for u in usuarios:
        if u.get("email") == email:
            flash("Esse email já existe!")
            return redirect("/admin")

    usuarios.append({
        "email": email,
        "senha": hash_senha(senha),
        "tipo": "dono",
        "negocio_id": negocio_id,
        "assinatura_status": "trial",
        "trial_ate": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "mp_subscription_id": None,
        "mp_pix_payment_id": None
    })

    salvar_usuarios(usuarios)
    flash("Dono criado com 7 dias grátis e vinculado ao negócio ✅")
    return redirect("/admin")


@admin_bp.route("/admin/excluir_dono/<path:email>")
def admin_excluir_dono(email):
    if not exigir_admin():
        return redirect("/login")

    email = unquote(email).strip().lower()

    usuarios = listar_usuarios()
    alvo = next((u for u in usuarios if u.get("email", "").lower() == email), None)

    if not alvo:
        flash("Dono não encontrado.")
        return redirect("/admin")

    if alvo.get("tipo") != "dono":
        flash("Esse usuário não é dono.")
        return redirect("/admin")

    usuarios = [u for u in usuarios if u.get("email", "").lower() != email]
    salvar_usuarios(usuarios)

    flash("Dono excluído ✅")
    return redirect("/admin")


@admin_bp.route("/admin/excluir_negocio/<int:negocio_id>")
def admin_excluir_negocio(negocio_id):
    if not exigir_admin():
        return redirect("/login")

    negocios = listar_negocios()
    existe = any(int(n.get("id", 0)) == int(negocio_id) for n in negocios)
    if not existe:
        flash("Negócio não encontrado.")
        return redirect("/admin")

    negocios = [n for n in negocios if int(n.get("id", 0)) != int(negocio_id)]
    salvar_negocios(negocios)

    profs = listar_profissionais()
    profs_ids = {int(p.get("id", 0)) for p in profs if int(p.get("negocio_id", 0)) == int(negocio_id)}
    profs = [p for p in profs if int(p.get("negocio_id", 0)) != int(negocio_id)]
    salvar_profissionais(profs)

    servs = listar_servicos()
    servs = [s for s in servs if int(s.get("negocio_id", 0)) != int(negocio_id)]
    salvar_servicos(servs)

    hs = carregar_json(HORARIOS_FILE)
    hs = [h for h in hs if int(h.get("negocio_id", 0)) != int(negocio_id)]
    salvar_json(HORARIOS_FILE, hs)

    ag = carregar_json(AGENDAMENTOS_FILE)
    ag = [a for a in ag if int(a.get("negocio_id", 0)) != int(negocio_id)]
    salvar_json(AGENDAMENTOS_FILE, ag)

    fin = carregar_json(FINANCEIRO_FILE)
    fin = [f for f in fin if int(f.get("negocio_id", 0)) != int(negocio_id)]
    salvar_json(FINANCEIRO_FILE, fin)

    usuarios = listar_usuarios()
    novo_usuarios = []
    for u in usuarios:
        if u.get("tipo") == "funcionario" and int(u.get("negocio_id", 0) or 0) == int(negocio_id):
            continue

        if u.get("tipo") == "dono" and int(u.get("negocio_id", 0) or 0) == int(negocio_id):
            u["tipo"] = "cliente"
            u["negocio_id"] = None
            u["profissional_id"] = None
            u["assinatura_status"] = None
            u["trial_ate"] = None
            u["mp_subscription_id"] = None
            u["mp_pix_payment_id"] = None

        if int(u.get("profissional_id", 0) or 0) in profs_ids:
            u["profissional_id"] = None

        novo_usuarios.append(u)

    salvar_usuarios(novo_usuarios)

    flash(f"Negócio {negocio_id} excluído ✅ (dados vinculados limpos)")
    return redirect("/admin")