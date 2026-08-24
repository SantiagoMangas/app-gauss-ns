# NC Dashboard

Web de evaluaciones (Streamlit) para Concentración Nacional. Lee un Google Sheet: campana, radar, boxplot, comparativas 1ª vs 2ª fecha y videos.

Hay dos entradas:

- **Entrenador** (mail + contraseña): puede guardar en la planilla.
- **Invitado**: mira y puede cargar un alumno para compararse. Eso no va a Google y se borra al cerrar.

## Cómo correrla en la PC

Desde esta carpeta:

```
cd app-gauss
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

En Windows, si `streamlit` no se reconoce, usá siempre `python -m streamlit run app.py` (el `.exe` queda fuera del PATH).

1. Copiá `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml`.
2. Completá `spreadsheet_id` (usá **la copia** del Sheet, no la original).
3. Completá `[coach]` con el mail y la clave que van a compartir los entrenadores.
4. Pegá la cuenta de servicio en `[gcp_service_account]` (el JSON que hoy está en `credentials.json`).
5. En Google Sheets: Compartir la copia con el mail del bot (`client_email`) como **Editor**.
6. Los logos están en `assets/` (copiados de `Logos NS Dash`). Si Nico manda uno nuevo, reemplazá `ns-progress-wordmark.png` (entrada) o `ns-mark.png` (ícono).

Si todavía tenés `credentials.json` en esta carpeta, la app lo usa como respaldo para Google. Igual hace falta `[coach]` en secrets para el login de entrenador. En Render no subas `credentials.json`.

## Subirla a Render (pago, no se duerme)

No uses Vercel: esto es Python, no una web estática.

1. Creá un repo git (sin `credentials.json` ni `secrets.toml`; ya están en `.gitignore`).
2. En [Render](https://render.com) → New → Blueprint, o Web Service apuntando al repo. El archivo `render.yaml` de la raíz ya define el servicio `nc-dashboard` en plan **Starter**.
3. Secret File llamado `.streamlit/secrets.toml` con el mismo contenido que usás en local (ID de la **copia**, coach, cuenta de servicio).
4. Deploy. El link queda siempre prendido si el plan no es el free que se duerme.

Si el bot no ve la planilla: volvé a compartir el Sheet con `client_email`.

## Qué no hace esta versión

- Login con Google (Gmail). Es mail + contraseña en secrets.
- Cuentas distintas por entrenador: todos usan la misma clave.
- Guardar invitados 24 horas: se borran al cerrar la pestaña.
