# -*- coding: utf-8 -*-
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from core.archive import expand_archives
from core.mover import move_files
from core.video_converter import ProcessRegistry, _resolve_output_path
from LivePhotoConverter.core.image_converter import ImageConverter
from workers.live_photo_worker import LivePhotoConfig, LivePhotoResult, LivePhotoWorker


class SafetyImprovementTests(unittest.TestCase):
    def test_archive_extraction_skips_path_traversal_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "photos.zip"
            outside = root.parent / "evil.jpg"
            if outside.exists():
                outside.unlink()

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../evil.jpg", b"bad")
                zf.writestr("album/good.jpg", b"good")

            expand_archives(root)

            self.assertFalse(outside.exists())
            self.assertEqual((root / ".unzipped" / "photos" / "album" / "good.jpg").read_bytes(), b"good")
            self.assertTrue((root / "_Processed_ZIPs" / "photos.zip").exists())

    def test_move_files_can_copy_without_removing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.jpg"
            dest_dir = root / "out"
            src.write_bytes(b"image")

            stats = move_files(
                [
                    {
                        "source_path": str(src),
                        "target_folder": str(dest_dir),
                        "file_name": "input.jpg",
                        "sort_status": "Success",
                    }
                ],
                remove_source=False,
            )

            self.assertTrue(src.exists())
            self.assertEqual((dest_dir / "input.jpg").read_bytes(), b"image")
            self.assertEqual(stats.verified, 1)
            self.assertEqual(stats.removed, 0)
            self.assertEqual(stats.copied_only, 1)

    def test_video_output_reservation_prevents_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            reserved = set()
            first = _resolve_output_path(Path("a/clip.mov"), output, reserved_paths=reserved)
            reserved.add(first)
            second = _resolve_output_path(Path("b/clip.mov"), output, reserved_paths=reserved)

            self.assertEqual(first.name, "clip.mov")
            self.assertEqual(second.name, "clip_1.mov")

    def test_process_registry_terminates_all_running_processes(self):
        class FakeProcess:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        first = FakeProcess()
        second = FakeProcess()
        registry = ProcessRegistry()
        registry.register(first)
        registry.register(second)
        registry.terminate_all()

        self.assertTrue(first.terminated)
        self.assertTrue(second.terminated)

    def test_live_photo_worker_collects_mobile_video_extensions_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.MOV", "b.mp4", "c.M4V", "d.3gp", "e.3G2", "ignore.jpg", "raw.DNG"):
                (root / name).write_bytes(b"stub")

            worker = LivePhotoWorker(
                LivePhotoConfig(input_folder=root, output_folder=root / "out")
            )
            names = sorted(path.name for path in worker._collect_video_files(root))

            self.assertEqual(names, ["a.MOV", "b.mp4", "c.M4V", "d.3gp", "e.3G2"])

    def test_live_photo_worker_moves_long_videos_to_no_livephoto(self):
        class FakeExtractor:
            def get_video_info(self, path):
                return {"duration_seconds": 12.0 if path.name == "long.MOV" else 3.0}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            short = root / "short.MOV"
            long = root / "long.MOV"
            short.write_bytes(b"stub")
            long.write_bytes(b"stub")

            worker = LivePhotoWorker(
                LivePhotoConfig(
                    input_folder=root,
                    output_folder=root / "out",
                    max_duration_seconds=10,
                )
            )
            result = LivePhotoResult()
            kept = worker._filter_by_duration([short, long], FakeExtractor(), result)

            self.assertEqual([path.name for path in kept], ["short.MOV"])
            self.assertEqual(result.skipped, 1)
            self.assertFalse(long.exists())
            self.assertTrue((root / "out" / "no_livephoto" / "long.MOV").exists())

    def test_live_photo_image_converter_saves_to_unicode_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "라이브포토 결과 !@#"
            frame = np.zeros((8, 8, 3), dtype=np.uint8)
            frame[:, :, 0] = 255
            converter = ImageConverter(jpeg_quality=95)

            jpg = converter.save_frame_as_jpeg(frame, output / "썸네일.jpg")
            png = converter.save_frame_as_png(frame, output / "썸네일.png")

            self.assertTrue(jpg.exists())
            self.assertTrue(png.exists())


if __name__ == "__main__":
    unittest.main()
