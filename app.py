import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, send_from_directory
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

# --- ESTA FUNCIÓN CREA LA TABLA AUTOMÁTICAMENTE ---
def crear_tablas_si_no_existen():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS perfil (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(50) UNIQUE,
                nombre_apellido VARCHAR(100),
                edad INTEGER,
                sexo VARCHAR(20),
                peso DECIMAL(5,2),
                nombre_medico VARCHAR(100),
                obra_social VARCHAR(100)
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error creando tabla: {e}")

# Ejecutamos la creación al iniciar
crear_tablas_si_no_existen()

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

@app.route("/perfil", methods=["GET", "POST"])
def editar_perfil():
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
    if request.method == "POST":
        cur.execute("""INSERT INTO perfil (usuario, nombre_apellido, edad, sexo, peso, nombre_medico, obra_social)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (usuario) DO UPDATE SET 
            nombre_apellido=EXCLUDED.nombre_apellido, edad=EXCLUDED.edad, sexo=EXCLUDED.sexo, 
            peso=EXCLUDED.peso, nombre_medico=EXCLUDED.nombre_medico, obra_social=EXCLUDED.obra_social""",
            (session["usuario"], request.form.get("nombre"), request.form.get("edad"), 
             request.form.get("sexo"), request.form.get("peso"), request.form.get("medico"), 
             request.form.get("obra_social")))
        conn.commit()
        flash("Ficha actualizada correctamente", "success")
    
    cur.execute("SELECT * FROM perfil WHERE usuario = %s", (session["usuario"],))
    perfil = cur.fetchone()
    cur.close(); conn.close()
    return render_template("index.html", modo="perfil", perfil=perfil, usuario=session["usuario"])

@app.route("/cargar", methods=["GET", "POST"])
def cargar_registro():
    if "usuario" not in session: return redirect(url_for("login"))
    success = None
    if request.method == "POST":
        try:
            conn = conectar(); cur = conn.cursor()
            cur.execute("""INSERT INTO registros 
                (fecha, hora, tipo, cant_izq, cant_der, presion_alta, presion_baja, pulso, glucosa, observaciones, usuario) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                (request.form.get("fecha"), request.form.get("hora"), request.form.get("tipo_registro"),
                 request.form.get("cantidad_izq") or None, request.form.get("cantidad_der") or None,
                 request.form.get("presion_alta") or None, request.form.get("presion_baja") or None,
                 request.form.get("pulso") or None, request.form.get("glucosa") or None,
                 request.form.get("observaciones"), session["usuario"]))
            conn.commit(); cur.close(); conn.close()
            success = "✅ Guardado"
        except Exception as e:
            return f"Error al guardar: {str(e)}", 500
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

@app.route("/reporte-pdf")
def descargar_pdf():
    if "usuario" not in session: return redirect(url_for("login"))
    try:
        dias = request.args.get('dias', default=7, type=int)
        tipo_f = request.args.get('tipo', default='todos')
        limite = datetime.now() - timedelta(days=dias)
        
        conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM perfil WHERE usuario = %s", (session["usuario"],))
        p = cur.fetchone()
        
        query = "SELECT * FROM registros WHERE usuario = %s AND fecha::date >= %s"
        params = [session["usuario"], limite.date()]
        if tipo_f != 'todos':
            query += " AND tipo = %s"
            params.append(tipo_f)
        query += " ORDER BY fecha DESC, hora DESC"
        cur.execute(query, params)
        registros = cur.fetchall()
        cur.close(); conn.close()

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        
        # --- ENCABEZADO: FICHA INDIVIDUAL ---
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 760, "FICHA DE CONTROL MÉDICO")
        c.setFont("Helvetica", 10)
        if p:
            c.drawString(50, 745, f"Paciente: {p['nombre_apellido']} | Edad: {p['edad']} | Sexo: {p['sexo']}")
            c.drawString(50, 730, f"Peso: {p['peso']} kg | Obra Social: {p['obra_social']}")
            c.drawString(50, 715, f"Médico: {p['nombre_medico']}")
        else:
            c.drawString(50, 745, "Paciente: (Completar perfil en la App)")
        
        c.line(50, 710, 550, 710)
        y = 680
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"REPORTE DE {tipo_f.upper()} - ÚLTIMOS {dias} DÍAS")
        y -= 25
        
        c.setFont("Helvetica", 9)
        for r in registros:
            if y < 50: c.showPage(); y = 750
            info = f"[{r['fecha']}] "
            if r['tipo'] == 'drenaje': info += f"💧 Drenaje: I:{r['cant_izq'] or 0}ml D:{r['cant_der'] or 0}ml"
            elif r['tipo'] == 'presion': info += f"❤️ Presión: {r['presion_alta']}/{r['presion_baja']} P:{r['pulso']}"
            else: info += f"🩸 Glucosa: {r['glucosa']} mg/dL"
            
            c.drawString(50, y, info)
            y -= 15
        c.save(); buf.seek(0)
        resp = make_response(buf.read())
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename=Reporte_Salud.pdf'
        return resp
    except Exception as e: return str(e), 500

@app.route("/borrar/<int:id>")
def borrar(id):
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor()
    cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("ver_registros"))

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