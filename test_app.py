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

CARPETA_FOTOS = armario.CARPETA_FOTOS


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
    assert os.path.exists(os.path.join(armario.CARPETA_STATIC, foto))
    cliente.post(f"/borrar/{prenda_id}")
    assert not os.path.exists(os.path.join(armario.CARPETA_STATIC, foto))


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


# ---------- 🧹 Borrar prendas que están en outfits ----------

def crear_outfit(cliente, ids, nombre="", ocasion="Casual"):
    cliente.post("/outfits/nuevo", data={"prendas": [str(i) for i in ids], "ocasion": ocasion, "nombre": nombre})
    conexion = armario.conectar()
    outfit_id = conexion.execute("SELECT MAX(id) FROM outfits").fetchone()[0]
    conexion.close()
    return outfit_id


def test_avisa_antes_de_borrar_una_prenda_que_esta_en_outfits(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    crear_outfit(cliente, ids_de_prendas(correo), nombre="playa")
    pagina = cliente.get("/prendas").get_data(as_text=True)
    assert "Esta prenda está en 1 outfit: playa" in pagina


def test_borrar_prenda_quita_outfits_que_quedan_con_menos_de_2(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    camisa, pantalon = ids_de_prendas(correo)
    outfit_id = crear_outfit(cliente, [camisa, pantalon], nombre="playa")
    respuesta = cliente.post(f"/borrar/{camisa}", follow_redirects=True)
    assert "También quitamos el outfit playa" in respuesta.get_data(as_text=True)
    conexion = armario.conectar()
    assert conexion.execute("SELECT * FROM outfits WHERE id=?", (outfit_id,)).fetchone() is None
    conexion.close()


def test_outfit_con_3_prendas_sigue_existiendo_pero_incompleto(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    subir_prenda(cliente, tipo="Zapatos", color="negro")
    camisa, pantalon, zapatos = ids_de_prendas(correo)
    crear_outfit(cliente, [camisa, pantalon, zapatos], nombre="oficina")
    cliente.post(f"/borrar/{zapatos}")
    pagina = cliente.get("/outfits").get_data(as_text=True)
    assert "oficina" in pagina
    assert "Incompleto: falta calzado" in pagina


def test_que_le_falta():
    assert armario.que_le_falta([{"tipo": "Vestido"}, {"tipo": "Tacos"}]) == []
    assert armario.que_le_falta([{"tipo": "Camisa"}, {"tipo": "Zapatos"}]) == ["parte de abajo"]


# ---------- ✏️ Editar outfit ----------

def test_editar_outfit(cliente):
    correo = crear_usuario(cliente)
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    subir_prenda(cliente, tipo="Zapatos", color="negro")
    camisa, pantalon, zapatos = ids_de_prendas(correo)
    outfit_id = crear_outfit(cliente, [camisa, pantalon], nombre="playa")

    pagina = cliente.get(f"/outfits/editar/{outfit_id}").get_data(as_text=True)
    assert "Editar outfit" in pagina and 'value="playa"' in pagina

    respuesta = cliente.post(f"/outfits/editar/{outfit_id}", data={
        "prendas": [str(camisa), str(pantalon), str(zapatos)], "ocasion": "Fiesta", "nombre": "fiesta playera"},
        follow_redirects=True)
    pagina = respuesta.get_data(as_text=True)
    assert "Outfit actualizado" in pagina and "fiesta playera" in pagina
    conexion = armario.conectar()
    cantidad = conexion.execute("SELECT COUNT(*) FROM outfit_prendas WHERE outfit_id=?", (outfit_id,)).fetchone()[0]
    conexion.close()
    assert cantidad == 3


def test_no_puedes_editar_el_outfit_de_otro(cliente):
    correo = crear_usuario(cliente, "ana")
    subir_prenda(cliente, tipo="Camisa", color="blanco")
    subir_prenda(cliente, tipo="Pantalón", color="azul")
    outfit_id = crear_outfit(cliente, ids_de_prendas(correo), nombre="de ana")
    cliente.get("/salir")
    crear_usuario(cliente, "beto")
    assert cliente.get(f"/outfits/editar/{outfit_id}").status_code == 302
    cliente.post(f"/outfits/editar/{outfit_id}", data={"prendas": [], "ocasion": "Casual", "nombre": "hackeado"})
    conexion = armario.conectar()
    assert conexion.execute("SELECT nombre FROM outfits WHERE id=?", (outfit_id,)).fetchone()["nombre"] == "de ana"
    conexion.close()


# ---------- 🔑 Recuperar contraseña ----------

import re

def codigo_de(pagina):
    # Saca el código "XXXX-XXXX-XXXX" que muestra la página
    encontrado = re.search(r'id="codigo">([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})<', pagina)
    return encontrado.group(1) if encontrado else None


def test_registro_muestra_codigo_de_recuperacion(cliente):
    respuesta = cliente.post("/registro", data={"nombre": "x", "correo": "codigo1@prueba.com", "contrasena": "123456"})
    assert codigo_de(respuesta.get_data(as_text=True)) is not None


def test_el_codigo_se_guarda_cifrado(cliente):
    respuesta = cliente.post("/registro", data={"nombre": "x", "correo": "codigo2@prueba.com", "contrasena": "123456"})
    codigo = codigo_de(respuesta.get_data(as_text=True))
    conexion = armario.conectar()
    guardado = conexion.execute("SELECT codigo_hash FROM usuarios WHERE correo=?", ("codigo2@prueba.com",)).fetchone()[0]
    conexion.close()
    assert guardado and codigo not in guardado and armario.limpiar_codigo(codigo) not in guardado


def test_recuperar_contrasena_con_el_codigo(cliente):
    respuesta = cliente.post("/registro", data={"nombre": "x", "correo": "codigo3@prueba.com", "contrasena": "123456"})
    codigo = codigo_de(respuesta.get_data(as_text=True))
    cliente.get("/salir")
    # sin guiones y en minúsculas también funciona
    respuesta = cliente.post("/olvide", data={"correo": "codigo3@prueba.com",
                                               "codigo": codigo.replace("-", " ").lower(), "nueva": "nueva123"})
    pagina = respuesta.get_data(as_text=True)
    assert "Cambiaste tu contraseña" in pagina
    codigo_nuevo = codigo_de(pagina)
    assert codigo_nuevo and codigo_nuevo != codigo           # te damos un código nuevo
    cliente.get("/salir")
    assert "Hola de nuevo" in cliente.post("/entrar", data={"correo": "codigo3@prueba.com", "contrasena": "nueva123"},
                                           follow_redirects=True).get_data(as_text=True)
    # el código viejo ya no sirve
    cliente.get("/salir")
    respuesta = cliente.post("/olvide", data={"correo": "codigo3@prueba.com", "codigo": codigo, "nueva": "otra123"})
    assert "incorrectos" in respuesta.get_data(as_text=True)


def test_codigo_incorrecto_no_cambia_la_contrasena(cliente):
    correo = crear_usuario(cliente)
    cliente.get("/salir")
    respuesta = cliente.post("/olvide", data={"correo": correo, "codigo": "AAAA-BBBB-CCCC", "nueva": "hackeada"})
    assert "Correo o código de recuperación incorrectos" in respuesta.get_data(as_text=True)
    assert "Hola de nuevo" in cliente.post("/entrar", data={"correo": correo, "contrasena": "123456"},
                                           follow_redirects=True).get_data(as_text=True)


def test_mi_cuenta_cambiar_contrasena(cliente):
    correo = crear_usuario(cliente)
    respuesta = cliente.post("/mi-cuenta", data={"accion": "cambiar", "actual": "mal", "nueva": "nueva123"},
                             follow_redirects=True)
    assert "contraseña actual no es correcta" in respuesta.get_data(as_text=True)
    respuesta = cliente.post("/mi-cuenta", data={"accion": "cambiar", "actual": "123456", "nueva": "nueva123"},
                             follow_redirects=True)
    assert "Contraseña cambiada" in respuesta.get_data(as_text=True)
    cliente.get("/salir")
    assert "Hola de nuevo" in cliente.post("/entrar", data={"correo": correo, "contrasena": "nueva123"},
                                           follow_redirects=True).get_data(as_text=True)


def test_mi_cuenta_generar_codigo_nuevo(cliente):
    crear_usuario(cliente)
    respuesta = cliente.post("/mi-cuenta", data={"accion": "codigo", "actual": "123456"})
    assert codigo_de(respuesta.get_data(as_text=True)) is not None


def test_mi_cuenta_pide_sesion(cliente):
    assert cliente.get("/mi-cuenta").status_code == 302

