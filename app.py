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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-segura-mauro-2026")

# --- CONFIGURACIÓN DE SESIÓN (7 DÍAS) ---
app.permanent_session_lifetime = timedelta(days=7)

DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode='require')

def es_clave_segura(password):
    if len(password) < 8: return False
    if not re.search("[a-zA-Z]", password): return False
    if not re.search("[0-9]", password): return False
    return True

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("usuario").strip().lower()
        password = request.form.get("password")
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
    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        username = request.form.get("usuario").strip().lower()
        password = request.form.get("password")
        if not es_clave_segura(password):
            flash("Mínimo 8 caracteres, letras y números.", "warning")
            return render_template("register.html")
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)",
                        (username, generate_password_hash(password, method='pbkdf2:sha256')))
            conn.commit()
            flash("¡Cuenta creada!", "success")
            return redirect(url_for("login"))
        except:
            flash("El usuario ya existe.", "danger")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session: return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""INSERT INTO registros 
            (fecha, hora, tipo, cant_izq, cant_der, presion_alta, presion_baja, pulso, glucosa, observaciones, usuario) 
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
            (request.form.get("fecha"), request.form.get("hora"), request.form.get("tipo_registro"),
             request.form.get("cantidad_izq") or None, request.form.get("cantidad_der") or None,
             request.form.get("presion_alta") or None, request.form.get("presion_baja") or None,
             request.form.get("pulso") or None, request.form.get("glucosa") or None,
             request.form.get("observaciones"), session["usuario"]))
        conn.commit()
        conn.close()
        success = "✅ Guardado"
    return render_template("index.html", usuario=session["usuario"], modo="cargar", success=success)

@app.route("/ver")
def ver_registros():
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
    registros = cur.fetchall()
    conn.close()
    return render_template("index.html", usuario=session["usuario"], registros=registros, modo="ver")

@app.route("/reporte-pdf")
def descargar_pdf():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        dias = request.args.get('dias', default=7, type=int)
        fecha_limite = datetime.now() - timedelta(days=dias)
        
        conn = conectar()
        cur = conn.cursor(cursor_factory=DictCursor)
        # ACÁ ESTÁ EL CAMBIO: agregamos ::date para convertir el texto a fecha
        cur.execute("""SELECT * FROM registros 
                       WHERE usuario = %s AND fecha::date >= %s 
                       ORDER BY fecha DESC, hora DESC""", 
                    (session["usuario"], fecha_limite.date()))
        registros = cur.fetchall()
        cur.close()
        conn.close()

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, f"Reporte de Salud - Ultimos {dias} dias")
        c.setFont("Helvetica", 10)
        c.drawString(50, 735, f"Usuario: {session['usuario']} | Generado: {datetime.now().strftime('%d/%m/%Y')}")
        c.line(50, 730, 550, 730)

        y = 700
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Fecha")
        c.drawString(130, y, "Tipo")
        c.drawString(210, y, "Valores / Notas")
        y -= 20
        
        c.setFont("Helvetica", 9)
        for r in registros:
            if y < 60:
                c.showPage()
                y = 750
            
            c.drawString(50, y, f"{r['fecha']}")
            
            tipo = "Glucosa"
            valores = f"{r['glucosa']} mg/dL"
            if r['cant_izq'] or r['cant_der']:
                tipo = "Drenaje"
                valores = f"I: {r['cant_izq'] or 0} | D: {r['cant_der'] or 0}"
            elif r['presion_alta']:
                tipo = "Presion"
                valores = f"{r['presion_alta']}/{r['presion_baja']} (P:{r['pulso']})"
                
            c.drawString(130, y, tipo)
            c.drawString(210, y, valores)
            
            if r['observaciones']:
                y -= 12
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(210, y, f"Nota: {str(r['observaciones'])[:70]}")
                c.setFont("Helvetica", 9)
            
            y -= 20

        c.save()
        buf.seek(0)
        
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=reporte_{dias}_dias.pdf'
        return response

    except Exception as e:
        return f"Error tecnico al generar PDF: {str(e)}", 500

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
    conn.commit()
    conn.close()
    return redirect(url_for("ver_registros"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))