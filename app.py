from flask import Flask, render_template, request, redirect
import os
from werkzeug.utils import secure_filename
import sqlite3 


def conectar():
    conexion = sqlite3.connect("armario.db")
    conexion.row_factory = sqlite3.Row
    return conexion

def crear_tabla():
    conexion = conectar()
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS prendas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        tipo TEXT,
        color TEXT,
        ocasion TEXT,
        foto TEXT)
        """)
    conexion.commit()
    conexion.close()


app = Flask (__name__)
CARPETA_FOTOS = os.path.join("static", "uploads")
os.makedirs(CARPETA_FOTOS, exist_ok=True)


@app.route("/")
def inicio():
    return render_template("index.html") 

@app.route("/prendas")
def prendas():
    conexion = conectar()
    lista_prendas = conexion.execute("SELECT * FROM prendas").fetchall()
    conexion.close()
    return render_template("prendas.html" , prendas=lista_prendas)


@app.route("/subir", methods=["GET","POST"])
def subir():
    if request.method=="POST":
        foto = request.files["foto"]
        nombre_archivo = secure_filename(foto.filename)
        foto.save(os.path.join(CARPETA_FOTOS, nombre_archivo))

        conexion = conectar()
        conexion.execute(
            "INSERT INTO prendas (nombre, tipo, color, ocasion, foto) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["nombre"],
                request.form["tipo"],
                request.form["color"],
                request.form["ocasion"],
                "uploads/"+ nombre_archivo
            )
        )
        conexion.commit()
        conexion.close()
        return redirect("/prendas")


    return render_template("subir.html")

@app.route("/borrar/<int:id>", methods=["POST"])
def borrar(id):
    conexion = conectar()
    conexion.execute(
        "DELETE FROM prendas WHERE id=?", (id,)
    )

    conexion.commit()
    conexion.close()
    return redirect("/prendas")


@app.route("/editar/<int:id>", methods=["GET","POST"])
def editar(id):
    if request.method=="POST":
        conexion = conectar()
        conexion.execute(
            "UPDATE prendas SET nombre = ?,tipo = ?, color = ?, ocasion = ? WHERE id = ?",
            (   request.form["nombre"],
                request.form["tipo"],
                request.form["color"],
                request.form["ocasion"],
                id)
            )
        conexion.commit()
        conexion.close()
        return redirect("/prendas")

    conexion = conectar()
    prenda = conexion.execute(
        "SELECT * FROM prendas WHERE id=?",(id,)).fetchone()
    conexion.close()
    return render_template("/editar.html", prenda=prenda)
    
        

crear_tabla()
app.run(debug=True)
