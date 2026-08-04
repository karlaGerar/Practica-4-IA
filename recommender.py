import os

import pandas as pd
from sklearn.neighbors import NearestNeighbors

RUTA_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canciones.csv")
GENEROS = ["Pop", "Rock", "Reggaeton", "Electronica", "Regional Mexicano", "Rap"]
ANIMOS = ["Feliz", "Triste", "Relajado", "Motivado", "Enamorado"]
DEFAULT_RECOMMENDATIONS = 10
ARTISTAS_SUGERIDOS = [
    "Bad Bunny",
    "Taylor Swift",
    "Peso Pluma",
    "Karol G",
    "Ed Sheeran",
    "Shakira",
    "Maluma",
    "Billie Eilish",
    "Dua Lipa",
    "The Weeknd",
    "Rosalía",
    "J Balvin",
    "Adele",
    "Coldplay",
    "Drake",
    "Justin Bieber",
    "Bruno Mars",
    "Camila Cabello",
    "Rihanna",
    "Karol G"
]
ENERGIA_MAP = {"Baja": 0.0, "Media": 0.5, "Alta": 1.0}


class RecomendadorMusical:
    def __init__(self):
        self.df, self.features = self.cargar_datos()
        artistas_dataset = [str(artista).strip() for artista in self.df["artista"].dropna().unique() if str(artista).strip()]
        artistas_base = [str(artista).strip() for artista in ARTISTAS_SUGERIDOS if str(artista).strip()]
        self.artistas_disponibles = sorted(set(artistas_base) | set(artistas_dataset))
        self.n_recomendaciones = min(DEFAULT_RECOMMENDATIONS, len(self.features))
        self.modelo = NearestNeighbors(n_neighbors=self.n_recomendaciones, metric="euclidean")
        self.modelo.fit(self.features)

    def cargar_datos(self):
        df = pd.read_csv(RUTA_CSV)

        genero_dummies = pd.get_dummies(df["genero"])
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

        artistas = [
            str(artista).strip()
            for artista in df["artista"].dropna().unique()
            if str(artista).strip()
        ]
        artistas = sorted(set(ARTISTAS_SUGERIDOS) | set(artistas))
        artista_cols = pd.DataFrame(
            {
                art: (df["artista"].astype(str).str.strip() == art).astype(int)
                for art in artistas
            }
        )

        features = pd.concat(
            [genero_dummies, animo_dummies, artista_cols, energia_num.rename("energia")],
            axis=1,
        )
        return df, features

    def construir_vector_usuario(self, genero, animo, artista):
        vector = {col: 0 for col in self.features.columns}
        if genero in vector:
            vector[genero] = 1
        if animo in vector:
            vector[animo] = 1
        if artista in vector:
            vector[artista] = 2
        vector["energia"] = 0.5
        return pd.DataFrame([vector])[self.features.columns]

    def recomendar(self, genero, animo, artista):
        vector_usuario = self.construir_vector_usuario(genero, animo, artista)
        distancias, indices = self.modelo.kneighbors(vector_usuario, n_neighbors=self.n_recomendaciones)
        resultados = self.df.iloc[indices[0]].copy()
        resultados["distancia"] = distancias[0]
        return resultados.sort_values("distancia")
