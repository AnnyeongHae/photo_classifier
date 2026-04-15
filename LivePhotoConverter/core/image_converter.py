"""
Image format conversion and optimization.
Converts extracted frames from numpy arrays to JPEG with quality control.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Union


class ImageConverter:
    """Converts and saves images in various formats."""
    
    def __init__(self, jpeg_quality: int = 95):
        """
        Initialize converter.
        
        Args:
            jpeg_quality: JPEG quality (1-100), default 95 for high quality
        """
        if not 1 <= jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        self.jpeg_quality = jpeg_quality
    
    def save_frame_as_jpeg(
        self,
        frame_rgb: np.ndarray,
        output_path: Union[str, Path],
        create_dirs: bool = True,
        optimize: bool = False
    ) -> Path:
        """
        Save an RGB frame as JPEG.
        
        Args:
            frame_rgb: RGB numpy array (H, W, 3) with values 0-255
            output_path: Destination JPEG file path
            create_dirs: If True, create parent directories if they don't exist
            optimize: If False (default), save with maximum quality. If True, optimize file size.
            
        Returns:
            Path to saved file
            
        Raises:
            ValueError: If frame format is invalid
        """
        output_path = Path(output_path)
        
        if len(frame_rgb.shape) != 3 or frame_rgb.shape[2] != 3:
            raise ValueError(f"Expected RGB frame (H, W, 3), got shape {frame_rgb.shape}")
        
        if create_dirs:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert RGB to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        
        # Determine quality based on optimization flag
        if optimize:
            quality = self.jpeg_quality  # Use configured quality (default 95)
        else:
            # Maximum quality mode - save without quality limit
            # Use optimize_quality approach for best results
            quality = min(98, self.jpeg_quality)  # 98 is near-lossless
        
        # Save with specified quality
        success = cv2.imwrite(
            str(output_path),
            frame_bgr,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        
        if not success:
            raise RuntimeError(f"Failed to save JPEG: {output_path}")
        
        return output_path
    
    def save_frame_as_png(
        self,
        frame_rgb: np.ndarray,
        output_path: Union[str, Path],
        create_dirs: bool = True
    ) -> Path:
        """
        Save an RGB frame as PNG (lossless).
        
        Args:
            frame_rgb: RGB numpy array (H, W, 3) with values 0-255
            output_path: Destination PNG file path
            create_dirs: If True, create parent directories if they don't exist
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        
        if len(frame_rgb.shape) != 3 or frame_rgb.shape[2] != 3:
            raise ValueError(f"Expected RGB frame (H, W, 3), got shape {frame_rgb.shape}")
        
        if create_dirs:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert RGB to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        
        cv2.imwrite(str(output_path), frame_bgr)
        
        return output_path
    
    def resize_frame(
        self,
        frame_rgb: np.ndarray,
        width: int = None,
        height: int = None,
        preserve_aspect: bool = True
    ) -> np.ndarray:
        """
        Resize a frame.
        
        Args:
            frame_rgb: RGB numpy array
            width: Target width (if None, inferred from height)
            height: Target height (if None, inferred from width)
            preserve_aspect: If True, maintain aspect ratio
            
        Returns:
            Resized RGB frame
        """
        h, w = frame_rgb.shape[:2]
        
        if width is None and height is None:
            raise ValueError("At least one of width or height must be specified")
        
        if preserve_aspect:
            if width is None:
                scale = height / h
                width = int(w * scale)
            elif height is None:
                scale = width / w
                height = int(h * scale)
            else:
                # Both specified, use the one that preserves aspect better
                scale_w = width / w
                scale_h = height / h
                scale = min(scale_w, scale_h)
                width = int(w * scale)
                height = int(h * scale)
        else:
            if width is None:
                width = w
            if height is None:
                height = h
        
        return cv2.resize(frame_rgb, (width, height), interpolation=cv2.INTER_LANCZOS4)
    
    def create_thumbnail(
        self,
        frame_rgb: np.ndarray,
        output_path: Union[str, Path],
        max_width: int = 300,
        max_height: int = 300,
        create_dirs: bool = True
    ) -> Path:
        """
        Create and save a thumbnail (resized with aspect ratio preserved).
        
        Args:
            frame_rgb: RGB numpy array
            output_path: Destination file path
            max_width: Maximum thumbnail width
            max_height: Maximum thumbnail height
            create_dirs: If True, create parent directories
            
        Returns:
            Path to saved thumbnail
        """
        h, w = frame_rgb.shape[:2]
        scale = min(max_width / w, max_height / h)
        
        if scale < 1:
            thumbnail = self.resize_frame(
                frame_rgb,
                width=int(w * scale),
                height=int(h * scale),
                preserve_aspect=True
            )
        else:
            thumbnail = frame_rgb
        
        return self.save_frame_as_jpeg(thumbnail, output_path, create_dirs)
