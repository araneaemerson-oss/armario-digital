from flask import Flask, render_template, request, redirect, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
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
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS usuarios(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        correo TEXT UNIQUE,
        contrasena_hash TEXT)
        """)

    # Si la tabla prendas todavía no tiene la columna usuario_id, la agregamos
    columnas = []
    for columna in conexion.execute("PRAGMA table_info(prendas)").fetchall():
        columnas.append(columna["name"])
    if "usuario_id" not in columnas:
        conexion.execute("ALTER TABLE prendas ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)")

    conexion.commit()
    conexion.close()


app = Flask(__name__)
# Clave que Flask necesita para los mensajes "flash".
# Más adelante, cuando subamos la app a internet, la pasaremos al archivo .env
app.secret_key = os.environ.get("SECRET_KEY", "clave-de-desarrollo-armario")

# ---------- Listas de opciones (en UN solo lugar) ----------
# Para agregar un tipo nuevo, solo agrega una línea aquí 👇
TIPOS = [
    {"valor": "Camisa",     "plural": "Camisas",     "icono": "👕"},
    {"valor": "Blusa",      "plural": "Blusas",      "icono": "👚"},
    {"valor": "Pantalón",   "plural": "Pantalones",  "icono": "👖"},
    {"valor": "Short",      "plural": "Shorts",      "icono": "🩳"},
    {"valor": "Vestido",    "plural": "Vestidos",    "icono": "👗"},
    {"valor": "Falda",      "plural": "Faldas",      "icono": "🎀"},
    {"valor": "Chaqueta",   "plural": "Chaquetas",   "icono": "🧥"},
    {"valor": "Zapatos",    "plural": "Zapatos",     "icono": "👟"},
    {"valor": "Tacos",      "plural": "Tacos",       "icono": "👠"},
    {"valor": "Bolso",      "plural": "Bolsos",      "icono": "👜"},
    {"valor": "Accesorios", "plural": "Accesorios",  "icono": "🧢"},
]
OCASIONES = ["Casual", "Formal", "Fiesta", "Deporte"]


# Esto hace que TIPOS y OCASIONES se puedan usar en TODOS los templates
@app.context_processor
def datos_globales():
    return {"TIPOS": TIPOS, "OCASIONES": OCASIONES}


CARPETA_FOTOS = os.path.join("static", "uploads")
os.makedirs(CARPETA_FOTOS, exist_ok=True)

# Solo aceptamos fotos, y de máximo 10 MB
EXTENSIONES_PERMITIDAS = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def es_foto_valida(foto):
    # ¿Llegó un archivo y termina en .jpg, .png, etc.?
    if foto is None or foto.filename == "":
        return False
    extension = os.path.splitext(foto.filename)[1].lower()
    return extension in EXTENSIONES_PERMITIDAS

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


# ---------- Proteger las páginas: hay que iniciar sesión ----------
PAGINAS_LIBRES = ["entrar", "registro", "static"]

@app.before_request
def pedir_inicio_de_sesion():
    # Esto se ejecuta ANTES de cada página
    if request.endpoint not in PAGINAS_LIBRES and "usuario_id" not in session:
        return redirect("/entrar")


def leer_formulario_prenda():
    # Lee los datos del formulario (Subir y Editar usan este mismo código ♻️)
    tipo = request.form.get("tipo", "")
    ocasion = request.form.get("ocasion", "")
    color = request.form.get("color", "").strip().capitalize()
    nombre = request.form.get("nombre", "").strip()

    tipos_validos = []
    for t in TIPOS:
        tipos_validos.append(t["valor"])
    if tipo not in tipos_validos or ocasion not in OCASIONES:
        return None                       # alguien mandó datos raros

    if nombre == "":                      # nombre opcional: lo armamos solos
        nombre = tipo + " " + color.lower()
    return {"nombre": nombre, "tipo": tipo, "color": color, "ocasion": ocasion}


@app.route("/")
def inicio():
    conexion = conectar()
    lista_prendas =  conexion.execute(
        "SELECT * FROM prendas WHERE usuario_id = ?", (session["usuario_id"],)
    ).fetchall()
    conexion.close()
    conteo = {}
    for tipo in TIPOS:
        conteo[tipo["valor"]] = 0          # cada tipo empieza en 0
    for prenda in lista_prendas:
        if prenda["tipo"] in conteo:       # por si hay un tipo viejo que ya no está en la lista
            conteo[prenda["tipo"]] += 1
    return render_template("index.html", total=len(lista_prendas), conteo=conteo) 

@app.route("/prendas")
def prendas():
    tipo = request.args.get("tipo")
    conexion = conectar()

    if tipo:
        lista_prendas = conexion.execute(
            "SELECT * FROM prendas WHERE usuario_id = ? AND tipo = ?", (session["usuario_id"], tipo)).fetchall()
    else:
        lista_prendas = conexion.execute(
            "SELECT * FROM prendas WHERE usuario_id = ?", (session["usuario_id"],)).fetchall()

    # ¿Qué tipos de prenda tiene este usuario? (DISTINCT = sin repetir)
    tipos_usados = []
    for fila in conexion.execute(
            "SELECT DISTINCT tipo FROM prendas WHERE usuario_id = ?", (session["usuario_id"],)).fetchall():
        tipos_usados.append(fila["tipo"])

    conexion.close()
    return render_template("prendas.html" , prendas=lista_prendas, tipo_actual=tipo, tipos_usados=tipos_usados)


@app.route("/subir", methods=["GET","POST"])
def subir():
    if request.method=="POST":
        datos = leer_formulario_prenda()
        if datos is None:
            flash("⚠️ Revisa el tipo y la ocasión de la prenda")
            return redirect("/subir")

        foto = request.files.get("foto")
        if not es_foto_valida(foto):
            flash("⚠️ Elige una foto en formato JPG, PNG o WEBP")
            return redirect("/subir")
        ruta_foto = guardar_foto(foto)

        conexion = conectar()
        conexion.execute(
            "INSERT INTO prendas (nombre, tipo, color, ocasion, foto, usuario_id) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datos["nombre"],
                datos["tipo"],
                datos["color"],
                datos["ocasion"],
                ruta_foto,
                session["usuario_id"]       # 👤 la prenda es de quien inició sesión
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
    prenda = conexion.execute(
        "SELECT foto FROM prendas WHERE id=? AND usuario_id=?", (id, session["usuario_id"])).fetchone()
    conexion.execute(
        "DELETE FROM prendas WHERE id=? AND usuario_id=?", (id, session["usuario_id"])
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
        "SELECT * FROM prendas WHERE id=? AND usuario_id=?",(id, session["usuario_id"])).fetchone()

    if prenda is None:
        conexion.close()
        flash("⚠️ Esa prenda no existe")
        return redirect("/prendas")

    if request.method=="POST":
        datos = leer_formulario_prenda()
        if datos is None:
            conexion.close()
            flash("⚠️ Revisa el tipo y la ocasión de la prenda")
            return redirect(f"/editar/{id}")

        ruta_foto = prenda["foto"]          # por defecto se queda la foto de antes
        foto_nueva = request.files.get("foto")
        if foto_nueva and foto_nueva.filename != "":
            if not es_foto_valida(foto_nueva):
                conexion.close()
                flash("⚠️ Elige una foto en formato JPG, PNG o WEBP")
                return redirect(f"/editar/{id}")
            ruta_foto = guardar_foto(foto_nueva)    # guardamos la nueva
            borrar_foto_del_disco(prenda["foto"])   # y borramos la vieja

        conexion.execute(
            "UPDATE prendas SET nombre = ?, tipo = ?, color = ?, ocasion = ?, foto = ? WHERE id = ?",
            (   datos["nombre"],
                datos["tipo"],
                datos["color"],
                datos["ocasion"],
                ruta_foto,
                id)
            )
        conexion.commit()
        conexion.close()
        flash("✏️ Cambios guardados")
        return redirect("/prendas")

    conexion.close()
    return render_template("editar.html", prenda=prenda)
    
        

# ---------- Usuarios: registro, entrar y salir ----------
@app.route("/registro", methods=["GET","POST"])
def registro():
    if "usuario_id" in session:
        return redirect("/")
    if request.method=="POST":
        nombre = request.form["nombre"].strip().title()     # "fabricio aranea" → "Fabricio Aranea"
        correo = request.form["correo"].strip().lower()
        contrasena = request.form["contrasena"]

        if len(contrasena) < 6:
            flash("⚠️ La contraseña debe tener al menos 6 caracteres")
            return render_template("registro.html", nombre=nombre, correo=correo)

        conexion = conectar()
        try:
            cursor = conexion.execute(
                "INSERT INTO usuarios (nombre, correo, contrasena_hash) VALUES (?, ?, ?)",
                (nombre, correo, generate_password_hash(contrasena))   # 🔐 guardamos el hash, nunca la contraseña
            )
            # Si eres el PRIMER usuario, te quedas con las prendas que ya existían sin dueño
            if cursor.lastrowid == conexion.execute("SELECT MIN(id) FROM usuarios").fetchone()[0]:
                conexion.execute("UPDATE prendas SET usuario_id = ? WHERE usuario_id IS NULL", (cursor.lastrowid,))
            conexion.commit()
        except sqlite3.IntegrityError:          # pasa cuando el correo ya existe (por el UNIQUE)
            conexion.close()
            flash("⚠️ Ya existe una cuenta con ese correo")
            return render_template("registro.html", nombre=nombre, correo=correo)
        conexion.close()

        # Al crear la cuenta, la dejamos con la sesión iniciada
        session["usuario_id"] = cursor.lastrowid
        session["usuario_nombre"] = nombre
        flash(f"🎉 ¡Bienvenido, {nombre}! Tu cuenta fue creada")
        return redirect("/")

    return render_template("registro.html")


@app.route("/entrar", methods=["GET","POST"])
def entrar():
    if "usuario_id" in session:
        return redirect("/")
    if request.method=="POST":
        correo = request.form["correo"].strip().lower()
        contrasena = request.form["contrasena"]

        conexion = conectar()
        usuario = conexion.execute("SELECT * FROM usuarios WHERE correo = ?", (correo,)).fetchone()
        conexion.close()

        if usuario and check_password_hash(usuario["contrasena_hash"], contrasena):
            session["usuario_id"] = usuario["id"]
            session["usuario_nombre"] = usuario["nombre"]
            flash(f"👋 ¡Hola de nuevo, {usuario['nombre']}!")
            return redirect("/")

        flash("⚠️ Correo o contraseña incorrectos")
        return render_template("entrar.html", correo=correo)

    return render_template("entrar.html")


@app.route("/salir")
def salir():
    session.clear()      # borramos los datos de la sesión
    flash("👋 Cerraste sesión. ¡Vuelve pronto!")
    return redirect("/entrar")


@app.route("/probador")
def probador():
    return render_template("probador.html")


# ---------- Páginas de error ----------
@app.errorhandler(404)
def pagina_no_encontrada(error):
    return render_template("404.html"), 404

@app.errorhandler(413)
def archivo_muy_grande(error):
    flash("⚠️ La foto es muy pesada. El máximo es 10 MB")
    return redirect(request.path)


crear_tabla()
app.run(debug=True)
