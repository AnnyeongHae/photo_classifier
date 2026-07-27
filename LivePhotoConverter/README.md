# LivePhotoConverter

**Independent service for converting Live Photos (MP4) to static images (JPEG)** with intelligent frame selection and metadata preservation.

![Status](https://img.shields.io/badge/status-production-brightgreen)  
![Python](https://img.shields.io/badge/python-3.9+-blue)  
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

LivePhotoConverter is a **standalone, dependency-free service** that converts Apple Live Photos (MP4 format) into high-quality static JPEG images. It intelligently selects the best frame from 3 candidates:

1. **First Frame** - Start of video
2. **Middle Frame** - Center position  
3. **Sharpest Frame** - Best focus detection (ensemble of Laplacian + Brenner metrics)

Key features:
- ✅ **Batch Processing** - Convert entire folders via CLI
- ✅ **Hybrid Mode** - Auto-select or manual review with UI
- ✅ **Metadata Preservation** - EXIF data copied from MP4 to JPEG using exiftool
- ✅ **Optimized Performance** - In-memory processing, no temp files
- ✅ **Ensemble Focus Detection** - Combines multiple algorithms for robust sharpness scoring

---

## Architecture

```
LivePhotoConverter/
├── core/                      # Core processing engines
│   ├── frame_extractor.py     # Extract frames from MP4
│   ├── focus_detector.py      # Detect sharp frames (Brenner + Laplacian)
│   ├── image_converter.py     # Save frames as JPEG/PNG
│   └── metadata_handler.py    # Preserve EXIF via exiftool
├── cli/                       # Command-line interface
│   └── batch_processor.py     # Batch folder processing
├── ui/                        # Optional GUI (PySide6)
│   └── thumbnail_selector.py  # Manual frame selection
└── tests/                     # Unit tests
```

**Design Philosophy:**
- **No external dependencies** on main codebase
- **Modular architecture** - Use CLI, UI, or import core modules directly
- **Production-ready** - Error handling, logging, metadata preservation

---

## Installation

### Prerequisites
- Python 3.9+
- `exiftool` (for metadata handling)
  - Windows: `choco install exiftool`
  - macOS: `brew install exiftool`
  - Linux: `sudo apt install exiftool`

### Setup

```bash
# Clone or download LivePhotoConverter
cd LivePhotoConverter

# Install dependencies
pip install -r requirements.txt

# Optional: install in editable mode
pip install -e .
```

---

## Usage

### 1. **CLI: Batch Processing** (Recommended)

Convert all Live Photos in a folder:

```bash
python -m cli.batch_processor \
  --input "C:\Photos\LivePhotos" \
  --output "C:\Photos\Converted" \
  --quality 95
```

**Options:**
- `--input` - Input folder with MP4/MOV files
- `--output` - Output folder for JPEG files
- `--pattern` - File pattern (e.g., `*.mov`) - repeatable
- `--quality` - JPEG quality 1-100 (default: 95)
- `--no-metadata` - Skip EXIF preservation
- `--exiftool` - Path to exiftool if not in PATH
- `--dry-run` - Preview without processing
- `--log` - Log file path
- `--debug` - Enable debug logging

**Example with options:**
```bash
python -m cli.batch_processor \
  --input ./videos \
  --output ./output \
  --pattern "*.MOV" \
  --pattern "*.mp4" \
  --quality 90 \
  --dry-run
```

### 2. **Python API: Direct Usage**

```python
from LivePhotoConverter.core import FrameExtractor, ImageConverter, MetadataHandler

# Extract frames
extractor = FrameExtractor(use_ensemble=True)
frames, metadata = extractor.extract_candidates(
    "photo.mp4",
    return_metadata=True
)

# frames[0]: first frame (RGB)
# frames[1]: middle frame (RGB)
# frames[2]: sharpest frame (RGB)
# metadata: dict with scores, indices, video info

# Save best frame
converter = ImageConverter(jpeg_quality=95)
converter.save_frame_as_jpeg(frames[2], "output.jpg")

# Preserve metadata
metadata_handler = MetadataHandler()
metadata_handler.copy_metadata_to_image("photo.mp4", "output.jpg")
```

### 3. **Hybrid Mode: Auto-select + Manual Review**

```python
from cli.batch_processor import BatchProcessor

processor = BatchProcessor(preserve_metadata=True)

# Single file with manual UI selection
output_path = processor.process_with_manual_review(
    "photo.mp4",
    "output_folder"
)
```

---

## API Reference

### FrameExtractor

```python
extractor = FrameExtractor(use_ensemble=True)

# Extract 3 candidates
frames, metadata = extractor.extract_candidates(
    video_path="photo.mp4",
    return_metadata=True
)

# Get single frame at index
frame = extractor.extract_frame_at_index("photo.mp4", frame_index=50)

# Get video properties
info = extractor.get_video_info("photo.mp4")
# Returns: {path, total_frames, fps, width, height, duration_seconds}
```

### FocusDetector

```python
detector = FocusDetector(resize_scale=0.5)

# Compute sharpness score (0-100)
score = detector.compute_sharpness(frame, use_ensemble=True)

# Find sharpest frame
best_idx, best_score = detector.find_sharpest_frame(frames)
```

### ImageConverter

```python
converter = ImageConverter(jpeg_quality=95)

# Save frame
converter.save_frame_as_jpeg(frame_rgb, "output.jpg")
converter.save_frame_as_png(frame_rgb, "output.png")

# Resize frame
resized = converter.resize_frame(frame, width=1920, height=1080)

# Create thumbnail
converter.create_thumbnail(frame, "thumb.jpg", max_width=300, max_height=300)
```

### MetadataHandler

```python
metadata = MetadataHandler(exiftool_path=None)

# Extract all metadata
all_meta = metadata.extract_metadata("photo.mp4")

# Copy metadata from video to image
metadata.copy_metadata_to_image("photo.mp4", "output.jpg")

# Get specific datetime
dt = metadata.get_datetime_from_video("photo.mp4")
```

---

## Performance Considerations

**Memory Usage:**
- In-memory processing (no temp files)
- 3x frame copies during extraction
- ~3-10MB per frame (depends on resolution)
- For 4K video: ~30-40MB peak

**Speed:**
- Sharpness detection optimized with frame resizing (50% scale)
- Full 1080p scan: ~2-3 seconds
- Full 4K scan: ~5-8 seconds

**Optimization Tips:**
1. Use `--pattern "*.mp4"` to skip unsupported formats
2. Batch processing: add files to queue instead of individual processing
3. For real-time processing, consider downsampling video resolution

---

## 2026 Tech Stack Rationale

**Why this setup?**

| Component | Choice | 2026 Alternative | Why Not |
|-----------|--------|------------------|---------|
| OpenCV | Frame extraction | FFmpeg-python | OpenCV sufficient, lower complexity |
| Laplacian + Brenner | Focus detection | Deep learning (YOLO) | Overkill for focus; classical sufficient |
| PySide6 | Optional UI | PyQt6/Tkinter | PySide6 modern, active dev |
| exiftool | Metadata | Pillow + piexif | exiftool more robust for complex EXIF |
| CLI (argparse) | Entry point | FastAPI/Typer | CLI sufficient, no need for API |

---

## Troubleshooting

### exiftool not found
```
Error: exiftool executable not found
```
**Solution:** Install exiftool or pass `--exiftool /path/to/exiftool`

### JPEG color appears blue (BGR vs RGB)
**Fixed** - frame extractor automatically converts BGR→RGB before output

### UI doesn't appear
**Ensure PySide6 is installed:**
```bash
pip install PySide6
```

### Metadata not copied
1. Verify exiftool is installed: `exiftool -ver`
2. Check source video has EXIF: `exiftool video.mp4`
3. Enable debug: `--debug`

---

## Testing

```bash
# Run tests
pytest tests/ -v

# Test specific module
pytest tests/test_frame_extractor.py -v

# Coverage report
pytest tests/ --cov=LivePhotoConverter --cov-report=html
```

---

## License

MIT License - See LICENSE file

---

## Contributing

Contributions welcome! Please:
1. Fork repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## Roadmap

- [ ] GPU acceleration for sharpness detection (CUDA/OpenCL)
- [ ] WebAssembly version for browser processing
- [ ] Parallel batch processing (multiprocessing)
- [ ] Advanced ML-based frame selection
- [ ] Integration with photo libraries (Photos.app, Lightroom)

---

**Questions?** See `/examples/sample_usage.py` for more examples.

## 실행방법
### 방법 1️⃣ : 가장 간단 (CLI 사용)]
```
# 1단계: 의존성 설치
pip install -r LivePhotoConverter/requirements.txt

# 2단계: 테스트 (확인용)
python LivePhotoConverter/test_validation.py

# 3단계: 실행!
python -m LivePhotoConverter.cli.batch_processor ^
  --input "C:\Photos\LivePhotos" ^
  --output "C:\Photos\Converted" ^
  --dry-run
```

--input          # 입력 폴더 (MP4/MOV 파일들)
--output         # 출력 폴더 (변환된 JPEG들)
--quality        # JPEG 품질 (1-100, 기본값 95)
--pattern        # 파일 패턴 (기본값: *.mp4, *.mov)
--dry-run        # 미리보기 (실제 변환 안 함)
--no-metadata    # EXIF 제외 (빠름)
--help           # 도움말


### 방법 2️⃣ : Python에서 직접 사용
```
from LivePhotoConverter.cli.batch_processor import BatchProcessor

# 초기화
processor = BatchProcessor(
    preserve_metadata=True,     # EXIF 보존
    jpeg_quality=95             # 품질
)

# 실행
stats = processor.process_folder(
    input_folder="C:\\Photos\\LivePhotos",
    output_folder="C:\\Photos\\Converted",
    dry_run=False,
    skip_existing=True
)

# 결과
print(f"변환됨: {stats['processed']}")
print(f"건너뜀: {stats['skipped']}")
print(f"실패: {stats['failed']}")
```

### 방법 3️⃣ : UI로 수동 선택 (선택 사항)
```
from LivePhotoConverter.core import FrameExtractor
from LivePhotoConverter.ui.thumbnail_selector import ThumbnailSelector

# 프레임 추출
extractor = FrameExtractor()
frames, metadata = extractor.extract_candidates("photo.mp4", return_metadata=True)

# UI 표시 (3개 프레임 선택 창)
selector = ThumbnailSelector()
selected_idx = selector.show_selection_dialog(frames, metadata)

if selected_idx is not None:
    print(f"선택됨: Frame {selected_idx}")
```