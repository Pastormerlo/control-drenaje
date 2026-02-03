import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import re
from datetime import timedelta

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

# RUTAS PARA PWA
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
            # ACTIVAR SESIÓN PERMANENTE
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
        # Nombres de columnas corregidos según tu base de datos (cant_izq / cant_der)
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