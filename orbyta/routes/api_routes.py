from datetime import datetime
from flask import Blueprint, request

from core.auth import exigir_login
from core.constants import SERVICOS_FILE
from core.json_db import carregar_json
from services.horarios_service import obter_horarios_disponiveis

api_bp = Blueprint("api", __name__)


@api_bp.get("/api/horarios-disponiveis")
def api_horarios_disponiveis():
    if not exigir_login():
        return {"times": []}

    negocio_id = int(request.args.get("negocio_id", "0"))
    barbeiro = request.args.get("barbeiro", "").strip()
    data = request.args.get("data", "").strip()
    servico_id = request.args.get("servico_id", "").strip()

    if not (negocio_id and barbeiro and data and servico_id.isdigit()):
        return {"times": []}

    servs = carregar_json(SERVICOS_FILE)
    serv = next(
        (
            s for s in servs
            if int(s.get("id", 0)) == int(servico_id)
            and int(s.get("negocio_id", 0)) == negocio_id
            and s.get("ativo", True)
        ),
        None
    )

    if not serv:
        return {"times": []}

    try:
        datetime.strptime(data, "%Y-%m-%d").date()
    except Exception:
        return {"times": []}

    livres = obter_horarios_disponiveis(negocio_id, barbeiro, data, int(servico_id))
    return {"times": livres}