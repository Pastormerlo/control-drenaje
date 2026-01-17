from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

@app.before_request
def inicializar_db():
    with conectar() as con:
        with con.cursor() as cur:
            # Creamos una tabla totalmente nueva para evitar conflictos de columnas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS registros_v2 (
                    id SERIAL PRIMARY KEY,
                    fecha TEXT,
                    hora TEXT,
                    cant_izq FLOAT,
                    cant_der FLOAT,
                    observaciones TEXT,
                    quien TEXT
                )
            """)
        con.commit()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            fecha = request.form.get("fecha")
            hora = request.form.get("hora")
            quien = request.form.get("quien")
            izq = float(request.form.get("cantidad_izq", 0).replace(',', '.'))
            der = float(request.form.get("cantidad_der", 0).replace(',', '.'))
            obs = request.form.get("observaciones", "")

            with conectar() as con:
                with con.cursor() as cur:
                    cur.execute("""
                        INSERT INTO registros_v2 (fecha, hora, cant_izq, cant_der, observaciones, quien)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (fecha, hora, izq, der, obs, quien))
                con.commit()
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error crítico al guardar: {e}"

    try:
        con = conectar()
        cur = con.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM registros_v2 ORDER BY fecha DESC, hora DESC")
        registros = cur.fetchall()
        cur.close()
        con.close()
        return render_template("index.html", registros=registros)
    except Exception as e:
        return f"Error al leer la base de datos: {e}"

@app.route("/borrar/<int:id>")
def borrar(id):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM registros_v2 WHERE id = %s", (id,))
        con.commit()
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)