import unittest

from recommender import RecomendadorMusical


class RecommenderTest(unittest.TestCase):
    def test_artistas_del_dataset_aparecen_en_features(self):
        recomendador = RecomendadorMusical()
        artista = str(recomendador.df["artista"].dropna().iloc[0]).strip()

        self.assertIn(artista, recomendador.features.columns)

    def test_recomendador_devuelve_mas_de_cinco_canciones(self):
        recomendador = RecomendadorMusical()
        resultados = recomendador.recomendar("Pop", "Feliz", "Bad Bunny")

        self.assertGreaterEqual(len(resultados), 6)


if __name__ == "__main__":
    unittest.main()
