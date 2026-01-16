from flask import Flask, render_template, request, redirect
import sqlite3
import os

base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=os.path.join(base_dir, 'templates'))

# Ruta a la base de datos
DB = os.path.join(base_dir, "drenaje.db")

def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

# Esta función se ejecuta automáticamente antes de procesar cualquier página
@app.before_request
def inicializar_db():
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

    # Si la tabla no existe por algún motivo, el before_request ya la habrá creado aquí
    con = conectar()
    registros = con.execute("SELECT * FROM registros ORDER BY fecha DESC, hora DESC").fetchall()
    con.close()
    return render_template("index.html", registros=registros)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)