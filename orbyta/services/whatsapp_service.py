import os
import re
from datetime import datetime
from urllib.parse import quote

import requests

DEFAULT_REMINDER_TEMPLATE = (
    "Olá {nome}! Aqui é da {negocio}. "
    "Faltam cerca de 45 minutos para o seu atendimento de {servico} em {data} às {horario} com {profissional}. "
    "Se precisar falar com a loja, chame em {whatsapp_dono}."
)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def normalizar_telefone_e164(telefone: str) -> str | None:
    digits = _somente_digitos(telefone)
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]

    if not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits

    if len(digits) < 12 or len(digits) > 13:
        return None

    return f"+{digits}"


def telefone_valido_br(telefone: str) -> bool:
    return normalizar_telefone_e164(telefone) is not None


def formatar_data_br(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso or "", "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_iso or ""


def numero_whatsapp_negocio(negocio: dict | None) -> str:
    negocio = negocio or {}
    return (negocio.get("whatsapp_numero_envio") or negocio.get("whatsapp") or "").strip()


def gerar_link_whatsapp(telefone: str, mensagem: str = "") -> str:
    numero = normalizar_telefone_e164(telefone)
    if not numero:
        return ""

    numero_sem_formatacao = _somente_digitos(numero)
    texto = (mensagem or "").strip()
    if texto:
        return f"https://wa.me/{numero_sem_formatacao}?text={quote(texto)}"
    return f"https://wa.me/{numero_sem_formatacao}"


def renderizar_template_lembrete(template: str, agendamento: dict, negocio: dict) -> str:
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    token = agendamento.get("confirmacao_token") or ""
    codigo_curto = agendamento.get("confirmacao_codigo") or ""
    mensagem_base = (template or "").strip() or DEFAULT_REMINDER_TEMPLATE
    whatsapp_dono = numero_whatsapp_negocio(negocio)
    ja_confirmado = (agendamento.get("status_confirmacao") or "").strip().lower() == "confirmado"

    # Usa código curto se disponível, senão usa token completo
    param_confirmar = codigo_curto or token
    param_cancelar = codigo_curto or token

    if not ja_confirmado and "{link_confirmar}" not in mensagem_base and "{link_cancelar}" not in mensagem_base:
        mensagem_base += "\n\nConfirmar: {link_confirmar}\nCancelar: {link_cancelar}"

    valores = _SafeDict({
        "nome": agendamento.get("nome") or "Cliente",
        "negocio": negocio.get("nome") or "seu atendimento",
        "data": formatar_data_br(agendamento.get("data") or ""),
        "horario": agendamento.get("horario") or "",
        "servico": agendamento.get("servico") or "Serviço",
        "profissional": agendamento.get("barbeiro") or "profissional",
        "telefone": agendamento.get("telefone") or "",
        "whatsapp_dono": whatsapp_dono,
        "link_confirmar": f"{base_url}/a/c/{param_confirmar}" if param_confirmar else base_url,
        "link_cancelar": f"{base_url}/a/x/{param_cancelar}" if param_cancelar else base_url,
    })

    return mensagem_base.format_map(valores)


def send_whatsapp_message(telefone: str, mensagem: str, negocio: dict | None = None):
    provider = (os.getenv("WHATSAPP_PROVIDER", "none") or "none").strip().lower()
    numero = normalizar_telefone_e164(telefone)
    numero_negocio = numero_whatsapp_negocio(negocio)
    if not numero:
        return False, "Número de telefone inválido"

    if provider in {"", "none"}:
        return False, "Provider de WhatsApp não configurado"

    if provider == "twilio":
        sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_number = (os.getenv("TWILIO_WHATSAPP_FROM", "").strip() or numero_negocio)

        if not all([sid, token, from_number]):
            return False, "Credenciais Twilio não configuradas"

        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={
                "From": from_number,
                "To": f"whatsapp:{numero}",
                "Body": mensagem,
            },
            timeout=20,
        )

        if response.status_code >= 400:
            return False, response.text
        return True, "Mensagem enviada via Twilio"

    if provider == "webhook":
        webhook_url = os.getenv("WHATSAPP_WEBHOOK_URL", "").strip()
        webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "").strip()

        if not webhook_url:
            return False, "WHATSAPP_WEBHOOK_URL não configurada"

        headers = {"Content-Type": "application/json"}
        if webhook_token:
            headers["Authorization"] = f"Bearer {webhook_token}"

        payload = {
            "to": numero,
            "channel": "whatsapp",
            "message": mensagem,
        }

        numero_envio = normalizar_telefone_e164(numero_negocio)
        if numero_envio:
            payload["from"] = numero_envio
            payload["sender"] = numero_envio
            payload["business_phone"] = numero_envio

        response = requests.post(
            webhook_url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        if response.status_code >= 400:
            return False, response.text
        return True, "Mensagem enviada via webhook"

    return False, f"Provider '{provider}' não suportado"
