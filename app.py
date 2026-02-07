import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import re
from datetime import datetime, timedelta
import io

# Librerías para el PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-segura-mauro-2026")

# Sesión persistente
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
        username = request.form.get("usuario", "").strip().lower()
        password = request.form.get("password", "")
        try:
            conn = conectar()
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT * FROM usuarios WHERE usuario = %s", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user and check_password_hash(user["password"], password):
                session.permanent = True 
                session["usuario"] = user["usuario"]
                return redirect(url_for("cargar_registro"))
            else:
                flash("Usuario o contraseña incorrectos.", "danger")
        except Exception as e:
            return f"Error crítico en Base de Datos: {str(e)}", 500
    return render_template("login.html")

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session: return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        try:
            # Detectamos el tipo automáticamente para evitar errores de null
            t = request.form.get("tipo_registro")
            conn = conectar()
            cur = conn.cursor()
            cur.execute("""INSERT INTO registros 
                (fecha, hora, tipo, cant_izq, cant_der, presion_alta, presion_baja, pulso, glucosa, observaciones, usuario) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                (request.form.get("fecha"), request.form.get("hora"), t,
                 request.form.get("cantidad_izq") or None, request.form.get("cantidad_der") or None,
                 request.form.get("presion_alta") or None, request.form.get("presion_baja") or None,
                 request.form.get("pulso") or None, request.form.get("glucosa") or None,
                 request.form.get("observaciones"), session["usuario"]))
            conn.commit()
            cur.close()
            conn.close()
            success = "✅ Guardado"
        except Exception as e:
            flash(f"Error al guardar: {e}", "danger")
    return render_template("index.html", usuario=session["usuario"], modo="cargar", success=success)

@app.route("/ver")
def ver_registros():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
        registros = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("index.html", usuario=session["usuario"], registros=registros, modo="ver")
    except Exception as e:
        return f"Error al recuperar datos: {str(e)}", 500

@app.route("/reporte-pdf")
def descargar_pdf():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        dias = request.args.get('dias', default=7, type=int)
        tipo_filtro = request.args.get('tipo', default='todos')
        fecha_limite = datetime.now() - timedelta(days=dias)
        
        conn = conectar()
        cur = conn.cursor(cursor_factory=DictCursor)
        query = "SELECT * FROM registros WHERE usuario = %s AND fecha::date >= %s"
        params = [session["usuario"], fecha_limite.date()]
        if tipo_filtro != 'todos':
            query += " AND tipo = %s"
            params.append(tipo_filtro)
        query += " ORDER BY fecha DESC, hora DESC"
        cur.execute(query, params)
        registros = cur.fetchall()
        cur.close()
        conn.close()

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, f"Reporte: {tipo_filtro.upper()} - {dias} dias")
        c.setFont("Helvetica", 10)
        c.drawString(50, 735, f"Usuario: {session['usuario']}")
        c.line(50, 730, 550, 730)

        y = 700
        for r in registros:
            if y < 60: c.showPage(); y = 750
            c.setFont("Helvetica-Bold", 9)
            c.drawString(50, y, f"{r['fecha']} {r['hora']}")
            
            info = ""
            if r['tipo'] == 'drenaje': info = f"I: {r['cant_izq'] or 0} | D: {r['cant_der'] or 0}"
            elif r['tipo'] == 'presion': info = f"{r['presion_alta']}/{r['presion_baja']} (P:{r['pulso']})"
            else: info = f"{r['glucosa']} mg/dL"
            
            c.setFont("Helvetica", 9)
            c.drawString(150, y, f"[{r['tipo']}] {info}")
            if r['observaciones']:
                y -= 12
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(150, y, f"Nota: {r['observaciones']}")
            y -= 20
        c.save()
        buf.seek(0)
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=reporte.pdf'
        return response
    except Exception as e:
        return f"Error en PDF: {str(e)}", 500

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip().lower()
        p = request.form.get("password", "")
        try:
            conn = conectar()
            cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)",
                        (u, generate_password_hash(p, method='pbkdf2:sha256')))
            conn.commit()
            cur.close(); conn.close()
            flash("Cuenta creada!", "success")
            return redirect(url_for("login"))
        except: flash("Error: El usuario ya existe.", "danger")
    return render_template("register.html")

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor()
    cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("ver_registros"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw(): return send_from_directory('static', 'sw.js')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))