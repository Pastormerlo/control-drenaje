from flask import Flask, render_template, request, redirect
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)

# Configuración de la base de datos desde la variable de entorno de Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def conectar():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

@app.before_request
def inicializar_db():
    with conectar() as con:
        with con.cursor() as cur:
            # 1. BORRAMOS LA TABLA VIEJA (Solo una vez para limpiar el error)
            # Esta línea soluciona el problema de "UndefinedColumn" y el bloqueo de decimales
            cur.execute("DROP TABLE IF EXISTS registros CASCADE")
            
            # 2. CREAMOS LA TABLA NUEVA con soporte para decimales (FLOAT)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS registros (
                    id SERIAL PRIMARY KEY,
                    fecha TEXT,
                    hora TEXT,
                    cant_izq FLOAT,
                    cant_der FLOAT,
                    observaciones TEXT
                )
            """)
        con.commit()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        fecha = request.form["fecha"]
        hora = request.form["hora"]
        
        # Recibimos los datos y reemplazamos la coma por punto para que Python no falle
        try:
            izq = float(request.form["cantidad_izq"].replace(',', '.'))
            der = float(request.form["cantidad_der"].replace(',', '.'))
        except ValueError:
            izq = 0.0
            der = 0.0
            
        observaciones = request.form["observaciones"]

        with conectar() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO registros 
                    (fecha, hora, cant_izq, cant_der, observaciones)
                    VALUES (%s, %s, %s, %s, %s)
                """, (fecha, hora, izq, der, observaciones))
            con.commit()
        return redirect("/")

    # Consultamos los datos para mostrar en la tabla
    con = conectar()
    cur = con.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT fecha, hora, cant_izq, cant_der, observaciones FROM registros ORDER BY fecha DESC, hora DESC")
    registros = cur.fetchall()
    cur.close()
    con.close()
    
    return render_template("index.html", registros=registros)

if __name__ == "__main__":
    # Render usa un puerto dinámico, lo leemos de la variable de entorno
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)