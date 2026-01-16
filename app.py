from flask import Flask, render_template, request, redirect
import sqlite3
import os

# Configuración de rutas absoluta para evitar el Error 500 en Render
base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, 
            template_folder=os.path.join(base_dir, 'templates'))

# Guardamos la DB en la carpeta /tmp de Render para asegurar permisos de escritura
# (Recuerda que esto es temporal y se borra al reiniciar)
DB = os.path.join(base_dir, "drenaje.db")

def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def inicializar_db():
    try:
        with conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT,
                    hora TEXT,
                    cantidad_izq INTEGER,
                    cantidad_der INTEGER,
                    observaciones TEXT
                )
            """)
    except Exception as e:
        print(f"Error inicializando DB: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        fecha = request.form.get("fecha")
        hora = request.form.get("hora")
        izq = request.form.get("cantidad_izq")
        der = request.form.get("cantidad_der")
        observaciones = request.form.get("observaciones")

        with conectar() as con:
            con.execute("""
                INSERT INTO registros 
                (fecha, hora, cantidad_izq, cantidad_der, observaciones)
                VALUES (?, ?, ?, ?, ?)
            """, (fecha, hora, izq, der, observaciones))
        return redirect("/")

    try:
        con = conectar()
        registros = con.execute("SELECT * FROM registros ORDER BY fecha DESC, hora DESC").fetchall()
        con.close()
        return render_template("index.html", registros=registros)
    except Exception as e:
        return f"Error en el servidor: {str(e)}"

if __name__ == "__main__":
    inicializar_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)