from flask import Flask, render_template, request, redirect, flash
import os, uuid
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


app = Flask(__name__)
# Clave que Flask necesita para los mensajes "flash".
# Más adelante, cuando subamos la app a internet, la pasaremos al archivo .env
app.secret_key = os.environ.get("SECRET_KEY", "clave-de-desarrollo-armario")

CARPETA_FOTOS = os.path.join("static", "uploads")
os.makedirs(CARPETA_FOTOS, exist_ok=True)


def guardar_foto(foto):
    # Guarda la foto con un nombre único y devuelve la ruta para la base de datos
    nombre_archivo = uuid.uuid4().hex + "_" + secure_filename(foto.filename)
    foto.save(os.path.join(CARPETA_FOTOS, nombre_archivo))
    return "uploads/" + nombre_archivo

def borrar_foto_del_disco(ruta_foto):
    # Borra el archivo de la foto (si existe) de la carpeta static/uploads
    if ruta_foto:
        ruta_completa = os.path.join("static", ruta_foto)
        if os.path.exists(ruta_completa):
            os.remove(ruta_completa)


@app.route("/")
def inicio():
    conexion = conectar()
    lista_prendas =  conexion.execute(
        "SELECT * FROM prendas"
    ).fetchall()
    conexion.close()
    conteo = {"Camisa": 0, "Pantalón": 0, "Zapatos": 0, "Accesorios": 0}
    for prenda in lista_prendas:
        conteo[prenda["tipo"]] += 1
    return render_template("index.html", total=len(lista_prendas), conteo=conteo) 

@app.route("/prendas")
def prendas():
    tipo = request.args.get("tipo")
    conexion = conectar()

    if tipo:
        lista_prendas = conexion.execute("SELECT * FROM prendas WHERE tipo = ?",(tipo,)).fetchall()
    else:
        lista_prendas = conexion.execute("SELECT * FROM prendas").fetchall()
    conexion.close()
    return render_template("prendas.html" , prendas=lista_prendas, tipo_actual=tipo)


@app.route("/subir", methods=["GET","POST"])
def subir():
    if request.method=="POST":
        ruta_foto = guardar_foto(request.files["foto"])

        conexion = conectar()
        conexion.execute(
            "INSERT INTO prendas (nombre, tipo, color, ocasion, foto) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["nombre"].strip(),
                request.form["tipo"],
                request.form["color"].strip().capitalize(),
                request.form["ocasion"],
                ruta_foto
            )
        )
        conexion.commit()
        conexion.close()
        flash("✅ Prenda guardada en tu armario")
        return redirect("/prendas")


    return render_template("subir.html")

@app.route("/borrar/<int:id>", methods=["POST"])
def borrar(id):
    conexion = conectar()
    prenda = conexion.execute("SELECT foto FROM prendas WHERE id=?", (id,)).fetchone()
    conexion.execute(
        "DELETE FROM prendas WHERE id=?", (id,)
    )
    conexion.commit()
    conexion.close()

    if prenda:
        borrar_foto_del_disco(prenda["foto"])
    flash("🗑️ Prenda borrada")
    return redirect("/prendas")


@app.route("/editar/<int:id>", methods=["GET","POST"])
def editar(id):
    conexion = conectar()
    prenda = conexion.execute(
        "SELECT * FROM prendas WHERE id=?",(id,)).fetchone()

    if prenda is None:
        conexion.close()
        flash("⚠️ Esa prenda no existe")
        return redirect("/prendas")

    if request.method=="POST":
        ruta_foto = prenda["foto"]          # por defecto se queda la foto de antes
        foto_nueva = request.files.get("foto")
        if foto_nueva and foto_nueva.filename != "":
            ruta_foto = guardar_foto(foto_nueva)    # guardamos la nueva
            borrar_foto_del_disco(prenda["foto"])   # y borramos la vieja

        conexion.execute(
            "UPDATE prendas SET nombre = ?, tipo = ?, color = ?, ocasion = ?, foto = ? WHERE id = ?",
            (   request.form["nombre"].strip(),
                request.form["tipo"],
                request.form["color"].strip().capitalize(),
                request.form["ocasion"],
                ruta_foto,
                id)
            )
        conexion.commit()
        conexion.close()
        flash("✏️ Cambios guardados")
        return redirect("/prendas")

    conexion.close()
    return render_template("editar.html", prenda=prenda)
    
        

crear_tabla()
app.run(debug=True)
