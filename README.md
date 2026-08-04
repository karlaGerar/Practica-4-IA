# Music AI Web

Aplicación web local para recomendar música con un look pastel y conexión básica a Spotify.

## Requisitos

- Python 3.14
- Paquetes en `requirements.txt`

## Instalación

En la carpeta del proyecto:

```powershell
& "C:\Users\Karlita Gerardo\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements.txt
```

## Ejecutar

```powershell
& "C:\Users\Karlita Gerardo\AppData\Local\Python\pythoncore-3.14-64\python.exe" "c:\Users\Karlita Gerardo\Documents\Practica 4\app.py"
```

Abre en el navegador:

```text
http://127.0.0.1:8888/
```

## Spotify

Para usar la conexión a Spotify, configura estas variables de entorno y reinicia la terminal:

```powershell
setx SPOTIFY_CLIENT_ID "TU_CLIENT_ID"
setx SPOTIFY_CLIENT_SECRET "TU_CLIENT_SECRET"
setx SPOTIFY_REDIRECT_URI "http://127.0.0.1:8888/callback"
```

Luego en la app presiona `Conectar Spotify`.
