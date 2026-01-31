import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import io
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

# --- CONFIGURACIÓN DE RUTAS ABSOLUTAS ---
# Esto soluciona el error TemplateNotFound en servidores Linux
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.environ.get("SECRET_KEY", "clave-secreta-para-produccion")

# --- CONEXIÓN A POSTGRESQL ---
DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    url = DATABASE_URL
    # Ajuste necesario para que SQLAlchemy/Psycopg2 acepten la URL de Render
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    conn = psycopg2.connect(url, sslmode='require')
    return conn

def init_db():
    """Inicializa las tablas si no existen al arrancar la app."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY, 
                    usuario TEXT UNIQUE NOT NULL, 
                    password TEXT NOT NULL)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS registros (
                    id SERIAL PRIMARY KEY, 
                    fecha TEXT, hora TEXT, cant_izq REAL, 
                    cant_der REAL, observaciones TEXT, usuario TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

# --- RUTAS DE ACCESO ---

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("usuario")
        password = request.form.get("password")
        conn = conectar()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM usuarios WHERE usuario = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["usuario"] = user["usuario"]
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Usuario o contraseña incorrectos")
    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        username = request.form.get("usuario")
        password = request.form.get("password")
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)",
                        (username, generate_password_hash(password)))
            conn.commit()
            return redirect(url_for("login"))
        except Exception:
            return render_template("register.html", error="El usuario ya existe")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", usuario=session["usuario"])

# --- RUTAS DE DRENAJE ---

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session:
        return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""INSERT INTO registros (fecha, hora, cant_izq, cant_der, observaciones, usuario) 
                       VALUES (%s,%s,%s,%s,%s,%s)""", 
                    (request.form.get("fecha"), request.form.get("hora"), 
                     request.form.get("cantidad_izq"), request.form.get("cantidad_der"), 
                     request.form.get("observaciones"), session["usuario"]))
        conn.commit()
        cur.close()
        conn.close()
        success = "✅ Cargado correctamente"
    return render_template("index.html", usuario=session["usuario"], modo="cargar", success=success)

@app.route("/ver")
def ver_registros():
    if "usuario" not in session:
        return redirect(url_for("login"))
    conn = conectar()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
    registros = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", usuario=session["usuario"], registros=registros, modo="ver")

# --- GENERACIÓN DE PDF ---

@app.route("/descargar_pdf")
def descargar_pdf():
    if "usuario" not in session:
        return redirect(url_for("login"))
    conn = conectar()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
    registros = cur.fetchall()
    cur.close()
    conn.close()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(190, 10, "Informe de Control de Drenaje", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(190, 10, f"Usuario: {session['usuario']}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_fill_color(200, 220, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 10, "Fecha", 1, 0, "C", True)
    pdf.cell(25, 10, "Hora", 1, 0, "C", True)
    pdf.cell(30, 10, "Izq (ml)", 1, 0, "C", True)
    pdf.cell(30, 10, "Der (ml)", 1, 0, "C", True)
    pdf.cell(70, 10, "Observaciones", 1, 1, "C", True)

    pdf.set_font("Helvetica", "", 9)
    for r in registros:
        pdf.cell(35, 10, str(r['fecha']), 1)
        pdf.cell(25, 10, str(r['hora']), 1)
        pdf.cell(30, 10, str(r['cant_izq']), 1)
        pdf.cell(30, 10, str(r['cant_der']), 1)
        obs = str(r['observaciones']).encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(70, 10, obs[:40], 1, 1)

    pdf_output = pdf.output()
    buffer = io.BytesIO(pdf_output)
    buffer.seek(0)

    return send_file(
        buffer, 
        as_attachment=True, 
        download_name=f"informe_{session['usuario']}.pdf", 
        mimetype="application/pdf"
    )

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" in session:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for("ver_registros"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    init_db()
    # Render usa el puerto que le asigna el entorno
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)