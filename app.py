import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-segura-mauro-2026")
app.permanent_session_lifetime = timedelta(days=7)

DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode='require')

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip().lower()
        p = request.form.get("password", "")
        try:
            conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT * FROM usuarios WHERE usuario = %s", (u,))
            user = cur.fetchone()
            cur.close(); conn.close()
            if user and check_password_hash(user["password"], p):
                session.permanent = True
                session["usuario"] = user["usuario"]
                return redirect(url_for("cargar_registro"))
            flash("Usuario o clave incorrectos", "danger")
        except Exception as e:
            return f"Error en Login: {str(e)}", 500
    return render_template("login.html")

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session: return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        try:
            conn = conectar(); cur = conn.cursor()
            # Agregamos 'tipo' a la inserción
            cur.execute("""INSERT INTO registros 
                (fecha, hora, tipo, cant_izq, cant_der, presion_alta, presion_baja, pulso, glucosa, observaciones, usuario) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                (request.form.get("fecha"), request.form.get("hora"), request.form.get("tipo_registro"),
                 request.form.get("cantidad_izq") or None, request.form.get("cantidad_der") or None,
                 request.form.get("presion_alta") or None, request.form.get("presion_baja") or None,
                 request.form.get("pulso") or None, request.form.get("glucosa") or None,
                 request.form.get("observaciones"), session["usuario"]))
            conn.commit(); cur.close(); conn.close()
            success = "✅ Guardado correctamente"
        except Exception as e:
            return f"Error al guardar: {str(e)}. ASEGURATE QUE LA COLUMNA 'tipo' EXISTA.", 500
    return render_template("index.html", modo="cargar", success=success, usuario=session["usuario"])

@app.route("/ver")
def ver_registros():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
        regs = cur.fetchall()
        cur.close(); conn.close()
        return render_template("index.html", registros=regs, modo="ver", usuario=session["usuario"])
    except Exception as e:
        return f"Error al ver: {str(e)}", 500

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        conn = conectar(); cur = conn.cursor()
        cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return redirect(url_for("ver_registros"))

@app.route("/reporte-pdf")
def descargar_pdf():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        dias = request.args.get('dias', default=7, type=int)
        tipo_f = request.args.get('tipo', default='todos')
        limite = datetime.now() - timedelta(days=dias)
        conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
        query = "SELECT * FROM registros WHERE usuario = %s AND fecha::date >= %s"
        params = [session["usuario"], limite.date()]
        if tipo_f != 'todos':
            query += " AND tipo = %s"
            params.append(tipo_f)
        query += " ORDER BY fecha DESC"
        cur.execute(query, params)
        registros = cur.fetchall()
        cur.close(); conn.close()
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(50, 750, f"Reporte {tipo_f} - {dias} dias")
        y = 700
        for r in registros:
            if y < 50: c.showPage(); y = 750
            c.drawString(50, y, f"{r['fecha']} - {r['tipo']}: {r['glucosa'] or r['cant_izq'] or r['presion_alta']}")
            y -= 20
        c.save(); buf.seek(0)
        resp = make_response(buf.read())
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = 'attachment; filename=reporte.pdf'
        return resp
    except Exception as e: return str(e), 500

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip().lower()
        p = request.form.get("password", "")
        conn = conectar(); cur = conn.cursor()
        cur.execute("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)", (u, generate_password_hash(p)))
        conn.commit(); cur.close(); conn.close()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))