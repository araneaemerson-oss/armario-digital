import sqlite3

conexion = sqlite3.connect("armario.db")
cursor = conexion.cursor()

cursor.execute("SELECT * FROM prendas")
prendas = cursor.fetchall()

for prenda in prendas:
    print(prenda[1])

conexion.close()