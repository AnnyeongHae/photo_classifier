"""
Metadata handling for Live Photos.
Preserves EXIF and other metadata from MP4 to JPEG using exiftool.
"""

import subprocess
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MetadataHandler:
    """Handles metadata extraction and preservation from Live Photos."""
    
    def __init__(self, exiftool_path: Optional[str] = None):
        """
        Initialize metadata handler.
        
        Args:
            exiftool_path: Path to exiftool executable. If None, searches in multiple locations.
            
        Raises:
            FileNotFoundError: If exiftool is not found
        """
        if exiftool_path:
            self.exiftool_path = exiftool_path
        else:
            self.exiftool_path = self._find_exiftool()

        if not self.exiftool_path:
            raise FileNotFoundError(
                "exiftool not found. Install it or provide path via exiftool_path parameter."
            )

    @staticmethod
    def _find_exiftool() -> Optional[str]:
        """Search for exiftool in system PATH and common project-local locations."""
        # System PATH (most reliable — returns absolute path or None)
        found = shutil.which("exiftool")
        if found:
            return found

        # Main-app bundled binary: <project_root>/assets/exiftool.exe
        # (Nuitka standalone build copies assets/ next to the exe)
        project_root = Path(__file__).parent.parent.parent
        bundled = project_root / "assets" / "exiftool.exe"
        if bundled.exists():
            return str(bundled)

        # Project-local Windows installations (any version under the project root)
        for candidate in sorted(project_root.glob("exiftool*/exiftool.exe")):
            if candidate.exists():
                return str(candidate)
        # Nested layout: exiftool-X/exiftool-X/exiftool.exe
        for candidate in sorted(project_root.glob("exiftool*/*/exiftool.exe")):
            if candidate.exists():
                return str(candidate)

        return None
    
    def extract_metadata(self, video_path: str | Path) -> Dict[str, Any]:
        """
        Extract metadata from MP4 using exiftool.
        
        Args:
            video_path: Path to MP4 file
            
        Returns:
            Dictionary of extracted metadata (JSON format)
            
        Raises:
            RuntimeError: If exiftool fails
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        try:
            result = subprocess.run(
                [self.exiftool_path, "-j", str(video_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            metadata_list = json.loads(result.stdout)
            if metadata_list:
                return metadata_list[0]
            return {}
        
        except subprocess.CalledProcessError as e:
            logger.warning(f"exiftool error for {video_path}: {e.stderr}")
            return {}
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse exiftool output as JSON")
            return {}
    
    def copy_metadata_to_image(
        self,
        source_video: str | Path,
        target_image: str | Path,
        overwrite_tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Copy metadata from MP4 to JPEG image.
        
        Args:
            source_video: Source MP4 file path
            target_image: Target JPEG file path
            overwrite_tags: Additional tags to set/override (e.g., {"DateTimeOriginal": "2024:01:15 10:30:00"})
            
        Returns:
            True if successful, False otherwise
        """
        source_video = Path(source_video)
        target_image = Path(target_image)
        
        if not source_video.exists():
            logger.error(f"Source video not found: {source_video}")
            return False
        
        if not target_image.exists():
            logger.error(f"Target image not found: {target_image}")
            return False
        
        try:
            # ── Strategy ─────────────────────────────────────────────────────
            # "-all:all>all:all" copies every metadata group exiftool can map
            # from the MOV to the image file.  Video-only QuickTime atoms that
            # have no JPEG/PNG equivalent are silently skipped — exiftool still
            # exits 0, so this is safe.
            #
            # iPhone GPS gap: Keys:GPSCoordinates is an Apple composite string
            # ("lat,lon,alt/") that -all:all>all:all cannot split into standard
            # EXIF GPS tags.  Composite:GPS* tags are synthesised by exiftool
            # from ANY GPS source in the video (Keys, QuickTime atoms, EXIF-IFD)
            # and CAN be written to EXIF GPS in the destination.
            # Listing Composite copies AFTER -all:all>all:all means they win
            # if non-empty — acting as the authoritative GPS value regardless of
            # which namespace held the coordinates in the source.
            cmd = [
                self.exiftool_path,
                "-overwrite_original",
                "-TagsFromFile", str(source_video),

                # ── 1. Comprehensive copy ─────────────────────────────────
                # Handles: EXIF-IFD embedded in MOV/MP4 (Samsung, Sony, Nikon,
                # Canon, GoPro, DJI), XMP (DJI, GoPro), IPTC, standard QuickTime
                # GPS atoms.  Video-only atoms (track duration, etc.) are silently
                # skipped — exiftool still exits 0.
                "-all:all>all:all",

                # ── 2. Datetime cross-namespace (ascending priority) ───────
                # For cameras that store timestamps only in QuickTime atoms
                # (no EXIF-IFD in the video): older Android, DJI, GoPro, etc.
                # Each line overrides the previous if its source is non-empty;
                # Keys:CreationDate (last = highest) carries timezone — iPhone.
                "-DateTimeOriginal<QuickTime:CreateDate",
                "-DateTimeOriginal<QuickTime:ContentCreateDate",
                "-DateTimeOriginal<Keys:CreationDate",
                "-CreateDate<QuickTime:CreateDate",
                "-CreateDate<Keys:CreationDate",

                # ── 3. Make / Model cross-namespace ──────────────────────
                # Fallback for cameras whose Make/Model lives in QuickTime atoms
                # rather than EXIF-IFD (some older Android, GoPro, DJI).
                # Keys:Make/Model (last) wins for iPhone.
                "-Make<QuickTime:Make",
                "-Model<QuickTime:Model",
                "-Make<Keys:Make",
                "-Model<Keys:Model",

                # ── 4. GPS synthesis — highest priority ──────────────────
                # Composite:GPS* is synthesised by exiftool from any GPS source
                # present in the video:
                #   • Keys:GPSCoordinates  ("lat,lon,alt/")  — iPhone
                #   • QuickTime GPS atoms                     — GoPro, DJI, Sony
                #   • EXIF-IFD GPS tags                      — Samsung, Canon, Nikon
                # Writing Composite:GPSLatitude (signed decimal) to EXIF:GPSLatitude
                # causes exiftool to automatically set GPSLatitudeRef (N/S) —
                # explicit Composite:GPSLatitudeRef/LongitudeRef are not valid
                # Composite tags and must NOT be referenced.
                "-GPSLatitude<Composite:GPSLatitude",
                "-GPSLongitude<Composite:GPSLongitude",
                "-GPSAltitude<Composite:GPSAltitude",
            ]

            # Caller-supplied overrides — appended last so they take precedence
            if overwrite_tags:
                for tag, value in overwrite_tags.items():
                    cmd.append(f"-{tag}={value}")

            cmd.append(str(target_image))

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.warning(f"exiftool error (rc={result.returncode}): {result.stderr.strip()}")
                return False

            # exiftool exits 0 even on per-tag warnings; only surface real errors
            if result.stderr and "Error" in result.stderr:
                logger.warning(f"exiftool reported errors: {result.stderr.strip()}")

            return True
        
        except Exception as e:
            logger.error(f"Failed to copy metadata: {e}")
            return False
    
    def extract_key_metadata(self, video_path: str | Path) -> Dict[str, str]:
        """
        Extract key metadata fields commonly used in photo management.
        
        Args:
            video_path: Path to MP4 file
            
        Returns:
            Dictionary with selected metadata fields
        """
        metadata = self.extract_metadata(video_path)
        
        key_fields = {
            "DateTimeOriginal": metadata.get("DateTimeOriginal"),
            "CreateDate": metadata.get("CreateDate"),
            "ModifyDate": metadata.get("ModifyDate"),
            "GPSLatitude": metadata.get("GPSLatitude"),
            "GPSLongitude": metadata.get("GPSLongitude"),
            "GPSAltitude": metadata.get("GPSAltitude"),
            "Make": metadata.get("Make"),
            "Model": metadata.get("Model"),
            "LensModel": metadata.get("LensModel"),
            "FNumber": metadata.get("FNumber"),
            "ExposureTime": metadata.get("ExposureTime"),
            "ISO": metadata.get("ISO"),
            "FocalLength": metadata.get("FocalLength"),
        }
        
        # Filter out None values
        return {k: v for k, v in key_fields.items() if v is not None}
    
    def get_datetime_from_video(self, video_path: str | Path) -> Optional[str]:
        """
        Get creation datetime from video file.
        
        Args:
            video_path: Path to MP4 file
            
        Returns:
            DateTime string (format: YYYY:MM:DD HH:MM:SS) or None if not found
        """
        metadata = self.extract_metadata(video_path)
        
        # Try different datetime fields in order of preference
        for field in ["DateTimeOriginal", "CreateDate", "ModifyDate", "FileModifyDate"]:
            if field in metadata:
                return metadata[field]
        
        return None
