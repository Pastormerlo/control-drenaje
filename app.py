from flask import Flask, render_template, request, redirect
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
            # Cambiamos INTEGER por FLOAT para permitir decimales
            cur.execute("""
                CREATE TABLE IF NOT EXISTS registros (
                    id SERIAL PRIMARY KEY,
                    fecha TEXT,
                    hora TEXT,
                    cantidad_izq FLOAT,
                    cantidad_der FLOAT,
                    observaciones TEXT
                )
            """)
        con.commit()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        fecha = request.form["fecha"]
        hora = request.form["hora"]
        # Usamos float() para convertir el texto a número decimal
        # Reemplazamos la coma por punto por si escribes con coma
        izq = float(request.form["cantidad_izq"].replace(',', '.'))
        der = float(request.form["cantidad_der"].replace(',', '.'))
        observaciones = request.form["observaciones"]

        with conectar() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO registros 
                    (fecha, hora, cantidad_izq, cantidad_der, observaciones)
                    VALUES (%s, %s, %s, %s, %s)
                """, (fecha, hora, izq, der, observaciones))
            con.commit()
        return redirect("/")

    con = conectar()
    cur = con.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM registros ORDER BY fecha DESC, hora DESC")
    registros = cur.fetchall()
    cur.close()
    con.close()
    return render_template("index.html", registros=registros)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)