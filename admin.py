# 🛠️ Herramienta de administrador del Armario Digital
# Solo la puede usar quien tenga acceso al servidor (tú 😉). Se usa desde la consola:
#
#   python admin.py usuarios                      → lista los usuarios registrados
#   python admin.py restablecer correo@ejemplo.com → contraseña temporal + código nuevo
#
# ⚠️ Antes de restablecer una cuenta, verifica que la persona es la dueña
#    (por ejemplo, que te escriba desde el MISMO correo de su cuenta).

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


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "usuarios":
        listar_usuarios()
    elif len(sys.argv) >= 3 and sys.argv[1] == "restablecer":
        restablecer(sys.argv[2])
    else:
        print("Uso:")
        print("  python admin.py usuarios")
        print("  python admin.py restablecer correo@ejemplo.com")
