"""
Batch processing for Live Photo conversion via CLI.
Handles folder-based processing with logging and error recovery.
"""

import argparse
import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import sys

from ..core import FrameExtractor, MetadataHandler, ImageConverter


logger = logging.getLogger(__name__)


class BatchProcessor:
    """Processes Live Photo files in batch mode."""
    
    def __init__(
        self,
        exiftool_path: Optional[str] = None,
        output_format: str = "png",
        jpeg_quality: int = 100,
        preserve_metadata: bool = True,
        use_ensemble_focus: bool = True,
        log_file: Optional[Path] = None
    ):
        """
        Initialize batch processor.
        
        Args:
            exiftool_path: Path to exiftool executable
            output_format: Output format ('png' for lossless, 'jpg' for compressed). Default: 'png'
            jpeg_quality: JPEG quality (1-100, only used if output_format='jpg')
            preserve_metadata: Whether to copy metadata from MP4 to output
            use_ensemble_focus: Use ensemble focus detection
            log_file: Path to log file (if None, logs to console)
        """
        if output_format.lower() not in ("png", "jpg", "jpeg"):
            raise ValueError("output_format must be 'png' or 'jpg'")
        
        self.output_format = output_format.lower() if output_format.lower() != "jpeg" else "jpg"
        
        self.frame_extractor = FrameExtractor(use_ensemble=use_ensemble_focus)
        self.image_converter = ImageConverter(jpeg_quality=jpeg_quality)
        
        try:
            self.metadata_handler = MetadataHandler(exiftool_path)
            self.preserve_metadata = preserve_metadata
        except FileNotFoundError as e:
            logger.warning(f"exiftool not found - metadata preservation disabled: {e}")
            self.metadata_handler = None
            self.preserve_metadata = False
        
        self._setup_logging(log_file)
    
    def _setup_logging(self, log_file: Optional[Path] = None):
        """Setup logging configuration."""
        fmt = "%(asctime)s [%(levelname)s] %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        
        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(fmt, datefmt))
            logger.addHandler(handler)
    
    def process_folder(
        self,
        input_folder: str | Path,
        output_folder: str | Path,
        patterns: List[str] = None,
        dry_run: bool = False,
        skip_existing: bool = True
    ) -> Dict[str, int]:
        """
        Process all Live Photo files in a folder.
        
        Args:
            input_folder: Folder containing MP4 files
            output_folder: Destination folder for JPEG files
            patterns: File patterns to match (default: ["*.mov", "*.mp4"])
            dry_run: If True, don't actually process files
            skip_existing: If True, skip files that already have output
            
        Returns:
            Dictionary with statistics: {processed, skipped, failed}
        """
        input_folder = Path(input_folder)
        output_folder = Path(output_folder)
        
        if not input_folder.exists():
            logger.error(f"Input folder not found: {input_folder}")
            return {"processed": 0, "skipped": 0, "failed": 0}
        
        if patterns is None:
            patterns = ["*.mov", "*.mp4", "*.MP4", "*.MOV"]
        
        # Collect files
        video_files = []
        for pattern in patterns:
            video_files.extend(input_folder.glob(f"**/{pattern}"))
        
        if not video_files:
            logger.warning(f"No video files found matching patterns: {patterns}")
            return {"processed": 0, "skipped": 0, "failed": 0}
        
        logger.info(f"Found {len(video_files)} video files to process")
        
        stats = {"processed": 0, "skipped": 0, "failed": 0}
        
        for i, video_file in enumerate(video_files, 1):
            logger.info(f"Processing [{i}/{len(video_files)}] {video_file.name}")
            
            # Generate output path with correct extension
            file_ext = ".png" if self.output_format == "png" else ".jpg"
            output_file = output_folder / f"{video_file.stem}{file_ext}"
            
            if output_file.exists() and skip_existing:
                logger.info(f"  -> Skipped (output exists)")
                stats["skipped"] += 1
                continue
            
            if dry_run:
                logger.info(f"  -> [DRY RUN] Would save to {output_file}")
                stats["processed"] += 1
                continue
            
            try:
                self._process_single_file(video_file, output_file)
                stats["processed"] += 1
            except Exception as e:
                logger.error(f"  -> Failed: {e}")
                stats["failed"] += 1
        
        return stats
    
    def _process_single_file(self, video_file: Path, output_file: Path):
        """Process a single Live Photo file."""
        # Extract frames
        frames, metadata = self.frame_extractor.extract_candidates(video_file, return_metadata=True)
        
        # Use sharpest frame (index 2) for conversion
        frame_rgb = frames[2]
        
        # Save image in correct format
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        if self.output_format == "png":
            self.image_converter.save_frame_as_png(frame_rgb, output_file)
        else:
            self.image_converter.save_frame_as_jpeg(frame_rgb, output_file)
        
        logger.info(f"  -> Saved: {output_file} ({self.output_format.upper()})")
        
        # Preserve metadata if available
        if self.preserve_metadata and self.metadata_handler:
            datetime_str = self.metadata_handler.get_datetime_from_video(video_file)
            overwrite_tags = None
            if datetime_str:
                overwrite_tags = {"DateTimeOriginal": datetime_str}
            
            self.metadata_handler.copy_metadata_to_image(video_file, output_file, overwrite_tags)
            logger.info(f"  -> Metadata preserved")
    
    def process_with_manual_review(
        self,
        video_file: str | Path,
        output_folder: str | Path
    ) -> Optional[Path]:
        """
        Process a single Live Photo with manual frame selection UI.
        (Requires UI module)
        
        Args:
            video_file: Path to MP4 file
            output_folder: Destination folder
            
        Returns:
            Path to saved image or None if cancelled
        """
        try:
            from ..ui.thumbnail_selector import ThumbnailSelector
        except ImportError:
            logger.error("UI module not available (PySide6 not installed)")
            return None
        
        video_file = Path(video_file)
        output_folder = Path(output_folder)
        
        try:
            # Extract candidate frames
            frames, metadata = self.frame_extractor.extract_candidates(video_file, return_metadata=True)
            
            # Show selection UI
            selector = ThumbnailSelector()
            selected_idx = selector.show_selection_dialog(frames, metadata)
            
            if selected_idx is None:
                logger.info("User cancelled selection")
                return None
            
            # Save selected frame
            output_folder.mkdir(parents=True, exist_ok=True)
            output_file = output_folder / f"{video_file.stem}.jpg"
            
            self.image_converter.save_frame_as_jpeg(frames[selected_idx], output_file)
            logger.info(f"Saved: {output_file}")
            
            # Preserve metadata
            if self.preserve_metadata and self.metadata_handler:
                datetime_str = self.metadata_handler.get_datetime_from_video(video_file)
                overwrite_tags = None
                if datetime_str:
                    overwrite_tags = {"DateTimeOriginal": datetime_str}
                
                self.metadata_handler.copy_metadata_to_image(video_file, output_file, overwrite_tags)
                logger.info("Metadata preserved")
            
            return output_file
        
        except Exception as e:
            logger.error(f"Failed to process {video_file}: {e}")
            return None


def main():
    """CLI entry point for batch processing."""
    parser = argparse.ArgumentParser(
        description="Convert Live Photos (MP4) to static images (JPEG)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ~/Photos/LivePhotos --output ~/Photos/Converted
  %(prog)s --input . --output ./output --pattern "*.MOV" --dry-run
  %(prog)s --input ./videos --output ./images --no-metadata --quality 90
        """
    )
    
    parser.add_argument(
        "--input",
        required=True,
        help="Input folder containing Live Photo files (MP4/MOV)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output folder for converted image files"
    )
    parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        default="png",
        help="Output format (default: png for lossless quality)"
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="File pattern to match (e.g., *.mov). Can be used multiple times."
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=98,
        help="JPEG quality 1-100 (only used if --format jpg, default: 98)"
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Disable EXIF metadata preservation"
    )
    parser.add_argument(
        "--exiftool",
        help="Path to exiftool executable (if not in PATH)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually processing"
    )
    parser.add_argument(
        "--log",
        help="Log file path (default: console output)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Run processor
    processor = BatchProcessor(
        exiftool_path=args.exiftool,
        output_format=args.format,
        jpeg_quality=args.quality,
        preserve_metadata=not args.no_metadata,
        log_file=Path(args.log) if args.log else None
    )
    
    stats = processor.process_folder(
        input_folder=args.input,
        output_folder=args.output,
        patterns=args.patterns,
        dry_run=args.dry_run,
        skip_existing=True
    )
    
    # Print summary
    print("\n" + "=" * 50)
    print("Batch Processing Summary:")
    print(f"  Processed: {stats['processed']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Failed:    {stats['failed']}")
    print("=" * 50)
    
    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
