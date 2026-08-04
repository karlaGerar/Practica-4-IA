"""
MusicAI - Sistema Inteligente de Recomendacion Musical
Proyecto: Ingenieria en Sistemas Computacionales - Aprendizaje Automatico
Algoritmo: K-Nearest Neighbors (KNN)

Como funciona:
1. Se carga un dataset de canciones (canciones.csv) con genero, animo, artista y energia.
2. Cada cancion se convierte en un vector numerico (one-hot encoding + energia normalizada).
3. Las preferencias del usuario se convierten al mismo formato de vector.
4. Se usa NearestNeighbors de scikit-learn para encontrar las 5 canciones
   mas parecidas al gusto del usuario (esto es lo que hace que sea "IA":
   encuentra patrones/similitudes en vez de escoger canciones al azar).
"""

import base64
import json
import os
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd

from sklearn.neighbors import NearestNeighbors
import tkinter as tk
from tkinter import ttk, messagebox

# ---------------------------------------------------------------------------
# 1. CARGA Y PREPARACION DE DATOS
# ---------------------------------------------------------------------------

RUTA_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canciones.csv")

GENEROS = ["Pop", "Rock", "Reggaeton", "Electronica", "Regional Mexicano", "Rap"]
ANIMOS = ["Feliz", "Triste", "Relajado", "Motivado", "Enamorado"]
ARTISTAS_SUGERIDOS = [
    "Bad Bunny", "Taylor Swift", "Peso Pluma", "Karol G", "Ed Sheeran"
]
ENERGIA_MAP = {"Baja": 0.0, "Media": 0.5, "Alta": 1.0}

DEFAULT_SPOTIFY_CLIENT_ID = "06ec744e95424070b3b011ca36bc7abb"
DEFAULT_SPOTIFY_CLIENT_SECRET = "9b210caf6fa94723a25b7b81fe7a6dca"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def _resolve_spotify_value(env_name, default_value):
    value = os.getenv(env_name, default_value).strip()
    if not value:
        return default_value
    placeholder_values = {
        "tu_client_id",
        "tu_client_secret",
        "your_client_id",
        "your_client_secret",
        "client_id_here",
        "client_secret_here",
        "replace_me",
    }
    normalized = value.lower()
    if normalized in placeholder_values or normalized.startswith("tu_") or normalized.startswith("your_"):
        return default_value
    return value


SPOTIFY_CLIENT_ID = _resolve_spotify_value("SPOTIFY_CLIENT_ID", DEFAULT_SPOTIFY_CLIENT_ID)
SPOTIFY_CLIENT_SECRET = _resolve_spotify_value("SPOTIFY_CLIENT_SECRET", DEFAULT_SPOTIFY_CLIENT_SECRET)
SPOTIFY_REDIRECT_URI = _resolve_spotify_value("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private user-read-private"


class SpotifyCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        query = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = query.get("code", [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Spotify autorizado. Puedes cerrar esta ventana.</h2></body></html>"
        )

    def log_message(self, format, *args):
        return


def construir_url_autorizacion():
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    if not client_id:
        raise ValueError(
            "Falta SPOTIFY_CLIENT_ID en las variables de entorno. Configura credenciales reales de Spotify para conectar la app."
        )
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "show_dialog": "true",
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)


def intercambiar_codigo_por_token(codigo):
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "Faltan SPOTIFY_CLIENT_ID o SPOTIFY_CLIENT_SECRET. Configura credenciales reales de Spotify para conectar la app."
        )
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }).encode("utf-8")
    auth_header = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def spotify_buscar_pistas(token, query, limite=1):
    request_url = (
        "https://api.spotify.com/v1/search?q="
        + urllib.parse.quote(query)
        + "&type=track&limit="
        + str(limite)
    )
    req = urllib.request.Request(
        request_url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
    items = data.get("tracks", {}).get("items", [])
    results = []
    for item in items:
        results.append(
            {
                "uri": item.get("uri"),
                "id": item.get("id"),
                "preview_url": item.get("preview_url"),
                "image": (item.get("album", {}).get("images") or [None])[0],
            }
        )
    return results


def spotify_crear_playlist(token, usuario_id, nombre, descripcion="Playlist creada con MusicAI"):
    payload = json.dumps({"name": nombre, "description": descripcion, "public": False}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/users/{usuario_id}/playlists",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def spotify_agregar_canciones_playlist(token, playlist_id, uris):
    payload = json.dumps({"uris": uris}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def cargar_datos():
    """Lee el CSV y devuelve el DataFrame original + la matriz de features para KNN."""
    df = pd.read_csv(RUTA_CSV)

    # One-hot encoding de genero y animo (esto convierte texto en columnas 0/1)
    genero_dummies = pd.get_dummies(df["genero"])
    # Aseguramos que existan todas las columnas de genero aunque el CSV no las use todas
    for g in GENEROS:
        if g not in genero_dummies.columns:
            genero_dummies[g] = 0
    genero_dummies = genero_dummies[GENEROS]

    animo_dummies = pd.get_dummies(df["animo"])
    for a in ANIMOS:
        if a not in animo_dummies.columns:
            animo_dummies[a] = 0
    animo_dummies = animo_dummies[ANIMOS]

    energia_num = df["energia"].map(ENERGIA_MAP).fillna(0.5)

    # A cada cancion tambien le damos una "pista" de si el artista coincide
    # con alguno de los artistas sugeridos (esto se combina despues con el usuario)
    artista_cols = pd.DataFrame(
        {art: (df["artista"] == art).astype(int) for art in ARTISTAS_SUGERIDOS}
    )

    features = pd.concat(
        [genero_dummies, animo_dummies, artista_cols, energia_num.rename("energia")],
        axis=1,
    )
    return df, features


def construir_vector_usuario(genero, animo, artista, columnas_features):
    """Convierte las respuestas del usuario en un vector con las mismas columnas
    que la matriz de canciones, para poder compararlos con KNN."""
    vector = {col: 0 for col in columnas_features}

    if genero in vector:
        vector[genero] = 1
    if animo in vector:
        vector[animo] = 1
    if artista in vector:
        # Le damos algo mas de peso al artista favorito
        vector[artista] = 2
    vector["energia"] = 0.5  # valor neutro por defecto

    return pd.DataFrame([vector])[columnas_features]


# ---------------------------------------------------------------------------
# 2. MOTOR DE RECOMENDACION (KNN)
# ---------------------------------------------------------------------------

class RecomendadorMusical:
    def __init__(self):
        self.df, self.features = cargar_datos()
        self.modelo = NearestNeighbors(n_neighbors=5, metric="euclidean")
        self.modelo.fit(self.features)

    def recomendar(self, genero, animo, artista):
        vector_usuario = construir_vector_usuario(
            genero, animo, artista, self.features.columns
        )
        distancias, indices = self.modelo.kneighbors(vector_usuario)
        resultados = self.df.iloc[indices[0]].copy()
        resultados["distancia"] = distancias[0]
        return resultados.sort_values("distancia")


def ejecutar_aplicacion(app):
    """Ejecuta la interfaz y cierra de forma limpia si el usuario interrumpe la app."""
    try:
        app.mainloop()
    except KeyboardInterrupt:
        for metodo in ("destroy", "quit"):
            callback = getattr(app, metodo, None)
            if callable(callback):
                try:
                    callback()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 3. INTERFAZ GRAFICA (Tkinter)
# ---------------------------------------------------------------------------

class MusicAIApp(tk.Tk):
    def __init__(self, recomendador: RecomendadorMusical):
        super().__init__()
        self.recomendador = recomendador
        self.title("MUSIC AI")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")
        self.minsize(900, 650)
        self.configure(bg="#0f172a")
        self._configurar_estilo()
        self.spotify_token = None
        self.spotify_user_id = None
        self.ultimas_recomendaciones = []
        self._construir_widgets()

    def _configurar_estilo(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#111827")
        style.configure("TLabel", background="#0f172a", foreground="#f8fafc")
        style.configure("Subtitle.TLabel", background="#0f172a", foreground="#94a3b8")
        style.configure("Accent.TButton", background="#7c3aed", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#6d28d9")])
        style.configure("Spotify.TButton", background="#1db954", foreground="#ffffff")
        style.map("Spotify.TButton", background=[("active", "#1aa34a")])

    def _construir_widgets(self):
        header = ttk.Frame(self, style="Card.TFrame", padding=24)
        header.pack(fill="x", padx=24, pady=(20, 12))

        ttk.Label(header, text="🎵 MUSIC AI", font=("Segoe UI", 32, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Descubre nuevas canciones según tu estado de ánimo, género y artista favorito.",
            style="Subtitle.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            header,
            text="Haz doble clic para reproducir una recomendación en Spotify o usa el botón de reproducción.",
            style="Subtitle.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        left = ttk.Frame(body, style="Card.TFrame", padding=24)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))

        ttk.Label(left, text="Elige tus preferencias", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(left, text="Crea una experiencia musical más personalizada.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 16))

        form = ttk.Frame(left, style="TFrame")
        form.pack(fill="x")

        ttk.Label(form, text="Género:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))
        self.combo_genero = ttk.Combobox(form, values=GENEROS, state="readonly", width=28)
        self.combo_genero.current(0)
        self.combo_genero.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Estado de ánimo:").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))
        self.combo_animo = ttk.Combobox(form, values=ANIMOS, state="readonly", width=28)
        self.combo_animo.current(0)
        self.combo_animo.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Artista favorito:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 10))
        self.combo_artista = ttk.Combobox(form, values=ARTISTAS_SUGERIDOS, state="readonly", width=28)
        self.combo_artista.current(0)
        self.combo_artista.grid(row=2, column=1, sticky="w", pady=6)

        buttons = ttk.Frame(left, style="TFrame")
        buttons.pack(fill="x", pady=(20, 10))

        ttk.Button(buttons, text="Recomendar música", style="Accent.TButton", command=self._on_recomendar).pack(side="left")
        ttk.Button(buttons, text="🔗 Conectar Spotify", style="Spotify.TButton", command=self._on_conectar_spotify).pack(side="left", padx=(10, 0))

        self.status_var = tk.StringVar(value="Listo para encontrar nuevas canciones.")
        ttk.Label(left, textvariable=self.status_var, style="Subtitle.TLabel", wraplength=700).pack(anchor="w", pady=(16, 0))

        right = ttk.Frame(body, style="Card.TFrame", padding=24)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(right, text="Tus recomendaciones", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(right, text="Estas canciones aparecen según tus preferencias y el algoritmo KNN.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 12))

        resultados_box = ttk.Frame(right, style="Card.TFrame")
        resultados_box.pack(fill="both", expand=True)

        canvas = tk.Canvas(resultados_box, bg="#111827", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(resultados_box, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.cards_container = ttk.Frame(canvas, style="Card.TFrame")
        self.cards_container.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.cards_container, anchor="nw")

        ttk.Label(
            right,
            text="Doble clic en la canción para reproducirla en Spotify",
            style="Subtitle.TLabel",
            wraplength=380
        ).pack(anchor="w", pady=(8, 0))

        ttk.Button(right, text="▶ Reproducir seleccionada", style="Accent.TButton", command=self._on_reproducir_seleccionada).pack(anchor="w", pady=(12, 4))
        ttk.Button(right, text="Crear playlist en Spotify", style="Spotify.TButton", command=self._on_crear_playlist_spotify).pack(anchor="w")

    def _on_recomendar(self):
        genero = self.combo_genero.get()
        animo = self.combo_animo.get()
        artista = self.combo_artista.get()

        try:
            resultados = self.recomendador.recomendar(genero, animo, artista)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar la recomendacion:\n{e}")
            return

        # Renderizar como tarjetas en lugar de lista
        self.ultimas_recomendaciones = []
        for child in getattr(self, "cards_container_children", []):
            try:
                child.destroy()
            except Exception:
                pass
        self.cards_container_children = []

        for _, fila in resultados.iterrows():
            cancion = fila["cancion"]
            artista = fila["artista"]
            self.ultimas_recomendaciones.append((cancion, artista))

            card = ttk.Frame(self.cards_container, style="Card.TFrame", padding=(10, 8))
            card.pack(fill="x", pady=6)
            self.cards_container_children.append(card)

            titulo = ttk.Label(card, text=f"{cancion}", font=("Segoe UI", 12, "bold"))
            titulo.grid(row=0, column=0, sticky="w")
            artista_lbl = ttk.Label(card, text=f"{artista}", style="Subtitle.TLabel")
            artista_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

            acciones = ttk.Frame(card)
            acciones.grid(row=0, column=1, rowspan=2, sticky="e")
            play_btn = ttk.Button(acciones, text="▶", width=4, command=lambda c=cancion, a=artista: self._abrir_o_reproducir(c, a))
            play_btn.pack(side="left", padx=(0, 6))
            open_btn = ttk.Button(acciones, text="Abrir", command=lambda c=cancion, a=artista: self._abrir_en_spotify(c, a))
            open_btn.pack(side="left")

        self.status_var.set(f"Se encontraron recomendaciones para {genero}, {animo} y {artista}.")

    def _on_conectar_spotify(self):
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            messagebox.showwarning(
                "Spotify",
                "Necesitas configurar SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en las variables de entorno."
            )
            return

        try:
            auth_url = construir_url_autorizacion()
        except Exception as e:
            messagebox.showerror("Spotify", f"No se pudo preparar la conexión: {e}")
            return

        self.status_var.set("Abriendo Spotify en el navegador para autorizar la aplicación...")
        try:
            server = HTTPServer(("127.0.0.1", 8000), SpotifyCallbackHandler)
        except OSError as e:
            self.status_var.set("No se pudo iniciar el servidor local para Spotify.")
            messagebox.showerror(
                "Spotify",
                f"No se pudo abrir el puerto local para la conexión: {e}\nCierra otra app que use el puerto 8000 o cambia SPOTIFY_REDIRECT_URI."
            )
            return

        server.auth_code = ""
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        webbrowser.open(auth_url)
        thread.join(120)

        if not server.auth_code:
            self.status_var.set("No se recibió el código de autorización de Spotify.")
            messagebox.showerror("Spotify", "No se pudo recibir la autorización. Comprueba que Spotify abrió la página y autorizaste la app.")
            return

        try:
            token_data = intercambiar_codigo_por_token(server.auth_code)
            self.spotify_token = token_data.get("access_token")
        except Exception as e:
            messagebox.showerror("Spotify", f"Error al intercambiar el código por token: {e}")
            return

        self.status_var.set("Conexión con Spotify completada. Ahora puedes crear una playlist.")
        messagebox.showinfo("Spotify", "Conexión exitosa con Spotify. Ya puedes crear tu playlist.")

    def _on_reproducir_click(self, event):
        self._reproducir_seleccionada()

    def _on_reproducir_seleccionada(self):
        # Si no hay Listbox (usamos tarjetas), pedimos usar los botones de cada tarjeta
        if hasattr(self, "lista_resultados"):
            selection = self.lista_resultados.curselection()
            if not selection:
                messagebox.showinfo("Reproducir", "Selecciona primero una canción de la lista.")
                return
            index = selection[0]
            texto = self.lista_resultados.get(index)
            if "🎵" in texto:
                texto = texto.replace("🎵", "").strip()
            query = urllib.parse.quote(texto)
            url = f"https://open.spotify.com/search/{query}"
            webbrowser.open(url)
            self.status_var.set(f"Abriendo {texto} en Spotify...")
        else:
            messagebox.showinfo("Reproducir", "Usa el botón ▶ en la tarjeta de la canción para reproducirla.")

    def _abrir_o_reproducir(self, cancion, artista):
        # Si estamos conectados a Spotify, intentamos buscar la pista y abrir su preview o URI
        query = f"{cancion} {artista}"
        try:
            if self.spotify_token:
                items = spotify_buscar_pistas(self.spotify_token, query, limite=1)
                if items:
                    item = items[0]
                    if item.get("preview_url"):
                        webbrowser.open(item.get("preview_url"))
                        self.status_var.set(f"Reproduciendo preview de {cancion}...")
                        return
                    if item.get("id"):
                        webbrowser.open(f"https://open.spotify.com/track/{item.get('id')}")
                        self.status_var.set(f"Abriendo {cancion} en Spotify...")
                        return
        except Exception:
            pass
        # Fallback: abrir búsqueda
        q = urllib.parse.quote(query)
        webbrowser.open(f"https://open.spotify.com/search/{q}")
        self.status_var.set(f"Abriendo {cancion} en Spotify...")

    def _abrir_en_spotify(self, cancion, artista):
        q = urllib.parse.quote(f"{cancion} {artista}")
        webbrowser.open(f"https://open.spotify.com/search/{q}")
        self.status_var.set(f"Abriendo {cancion} en Spotify...")

    def _on_crear_playlist_spotify(self):
        if not self.spotify_token:
            messagebox.showwarning("Spotify", "Primero conecta tu cuenta de Spotify.")
            return
        if not self.ultimas_recomendaciones:
            messagebox.showwarning("Spotify", "Primero genera recomendaciones.")
            return

        try:
            req = urllib.request.Request(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {self.spotify_token}"},
                method="GET",
            )
            with urllib.request.urlopen(req) as response:
                profile = json.loads(response.read().decode("utf-8"))
            self.spotify_user_id = profile.get("id")
        except Exception as e:
            messagebox.showerror("Spotify", f"No se pudo obtener el perfil de Spotify: {e}")
            return

        pistas = []
        for cancion, artista in self.ultimas_recomendaciones[:5]:
            query = f"{cancion} {artista}"
            try:
                uris = spotify_buscar_pistas(self.spotify_token, query)
                if uris:
                    pistas.extend(uris)
            except Exception:
                continue

        if not pistas:
            messagebox.showwarning("Spotify", "No se encontraron canciones válidas en Spotify para las recomendaciones.")
            return

        playlist_name = f"MusicAI - {self.combo_genero.get()}"
        try:
            playlist_data = spotify_crear_playlist(self.spotify_token, self.spotify_user_id, playlist_name)
            spotify_agregar_canciones_playlist(self.spotify_token, playlist_data["id"], pistas)
        except Exception as e:
            messagebox.showerror("Spotify", f"No se pudo crear la playlist: {e}")
            return

        self.status_var.set("Playlist creada correctamente en Spotify.")
        messagebox.showinfo("Spotify", f"Playlist creada: {playlist_name}")


# ---------------------------------------------------------------------------
# 4. PUNTO DE ENTRADA
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    recomendador = RecomendadorMusical()
    app = MusicAIApp(recomendador)
    ejecutar_aplicacion(app)
