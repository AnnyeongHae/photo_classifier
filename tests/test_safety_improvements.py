# -*- coding: utf-8 -*-
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.archive import expand_archives
from core.mover import move_files
from core.video_converter import ProcessRegistry, _resolve_output_path


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


if __name__ == "__main__":
    unittest.main()
