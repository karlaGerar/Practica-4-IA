import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import music_ai


class MusicAITest(unittest.TestCase):
    def test_cargar_datos_devuelve_dataframe_y_features(self):
        df, features = music_ai.cargar_datos()

        self.assertFalse(df.empty)
        self.assertFalse(features.empty)
        self.assertIn("energia", features.columns)
        self.assertTrue(set(music_ai.GENEROS).issubset(features.columns))
        self.assertTrue(set(music_ai.ANIMOS).issubset(features.columns))

    def test_construir_vector_usuario_asigna_valores_correctos(self):
        _, features = music_ai.cargar_datos()
        vector = music_ai.construir_vector_usuario(
            "Pop", "Feliz", "Bad Bunny", features.columns
        )

        self.assertEqual(vector.loc[0, "Pop"], 1)
        self.assertEqual(vector.loc[0, "Feliz"], 1)
        self.assertEqual(vector.loc[0, "Bad Bunny"], 2)
        self.assertEqual(vector.loc[0, "energia"], 0.5)

    def test_ejecutar_aplicacion_silencia_keyboardinterrupt(self):
        class DummyApp:
            def __init__(self):
                self.destroy_called = False

            def mainloop(self):
                raise KeyboardInterrupt

            def destroy(self):
                self.destroy_called = True

        app = DummyApp()
        music_ai.ejecutar_aplicacion(app)

        self.assertTrue(app.destroy_called)

    def test_construir_url_autorizacion_requiere_client_id(self):
        original_id = os.environ.get("SPOTIFY_CLIENT_ID")
        os.environ.pop("SPOTIFY_CLIENT_ID", None)
        try:
            with self.assertRaises(ValueError):
                music_ai.construir_url_autorizacion()
        finally:
            if original_id is not None:
                os.environ["SPOTIFY_CLIENT_ID"] = original_id


if __name__ == "__main__":
    unittest.main()
