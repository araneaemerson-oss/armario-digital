# 👕 Armario Digital

Aplicación web para organizar tu ropa: tomas fotos de tus prendas, se guardan en tu armario digital y puedes verlas todas en un solo lugar, sin abrir el clóset.

> Proyecto personal en desarrollo, creado para practicar desarrollo web con Python.

## ✨ Funcionalidades

- 🔐 **Cuentas de usuario**: registro, inicio y cierre de sesión con contraseñas cifradas (hash)
- 🙈 Cada usuario ve, edita y borra **solo su propia ropa**
- 📸 Subir prendas con foto (con vista previa), tipo, color, ocasión y nombre opcional
- ✂️ Quitar el fondo de las fotos automáticamente con IA (`rembg`)
- 👔 Armar y guardar outfits combinando prendas
- 🗂️ 11 categorías (camisas, vestidos, tacos, bolsos...) definidas en un solo lugar del código
- 🏠 Inicio que se adapta a cada usuario: muestra solo las categorías que usa
- 🔍 Filtros por tipo de prenda
- ✏️ Editar prendas, incluida la foto, y 🗑️ borrarlas con confirmación
- 🧹 Las fotos viejas se borran del disco automáticamente
- 💬 Mensajes de confirmación y validación de datos (formato y tamaño de la foto)
- 📱 Diseño responsive: se ve bien en computadora y en celular

## 🛠️ Tecnologías

- **Python** y **Flask** (backend)
- **HTML**, **CSS** y **Jinja** (frontend y plantillas)
- **SQLite** y **SQL** (base de datos con tablas relacionadas)
- **JavaScript** (vista previa de fotos y nombre sugerido)

## 🚀 Cómo ejecutarlo

1. Instala las librerías:
   ```
   pip install -r requirements.txt
   ```
2. Ejecuta la aplicación:
   ```
   python app.py
   ```
3. Abre en el navegador: http://127.0.0.1:5000

La base de datos (`armario.db`) se crea sola la primera vez que se ejecuta la app. La primera vez que quitas un fondo, `rembg` descarga su modelo de IA (unos 170 MB).

## 🗺️ Próximos pasos

- [x] Borrar y editar prendas
- [x] Cuentas de usuario
- [x] Armar y guardar outfits
- [x] Quitar el fondo de las fotos automáticamente
- [ ] Probador: avatar con la foto del usuario para probar outfits
- [ ] Publicar la app en internet

## 🤖 Uso de IA

Desarrollado con apoyo de IA (Claude) como tutor: la usé para aprender los conceptos y revisar mi código, que fui escribiendo y corrigiendo yo mismo.

## 👤 Autor

**Fabricio Aranea** — Tecnólogo en Desarrollo de Software, Guayaquil, Ecuador.
