import os
import threading
import time
from datetime import datetime

from core.constants import AGENDAMENTOS_FILE
from core.json_db import carregar_json, salvar_json
from services.negocios_service import get_negocio
from services.whatsapp_service import renderizar_template_lembrete, send_whatsapp_message

_worker_started = False
_worker_lock = threading.Lock()


def _parse_data_hora(agendamento: dict):
    try:
        return datetime.strptime(
            f"{agendamento.get('data', '')} {agendamento.get('horario', '')}",
            "%Y-%m-%d %H:%M",
        )
    except Exception:
        return None


def _parse_datetime(raw: str):
    try:
        return datetime.strptime(raw or "", "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def process_due_reminders():
    agendamentos = carregar_json(AGENDAMENTOS_FILE)
    if not agendamentos:
        return

    now = datetime.now()
    retry_seconds = int(os.getenv("WHATSAPP_RETRY_SECONDS", "300"))
    alterado = False

    for item in agendamentos:
        telefone = (item.get("telefone") or "").strip()
        token = (item.get("confirmacao_token") or "").strip()
        status = (item.get("status_confirmacao") or "").strip().lower()

        if not telefone or not token:
            continue
        if status in {"confirmado", "cancelado"}:
            continue
        if item.get("lembrete_whatsapp_enviado_em"):
            continue

        ultima_tentativa = _parse_datetime(item.get("lembrete_whatsapp_ultima_tentativa_em"))
        if ultima_tentativa and (now - ultima_tentativa).total_seconds() < retry_seconds:
            continue

        horario_agendado = _parse_data_hora(item)
        if not horario_agendado:
            continue

        faltam_minutos = (horario_agendado - now).total_seconds() / 60
        if not (0 < faltam_minutos <= 45):
            continue

        negocio = get_negocio(item.get("negocio_id"))
        if not negocio:
            continue

        ativo = str(negocio.get("whatsapp_lembrete_ativo", True)).strip().lower() not in {"0", "false", "off", "no"}
        if not ativo:
            continue

        mensagem = renderizar_template_lembrete(negocio.get("whatsapp_mensagem_template", ""), item, negocio)
        ok, detalhe = send_whatsapp_message(telefone, mensagem, negocio=negocio)

        item["lembrete_whatsapp_ultima_tentativa_em"] = now.strftime("%Y-%m-%d %H:%M:%S")
        item["lembrete_whatsapp_status"] = "enviado" if ok else "erro"
        if ok:
            item["lembrete_whatsapp_enviado_em"] = now.strftime("%Y-%m-%d %H:%M:%S")
            item["lembrete_whatsapp_erro"] = None
        else:
            item["lembrete_whatsapp_erro"] = detalhe

        alterado = True

    if alterado:
        salvar_json(AGENDAMENTOS_FILE, agendamentos)


def _worker_loop(app):
    interval = max(int(os.getenv("REMINDER_CHECK_INTERVAL", "60")), 15)

    while True:
        try:
            with app.app_context():
                process_due_reminders()
        except Exception as exc:
            print(f"[Orbyta Reminder Worker] erro: {exc}")
        time.sleep(interval)


def start_reminder_worker(app):
    global _worker_started

    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    thread = threading.Thread(
        target=_worker_loop,
        args=(app,),
        name="orbyta-reminder-worker",
        daemon=True,
    )
    thread.start()
