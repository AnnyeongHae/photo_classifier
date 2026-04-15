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
            # Try multiple locations
            candidates = [
                "exiftool",  # In PATH
                shutil.which("exiftool"),  # System PATH
            ]
            
            # Add project-local exiftool (Windows)
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            # Try both possible locations (direct and nested)
            project_exiftool_paths = [
                project_root / "exiftool-13.55_64" / "exiftool-13.55_64" / "exiftool.exe",
                project_root / "exiftool-13.55_64" / "exiftool.exe",
            ]
            for exiftool_candidate in project_exiftool_paths:
                if exiftool_candidate.exists():
                    candidates.insert(0, str(exiftool_candidate))
                    break
            
            self.exiftool_path = None
            for candidate in candidates:
                if candidate and Path(candidate).exists():
                    self.exiftool_path = str(candidate)
                    break
        
        if not self.exiftool_path:
            raise FileNotFoundError(
                "exiftool not found. Install it or provide path via exiftool_path parameter."
            )
    
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
            cmd = [
                self.exiftool_path,
                "-overwrite_original",
                "-TagsFromFile",
                str(source_video),
                "-all:all>all:all",  # Copy all tags
                str(target_image)
            ]
            
            # Add custom tags if provided
            if overwrite_tags:
                for tag, value in overwrite_tags.items():
                    cmd.insert(-1, f"-{tag}={value}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.warning(f"exiftool warning/error: {result.stderr}")
                # exiftool returns 0 even with warnings, so check for actual errors
                if "Error" in result.stderr:
                    return False
            
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
