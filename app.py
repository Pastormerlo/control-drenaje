import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

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
        cur.execute("CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE, password TEXT);")
        cur.execute("""CREATE TABLE IF NOT EXISTS perfil (
            id SERIAL PRIMARY KEY, usuario VARCHAR(50) UNIQUE, nombre_apellido VARCHAR(100),
            edad INTEGER, sexo VARCHAR(20), peso DECIMAL(5,2), nombre_medico VARCHAR(100), obra_social VARCHAR(100)
        );""")
        cur.execute("""CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY, fecha DATE, hora TIME, tipo VARCHAR(50), 
            cant_izq DECIMAL(5,2), cant_der DECIMAL(5,2), presion_alta INTEGER, 
            presion_baja INTEGER, pulso INTEGER, glucosa INTEGER, 
            oxigeno INTEGER, temperatura DECIMAL(4,1), observaciones TEXT, usuario VARCHAR(50)
        );""")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: print(f"Error inicializando: {e}")

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
                return redirect(url_for("ver_registros"))
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
            flash("Cuenta creada correctamente.", "success")
            return redirect(url_for("login"))
        except: flash("El usuario ya existe", "danger")
    return render_template("register.html")

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
        success = "✅ Registro guardado"
    return render_template("index.html", modo="cargar", success=success, usuario=session["usuario"])

@app.route("/ver")
def ver_registros():
    if "usuario" not in session: return redirect(url_for("login"))
    conn = conectar(); cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM registros WHERE usuario = %s ORDER BY fecha DESC, hora DESC LIMIT 50", (session["usuario"],))
    regs = cur.fetchall()
    
    hace_30 = datetime.now() - timedelta(days=30)
    cur.execute("SELECT * FROM registros WHERE usuario = %s AND fecha >= %s", (session["usuario"], hace_30.date()))
    r_stats = cur.fetchall()
    
    stats = {
        'glucosa': {'prom':0, 'max':0, 'min':999, 'alertas':0, 'count':0},
        'presion': {'prom_a':0, 'prom_b':0, 'max_a':0, 'min_a':999, 'alertas':0, 'count':0},
        'pulso': {'prom':0},
        'oxigeno': {'prom':0, 'max':0, 'min':100, 'alertas':0, 'count':0},
        'temp': {'prom':0, 'max':0, 'min':99, 'alertas':0, 'count':0}
    }
    
    for r in r_stats:
        if r['tipo'] == 'glucosa' and r['glucosa']:
            v = r['glucosa']; stats['glucosa']['count'] += 1; stats['glucosa']['prom'] += v
            if v > stats['glucosa']['max']: stats['glucosa']['max'] = v
            if v < stats['glucosa']['min']: stats['glucosa']['min'] = v
            if v > 140 or v < 70: stats['glucosa']['alertas'] += 1
        elif r['tipo'] == 'presion':
            if r['presion_alta'] and r['presion_baja']:
                stats['presion']['count'] += 1
                stats['presion']['prom_a'] += r['presion_alta']; stats['presion']['prom_b'] += r['presion_baja']
                if r['presion_alta'] > stats['presion']['max_a']: stats['presion']['max_a'] = r['presion_alta']
                if r['presion_alta'] < stats['presion']['min_a']: stats['presion']['min_a'] = r['presion_alta']
                if r['presion_alta'] >= 140 or r['presion_baja'] >= 90: stats['presion']['alertas'] += 1
            if r['pulso']: stats['pulso']['prom'] += r['pulso']
        elif r['tipo'] == 'oxigeno' and r['oxigeno']:
            v = r['oxigeno']; stats['oxigeno']['count'] += 1; stats['oxigeno']['prom'] += v
            if v > stats['oxigeno']['max']: stats['oxigeno']['max'] = v
            if v < stats['oxigeno']['min']: stats['oxigeno']['min'] = v
            if v < 95: stats['oxigeno']['alertas'] += 1
        elif r['tipo'] == 'temperatura' and r['temperatura']:
            v = float(r['temperatura']); stats['temp']['count'] += 1; stats['temp']['prom'] += v
            if v > stats['temp']['max']: stats['temp']['max'] = v
            if v < stats['temp']['min']: stats['temp']['min'] = v
            if v >= 37.5: stats['temp']['alertas'] += 1

    # Limpieza de cálculos
    if stats['glucosa']['count'] > 0: stats['glucosa']['prom'] //= stats['glucosa']['count']
    else: stats['glucosa']['min'] = 0
    if stats['presion']['count'] > 0:
        stats['presion']['prom_a'] //= stats['presion']['count']; stats['presion']['prom_b'] //= stats['presion']['count']
        stats['pulso']['prom'] //= stats['presion']['count']
    if stats['oxigeno']['count'] > 0: stats['oxigeno']['prom'] //= stats['oxigeno']['count']
    else: stats['oxigeno']['min'] = 0
    if stats['temp']['count'] > 0: stats['temp']['prom'] = round(stats['temp']['prom'] / stats['temp']['count'], 1)

    cur.close(); conn.close()
    return render_template("index.html", registros=regs, stats=stats, modo="ver", usuario=session["usuario"])

@app.route("/mi-ficha", methods=["GET", "POST"])
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
        conn.commit(); flash("Ficha actualizada", "success")
    cur.execute("SELECT * FROM perfil WHERE usuario = %s", (session["usuario"],))
    perfil = cur.fetchone()
    cur.close(); conn.close()
    return render_template("index.html", modo="perfil", perfil=perfil, usuario=session["usuario"])

@app.route("/borrar/<int:id>")
def borrar(id):
    conn = conectar(); cur = conn.cursor()
    cur.execute("DELETE FROM registros WHERE id = %s AND usuario = %s", (id, session["usuario"]))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("ver_registros"))

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))