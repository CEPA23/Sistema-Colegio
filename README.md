# Sistema-Colegio
Realizacion de un sistema para un colegio.

## Despliegue con base de datos persistente

Para evitar que los datos se pierdan en cada deploy, la aplicacion debe usar PostgreSQL mediante la variable `DATABASE_URL`.

En local:
- Si `DATABASE_URL` no existe, el proyecto usa `db.sqlite3`.

En produccion:
- Configura `DATABASE_URL` con la cadena de conexion de PostgreSQL.
- Configura `DEBUG=False`.
- Configura `SECRET_KEY` con una clave segura.
- Configura `ALLOWED_HOSTS` con el dominio de tu app.
- Configura `CSRF_TRUSTED_ORIGINS` con la URL completa, por ejemplo `https://tu-app.onrender.com`.

Tienes un ejemplo en `.env.example`.
