import os
import time

from werkzeug.security import check_password_hash, generate_password_hash

_HASH_PREFIXES = ("pbkdf2:", "scrypt:")
_LOGIN_ATTEMPTS = {}


def senha_forte(senha: str, minimo: int = 6) -> bool:
    if senha is None:
        return False
    return len(str(senha).strip()) >= minimo


def hash_senha(senha: str) -> str:
    return generate_password_hash(senha)


def senha_precisa_migrar(senha_armazenada: str) -> bool:
    if not senha_armazenada:
        return True
    return not str(senha_armazenada).startswith(_HASH_PREFIXES)


def verificar_senha(senha_digitada: str, senha_armazenada: str) -> bool:
    if not senha_armazenada:
        return False

    valor = str(senha_armazenada)
    if valor.startswith(_HASH_PREFIXES):
        return check_password_hash(valor, senha_digitada)

    # Compatibilidade com dados legados em texto puro.
    return valor == senha_digitada


def _max_login_attempts() -> int:
    return int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))


def _login_window_seconds() -> int:
    return int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))


def _login_key(remote_addr: str, email: str) -> str:
    ip = (remote_addr or "desconhecido").strip().lower()
    user = (email or "*").strip().lower()
    return f"{ip}|{user}"


def _prune_attempts(key: str):
    now = time.time()
    window_start = now - _login_window_seconds()
    history = [ts for ts in _LOGIN_ATTEMPTS.get(key, []) if ts >= window_start]
    if history:
        _LOGIN_ATTEMPTS[key] = history
    else:
        _LOGIN_ATTEMPTS.pop(key, None)
    return history


def login_bloqueado(remote_addr: str, email: str) -> int:
    key = _login_key(remote_addr, email)
    history = _prune_attempts(key)
    if len(history) < _max_login_attempts():
        return 0

    restante = int(_login_window_seconds() - (time.time() - history[0]))
    return max(restante, 1)


def registrar_falha_login(remote_addr: str, email: str) -> dict:
    key = _login_key(remote_addr, email)
    history = _prune_attempts(key)
    history.append(time.time())
    _LOGIN_ATTEMPTS[key] = history

    bloqueado_por = login_bloqueado(remote_addr, email)
    tentativas_restantes = max(_max_login_attempts() - len(history), 0)
    return {
        "bloqueado_por": bloqueado_por,
        "tentativas_restantes": tentativas_restantes,
    }


def limpar_falhas_login(remote_addr: str, email: str) -> None:
    _LOGIN_ATTEMPTS.pop(_login_key(remote_addr, email), None)


def formatar_tempo_bloqueio(segundos: int) -> str:
    if segundos < 60:
        return f"{segundos}s"
    minutos = (segundos + 59) // 60
    return f"{minutos} min"
