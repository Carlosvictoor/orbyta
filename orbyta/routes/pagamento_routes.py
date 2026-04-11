import uuid
from datetime import datetime

import requests
from flask import Blueprint, render_template, redirect, request, flash

from core.auth import exigir_login, usuario_atual
from core.constants import (
    APP_BASE_URL,
    MP_ACCESS_TOKEN,
    MP_API,
    MP_PUBLIC_KEY,
    MP_STATEMENT_DESCRIPTOR,
    PLANO_MOEDA,
    PLANO_PADRAO,
    PLANOS_CONFIG,
    obter_plano_config,
)
from services.usuarios_service import atualizar_usuario

pagamento_bp = Blueprint("pagamento", __name__)


def _app_base_url():
    base = (APP_BASE_URL or request.url_root or "http://127.0.0.1:5000").strip()
    return base.rstrip("/")


def _plano_escolhido(u: dict | None = None) -> dict:
    slug = (request.args.get("plano") or (u or {}).get("plano_slug") or PLANO_PADRAO).strip().lower()
    if slug not in PLANOS_CONFIG:
        slug = PLANO_PADRAO
    return obter_plano_config(slug)


def _status_para_local(status_raw: str) -> str:
    status = (status_raw or "").strip().lower()

    if status in {"approved", "authorized", "active"}:
        return "ativa"
    if status in {"pending", "in_process", "in_mediation", "pending_waiting_transfer", "paused"}:
        return "pendente"
    if status in {"cancelled", "canceled", "rejected", "refunded", "charged_back"}:
        return "cancelada"
    return "pendente"


def _atualizar_status_usuario(email: str, status_raw: str, extra_patch: dict | None = None) -> str:
    patch = {
        "assinatura_status": _status_para_local(status_raw),
        "ultima_verificacao_pagamento_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if patch["assinatura_status"] == "ativa":
        patch["trial_ate"] = None
    if extra_patch:
        patch.update(extra_patch)
    atualizar_usuario(email, patch)
    return patch["assinatura_status"]


def _consultar_status_no_mp(u: dict | None):
    if not u:
        return False, "Usuário não encontrado."
    if not MP_ACCESS_TOKEN:
        return False, "Configure o `MP_ACCESS_TOKEN` no arquivo .env antes de usar o pagamento."

    email = (u.get("email") or "").strip().lower()
    consultas = []

    if u.get("mp_pix_payment_id"):
        consultas.append(("pix", str(u.get("mp_pix_payment_id")), f"{MP_API}/v1/payments/{u.get('mp_pix_payment_id')}"))
    if u.get("mp_subscription_id"):
        consultas.append(("assinatura", str(u.get("mp_subscription_id")), f"{MP_API}/preapproval/{u.get('mp_subscription_id')}"))

    if not consultas:
        return False, "Nenhum pagamento anterior foi encontrado para essa conta."

    for origem, _ref, url in consultas:
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
                timeout=20,
            )
        except Exception as exc:
            return False, f"Falha ao consultar o Mercado Pago: {exc}"

        if resp.status_code >= 400:
            continue

        data = resp.json()
        status_externo = (data.get("status") or "").strip().lower()
        status_local = _atualizar_status_usuario(email, status_externo)
        return True, f"Status do {origem}: {status_local}."

    return False, "Não foi possível confirmar o status agora. Confira se a chave do Mercado Pago está correta."


@pagamento_bp.route("/assinar")
def assinar():
    from flask import session

    if not exigir_login():
        return redirect("/login")
    if session.get("tipo") != "dono":
        return redirect("/")

    u = usuario_atual()
    plano_query = (request.args.get("plano") or "").strip().lower()
    if u and plano_query in PLANOS_CONFIG:
        plano_tmp = obter_plano_config(plano_query)
        atualizar_usuario(
            u["email"],
            {
                "plano_slug": plano_tmp["slug"],
                "plano_nome": plano_tmp["nome"],
                "limite_funcionarios": plano_tmp.get("limite_funcionarios"),
                "valor_plano": plano_tmp["valor"],
            },
        )
        u = usuario_atual() or u

    plano_atual = _plano_escolhido(u)
    planos = [obter_plano_config("solo"), obter_plano_config("pro")]
    return render_template(
        "assinar.html",
        u=u,
        valor=plano_atual["valor"],
        plano_atual=plano_atual,
        planos=planos,
        token_configurado=bool(MP_ACCESS_TOKEN),
        public_key_configurada=bool(MP_PUBLIC_KEY),
    )


@pagamento_bp.route("/assinar/cartao")
def assinar_cartao():
    from flask import session

    if not exigir_login() or session.get("tipo") != "dono":
        return redirect("/login")

    if not MP_ACCESS_TOKEN:
        flash("Configure o Mercado Pago no .env para liberar o pagamento com cartão.")
        return redirect("/assinar")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    plano = _plano_escolhido(u)
    base_url = _app_base_url()
    external_reference = f"orbyta_sub:{u.get('email')}:{uuid.uuid4().hex}"

    payload = {
        "reason": f"{plano['nome']} - R$ {plano['valor']:.2f}/mês",
        "payer_email": u.get("email"),
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(plano["valor"]),
            "currency_id": PLANO_MOEDA,
        },
        "back_url": f"{base_url}/assinatura/retorno",
        "notification_url": f"{base_url}/webhook/mercadopago",
        "external_reference": external_reference,
        "status": "pending",
    }

    try:
        response = requests.post(
            f"{MP_API}/preapproval",
            headers={
                "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": uuid.uuid4().hex,
            },
            json=payload,
            timeout=20,
        )
    except Exception as exc:
        flash(f"Falha ao conectar com o Mercado Pago: {exc}")
        return redirect("/assinar")

    if response.status_code >= 400:
        flash("Erro ao iniciar a assinatura com cartão. Revise as credenciais do Mercado Pago.")
        return redirect("/assinar")

    data = response.json()
    sub_id = data.get("id")
    init_point = data.get("init_point") or data.get("sandbox_init_point")

    atualizar_usuario(
        u["email"],
        {
            "assinatura_status": _status_para_local(data.get("status") or "pending"),
            "mp_subscription_id": sub_id,
            "plano_slug": plano["slug"],
            "plano_nome": plano["nome"],
            "limite_funcionarios": plano.get("limite_funcionarios"),
            "valor_plano": plano["valor"],
        },
    )

    if not init_point:
        flash("A assinatura foi criada, mas o Mercado Pago não retornou o link de pagamento.")
        return redirect("/assinar")

    return redirect(init_point)


@pagamento_bp.route("/assinar/pix")
def assinar_pix():
    from flask import session

    if not exigir_login() or session.get("tipo") != "dono":
        return redirect("/login")

    if not MP_ACCESS_TOKEN:
        flash("Configure o Mercado Pago no .env para liberar o pagamento via Pix.")
        return redirect("/assinar")

    u = usuario_atual()
    if not u:
        return redirect("/login")

    plano = _plano_escolhido(u)
    base_url = _app_base_url()
    external_reference = f"orbyta_pix:{u.get('email')}:{uuid.uuid4().hex}"

    payload = {
        "transaction_amount": float(plano["valor"]),
        "description": f"{plano['nome']} - Mensalidade",
        "payment_method_id": "pix",
        "statement_descriptor": MP_STATEMENT_DESCRIPTOR[:13] or "ORBYTA",
        "payer": {"email": u.get("email")},
        "external_reference": external_reference,
        "notification_url": f"{base_url}/webhook/mercadopago",
    }

    try:
        response = requests.post(
            f"{MP_API}/v1/payments",
            headers={
                "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": uuid.uuid4().hex,
            },
            json=payload,
            timeout=20,
        )
    except Exception as exc:
        flash(f"Falha ao conectar com o Mercado Pago: {exc}")
        return redirect("/assinar")

    if response.status_code >= 400:
        flash("Erro ao gerar o Pix. Revise as credenciais do Mercado Pago.")
        return redirect("/assinar")

    data = response.json()
    pay_id = data.get("id")

    poi = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
    qr_code = poi.get("qr_code")
    qr_base64 = poi.get("qr_code_base64")

    atualizar_usuario(
        u["email"],
        {
            "assinatura_status": _status_para_local(data.get("status") or "pending"),
            "mp_pix_payment_id": pay_id,
            "plano_slug": plano["slug"],
            "plano_nome": plano["nome"],
            "limite_funcionarios": plano.get("limite_funcionarios"),
            "valor_plano": plano["valor"],
        },
    )

    return render_template("pix_qr.html", valor=plano["valor"], pay_id=pay_id, qr_code=qr_code, qr_base64=qr_base64, plano=plano)


@pagamento_bp.route("/assinatura/retorno")
def assinatura_retorno():
    ok, msg = _consultar_status_no_mp(usuario_atual())
    flash(msg if ok else f"Pagamento recebido. {msg}")
    return redirect("/painel")


@pagamento_bp.route("/assinatura/status")
def assinatura_status():
    if not exigir_login():
        return redirect("/login")

    ok, msg = _consultar_status_no_mp(usuario_atual())
    flash(msg if ok else msg)
    return redirect("/assinar")


@pagamento_bp.route("/webhook/mercadopago", methods=["POST", "GET"])
def webhook_mercadopago():
    if not MP_ACCESS_TOKEN:
        return ("", 200)

    payload = request.get_json(silent=True) or {}
    data = payload.get("data") or {}
    event_id = data.get("id") or payload.get("id") or request.args.get("id") or request.args.get("data.id")
    event_type = (payload.get("type") or request.args.get("type") or request.args.get("topic") or "").strip().lower()

    if not event_id:
        return ("", 200)

    urls = []
    if "preapproval" in event_type or "subscription" in event_type:
        urls.append(f"{MP_API}/preapproval/{event_id}")
    elif "payment" in event_type or not event_type:
        urls.append(f"{MP_API}/v1/payments/{event_id}")
        urls.append(f"{MP_API}/preapproval/{event_id}")

    for url in urls:
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
                timeout=20,
            )
        except Exception:
            continue
        if resp.status_code >= 400:
            continue

        info = resp.json()
        payer_email = ((info.get("payer") or {}).get("email") or info.get("payer_email") or "").strip().lower()
        status_externo = (info.get("status") or "").strip().lower()

        if payer_email:
            _atualizar_status_usuario(payer_email, status_externo)
        break

    return ("", 200)