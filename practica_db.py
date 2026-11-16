import sqlite3

conexion = sqlite3.connect("armario.db")
cursor = conexion.cursor()

cursor.execute ("""
    CREATE TABLE IF NOT EXISTS prendas(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    tipo TEXT,
    color TEXT,
    ocasion TEXT,
    foto TEXT)
""")


cursor.execute(
    "INSERT INTO prendas(nombre,tipo,color,ocasion) VALUES(?, ?, ?, ?)",
    ("camisa zara ", "camisa", "blanca", "formal")

)

cursor.execute(
    "INSERT INTO prendas(nombre,tipo,color,ocasion) VALUES(?, ?, ?, ?)",
    ("panatalon vintage", "pantalon", "negro", "formal ")
)

conexion.commit()
conexion.close()
print("¡PRENDA GUARDADA!")