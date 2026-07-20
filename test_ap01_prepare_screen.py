import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ap01_prepare_screen import build


class PrepareScreenTests(unittest.TestCase):
    def test_still_image_becomes_two_frame_gif89a(self) -> None:
        from PIL import Image

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "still.png"
            output = root / "screen.gif"
            Image.new("RGB", (800, 600), "#244466").save(source)
            info = build(
                source,
                output,
                mode="contain",
                background=(1, 4, 11),
                duration=1200,
                maximum_bytes=90_000,
            )
            with Image.open(output) as image:
                self.assertEqual(image.size, (320, 240))
                self.assertEqual(image.n_frames, 2)
                self.assertEqual(image.info.get("version"), b"GIF89a")
            self.assertEqual(info["source_frames"], 1)

    def test_animated_gif_keeps_visible_motion_and_timing(self) -> None:
        from PIL import Image

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "animated.gif"
            output = root / "screen.gif"
            frames = [
                Image.new("RGB", (160, 120), color)
                for color in ("#FF0000", "#00FF00", "#0000FF")
            ]
            frames[0].save(
                source,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                loop=0,
                duration=[120, 240, 360],
                disposal=2,
            )
            info = build(
                source,
                output,
                mode="stretch",
                background=(1, 4, 11),
                duration=1200,
                maximum_bytes=90_000,
                maximum_frames=8,
                minimum_frame_ms=100,
            )
            colors = []
            durations = []
            with Image.open(output) as image:
                self.assertEqual(image.n_frames, 3)
                self.assertEqual(image.info.get("version"), b"GIF89a")
                for index in range(image.n_frames):
                    image.seek(index)
                    colors.append(image.convert("RGB").getpixel((160, 120)))
                    durations.append(image.info.get("duration"))
            self.assertEqual(len(set(colors)), 3)
            self.assertEqual(durations, [120, 240, 360])
            self.assertEqual(info["source_frames"], 3)
            self.assertEqual(info["output_frames"], 3)
            self.assertEqual(info["total_duration_ms"], 720)


if __name__ == "__main__":
    unittest.main()
