"""
Quick validation test for LivePhotoConverter CLI and core modules.
Verifies that all modules can be imported and basic functionality works.
"""

import sys
from pathlib import Path

# Add LivePhotoConverter to path
lpc_path = Path(__file__).parent
sys.path.insert(0, str(lpc_path.parent))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        from LivePhotoConverter.core import (
            FrameExtractor,
            MetadataHandler,
            ImageConverter,
            FocusDetector,
        )
        print("✓ Core modules imported successfully")
        
        from LivePhotoConverter.cli.batch_processor import BatchProcessor
        print("✓ CLI BatchProcessor imported successfully")
        
        try:
            from LivePhotoConverter.ui.thumbnail_selector import ThumbnailSelector
            print("✓ UI ThumbnailSelector imported (PySide6 available)")
        except ImportError as e:
            print(f"⚠ UI module skipped: {e}")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_focus_detector():
    """Test FocusDetector functionality."""
    print("\nTesting FocusDetector...")
    
    try:
        import numpy as np
        from LivePhotoConverter.core import FocusDetector
        
        detector = FocusDetector(resize_scale=0.5)
        
        # Create dummy test frame (640x480 RGB)
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Test compute_sharpness
        score = detector.compute_sharpness(test_frame, use_ensemble=True)
        print(f"✓ Computed sharpness score: {score:.2f}")
        
        # Test find_sharpest_frame
        frames = [test_frame, test_frame, test_frame]
        best_idx, best_score = detector.find_sharpest_frame(frames)
        print(f"✓ Found sharpest frame at index: {best_idx}, score: {best_score:.2f}")
        
        return True
    except Exception as e:
        print(f"✗ FocusDetector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_converter():
    """Test ImageConverter functionality."""
    print("\nTesting ImageConverter...")
    
    try:
        import numpy as np
        from LivePhotoConverter.core import ImageConverter
        
        converter = ImageConverter(jpeg_quality=95)
        
        # Create dummy test frame
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Test resize
        resized = converter.resize_frame(test_frame, width=320, height=240)
        print(f"✓ Resized frame from {test_frame.shape} to {resized.shape}")
        
        # Test thumbnail
        thumb = converter.resize_frame(test_frame, width=100, height=100, preserve_aspect=True)
        print(f"✓ Created thumbnail: {thumb.shape}")
        
        return True
    except Exception as e:
        print(f"✗ ImageConverter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cli_help():
    """Test CLI help."""
    print("\nTesting CLI help...")
    
    try:
        from LivePhotoConverter.cli.batch_processor import main
        import io
        import contextlib
        
        # Capture help output
        old_argv = sys.argv
        sys.argv = ["batch_processor", "--help"]
        
        help_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(help_buffer):
                main()
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv
        
        help_text = help_buffer.getvalue()
        if "--input" in help_text and "--output" in help_text:
            print("✓ CLI help shows expected options")
            return True
        else:
            print("✗ CLI help missing expected options")
            return False
    
    except Exception as e:
        print(f"✗ CLI test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("LivePhotoConverter - Validation Tests")
    print("=" * 60)
    
    results = {
        "Imports": test_imports(),
        "FocusDetector": test_focus_detector(),
        "ImageConverter": test_image_converter(),
        "CLI Help": test_cli_help(),
    }
    
    print("\n" + "=" * 60)
    print("Test Results Summary:")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    
    print("=" * 60)
    print(f"Total: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
