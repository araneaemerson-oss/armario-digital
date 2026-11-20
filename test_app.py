# 🧪 Pruebas automáticas del Armario Digital
# Cómo correrlas:  python -m pytest -v
#
# Cada prueba revisa que una parte de la app funcione bien.
# Usan una base de datos APARTE (temporal), así que tu armario real no se toca.

import io
import os
import tempfile

import pytest

# 1) Antes de importar la app, le decimos que use una base de datos temporal
CARPETA_TEMPORAL = tempfile.mkdtemp()
os.environ["ARMARIO_DB"] = os.path.join(CARPETA_TEMPORAL, "pruebas.db")

import app as armario   # noqa: E402  (se importa después de configurar la base de datos)

CARPETA_FOTOS = os.path.join("static", "uploads")


# ---------- Herramientas para las pruebas ----------

@pytest.fixture(scope="session", autouse=True)
def limpiar_fotos_de_prueba():
    # Al terminar TODAS las pruebas, borramos las fotos que se crearon
    os.makedirs(CARPETA_FOTOS, exist_ok=True)
    antes = set(os.listdir(CARPETA_FOTOS))
    yield
    for archivo in set(os.listdir(CARPETA_FOTOS)) - antes:
        os.remove(os.path.join(CARPETA_FOTOS, archivo))


CLIMA_DE_PRUEBA = {"ciudad": "Guayaquil", "temperatura": 25, "lluvia": False,
                   "icono": "⛅", "descripcion": "Parcialmente nublado"}

@pytest.fixture(autouse=True)
def clima_falso(monkeypatch):
    # Las pruebas no se conectan a internet: usamos un clima inventado
    monkeypatch.setattr(armario, "clima_de_hoy", lambda: dict(CLIMA_DE_PRUEBA))


@pytest.fixture
def cliente():
    # Un "navegador de mentira" para visitar las páginas de la app
    armario.app.config["TESTING"] = True
    return armario.app.test_client()


contador_usuarios = 0

def crear_usuario(cliente, nombre="ana"):
    # Registra un usuario nuevo con un correo distinto cada vez
    global contador_usuarios
    contador_usuarios += 1
    correo = f"{nombre}{contador_usuarios}@prueba.com"
    cliente.post("/registro", data={"nombre": nombre, "correo": correo, "contrasena": "123456"})
    return correo


def foto_falsa(color=(30, 30, 30), nombre="foto.png"):
    # Crea una imagen pequeñita en memoria (sin necesitar archivos reales)
    from PIL import Image
    imagen = Image.new("RGB", (60, 60), color)
    datos = io.BytesIO()
    imagen.save(datos, "PNG")
    datos.seek(0)
    return (datos, nombre)


def subir_prenda(cliente, tipo="Camisa", color="", nombre="", ocasion="Casual", foto=None):
    return cliente.post("/subir", data={
        "tipo": tipo, "color": color, "nombre": nombre, "ocasion": ocasion,
        "foto": foto or foto_falsa(),
    }, content_type="multipart/form-data", follow_redirects=True)


def ids_de_prendas(correo):
    conexion = armario.conectar()
    filas = conexion.execute("""
        SELECT prendas.id FROM prendas JOIN usuarios ON usuarios.id = prendas.usuario_id
        WHERE usuarios.correo = ?""", (correo,)).fetchall()
    conexion.close()
    return [fila["id"] for fila in filas]


# ---------- 🔐 Usuarios y seguridad ----------

def test_sin_sesion_te_manda_a_entrar(cliente):
    for pagina in ["/", "/prendas", "/subir", "/outfits"]:
        respuesta = cliente.get(pagina)
        assert respuesta.status_code == 302
        assert "/entrar" in respuesta.headers["Location"]


def test_registro_inicia_sesion_y_saluda(cliente):
    crear_usuario(cliente, "maria")
    pagina = cliente.get("/").get_data(as_text=True)
    assert "Hola, Maria" in pagina          # el nombre se guarda con mayúscula


def test_la_contrasena_se_guarda_cifrada(cliente):
    correo = crear_usuario(cliente)
    conexion = armario.conectar()
    usuario = conexion.execute("SELECT contrasena_hash FROM usuarios WHERE correo=?", (correo,)).fetchone()
    conexion.close()
    assert usuario["contrasena_hash"] != "123456"     # ¡nunca la contraseña real!


def test_no_deja_correo_repetido(cliente):
    correo = crear_usuario(cliente)
    cliente.get("/salir")
    respuesta = cliente.post("/registro", data={"nombre": "otro", "correo": correo, "contrasena": "123456"})
    assert "Ya existe una cuenta con ese correo" in respuesta.get_data(as_text=True)


def test_contrasena_muy_corta(cliente):
    respuesta = cliente.post("/registro", data={"nombre": "x", "correo": "corta@prueba.com", "contrasena": "123"})
    assert "al menos 6 caracteres" in respuesta.get_data(as_text=True)


def test_entrar_con_contrasena_incorrecta(cliente):
    correo = crear_usuario(cliente)
    cliente.get("/salir")
    respuesta = cliente.post("/entrar", data={"correo": correo, "contrasena": "equivocada"})
    assert "Correo o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_entrar_y_salir(cliente):
    correo = crear_usuario(cliente)
    cliente.get("/salir")
    respuesta = cliente.post("/entrar", data={"correo": correo.upper(), "contrasena": "123456"},
                             follow_redirects=True)
    assert "Hola de nuevo" in respuesta.get_data(as_text=True)   # el correo no distingue mayúsculas
    cliente.get("/salir")
    assert cliente.get("/").status_code == 302


# ---------- 👕 Prendas ----------

def test_subir_prenda_con_nombre_y_color_automaticos(cliente):
    crear_usuario(cliente)
    respuesta = subir_prenda(cliente, tipo="Camisa", foto=foto_falsa((20, 20, 20)))
    pagina = respuesta.get_data(as_text=True)
    assert "Prenda guardada" in pagina
    assert "Camisa negra" in pagina          # color detectado + concordancia


def test_rechaza_archivos_que_no_son_fotos(cliente):
    crear_usuario(cliente)
    archivo_raro = (io.BytesIO(b"esto no es una foto"), "virus.exe")
    respuesta = subir_prenda(cliente, foto=archivo_raro)
    assert "formato JPG, PNG o WEBP" in respuesta.get_data(as_text=True)


def test_rechaza_tipo_inventado(cliente):
    crear_usuario(cliente)
    respuesta = subir_prenda(cliente, tipo="Nave espacial")
    assert "Revisa el tipo" in respuesta.get_data(as_text=True)


def test_nadie_puede_ver_editar_ni_borrar_la_ropa_de_otro(cliente):
    correo_ana = crear_usuario(cliente, "ana")
    subir_prenda(cliente, nombre="Camisa secreta de Ana")
    id_de_ana = ids_de_prendas(correo_ana)[0]
    cliente.get("/salir")

    crear_usuario(cliente, "beto")
    assert "Camisa secreta de Ana" not in cliente.get("/prendas").get_data(as_text=True)
    assert cliente.get(f"/editar/{id_de_ana}").status_code == 302      # lo saca de ahí
    cliente.post(f"/borrar/{id_de_ana}")
    assert id_de_ana in ids_de_prendas(correo_ana)                     # la prenda sigue existiendo


def test_borrar_prenda_tambien_borra_la_foto(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente)
    prenda_id = ids_de_prendas(correo)[0]
    conexion = armario.conectar()
    foto = conexion.execute("SELECT foto FROM prendas WHERE id=?", (prenda_id,)).fetchone()["foto"]
    conexion.close()
    assert os.path.exists(os.path.join("static", foto))
    cliente.post(f"/borrar/{prenda_id}")
    assert not os.path.exists(os.path.join("static", foto))


# ---------- 👔 Outfits ----------

def test_outfit_necesita_al_menos_2_prendas(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente)
    ids = ids_de_prendas(correo)
    respuesta = cliente.post("/outfits/nuevo", data={"prendas": [str(ids[0])], "ocasion": "Casual"},
                             follow_redirects=True)
    assert "al menos 2 prendas" in respuesta.get_data(as_text=True)


def test_crear_y_borrar_outfit(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    ids = [str(i) for i in ids_de_prendas(correo)]
    respuesta = cliente.post("/outfits/nuevo", data={"prendas": ids, "ocasion": "Formal", "nombre": ""},
                             follow_redirects=True)
    pagina = respuesta.get_data(as_text=True)
    assert "Outfit guardado" in pagina and "Outfit formal" in pagina

    conexion = armario.conectar()
    outfit_id = conexion.execute("SELECT MAX(id) FROM outfits").fetchone()[0]
    conexion.close()
    respuesta = cliente.post(f"/outfits/borrar/{outfit_id}", follow_redirects=True)
    assert "Outfit borrado" in respuesta.get_data(as_text=True)


def test_sugerir_outfit_elige_arriba_abajo_y_zapatos(cliente):
    crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="negro")
    subir_prenda(cliente, tipo="Zapatos", color="negro")
    datos = cliente.get("/outfits/sugerir?ocasion=Casual").get_json()
    assert len(datos["ids"]) >= 3
    assert datos["explicacion"]


# ---------- 🎨 Funciones de ayuda ----------

@pytest.mark.parametrize("tipo, color, esperado", [
    ("Camisa", "Negro", "negra"),
    ("Zapatos", "Negro", "negros"),
    ("Zapatos", "Azul", "azules"),
    ("Zapatos", "Beige", "beige"),
    ("Pantalón", "Blanco", "blanco"),
    ("Falda", "azul marino", "azul marino"),
])
def test_concordar_color(tipo, color, esperado):
    assert armario.concordar_color(tipo, color) == esperado


@pytest.mark.parametrize("rgb, esperado", [
    ((15, 15, 15), "negro"),
    ((245, 245, 245), "blanco"),
    ((200, 30, 40), "rojo"),
    ((20, 30, 90), "azul marino"),
    ((40, 140, 60), "verde"),
])
def test_nombre_del_color(rgb, esperado):
    assert armario.nombre_del_color(*rgb) == esperado


def test_pagina_que_no_existe_muestra_404(cliente):
    crear_usuario(cliente)
    respuesta = cliente.get("/esta-pagina-no-existe")
    assert respuesta.status_code == 404
    assert "calcetín" in respuesta.get_data(as_text=True)


# ---------- 🌦️ ¿Qué me pongo hoy? ----------

def test_inicio_muestra_el_clima_y_un_outfit(cliente):
    crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="negro")
    pagina = cliente.get("/").get_data(as_text=True)
    assert "25°C" in pagina and "Guayaquil" in pagina
    assert "Tu outfit para hoy" in pagina and "Hoy me pongo esto" in pagina


def test_con_calor_prefiere_short_y_sin_chaqueta():
    prendas = [
        {"id": 1, "tipo": "Camisa", "color": "Blanco", "ocasion": "Casual", "nombre": "Camisa"},
        {"id": 2, "tipo": "Pantalón", "color": "Negro", "ocasion": "Casual", "nombre": "Pantalón"},
        {"id": 3, "tipo": "Short", "color": "Azul", "ocasion": "Casual", "nombre": "Short"},
        {"id": 4, "tipo": "Chaqueta", "color": "Negro", "ocasion": "Casual", "nombre": "Chaqueta"},
    ]
    calor = {"temperatura": 32, "lluvia": False}
    for _ in range(20):                      # como es al azar, probamos varias veces
        ids, explicacion = armario.sugerir_outfit(prendas, "Casual", calor)
        assert 3 in ids and 2 not in ids and 4 not in ids


def test_con_lluvia_agrega_chaqueta():
    prendas = [
        {"id": 1, "tipo": "Camisa", "color": "Blanco", "ocasion": "Casual", "nombre": "Camisa"},
        {"id": 2, "tipo": "Pantalón", "color": "Negro", "ocasion": "Casual", "nombre": "Pantalón"},
        {"id": 4, "tipo": "Chaqueta", "color": "Negro", "ocasion": "Casual", "nombre": "Chaqueta"},
    ]
    ids, explicacion = armario.sugerir_outfit(prendas, "Casual", {"temperatura": 24, "lluvia": True})
    assert 4 in ids


# ---------- 📊 ¿Cuánto uso mi ropa? ----------

def test_hoy_me_pongo_esto_registra_el_uso_una_vez_por_dia(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="negro")
    prenda_id = ids_de_prendas(correo)[0]
    cliente.post("/usar", data={"prendas": [str(prenda_id)]})
    cliente.post("/usar", data={"prendas": [str(prenda_id)]})      # dos veces el mismo día
    pagina = cliente.get("/mi-uso").get_data(as_text=True)
    assert "Usada 1 vez" in pagina
    assert "Ya anotaste lo que te pusiste hoy" in cliente.get("/").get_data(as_text=True)


def test_no_puedes_registrar_uso_de_ropa_ajena(cliente):
    correo_ana = crear_usuario(cliente, "ana")
    subir_prenda(cliente)
    id_de_ana = ids_de_prendas(correo_ana)[0]
    cliente.get("/salir")
    crear_usuario(cliente, "beto")
    cliente.post("/usar", data={"prendas": [str(id_de_ana)]})
    conexion = armario.conectar()
    usos = conexion.execute("SELECT COUNT(*) FROM usos WHERE prenda_id=?", (id_de_ana,)).fetchone()[0]
    conexion.close()
    assert usos == 0


def test_me_puse_el_outfit_registra_todas_sus_prendas(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    ids = [str(i) for i in ids_de_prendas(correo)]
    cliente.post("/outfits/nuevo", data={"prendas": ids, "ocasion": "Casual"})
    conexion = armario.conectar()
    outfit_id = conexion.execute("SELECT MAX(id) FROM outfits").fetchone()[0]
    conexion.close()
    respuesta = cliente.post(f"/outfits/usar/{outfit_id}", follow_redirects=True)
    assert "Hoy te pusiste este outfit" in respuesta.get_data(as_text=True)
    pagina = cliente.get("/mi-uso").get_data(as_text=True)
    assert pagina.count("Usada 1 vez") == 2


def test_mi_uso_muestra_ropa_nunca_usada(cliente):
    crear_usuario(cliente)
    subir_prenda(cliente, nombre="Chaqueta olvidada", tipo="Chaqueta", color="gris")
    pagina = cliente.get("/mi-uso").get_data(as_text=True)
    assert "Chaqueta olvidada" in pagina and "Nunca usada" in pagina
