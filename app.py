import base64
import json
import os
import urllib.parse
import urllib.request
import webbrowser
from urllib.error import HTTPError

from flask import Flask, redirect, render_template, request, session, url_for

from recommender import ANIMOS, GENEROS, RecomendadorMusical

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "music-ai-secret-key")

DEFAULT_SPOTIFY_CLIENT_ID = "06ec744e95424070b3b011ca36bc7abb"
DEFAULT_SPOTIFY_CLIENT_SECRET = "9b210caf6fa94723a25b7b81fe7a6dca"
DEFAULT_REDIRECT_URI = "https://tu-link-de-vercel.vercel.app/callback"


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

env_redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "").strip()
if env_redirect_uri and env_redirect_uri.lower() not in {
    "tu_redirect_uri",
    "your_redirect_uri",
    "redirect_uri_here",
    "replace_me",
} and env_redirect_uri != DEFAULT_REDIRECT_URI:
    print(
        f"[MusicAI] WARNING: SPOTIFY_REDIRECT_URI env value {env_redirect_uri} ignored. "
        f"Using fixed callback {DEFAULT_REDIRECT_URI} because the app runs on port 8888."
    )
SPOTIFY_REDIRECT_URI = DEFAULT_REDIRECT_URI
SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private user-read-private"

print(
    f"[MusicAI] Spotify configured: client_id={'SET' if SPOTIFY_CLIENT_ID else 'MISSING'}, "
    f"client_secret={'SET' if SPOTIFY_CLIENT_SECRET else 'MISSING'}, "
    f"redirect_uri={SPOTIFY_REDIRECT_URI}"
)

recommendador = RecomendadorMusical()

def spotify_is_configured():
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)


def spotify_auth_url():
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "show_dialog": "true",
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)


def spotify_exchange_code(code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }).encode("utf-8")
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
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


def spotify_search_tracks(token, query, limit=1):
    request_url = (
        "https://api.spotify.com/v1/search?q="
        + urllib.parse.quote(query)
        + "&type=track&limit="
        + str(limit)
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


def spotify_create_playlist(token, user_id, name, description="Playlist creada con MusicAI"):
    payload = json.dumps({"name": name, "description": description, "public": False}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/users/{user_id}/playlists",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def spotify_add_tracks(token, playlist_id, uris):
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


def get_spotify_token():
    return session.get("spotify_token")


def get_last_recommendations():
    return session.get("last_recommendations", [])


@app.route("/")
@app.route("/bienvenido")
def welcome():
    return render_template("welcome.html")


@app.route("/app", methods=["GET", "POST"])
def index():
    recommendations = get_last_recommendations()
    spotify_connected = bool(get_spotify_token())
    spotify_configured = spotify_is_configured()
    message = session.pop("spotify_message", None)

    selected_genero = GENEROS[0]
    selected_animo = ANIMOS[0]
    selected_artista = "Bad Bunny" if "Bad Bunny" in recommendador.artistas_disponibles else recommendador.artistas_disponibles[0]

    if request.method == "POST":
        genero = request.form.get("genero") or selected_genero
        animo = request.form.get("animo") or selected_animo
        artista = request.form.get("artista") or selected_artista

        selected_genero = genero
        selected_animo = animo
        selected_artista = artista

        results = recommendador.recomendar(genero, animo, artista)

        cards = []
        token = get_spotify_token()
        for _, fila in results.iterrows():
            title = fila["cancion"]
            artist = fila["artista"]
            query = f"{title} {artist}"
            search_url = "https://open.spotify.com/search/" + urllib.parse.quote(query)

            preview_url = None
            image_url = None
            if token:
                try:
                    spotify_results = spotify_search_tracks(token, query, limit=1)
                    if spotify_results:
                        first_match = spotify_results[0]
                        preview_url = first_match.get("preview_url")
                        image_data = first_match.get("image")
                        if isinstance(image_data, dict):
                            image_url = image_data.get("url")
                except Exception:
                    pass

            cards.append(
                {
                    "title": title,
                    "artist": artist,
                    "search_url": search_url,
                    "preview_url": preview_url,
                    "image_url": image_url,
                }
            )

        session["last_recommendations"] = cards
        recommendations = cards
        message = "¡Recomendaciones generadas con éxito!"

    return render_template(
        "index.html",
        generos=GENEROS,
        animo=ANIMOS,
        artistas=recommendador.artistas_disponibles,
        recommendations=recommendations,
        spotify_connected=spotify_connected,
        spotify_configured=spotify_configured,
        message=message,
        selected_genero=selected_genero,
        selected_animo=selected_animo,
        selected_artista=selected_artista,
    )


@app.route("/connect_spotify")
def connect_spotify():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        session["spotify_message"] = (
            "Configura SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET como variables de entorno "
            "antes de conectar Spotify."
        )
        return redirect(url_for("index"))
    return redirect(spotify_auth_url())


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))
    try:
        token_data = spotify_exchange_code(code)
    except HTTPError:
        return redirect(url_for("index"))
    session["spotify_token"] = token_data.get("access_token")
    session["spotify_message"] = "Spotify conectado correctamente. Ahora puedes reproducir previews desde la página."
    return redirect(url_for("index"))


@app.route("/create_playlist")
def create_playlist():
    token = get_spotify_token()
    recommendations = get_last_recommendations()
    if not token:
        session["spotify_message"] = "Conecta Spotify primero para crear la playlist."
        return redirect(url_for("index"))

    if not recommendations:
        session["spotify_message"] = "Genera recomendaciones primero para crear una playlist."
        return redirect(url_for("index"))

    try:
        req = urllib.request.Request(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(req) as response:
            profile = json.loads(response.read().decode("utf-8"))
        user_id = profile.get("id")

        uris = []
        for rec in recommendations:
            query = f"{rec['title']} {rec['artist']}"
            tracks = spotify_search_tracks(token, query, limit=1)
            if tracks and tracks[0].get("uri"):
                uris.append(tracks[0]["uri"])

        if not uris:
            session["spotify_message"] = (
                "No se encontraron previews válidos para crear la playlist. "
                "Usa Spotify para escuchar las canciones individualmente."
            )
            return redirect(url_for("index"))

        playlist = spotify_create_playlist(token, user_id, "MusicAI Recomendadas")
        spotify_add_tracks(token, playlist["id"], uris)
        session["spotify_message"] = "Playlist creada correctamente en tu cuenta de Spotify."
    except Exception:
        session["spotify_message"] = "No se pudo crear la playlist en Spotify. Intenta de nuevo más tarde."

    return redirect(url_for("index"))


PORT = 8888

def open_browser():
    webbrowser.open_new_tab(f"http://127.0.0.1:{PORT}/")


if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        open_browser()
    app.run(debug=True, port=PORT)
