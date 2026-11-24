# 🛠️ Herramienta de administrador del Armario Digital
# Solo la puede usar quien tenga acceso al servidor (tú 😉). Se usa desde la consola:
#
#   python admin.py usuarios                      → lista los usuarios registrados
#   python admin.py restablecer correo@ejemplo.com → contraseña temporal + código nuevo
#   python admin.py limpiar                       → borra datos y fotos que ya no se usan
#
# ⚠️ Antes de restablecer una cuenta, verifica que la persona es la dueña
#    (por ejemplo, que te escriba desde el MISMO correo de su cuenta).

import os
import sys

import app


def listar_usuarios():
    conexion = app.conectar()
    usuarios = conexion.execute("SELECT id, nombre, correo FROM usuarios ORDER BY id").fetchall()
    conexion.close()
    if not usuarios:
        print("Todavía no hay usuarios.")
    for usuario in usuarios:
        print(f"{usuario['id']:>4}  {usuario['nombre']:<20} {usuario['correo']}")


def restablecer(correo):
    resultado = app.restablecer_acceso(correo)
    if resultado is None:
        print(f"❌ No existe ningún usuario con el correo {correo}")
        return
    temporal, codigo = resultado
    print(f"✅ Acceso restablecido para {correo}")
    print(f"   Contraseña temporal:     {temporal}")
    print(f"   Código de recuperación:  {codigo}")
    print("   👉 Envíale estos datos a la persona y pídele que cambie la contraseña en 'Mi cuenta'.")


def limpiar():
    # Busca "basura": cosas que quedaron de pruebas viejas y que la app ya no usa 🧹
    conexion = app.conectar()
    sin_dueno = conexion.execute("SELECT id, nombre FROM prendas WHERE usuario_id IS NULL").fetchall()
    tablas = [fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    columnas = [fila["name"] for fila in conexion.execute("PRAGMA table_info(usuarios)")]

    fotos_en_uso = set()
    for fila in conexion.execute("SELECT foto FROM prendas WHERE foto IS NOT NULL"):
        fotos_en_uso.add(os.path.basename(fila["foto"]))
    fotos_sueltas = []
    for archivo in os.listdir(app.CARPETA_FOTOS):
        if archivo not in fotos_en_uso:
            fotos_sueltas.append(archivo)

    print("🧹 Encontré esto para limpiar:")
    print(f"   • {len(sin_dueno)} prendas sin dueño (de las prácticas del inicio)")
    print(f"   • {len(fotos_sueltas)} fotos que ninguna prenda usa")
    print(f"   • Tabla 'posiciones' del probador: {'sí' if 'posiciones' in tablas else 'no'}")
    print(f"   • Columna 'avatar' del probador: {'sí' if 'avatar' in columnas else 'no'}")
    if not (sin_dueno or fotos_sueltas or "posiciones" in tablas or "avatar" in columnas):
        print("✨ ¡Todo está limpio!")
        conexion.close()
        return

    respuesta = input("¿Borrar todo esto? Escribe si para confirmar: ")
    if respuesta.strip().lower() not in ["si", "sí"]:
        print("No se borró nada.")
        conexion.close()
        return

    conexion.execute("DELETE FROM outfit_prendas WHERE prenda_id IN (SELECT id FROM prendas WHERE usuario_id IS NULL)")
    conexion.execute("DELETE FROM prendas WHERE usuario_id IS NULL")
    conexion.execute("DROP TABLE IF EXISTS posiciones")
    if "avatar" in columnas:
        conexion.execute("ALTER TABLE usuarios DROP COLUMN avatar")
    conexion.commit()
    conexion.close()
    for archivo in fotos_sueltas:
        os.remove(os.path.join(app.CARPETA_FOTOS, archivo))
    print("✅ ¡Listo! Tu base de datos y tu carpeta de fotos están limpias.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "usuarios":
        listar_usuarios()
    elif len(sys.argv) >= 3 and sys.argv[1] == "restablecer":
        restablecer(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "limpiar":
        limpiar()
    else:
        print("Uso:")
        print("  python admin.py usuarios")
        print("  python admin.py restablecer correo@ejemplo.com")
        print("  python admin.py limpiar")
