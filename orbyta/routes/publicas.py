from flask import Blueprint, render_template, request, current_app, make_response
from services.negocios_service import listar_negocios, get_negocio
from services.servicos_service import servicos_do_negocio, agrupar_servicos_por_categoria
from services.profissionais_service import profissionais_do_negocio
from services.horarios_service import obter_horarios_globais

publicas_bp = Blueprint("publicas", __name__)


# ── PWA routes ───────────────────────────────────────────────

@publicas_bp.get("/sw.js")
def service_worker():
    """Serve o service worker na raiz para que o escopo cubra todo o app."""
    response = make_response(
        current_app.send_static_file("sw.js")
    )
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@publicas_bp.get("/manifest.json")
def web_manifest():
    response = make_response(
        current_app.send_static_file("manifest.json")
    )
    response.headers["Content-Type"] = "application/manifest+json"
    return response


@publicas_bp.get("/offline")
def offline():
    return render_template("offline.html"), 200


@publicas_bp.route("/")
def index():
    return render_template("index.html")


@publicas_bp.route("/planos")
def planos():
    return render_template("planos.html")


@publicas_bp.route("/negocios")
def negocios_inicio():
    negocios = listar_negocios()
    categorias = [
        {
            "tipo": "saloes",
            "titulo": "Salões de Beleza",
            "icone": "💇‍♀️",
            "descricao": "Cabelos, unhas, maquiagem e cuidados para o dia a dia ou ocasiões especiais.",
        },
        {
            "tipo": "barbearias",
            "titulo": "Barbearias",
            "icone": "💈",
            "descricao": "Corte, barba, acabamento e atendimento rápido com estilo.",
        },
        {
            "tipo": "studios",
            "titulo": "Studios",
            "icone": "✨",
            "descricao": "Studios de design, nail, sobrancelha e atendimentos especializados.",
        },
        {
            "tipo": "clinicas",
            "titulo": "Clínicas de Estética",
            "icone": "🧴",
            "descricao": "Tratamentos, estética facial e corporal com mais organização no agendamento.",
        },
    ]

    for item in categorias:
        item["total"] = sum(1 for n in negocios if n.get("tipo") == item["tipo"])

    return render_template("negocios_inicio.html", categorias=categorias, total=len(negocios))


@publicas_bp.route("/negocios/<tipo>")
def listar_negocios_route(tipo):
    q = request.args.get("q", "").strip().lower()
    negocios = listar_negocios()

    lista = [n for n in negocios if n.get("tipo") == tipo]

    if q:
        lista = [
            n for n in lista
            if q in n.get("nome", "").lower()
            or q in n.get("cidade", "").lower()
            or q in n.get("bairro", "").lower()
        ]

    titulos = {
        "saloes": "Salões de Beleza",
        "barbearias": "Barbearias",
        "clinicas": "Clínicas de Estética",
        "studios": "Studios"
    }

    return render_template("negocios.html", titulo=titulos.get(tipo, "Negócios"), tipo=tipo, lista=lista, q=q)


@publicas_bp.route("/loja/<int:negocio_id>")
def loja(negocio_id):
    negocio = get_negocio(negocio_id)
    if not negocio:
        return "Negócio não encontrado", 404

    servs = servicos_do_negocio(negocio_id)
    servicos_categoria = agrupar_servicos_por_categoria(servs)
    profs = profissionais_do_negocio(negocio_id)
    horarios = obter_horarios_globais(negocio_id)

    return render_template("loja.html", negocio=negocio, servs=servs, servicos_categoria=servicos_categoria, profs=profs, horarios=horarios)