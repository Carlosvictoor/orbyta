from flask import Blueprint, render_template, request, redirect, session, flash

from core.security import (
    formatar_tempo_bloqueio,
    hash_senha,
    limpar_falhas_login,
    login_bloqueado,
    registrar_falha_login,
    senha_forte,
    senha_precisa_migrar,
    verificar_senha,
)
from services.usuarios_service import listar_usuarios, salvar_usuarios, atualizar_usuario
from services.whatsapp_service import normalizar_telefone_e164, telefone_valido_br

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        telefone = request.form.get("telefone", "").strip()
        senha = request.form["senha"]

        if not senha_forte(senha):
            flash("A senha precisa ter pelo menos 6 caracteres.")
            return redirect("/cadastro")

        if telefone and not telefone_valido_br(telefone):
            flash("Informe um telefone/WhatsApp válido com DDD.")
            return redirect("/cadastro")

        telefone_normalizado = normalizar_telefone_e164(telefone) or ""

        usuarios = listar_usuarios()
        for u in usuarios:
            if u.get("email") == email:
                flash("Esse email já está cadastrado!")
                return redirect("/cadastro")

            telefone_existente = normalizar_telefone_e164(u.get("telefone", "") or "") or ""
            if telefone_normalizado and telefone_existente == telefone_normalizado:
                flash("Esse telefone já está cadastrado!")
                return redirect("/cadastro")

        usuarios.append({
            "email": email,
            "telefone": telefone,
            "senha": hash_senha(senha),
            "tipo": "cliente",
            "negocio_id": None,
            "assinatura_status": None,
            "trial_ate": None,
            "mp_subscription_id": None,
            "mp_pix_payment_id": None
        })
        salvar_usuarios(usuarios)

        flash("Cadastro realizado!")
        return redirect("/login")

    return render_template("cadastro.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identificador = request.form["email"].strip()
        email = identificador.lower()
        telefone_login = normalizar_telefone_e164(identificador) or ""
        senha = request.form["senha"]
        ip_origem = (request.headers.get("X-Forwarded-For", request.remote_addr or "desconhecido").split(",")[0]).strip()

        bloqueado_por = login_bloqueado(ip_origem, email)
        if bloqueado_por > 0:
            flash(f"Muitas tentativas de login. Tente novamente em {formatar_tempo_bloqueio(bloqueado_por)}.")
            return redirect("/login")

        usuarios = listar_usuarios()

        for u in usuarios:
            email_cadastrado = (u.get("email") or "").strip().lower()
            telefone_cadastrado = normalizar_telefone_e164(u.get("telefone", "") or "") or ""
            senha_cadastrada = u.get("senha") or ""
            login_ok = email_cadastrado == email or (telefone_login and telefone_cadastrado == telefone_login)

            if login_ok and verificar_senha(senha, senha_cadastrada):
                limpar_falhas_login(ip_origem, email)

                if senha_precisa_migrar(senha_cadastrada):
                    atualizar_usuario(email_cadastrado, {"senha": hash_senha(senha)})

                session.clear()
                session["usuario"] = email_cadastrado
                session["tipo"] = u.get("tipo")
                session["negocio_id"] = u.get("negocio_id")
                session["profissional_id"] = u.get("profissional_id")

                if u.get("tipo") == "admin":
                    return redirect("/admin")
                if u.get("tipo") == "dono":
                    return redirect("/painel")
                if u.get("tipo") == "funcionario":
                    return redirect("/painel-funcionario")
                if u.get("tipo") == "cliente":
                    return redirect("/negocios")

                return redirect("/")

        status = registrar_falha_login(ip_origem, email)
        if status["bloqueado_por"] > 0:
            flash(f"Login bloqueado temporariamente por segurança. Tente novamente em {formatar_tempo_bloqueio(status['bloqueado_por'])}.")
        else:
            flash("Erro: email ou senha inválidos!")
        return redirect("/login")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")