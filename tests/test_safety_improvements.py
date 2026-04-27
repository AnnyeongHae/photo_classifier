# -*- coding: utf-8 -*-
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.archive import expand_archives
from core.mover import move_files
from core.video_converter import ProcessRegistry, _resolve_output_path
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

    def test_live_photo_worker_filters_out_long_videos(self):
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


if __name__ == "__main__":
    unittest.main()
