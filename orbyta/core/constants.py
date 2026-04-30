import os

from core.config import load_env_file

load_env_file()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DEFAULT_DB_FILE = "/app/data/database.db"

# Permite usar um volume persistente em produção (Render/Railway/VPS).
ENV_DATA_DIR = os.getenv("ORBYTA_DATA_DIR", "").strip()
ENV_DB_FILE = os.getenv("ORBYTA_DB_FILE", "").strip()

# Prioriza a pasta data configurada no ambiente; se não existir, usa a raiz do workspace e depois a local do app.
ROOT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOCAL_DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_DIR = ENV_DATA_DIR or (ROOT_DATA_DIR if os.path.isdir(ROOT_DATA_DIR) else LOCAL_DATA_DIR)
DB_FILE = ENV_DB_FILE or (DEFAULT_DB_FILE if os.path.isdir("/app/data") else os.path.join(DATA_DIR, "database.db"))

USUARIOS_FILE = os.path.join(DATA_DIR, "usuarios.json")
AGENDAMENTOS_FILE = os.path.join(DATA_DIR, "agendamentos.json")
BARBEIROS_FILE = os.path.join(DATA_DIR, "barbeiros.json")
NEGOCIOS_FILE = os.path.join(DATA_DIR, "negocios.json")
PROFISSIONAIS_FILE = os.path.join(DATA_DIR, "profissionais.json")
SERVICOS_FILE = os.path.join(DATA_DIR, "servicos.json")
HORARIOS_FILE = os.path.join(DATA_DIR, "horarios.json")
FINANCEIRO_FILE = os.path.join(DATA_DIR, "financeiro.json")
RANKING_RESET_FILE = os.path.join(DATA_DIR, "ranking_reset.json")

JSON_FILES = [
    USUARIOS_FILE,
    AGENDAMENTOS_FILE,
    BARBEIROS_FILE,
    NEGOCIOS_FILE,
    PROFISSIONAIS_FILE,
    SERVICOS_FILE,
    HORARIOS_FILE,
    FINANCEIRO_FILE,
    RANKING_RESET_FILE,
]

APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "").strip()
MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "").strip()
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "").strip()
MP_STATEMENT_DESCRIPTOR = os.getenv("MP_STATEMENT_DESCRIPTOR", "ORBYTA").strip()
MP_API = "https://api.mercadopago.com"

PLANO_PADRAO = "pro"
PLANOS_CONFIG = {
    "solo": {
        "nome": "Orbyta Solo",
        "valor": 14.99,
        "limite_funcionarios": 1,
        "descricao": "Perfeito para autônomos e pequenos negócios com até 1 funcionário.",
    },
    "pro": {
        "nome": "Orbyta Pro",
        "valor": 29.99,
        "limite_funcionarios": None,
        "descricao": "Para negócios com equipe e crescimento sem limite de funcionários.",
    },
    "copiloto": {
        "nome": "Orbyta Copiloto",
        "valor": 59.99,
        "limite_funcionarios": None,
        "descricao": "Tudo do Pro mais notificações automáticas, lembretes e suporte prioritário.",
    },
}

PLANO_VALOR = PLANOS_CONFIG[PLANO_PADRAO]["valor"]
PLANO_MOEDA = "BRL"


def obter_plano_config(slug=None):
    chave = str(slug or PLANO_PADRAO).strip().lower()
    plano = dict(PLANOS_CONFIG.get(chave, PLANOS_CONFIG[PLANO_PADRAO]))
    plano["slug"] = chave if chave in PLANOS_CONFIG else PLANO_PADRAO
    return plano
