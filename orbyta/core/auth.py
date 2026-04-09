from flask import session
from services.usuarios_service import get_usuario
from services.assinatura_service import dono_tem_acesso


def usuario_atual():
    if "usuario" not in session:
        return None
    return get_usuario(session["usuario"])


def exigir_login():
    return "usuario" in session


def exigir_dono():
    return session.get("tipo") == "dono"


def exigir_admin():
    return session.get("tipo") == "admin"


def exigir_cliente():
    return session.get("tipo") == "cliente"


def exigir_funcionario():
    return session.get("tipo") == "funcionario"


def exigir_assinatura_dono():
    u = usuario_atual()
    if not u:
        return False
    return dono_tem_acesso(u)