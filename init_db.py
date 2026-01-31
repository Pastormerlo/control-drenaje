import sqlite3

con = sqlite3.connect("database.db")
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

con.commit()
con.close()

print("DB OK")

