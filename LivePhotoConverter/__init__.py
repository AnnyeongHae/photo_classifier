"""
LivePhotoConverter: Independent service for converting Live Photos to static images.

A production-ready tool for extracting the best frame from Live Photo videos (MP4)
and converting to high-quality JPEG with metadata preservation.

Key Features:
- Intelligent frame selection (first, middle, sharpest)
- Ensemble focus detection (Laplacian + Brenner metrics)
- EXIF metadata preservation via exiftool
- Batch CLI processing + optional GUI
- In-memory processing (no temp files)

Quick Start:
    # CLI batch processing
    python -m cli.batch_processor --input ./videos --output ./images

    # Python API
    from LivePhotoConverter.core import FrameExtractor
    frames, metadata = FrameExtractor().extract_candidates("photo.mp4", return_metadata=True)
"""

__version__ = "1.0.0"
__author__ = "Photo Classification System"
__all__ = ["FrameExtractor", "MetadataHandler", "ImageConverter", "FocusDetector"]

from .core import (
    FrameExtractor,
    MetadataHandler,
    ImageConverter,
    FocusDetector,
)
