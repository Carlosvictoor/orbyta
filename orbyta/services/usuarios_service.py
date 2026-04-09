from core.constants import USUARIOS_FILE
from core.json_db import carregar_json, salvar_json


def get_usuario(email):
    usuarios = carregar_json(USUARIOS_FILE)
    for u in usuarios:
        if u.get("email", "").lower() == email.lower():
            return u
    return None


def atualizar_usuario(email, patch: dict):
    usuarios = carregar_json(USUARIOS_FILE)
    for u in usuarios:
        if u.get("email", "").lower() == email.lower():
            u.update(patch)
            salvar_json(USUARIOS_FILE, usuarios)
            return True
    return False


def listar_usuarios():
    return carregar_json(USUARIOS_FILE)


def salvar_usuarios(usuarios):
    salvar_json(USUARIOS_FILE, usuarios)