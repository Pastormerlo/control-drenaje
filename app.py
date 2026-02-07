import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-segura-mauro-2026")
app.permanent_session_lifetime = timedelta(days=7)

DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode='require')

def inicializar_sistema():
    try:
        conn = conectar(); cur = conn.cursor()
        # Crear tablas básicas
        cur.execute("CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE, password TEXT);")
        cur.execute("""CREATE TABLE IF NOT EXISTS perfil (
            id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE, nombre_apellido VARCHAR(100),
            edad INTEGER, sexo VARCHAR(20), peso DECIMAL(5,2), nombre_medico VARCHAR(100), obra_social VARCHAR(100)
        );""")
        cur.execute("""CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY, fecha DATE, hora TIME, tipo VARCHAR(50), 
            cant_izq DECIMAL(5,2), cant_der DECIMAL(5,2), presion_alta INTEGER, 
            presion_baja INTEGER, pulso INTEGER, glucosa INTEGER, observaciones TEXT, usuario VARCHAR(50)
        );""")
        
        # --- ESTO ARREGLA EL ERROR: Agrega las columnas nuevas si no existen ---
        cur.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS oxigeno INTEGER;")
        cur.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS temperatura DECIMAL(4,1);")
        
        conn.commit(); cur.close(); conn.close()
        print("Base de datos actualizada con éxito.")
    except Exception as e: 
        print(f"Error inicializando: {e}")

# Se ejecuta al arrancar la app
inicializar_sistema()

@app.route("/", methods=["GET", "POST"])
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
                session["usuario"] = u
                return redirect(url_for("cargar_registro"))
            flash("Usuario o clave incorrectos", "danger")
        except Exception as e: return f"Error: {e}", 500
    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip().lower()
        p = request.form.get("password", "")
        try:
            conn = conectar(); cur = conn.cursor()
            cur.execute("INSERT INTO usuarios (usuario, password) VALUES (%s, %s)", (u, generate_password_hash(p)))
            conn.commit(); cur.close(); conn.close()
            flash("Cuenta creada.", "success")
            return redirect(url_for("login"))
        except: flash("El usuario ya existe", "danger")
    return render_template("register.html")

@app.route("/perfil", methods=["GET", "POST"])
def editar_perfil():
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
    if request.method == "POST":
        cur.execute("""INSERT INTO perfil (usuario, nombre_apellido, edad, sexo, peso, nombre_medico, obra_social)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (usuario) DO UPDATE SET 
            nombre_apellido=EXCLUDED.nombre_apellido, edad=EXCLUDED.edad, sexo=EXCLUDED.sexo, 
            peso=EXCLUDED.peso, nombre_medico=EXCLUDED.nombre_medico, obra_social=EXCLUDED.obra_social""",
            (session["usuario"], request.form.get("nombre"), request.form.get("edad"), 
             request.form.get("sexo"), request.form.get("peso"), request.form.get("medico"), request.form.get("obra_social")))
        conn.commit()
        flash("Ficha guardada", "success")
    cur.execute("SELECT * FROM perfil WHERE usuario = %s", (session["usuario"],))
    perfil = cur.fetchone()
    cur.close(); conn.close()
    return render_template("index.html", modo="perfil", perfil=perfil, usuario=session["usuario"])

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session: return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        conn = conectar(); cur = conn.cursor()
        cur.execute("""INSERT INTO registros (fecha, hora, tipo, cant_izq, cant_der, presion_alta, presion_baja, pulso, glucosa, oxigeno, temperatura, observaciones, usuario) 
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
            (request.form.get("fecha"), request.form.get("hora"), request.form.get("tipo_registro"),
             request.form.get("cantidad_izq") or None, request.form.get("cantidad_der") or None,
             request.form.get("presion_alta") or None, request.form.get("presion_baja") or None,
             request.form.get("pulso") or None, request.form.get("glucosa") or None,
             request.form.get("oxigeno") or None, request.form.get("temperatura") or None,
             request.form.get("observaciones"), session["usuario"]))
        conn.commit(); cur.close(); conn.close()
        success = "✅ Guardado correctamente"
    return render_template("index.html", modo="cargar", success=success, usuario=session["usuario"])

@app.route("/ver")
def ver_registros():
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC", (session["usuario"],))
    regs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("index.html", registros=regs, modo="ver", usuario=session["usuario"])

@app.route("/reporte-pdf")
def descargar_pdf():
    if "usuario" not in session: return redirect(url_for("login"))
    dias = request.args.get('dias', default=7, type=int)
    tipo_f = request.args.get('tipo', default='todos')
    limite = datetime.now() - timedelta(days=dias)
    conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM perfil WHERE usuario = %s", (session["usuario"],))
    p = cur.fetchone()
    query = "SELECT * FROM registros WHERE usuario = %s AND fecha::date >= %s"
    params = [session["usuario"], limite.date()]
    if tipo_f != 'todos': query += " AND tipo = %s"; params.append(tipo_f)
    cur.execute(query + " ORDER BY fecha DESC", params)
    regs = cur.fetchall(); cur.close(); conn.close()
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=letter)
    
    c.setFont("Helvetica-Bold", 14); c.drawString(50, 760, "REPORTE DE SALUD - MAURO")
    c.setFont("Helvetica", 10)
    if p:
        c.drawString(50, 740, f"Paciente: {p['nombre_apellido']} | OS: {p['obra_social']}")
    c.line(50, 715, 550, 715)
    
    y = 690
    for r in regs:
        if y < 50: c.showPage(); y = 750
        txt = f"[{r['fecha']}] {r['tipo'].upper()}: "
        if r['tipo'] == 'drenaje': txt += f"I:{r['cant_izq']}ml D:{r['cant_der']}ml"
        elif r['tipo'] == 'presion': txt += f"P:{r['presion_alta']}/{r['presion_baja']} Pulso:{r['pulso']}"
        elif r['tipo'] == 'glucosa': txt += f"G:{r['glucosa']}mg/dL"
        elif r['tipo'] == 'oxigeno': txt += f"O2:{r['oxigeno']}%"
        elif r['tipo'] == 'temperatura': txt += f"Temp:{r['temperatura']}C"
        c.drawString(50, y, txt)
        y -= 20
        
    c.save(); buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Reporte_Salud.pdf'
    return resp

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor()
    cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("ver_registros"))

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))