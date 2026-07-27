"""
Sample usage examples for LivePhotoConverter.
Demonstrates core API, batch processing, and hybrid modes.
"""

from pathlib import Path
from LivePhotoConverter.core import (
    FrameExtractor,
    ImageConverter,
    MetadataHandler,
    FocusDetector,
)
from LivePhotoConverter.cli.batch_processor import BatchProcessor


def example_1_extract_frames():
    """Example 1: Extract 3 candidate frames from a Live Photo."""
    print("\n=== Example 1: Extract Frames ===")
    
    video_path = "sample_video.mp4"  # Replace with actual file
    
    # Create extractor
    extractor = FrameExtractor(use_ensemble=True)
    
    # Extract candidates with metadata
    frames, metadata = extractor.extract_candidates(video_path, return_metadata=True)
    
    print(f"Video: {video_path}")
    print(f"Total frames: {metadata['total_frames']}")
    print(f"FPS: {metadata['fps']}")
    print(f"Duration: {metadata['duration_seconds']:.2f} seconds")
    print(f"Frame indices: {metadata['frame_indices']}")
    print(f"Sharpness scores: {[f'{s:.2f}' for s in metadata['sharpness_scores']]}")
    print(f"Best frame: {metadata['frame_labels'][2]} (score: {metadata['sharpness_scores'][2]:.2f})")


def example_2_save_frames():
    """Example 2: Save extracted frames as JPEG."""
    print("\n=== Example 2: Save Frames ===")
    
    video_path = "sample_video.mp4"
    output_dir = Path("output_frames")
    
    # Extract frames
    extractor = FrameExtractor()
    frames, metadata = extractor.extract_candidates(video_path, return_metadata=True)
    
    # Save each frame
    converter = ImageConverter(jpeg_quality=95)
    for i, (frame_rgb, label) in enumerate(zip(frames, metadata['frame_labels'])):
        output_file = output_dir / f"frame_{i}_{label.replace(' ', '_')}.jpg"
        converter.save_frame_as_jpeg(frame_rgb, output_file)
        print(f"Saved: {output_file}")


def example_3_preserve_metadata():
    """Example 3: Preserve EXIF metadata from MP4 to JPEG."""
    print("\n=== Example 3: Preserve Metadata ===")
    
    video_path = "sample_video.mp4"
    image_path = "output_image.jpg"
    
    # First, extract and save frame
    extractor = FrameExtractor()
    frames, _ = extractor.extract_candidates(video_path)
    
    converter = ImageConverter(jpeg_quality=95)
    converter.save_frame_as_jpeg(frames[2], image_path)
    
    # Then preserve metadata
    metadata_handler = MetadataHandler()
    
    # Get original datetime
    original_datetime = metadata_handler.get_datetime_from_video(video_path)
    print(f"Original datetime: {original_datetime}")
    
    # Copy metadata
    success = metadata_handler.copy_metadata_to_image(video_path, image_path)
    if success:
        print(f"Metadata preserved in {image_path}")
    else:
        print("Metadata preservation failed")


def example_4_batch_processing():
    """Example 4: Batch process entire folder."""
    print("\n=== Example 4: Batch Processing ===")
    
    input_folder = Path("live_photos")
    output_folder = Path("converted_photos")
    
    # Create processor
    processor = BatchProcessor(
        preserve_metadata=True,
        jpeg_quality=95,
        use_ensemble_focus=True
    )
    
    # Process folder
    stats = processor.process_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        patterns=["*.mp4", "*.mov"],
        dry_run=False,
        skip_existing=True
    )
    
    print(f"\nBatch Processing Results:")
    print(f"  Processed: {stats['processed']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Failed:    {stats['failed']}")


def example_5_focus_detection():
    """Example 5: Focus detection (sharpness scoring)."""
    print("\n=== Example 5: Focus Detection ===")
    
    video_path = "sample_video.mp4"
    
    # Extract all frames (in real usage, you'd sample)
    extractor = FrameExtractor()
    
    # Get video info
    info = extractor.get_video_info(video_path)
    print(f"Video resolution: {info['width']}x{info['height']}")
    print(f"Total frames: {info['total_frames']}")
    
    # Find sharpest frame
    detector = FocusDetector(resize_scale=0.5)
    
    # Scan frames (sample every 10th frame for demo)
    sample_frames = []
    for i in range(0, info['total_frames'], max(1, info['total_frames'] // 30)):
        frame = extractor.extract_frame_at_index(video_path, i)
        sample_frames.append(frame)
    
    best_idx, best_score = detector.find_sharpest_frame(sample_frames)
    print(f"Sharpest frame index (of samples): {best_idx}")
    print(f"Sharpness score: {best_score:.2f}")


def example_6_custom_processing():
    """Example 6: Custom processing pipeline."""
    print("\n=== Example 6: Custom Processing ===")
    
    video_path = "sample_video.mp4"
    
    # Step 1: Extract
    extractor = FrameExtractor(use_ensemble=True)
    frames, metadata = extractor.extract_candidates(video_path, return_metadata=True)
    
    # Step 2: Process (e.g., resize before saving)
    converter = ImageConverter(jpeg_quality=95)
    
    # Resize and create thumbnail
    best_frame = frames[2]  # Sharpest frame
    resized = converter.resize_frame(best_frame, width=1920, height=1080, preserve_aspect=True)
    thumbnail = converter.resize_frame(best_frame, width=300, height=300, preserve_aspect=True)
    
    # Step 3: Save
    converter.save_frame_as_jpeg(resized, "full_res_output.jpg")
    converter.save_frame_as_jpeg(thumbnail, "thumbnail.jpg")
    
    print("Saved full resolution and thumbnail")
    
    # Step 4: Preserve metadata
    metadata_handler = MetadataHandler()
    metadata_handler.copy_metadata_to_image(video_path, "full_res_output.jpg")
    
    print("Metadata preserved")


def example_7_hybrid_mode():
    """Example 7: Hybrid mode - automatic + manual review option."""
    print("\n=== Example 7: Hybrid Mode (Auto + Manual) ===")
    
    video_path = "sample_video.mp4"
    
    processor = BatchProcessor(preserve_metadata=True)
    
    # Option 1: Automatic (non-interactive)
    print("Automatic mode: Using sharpest frame")
    extractor = FrameExtractor()
    frames, metadata = extractor.extract_candidates(video_path)
    converter = ImageConverter()
    converter.save_frame_as_jpeg(frames[2], "auto_output.jpg")
    print("Saved: auto_output.jpg (sharpest frame)")
    
    # Option 2: Manual review (requires PySide6)
    print("\nManual mode: Show UI for user selection")
    try:
        output_path = processor.process_with_manual_review(video_path, Path("output"))
        if output_path:
            print(f"User selected frame saved to: {output_path}")
        else:
            print("User cancelled selection")
    except ImportError:
        print("PySide6 not installed - UI not available")


if __name__ == "__main__":
    print("LivePhotoConverter - Usage Examples")
    print("=" * 50)
    
    # Uncomment examples to run (adjust file paths first)
    # example_1_extract_frames()
    # example_2_save_frames()
    # example_3_preserve_metadata()
    # example_4_batch_processing()
    # example_5_focus_detection()
    # example_6_custom_processing()
    # example_7_hybrid_mode()
    
    print("\n" + "=" * 50)
    print("See comments above to run individual examples")
    print("Update file paths in each example before running")
