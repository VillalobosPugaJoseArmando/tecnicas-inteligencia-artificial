import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

import ollama
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "cambia-esto-antes-de-subirlo"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tutor.db"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "entrar"

MODELO = "qwen3.5:4b"  # el que descargaste con ollama pull (ej. "llama3.1:8b")
XP_POR_ACIERTO = 10
XP_POR_NIVEL = 50
ETIQUETA_XP = "[[XP+10]]"

MATERIAS = {
    "inteligencia-artificial": {
        "nombre": "Inteligencia Artificial",
        "sugerencias": [
            "Explícame qué es el aprendizaje supervisado",
            "¿Qué diferencia hay entre IA y machine learning?",
            "Ponme un reto fácil",
            "Hazme un mini examen para saber mi nivel",
        ],
    },
    "base-de-datos": {
        "nombre": "Base de Datos",
        "sugerencias": [
            "Explícame qué es una llave primaria",
            "¿Qué es normalizar una base de datos?",
            "Ponme un reto de SQL",
            "Hazme un mini examen para saber mi nivel",
        ],
    },
    "redes-y-cableado": {
        "nombre": "Redes y Cableado",
        "sugerencias": [
            "Explícame el modelo OSI",
            "¿Qué categorías de cable UTP existen?",
            "Ponme un reto de direcciones IP",
            "Hazme un mini examen para saber mi nivel",
        ],
    },
}


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    xp = db.Column(db.Integer, default=0)
    racha = db.Column(db.Integer, default=0)
    ultima = db.Column(db.Date)

    @property
    def nivel(self):
        return self.xp // XP_POR_NIVEL + 1


@login_manager.user_loader
def cargar_usuario(uid):
    return db.session.get(Usuario, int(uid))


def registrar_actividad(gano):
    hoy = date.today()
    if current_user.ultima != hoy:  # primera actividad del día
        continua = current_user.ultima == hoy - timedelta(days=1)
        current_user.racha = (current_user.racha or 0) + 1 if continua else 1
        current_user.ultima = hoy
    if gano:
        current_user.xp += XP_POR_ACIERTO
    db.session.commit()


def instrucciones(nombre, nivel):
    return (
        f"Eres un tutor de {nombre} para estudiantes de la Facultad de Informática "
        f"Mazatlán (UAS). El alumno está en nivel {nivel}: adapta la dificultad. "
        "Responde en español, con tono amigable, en máximo 150 palabras y con ejemplos "
        "prácticos. Escribe en texto plano, sin Markdown; los comandos o el código van "
        "en una línea aparte. Solo hablas de este tema; si preguntan otra cosa, "
        "regresa amablemente al tema. Cuando propongas un reto, haz UNA sola pregunta "
        "y espera la respuesta. Cuando el alumno conteste correctamente un reto tuyo, "
        f"felicítalo y termina tu mensaje con la etiqueta exacta {ETIQUETA_XP}. "
        "Si falla, explica el error y no pongas la etiqueta. Nunca la pongas en otro caso."
    )


CHARLA = re.compile(r"\b(reto|examen|ponme|hazme|dame|siguiente|otra|otro)\b", re.I)


def buscar_wikipedia(consulta, n=3):
    """Trae el inicio de los n artículos más relevantes de es.wikipedia.org."""
    url = ("https://es.wikipedia.org/w/api.php?action=query&format=json&generator=search"
           f"&gsrlimit={n}&prop=extracts&exintro=1&explaintext=1&exchars=1200&gsrsearch="
           + urllib.parse.quote(consulta))
    req = urllib.request.Request(url, headers={"User-Agent": "TutorInteligenteFIMAZ/1.0 (proyecto escolar)"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            paginas = json.load(r).get("query", {}).get("pages", {})
    except Exception:
        return ""
    orden = sorted(paginas.values(), key=lambda p: p.get("index", 99))
    texto = "\n\n".join(f"[{p['title']}] {p['extract'].strip()}" for p in orden if p.get("extract"))
    return texto.replace(ETIQUETA_XP, "")


def consulta_para(msgs):
    """Devuelve qué buscar, o None si el mensaje no es una pregunta de concepto."""
    ult = msgs[-1]["content"].strip()
    if len(ult.split()) < 3 or CHARLA.search(ult):
        return None
    if len(msgs) > 1 and msgs[-2]["content"].rstrip().endswith("?"):
        return None  # está contestando un reto
    return f"informática {ult}"[:200]


@app.route("/")
def inicio():
    if not current_user.is_authenticated:
        return redirect(url_for("ranking"))
    return render_template("inicio.html", materias=MATERIAS)


@app.route("/ranking")
def ranking():
    usuarios = Usuario.query.order_by(Usuario.xp.desc(), Usuario.username).all()
    return render_template("ranking.html", usuarios=usuarios)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]
        if len(u) < 3 or len(p) < 6:
            flash("El usuario necesita 3 caracteres o más y la contraseña 6 o más.")
        elif Usuario.query.filter_by(username=u).first():
            flash("Ese usuario ya existe. Elige otro.")
        else:
            nuevo = Usuario(username=u, password_hash=generate_password_hash(p))
            db.session.add(nuevo)
            db.session.commit()
            login_user(nuevo)
            return redirect(url_for("inicio"))
    return render_template("login.html", registro=True)


@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    if request.method == "POST":
        u = Usuario.query.filter_by(username=request.form["username"].strip()).first()
        if u and check_password_hash(u.password_hash, request.form["password"]):
            login_user(u)
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos.")
    return render_template("login.html", registro=False)


@app.route("/salir")
def salir():
    logout_user()
    return redirect(url_for("ranking"))


@app.route("/chat/<slug>")
@login_required
def chat(slug):
    if slug not in MATERIAS:
        abort(404)
    return render_template("chat.html", slug=slug, **MATERIAS[slug])


@app.route("/api/chat/<slug>", methods=["POST"])
@login_required
def api_chat(slug):
    if slug not in MATERIAS:
        abort(404)
    crudos = (request.get_json(silent=True) or {}).get("mensajes") or []
    msgs = [
        {"role": m["role"], "content": str(m.get("content", ""))[:1000]}
        for m in crudos[-20:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs or msgs[-1]["role"] != "user":
        return jsonify(error="Escribe un mensaje primero."), 400
    sistema = instrucciones(MATERIAS[slug]["nombre"], current_user.nivel)
    consulta = consulta_para(msgs)
    fuentes = buscar_wikipedia(consulta) if consulta else ""
    if fuentes:
        sistema += ("\n\nFuentes de Wikipedia para apoyarte. Úsalas solo si ayudan, "
                    "explícalas con tus palabras y si no sirven, ignóralas:\n" + fuentes)
    try:
        r = ollama.chat(
            model=MODELO,
            messages=[{"role": "system", "content": sistema}] + msgs,
            think=False,  # sin razonamiento largo: en CPU cada token cuenta
            options={"num_predict": 400},
        )
    except ollama.ResponseError:
        return jsonify(error=f"Falta el modelo. Corre: ollama pull {MODELO}"), 500
    except ConnectionError:
        return jsonify(error="No pude conectar con Ollama. Corre: sudo systemctl start ollama"), 502
    texto = re.sub(r"<think>.*?</think>", "", r.message.content or "", flags=re.S)
    gano = ETIQUETA_XP in texto
    texto = texto.replace(ETIQUETA_XP, "").strip()
    registrar_actividad(gano)
    return jsonify(respuesta=texto, gano=gano, xp=current_user.xp,
                   racha=current_user.racha)


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
