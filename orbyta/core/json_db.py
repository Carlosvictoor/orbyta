import json
import os
import sqlite3

from core.constants import DB_FILE


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _deve_migrar_json_para_db():
    """
    Define se o bootstrap via arquivos JSON deve rodar.

    Regra padrão:
    - Desenvolvimento local (sem ORBYTA_DATA_DIR): migra JSON -> DB.
    - Produção (com ORBYTA_DATA_DIR): NÃO migra, para evitar
      ressuscitar dados antigos quando houver reinício/deploy.

    Override:
    - ORBYTA_SEED_FROM_JSON=1 força migração.
    - ORBYTA_SEED_FROM_JSON=0 bloqueia migração.
    """
    seed_explicit = os.getenv("ORBYTA_SEED_FROM_JSON")
    if seed_explicit is not None:
        return _env_bool("ORBYTA_SEED_FROM_JSON", False)

    using_persistent_data_dir = bool(os.getenv("ORBYTA_DATA_DIR", "").strip())
    return not using_persistent_data_dir

TABLE_SCHEMAS = {
    "usuarios": [
        "email",
        "senha",
        "tipo",
        "negocio_id",
        "profissional_id",
        "assinatura_status",
        "trial_ate",
        "mp_subscription_id",
        "mp_pix_payment_id",
    ],
    "negocios": [
        "id",
        "tipo",
        "nome",
        "cidade",
        "bairro",
        "endereco",
        "whatsapp",
        "instagram",
    ],
    "profissionais": [
        "id",
        "nome",
        "negocio_id",
        "comissao_pct",
    ],
    "servicos": [
        "id",
        "nome",
        "negocio_id",
        "duracao_min",
        "preco",
        "ativo",
    ],
    "horarios": [
        "id",
        "negocio_id",
        "modo",
        "times",
    ],
    "agendamentos": [
        "id",
        "negocio_id",
        "nome",
        "cliente",
        "data",
        "horario",
        "barbeiro",
        "servico_id",
        "servico",
        "profissional_id",
    ],
    "financeiro": [
        "id",
        "negocio_id",
        "profissional_id",
        "tipo",
        "valor",
        "data",
        "descricao",
    ],
    "barbeiros": [
        "id",
        "nome",
        "negocio_id",
    ],
}

COLUMN_TYPES = {
    "email": "TEXT",
    "senha": "TEXT",
    "tipo": "TEXT",
    "negocio_id": "INTEGER",
    "profissional_id": "INTEGER",
    "assinatura_status": "TEXT",
    "trial_ate": "TEXT",
    "mp_subscription_id": "TEXT",
    "mp_pix_payment_id": "TEXT",
    "id": "INTEGER",
    "nome": "TEXT",
    "cidade": "TEXT",
    "bairro": "TEXT",
    "endereco": "TEXT",
    "whatsapp": "TEXT",
    "instagram": "TEXT",
    "comissao_pct": "REAL",
    "duracao_min": "INTEGER",
    "preco": "TEXT",
    "ativo": "INTEGER",
    "modo": "TEXT",
    "times": "TEXT",
    "cliente": "TEXT",
    "data": "TEXT",
    "horario": "TEXT",
    "barbeiro": "TEXT",
    "servico": "TEXT",
    "tipo": "TEXT",
    "valor": "TEXT",
    "descricao": "TEXT",
}


def iniciar_arquivo(nome):
    pasta = os.path.dirname(nome)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta, exist_ok=True)

    if nome.endswith(".json") and not os.path.exists(nome):
        with open(nome, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)


def _table_name(nome):
    base = os.path.basename(nome)
    tabela, ext = os.path.splitext(base)
    if ext.lower() != ".json" or not tabela:
        raise ValueError(f"Nome de arquivo inválido para tabela: {nome}")
    return tabela


def _connect():
    pasta_db = os.path.dirname(DB_FILE)
    if pasta_db and not os.path.exists(pasta_db):
        os.makedirs(pasta_db, exist_ok=True)
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def _column_definition(col):
    sql_type = COLUMN_TYPES.get(col, "TEXT")
    if col == "id":
        return "id INTEGER PRIMARY KEY"
    if col == "email":
        return "email TEXT PRIMARY KEY"
    return f"{col} {sql_type}"


def _get_table_columns(conn, tabela):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info('{tabela}')")
    rows = cursor.fetchall()
    return [row[1] for row in rows] if rows else []


def _table_exists(conn, tabela):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabela,))
    return cursor.fetchone() is not None


def _table_is_generic(conn, tabela):
    if not _table_exists(conn, tabela):
        return False
    cols = _get_table_columns(conn, tabela)
    return "data" in cols and "extra_data" not in cols


def _create_table(conn, tabela):
    if tabela in TABLE_SCHEMAS:
        columns = [_column_definition(col) for col in TABLE_SCHEMAS[tabela]]
        columns.append("extra_data TEXT")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS \"{tabela}\" ({', '.join(columns)})"
        )
    else:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS \"{tabela}\" (rowid INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)"
        )
    conn.commit()


def _migrate_generic_table(conn, tabela):
    if not _table_is_generic(conn, tabela):
        return

    cursor = conn.cursor()
    cursor.execute(f"SELECT rowid, data FROM \"{tabela}\"")
    rows = cursor.fetchall()

    temp_table = f"{tabela}_old"
    conn.execute(f"ALTER TABLE \"{tabela}\" RENAME TO \"{temp_table}\"")
    _create_table(conn, tabela)

    cols = TABLE_SCHEMAS.get(tabela, [])
    for row in rows:
        item = json.loads(row[1])
        if tabela in TABLE_SCHEMAS:
            extras = {}
            values = []
            placeholders = []
            for col in cols:
                values.append(_cacheable_value(col, item.get(col)))
                placeholders.append("?")
            for key, val in item.items():
                if key not in cols:
                    extras[key] = val
            query = f"INSERT INTO \"{tabela}\" ({', '.join(cols)}, extra_data) VALUES ({', '.join(placeholders)}, ?)"
            cursor.execute(query, (*values, json.dumps(extras, ensure_ascii=False)))
        else:
            cursor.execute(
                f"INSERT INTO \"{tabela}\" (data) VALUES (?)",
                (row[1],),
            )

    conn.commit()
    conn.execute(f"DROP TABLE \"{temp_table}\"")


def _load_json_file(nome):
    if not os.path.exists(nome):
        return []


def _write_json_snapshot(nome, dados):
    """Mantem um snapshot JSON atualizado como fallback de recuperacao."""
    pasta = os.path.dirname(nome)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta, exist_ok=True)

    with open(nome, "w", encoding="utf-8") as f:
        json.dump(dados or [], f, indent=4, ensure_ascii=False)

    try:
        with open(nome, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            if not txt:
                return []
            return json.loads(txt)
    except json.JSONDecodeError:
        try:
            os.rename(nome, nome + ".bak")
        except Exception:
            pass

        with open(nome, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)

        return []


def _cacheable_value(col, value):
    if value is None:
        return None
    if col == "ativo":
        return 1 if bool(value) else 0
    if col == "times":
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _db_to_python(col, value):
    if value is None:
        return None
    if col == "ativo":
        return bool(value)
    if col == "times":
        try:
            return json.loads(value)
        except Exception:
            return []
    if col == "extra_data":
        try:
            return json.loads(value) if value else {}
        except Exception:
            return {}
    return value


def _row_to_dict(row, tabela):
    if tabela in TABLE_SCHEMAS and "extra_data" in row.keys():
        item = {}
        for col in TABLE_SCHEMAS[tabela]:
            item[col] = _db_to_python(col, row[col])
        extras = _db_to_python("extra_data", row["extra_data"])
        if extras:
            item.update(extras)
        return item

    try:
        return json.loads(row["data"])
    except Exception:
        return {}


def _normalize_schema_item(tabela, item):
    if isinstance(item, dict):
        return item

    # Compatibilidade com formato legado: barbeiros como lista de nomes.
    if tabela == "barbeiros" and isinstance(item, str):
        return {
            "id": None,
            "nome": item,
            "negocio_id": None,
        }

    return None


def _migrate_json_to_db(arquivos):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for arquivo in arquivos:
        tabela = _table_name(arquivo)
        cursor.execute(f"SELECT COUNT(*) AS total FROM \"{tabela}\"")
        total = cursor.fetchone()[0]
        if total == 0:
            dados = _load_json_file(arquivo)
            if dados:
                for item in dados:
                    if tabela in TABLE_SCHEMAS:
                        item = _normalize_schema_item(tabela, item)
                        if item is None:
                            continue

                        cols = TABLE_SCHEMAS[tabela]
                        extras = {}
                        values = []
                        placeholders = []

                        for col in cols:
                            if col in item:
                                values.append(_cacheable_value(col, item[col]))
                            else:
                                values.append(None)
                            placeholders.append("?")

                        for key, val in item.items():
                            if key not in cols:
                                extras[key] = val

                        query = f"INSERT INTO \"{tabela}\" ({', '.join(cols)}, extra_data) VALUES ({', '.join(placeholders)}, ?)"
                        cursor.execute(query, (*values, json.dumps(extras, ensure_ascii=False)))
                    else:
                        cursor.execute(
                            f"INSERT INTO \"{tabela}\" (data) VALUES (?)",
                            (json.dumps(item, ensure_ascii=False),),
                        )

    conn.commit()
    conn.close()


def iniciar_banco_json(arquivos):
    for arquivo in arquivos:
        iniciar_arquivo(arquivo)

    pasta_db = os.path.dirname(DB_FILE)
    if pasta_db and not os.path.exists(pasta_db):
        os.makedirs(pasta_db, exist_ok=True)

    conn = _connect()
    for arquivo in arquivos:
        tabela = _table_name(arquivo)
        if _table_is_generic(conn, tabela):
            _migrate_generic_table(conn, tabela)
        else:
            _create_table(conn, tabela)
    conn.close()

    if _deve_migrar_json_para_db():
        _migrate_json_to_db(arquivos)


def carregar_json(nome):
    tabela = _table_name(nome)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if tabela in TABLE_SCHEMAS:
            cursor.execute(f"SELECT {', '.join(TABLE_SCHEMAS[tabela])}, extra_data FROM \"{tabela}\" ORDER BY rowid")
        else:
            cursor.execute(f"SELECT data FROM \"{tabela}\" ORDER BY rowid")
    except sqlite3.OperationalError:
        cursor.execute(f"SELECT data FROM \"{tabela}\" ORDER BY rowid")

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_dict(row, tabela) for row in rows]


def salvar_json(nome, dados):
    if dados is None:
        dados = []
    if not isinstance(dados, list):
        raise ValueError("Dados deve ser uma lista de objetos JSON")

    tabela = _table_name(nome)
    conn = _connect()
    _create_table(conn, tabela)
    cursor = conn.cursor()

    if tabela in TABLE_SCHEMAS:
        cols = TABLE_SCHEMAS[tabela]
        cursor.execute(f"DELETE FROM \"{tabela}\"")

        for item in dados:
            item = _normalize_schema_item(tabela, item)
            if item is None:
                continue

            extras = {}
            values = []
            placeholders = []
            for col in cols:
                values.append(_cacheable_value(col, item.get(col)))
                placeholders.append("?")
            for key, val in item.items():
                if key not in cols:
                    extras[key] = val
            query = f"INSERT INTO \"{tabela}\" ({', '.join(cols)}, extra_data) VALUES ({', '.join(placeholders)}, ?)"
            cursor.execute(query, (*values, json.dumps(extras, ensure_ascii=False)))
    else:
        cursor.execute(f"DELETE FROM \"{tabela}\"")
        for item in dados:
            cursor.execute(
                f"INSERT INTO \"{tabela}\" (data) VALUES (?)",
                (json.dumps(item, ensure_ascii=False),),
            )

    conn.commit()
    conn.close()

    # Espelha no JSON para facilitar recuperacao se o banco SQLite for recriado.
    _write_json_snapshot(nome, dados)
