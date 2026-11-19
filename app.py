from flask import Flask, render_template, request, redirect, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os, uuid, random, colorsys
from werkzeug.utils import secure_filename
import sqlite3 

import importlib.util

# rembg quita el fondo de las fotos con IA. Si no está instalado, la app sigue funcionando igual.
# Solo REVISAMOS si está instalado (es rapidísimo). Lo cargamos de verdad la primera vez que se usa,
# porque cargarlo tarda bastante y no queremos que la app demore en arrancar.
REMBG_DISPONIBLE = importlib.util.find_spec("rembg") is not None
sesion_rembg = None


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

    # Outfits: un conjunto de prendas con nombre y ocasión
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS outfits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        ocasion TEXT,
        usuario_id INTEGER REFERENCES usuarios(id))
        """)
    # Tabla "puente": qué prendas tiene cada outfit (relación muchos a muchos)
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS outfit_prendas(
        outfit_id INTEGER REFERENCES outfits(id),
        prenda_id INTEGER REFERENCES prendas(id))
        """)

    # Si la tabla prendas todavía no tiene la columna usuario_id, la agregamos
    columnas = []
    for columna in conexion.execute("PRAGMA table_info(prendas)").fetchall():
        columnas.append(columna["name"])
    if "usuario_id" not in columnas:
        conexion.execute("ALTER TABLE prendas ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)")

    # Corrige los nombres automáticos viejos que quedaron mal ("Camisa blanco" → "Camisa blanca")
    for prenda in conexion.execute("SELECT id, nombre, tipo, color FROM prendas").fetchall():
        if prenda["tipo"] and prenda["color"] and prenda["nombre"] == prenda["tipo"] + " " + prenda["color"].lower():
            nuevo = (prenda["tipo"] + " " + concordar_color(prenda["tipo"], prenda["color"])).strip()
            conexion.execute("UPDATE prendas SET nombre=? WHERE id=?", (nuevo, prenda["id"]))

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

# Para escribir bien el nombre automático: "Camisa blanca", "Zapatos negros", "Pantalón azul"
TIPOS_FEMENINOS = ["Camisa", "Blusa", "Chaqueta", "Falda"]
TIPOS_PLURALES = ["Zapatos", "Tacos", "Accesorios"]
COLORES_INVARIABLES = ["beige", "rosa", "naranja", "lila", "fucsia", "turquesa", "crema",
                       "vino", "café", "mostaza", "coral", "caqui", "nude", "oro", "plata"]

def concordar_color(tipo, color):
    # Cambia la primera palabra del color según el tipo: blanco → blanca / blancos
    palabras = color.lower().split()
    if not palabras:
        return ""
    c = palabras[0]
    if c not in COLORES_INVARIABLES:
        if tipo in TIPOS_FEMENINOS and c.endswith("o"):
            c = c[:-1] + "a"                       # negro → negra
        if tipo in TIPOS_PLURALES:
            if c.endswith(("a", "e", "o")):
                c = c + "s"                        # negro → negros
            elif c.endswith("ón"):
                c = c[:-2] + "ones"                # marrón → marrones
            elif c.endswith("z"):
                c = c[:-1] + "ces"
            else:
                c = c + "es"                       # azul → azules, gris → grises
    palabras[0] = c
    return " ".join(palabras)


# Parte del cuerpo de cada tipo: sirve para mostrar los outfits con proporciones reales
PARTE_DEL_CUERPO = {
    "Accesorios": "accesorio", "Chaqueta": "arriba", "Camisa": "arriba", "Blusa": "arriba",
    "Vestido": "vestido", "Pantalón": "abajo", "Falda": "falda", "Short": "short",
    "Bolso": "bolso", "Zapatos": "pies", "Tacos": "pies",
}

# Orden en el cuerpo, de arriba (0) hacia abajo, para mostrar los outfits como una persona vestida
ORDEN_CUERPO = {
    "Accesorios": 0, "Chaqueta": 1, "Camisa": 2, "Blusa": 2, "Vestido": 3,
    "Pantalón": 4, "Short": 4, "Falda": 4, "Bolso": 5, "Zapatos": 6, "Tacos": 6,
}


# Esto hace que TIPOS y OCASIONES se puedan usar en TODOS los templates
@app.context_processor
def datos_globales():
    return {"TIPOS": TIPOS, "OCASIONES": OCASIONES, "REMBG_DISPONIBLE": REMBG_DISPONIBLE,
            "PARTE_DEL_CUERPO": PARTE_DEL_CUERPO}


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

def quitar_fondo(bytes_imagen):
    # Recibe la imagen en bytes y devuelve un PNG sin fondo (o None si algo falla)
    global sesion_rembg
    if not REMBG_DISPONIBLE:
        return None
    try:
        from rembg import remove, new_session      # se carga aquí, solo cuando hace falta
        if sesion_rembg is None:
            sesion_rembg = new_session("isnet-general-use")   # modelo más preciso para objetos
        resultado = remove(bytes_imagen, session=sesion_rembg)
        return limpiar_recorte(resultado)
    except Exception as error:
        print("No se pudo quitar el fondo:", error)
        return None

def limpiar_recorte(bytes_png):
    # Deja el recorte más limpio:
    #  1) borra la "neblina" y el humo (píxeles medio transparentes)
    #  2) borra manchitas sueltas que no son parte de la prenda
    #  3) recorta los bordes vacíos para que la prenda ocupe toda la imagen
    import io
    from PIL import Image
    imagen = Image.open(io.BytesIO(bytes_png)).convert("RGBA")
    transparencia = imagen.getchannel("A")
    transparencia = transparencia.point(lambda valor: 0 if valor < 170 else (255 if valor > 225 else valor))

    try:
        import numpy
        from scipy import ndimage           # vienen instaladas junto con rembg
        mascara = numpy.array(transparencia) > 0
        etiquetas, cantidad = ndimage.label(mascara)      # separa las "islas" de píxeles
        if cantidad > 1:
            tamanos = ndimage.sum(mascara, etiquetas, range(1, cantidad + 1))
            grande = tamanos.max()
            # nos quedamos con las islas grandes (por ejemplo, los DOS zapatos) y borramos las chiquitas
            conservar = numpy.isin(etiquetas, [i + 1 for i, t in enumerate(tamanos) if t >= grande * 0.15])
            limpia = numpy.where(conservar, numpy.array(transparencia), 0).astype("uint8")
            transparencia = Image.fromarray(limpia)
    except ImportError:
        pass

    imagen.putalpha(transparencia)
    borde = transparencia.getbbox()          # el rectángulo donde SÍ hay prenda
    if borde:
        imagen = imagen.crop(borde)
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    return salida.getvalue()


# ---------- Color automático (gratis, sin IA) ----------
def nombre_del_color(r, g, b):
    # Convierte un color RGB en un nombre en español usando tono, saturación y brillo (HSV)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h = h * 360
    if v < 0.2:
        return "negro"
    if s < 0.15:
        if v > 0.78:
            return "blanco"
        if v < 0.32:
            return "negro"
        return "gris"
    if s < 0.38 and v > 0.6 and 15 <= h <= 55:
        return "beige"
    if h < 12 or h >= 345:
        if v < 0.45:
            return "vino"
        return "rosa" if (s < 0.5 and v > 0.7) else "rojo"
    if h < 42:
        return "café" if v < 0.6 else "naranja"
    if h < 68:
        return "mostaza" if v < 0.6 else "amarillo"
    if h < 165:
        return "verde"
    if h < 200:
        return "azul" if v < 0.5 else "celeste"
    if h < 255:
        if v < 0.38:
            return "azul marino"
        return "celeste" if (s < 0.45 and v > 0.7) else "azul"
    if h < 290:
        return "lila" if (s < 0.4 and v > 0.7) else "morado"
    return "vino" if v < 0.45 else "rosa"

def detectar_color(ruta_imagen):
    # Mira los píxeles de la prenda y "vota" por el color que más se repite
    try:
        from PIL import Image
    except ImportError:
        return ""
    try:
        imagen = Image.open(ruta_imagen).convert("RGBA")
    except Exception:
        return ""
    imagen.thumbnail((80, 80))                       # más pequeña = más rápido
    tiene_transparencia = imagen.getchannel("A").getextrema()[0] < 200
    if not tiene_transparencia:
        # Sin fondo quitado: usamos solo el centro, donde suele estar la prenda
        ancho, alto = imagen.size
        imagen = imagen.crop((ancho // 4, alto // 4, ancho * 3 // 4, alto * 3 // 4))

    votos = {}
    for r, g, b, a in imagen.getdata():
        if a < 200:
            continue                                 # ignoramos el fondo transparente
        nombre = nombre_del_color(r, g, b)
        votos[nombre] = votos.get(nombre, 0) + 1
    if not votos:
        return ""
    ganador = max(votos, key=votos.get)
    return ganador.capitalize()


def guardar_foto(foto, sin_fondo=False):
    # Guarda la foto con un nombre único y devuelve la ruta para la base de datos
    nombre_original = secure_filename(foto.filename)
    if sin_fondo:
        imagen_sin_fondo = quitar_fondo(foto.read())
        if imagen_sin_fondo:
            nombre_archivo = uuid.uuid4().hex + "_" + os.path.splitext(nombre_original)[0] + ".png"
            with open(os.path.join(CARPETA_FOTOS, nombre_archivo), "wb") as archivo:
                archivo.write(imagen_sin_fondo)
            return "uploads/" + nombre_archivo
        foto.seek(0)       # si falló, volvemos al inicio del archivo y guardamos la foto normal
    nombre_archivo = uuid.uuid4().hex + "_" + nombre_original
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

    return {"nombre": nombre, "tipo": tipo, "color": color, "ocasion": ocasion}


def completar_datos(datos, ruta_foto):
    # Si el usuario dejó el color vacío, lo detectamos de la foto 🎨
    if datos["color"] == "" and ruta_foto:
        datos["color"] = detectar_color(os.path.join("static", ruta_foto))
    # Si dejó el nombre vacío, lo armamos: "Camisa blanca" ✏️
    if datos["nombre"] == "":
        datos["nombre"] = (datos["tipo"] + " " + concordar_color(datos["tipo"], datos["color"])).strip()
    return datos


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
        ruta_foto = guardar_foto(foto, sin_fondo="sin_fondo" in request.form)
        datos = completar_datos(datos, ruta_foto)

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
    if prenda:
        # también la sacamos de los outfits donde estaba
        conexion.execute("DELETE FROM outfit_prendas WHERE prenda_id=?", (id,))
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
            ruta_foto = guardar_foto(foto_nueva, sin_fondo="sin_fondo" in request.form)    # guardamos la nueva
            borrar_foto_del_disco(prenda["foto"])   # y borramos la vieja
        datos = completar_datos(datos, ruta_foto)

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


@app.route("/quitar-fondo/<int:id>", methods=["POST"])
def quitar_fondo_prenda(id):
    # Quita el fondo de la foto de una prenda que YA estaba guardada
    conexion = conectar()
    prenda = conexion.execute(
        "SELECT * FROM prendas WHERE id=? AND usuario_id=?", (id, session["usuario_id"])).fetchone()
    if prenda is None or not prenda["foto"]:
        conexion.close()
        flash("⚠️ Esa prenda no tiene foto")
        return redirect("/prendas")

    ruta_vieja = os.path.join("static", prenda["foto"])
    with open(ruta_vieja, "rb") as archivo:
        imagen_sin_fondo = quitar_fondo(archivo.read())

    if imagen_sin_fondo is None:
        conexion.close()
        flash("⚠️ No se pudo quitar el fondo. ¿Instalaste rembg?")
        return redirect(f"/editar/{id}")

    nombre_archivo = uuid.uuid4().hex + "_sin_fondo.png"
    with open(os.path.join(CARPETA_FOTOS, nombre_archivo), "wb") as archivo:
        archivo.write(imagen_sin_fondo)
    conexion.execute("UPDATE prendas SET foto=? WHERE id=?", ("uploads/" + nombre_archivo, id))
    conexion.commit()
    conexion.close()
    borrar_foto_del_disco(prenda["foto"])
    flash("✂️ ¡Listo! Le quitamos el fondo a tu prenda")
    return redirect(f"/editar/{id}")


# ---------- Outfits ----------
@app.route("/outfits")
def outfits():
    conexion = conectar()
    lista_outfits = conexion.execute(
        "SELECT * FROM outfits WHERE usuario_id = ? ORDER BY id DESC", (session["usuario_id"],)).fetchall()

    outfits_con_prendas = []
    for outfit in lista_outfits:
        # JOIN: unimos outfit_prendas con prendas para traer los datos de cada prenda
        prendas_del_outfit = conexion.execute("""
            SELECT prendas.* FROM prendas
            JOIN outfit_prendas ON prendas.id = outfit_prendas.prenda_id
            WHERE outfit_prendas.outfit_id = ?
            """, (outfit["id"],)).fetchall()
        # Las ordenamos de arriba hacia abajo, como en el cuerpo 🧍
        prendas_ordenadas = sorted(prendas_del_outfit, key=lambda p: ORDEN_CUERPO.get(p["tipo"], 5))
        outfits_con_prendas.append({"outfit": outfit, "prendas": prendas_ordenadas})

    conexion.close()
    return render_template("outfits.html", outfits=outfits_con_prendas)


@app.route("/outfits/nuevo", methods=["GET","POST"])
def nuevo_outfit():
    conexion = conectar()
    mis_prendas = conexion.execute(
        "SELECT * FROM prendas WHERE usuario_id = ?", (session["usuario_id"],)).fetchall()

    if request.method=="POST":
        ocasion = request.form.get("ocasion", "")
        nombre = request.form.get("nombre", "").strip()
        ids_elegidos = request.form.getlist("prendas")     # getlist: trae TODAS las casillas marcadas

        # Solo aceptamos prendas que sean de este usuario
        ids_mios = []
        for prenda in mis_prendas:
            ids_mios.append(str(prenda["id"]))
        ids_validos = []
        for prenda_id in ids_elegidos:
            if prenda_id in ids_mios:
                ids_validos.append(int(prenda_id))

        if len(ids_validos) < 2:
            conexion.close()
            flash("⚠️ Elige al menos 2 prendas para armar un outfit")
            return redirect("/outfits/nuevo")
        if ocasion not in OCASIONES:
            ocasion = OCASIONES[0]
        if nombre == "":
            nombre = "Outfit " + ocasion.lower()

        cursor = conexion.execute(
            "INSERT INTO outfits (nombre, ocasion, usuario_id) VALUES (?, ?, ?)",
            (nombre, ocasion, session["usuario_id"]))
        outfit_id = cursor.lastrowid
        for prenda_id in ids_validos:
            conexion.execute(
                "INSERT INTO outfit_prendas (outfit_id, prenda_id) VALUES (?, ?)", (outfit_id, prenda_id))
        conexion.commit()
        conexion.close()
        flash("👔 Outfit guardado")
        return redirect("/outfits")

    conexion.close()
    return render_template("nuevo_outfit.html", prendas=mis_prendas)


# ---------- Sugerir outfit con reglas de moda (gratis, sin IA) ----------
COLORES_NEUTROS = ["negro", "blanco", "gris", "beige", "azul marino", "café", "crema", "nude"]

def es_neutro(color):
    return (color or "").lower() in COLORES_NEUTROS

def combinan(color1, color2):
    # Regla de moda sencilla: los neutros combinan con todo; dos colores fuertes, solo si son iguales
    return es_neutro(color1) or es_neutro(color2) or (color1 or "").lower() == (color2 or "").lower()

def elegir(candidatas, colores_elegidos):
    # De las prendas candidatas, elige al azar una que combine con TODO lo ya elegido
    buenas = []
    for prenda in candidatas:
        if all(combinan(prenda["color"], c) for c in colores_elegidos):
            buenas.append(prenda)
    if not buenas:
        buenas = candidatas                    # si ninguna combina perfecto, usamos cualquiera
    return random.choice(buenas) if buenas else None

def sugerir_outfit(prendas, ocasion):
    grupos = {"arriba": [], "abajo": [], "vestido": [], "pies": [], "chaqueta": [], "extra": []}
    grupo_de = {"Camisa": "arriba", "Blusa": "arriba", "Pantalón": "abajo", "Short": "abajo",
                "Falda": "abajo", "Vestido": "vestido", "Zapatos": "pies", "Tacos": "pies",
                "Chaqueta": "chaqueta", "Bolso": "extra", "Accesorios": "extra"}
    for prenda in prendas:
        grupo = grupo_de.get(prenda["tipo"])
        if grupo:
            grupos[grupo].append(prenda)

    def de_la_ocasion(grupo):
        # Preferimos las prendas de la ocasión elegida; si no hay, usamos todas las del grupo
        mismas = [p for p in grupos[grupo] if p["ocasion"] == ocasion]
        return mismas if mismas else grupos[grupo]

    elegidas = []
    usar_vestido = grupos["vestido"] and (not (grupos["arriba"] and grupos["abajo"]) or random.random() < 0.4)
    if usar_vestido:
        orden = ["vestido"]
    elif grupos["arriba"] and grupos["abajo"]:
        orden = ["arriba", "abajo"]
    else:
        return [], ["Te faltan prendas: necesitas una parte de arriba y una de abajo, o un vestido. 👕👖"]

    orden.append("pies")
    if ocasion == "Formal" or random.random() < 0.3:
        orden.append("chaqueta")
    if random.random() < 0.5:
        orden.append("extra")

    for grupo in orden:
        if grupos[grupo]:
            prenda = elegir(de_la_ocasion(grupo), [p["color"] for p in elegidas])
            if prenda:
                elegidas.append(prenda)

    # Explicamos por qué combina 💬
    explicacion = []
    neutros = [p["nombre"] for p in elegidas if es_neutro(p["color"])]
    con_color = [p["nombre"] for p in elegidas if not es_neutro(p["color"])]
    if con_color and neutros:
        explicacion.append("🎨 " + ", ".join(con_color) + " resalta, y lo acompañan colores neutros (" + ", ".join(neutros) + ").")
    elif neutros and not con_color:
        explicacion.append("🤍 Todo en colores neutros: elegante y fácil de combinar.")
    else:
        explicacion.append("🌈 Combinación en el mismo tono.")
    if any(p["ocasion"] == ocasion for p in elegidas):
        explicacion.append("✅ Elegimos prendas para la ocasión " + ocasion.lower() + ".")
    if not grupos["pies"]:
        explicacion.append("👟 Tip: sube unos zapatos para completar tus outfits.")
    return [p["id"] for p in elegidas], explicacion


@app.route("/outfits/sugerir")
def sugerir():
    ocasion = request.args.get("ocasion", OCASIONES[0])
    conexion = conectar()
    mis_prendas = conexion.execute(
        "SELECT * FROM prendas WHERE usuario_id = ?", (session["usuario_id"],)).fetchall()
    conexion.close()
    ids, explicacion = sugerir_outfit(mis_prendas, ocasion)
    return jsonify({"ids": ids, "explicacion": explicacion})


@app.route("/outfits/borrar/<int:id>", methods=["POST"])
def borrar_outfit(id):
    conexion = conectar()
    outfit = conexion.execute(
        "SELECT id FROM outfits WHERE id=? AND usuario_id=?", (id, session["usuario_id"])).fetchone()
    if outfit:
        conexion.execute("DELETE FROM outfit_prendas WHERE outfit_id=?", (id,))
        conexion.execute("DELETE FROM outfits WHERE id=?", (id,))
        conexion.commit()
        flash("🗑️ Outfit borrado")
    conexion.close()
    return redirect("/outfits")


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
