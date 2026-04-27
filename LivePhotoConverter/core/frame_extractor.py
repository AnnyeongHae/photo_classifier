"""
Frame extraction from Live Photo (MP4) videos.
Extracts 3 candidate frames: first, middle, and sharpest.
Optimized for memory efficiency (in-memory processing, no temp files).
"""

import cv2
import numpy as np
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Tuple, Optional
from .focus_detector import FocusDetector


class FrameExtractor:
    """Extracts candidate frames from Live Photo videos."""
    
    def __init__(self, use_ensemble: bool = True):
        """
        Initialize frame extractor.
        
        Args:
            use_ensemble: Use ensemble focus detection (Laplacian + Brenner)
        """
        self.focus_detector = FocusDetector(resize_scale=0.5)
        self.use_ensemble = use_ensemble
    
    def extract_candidates(
        self,
        video_path: str | Path,
        return_metadata: bool = False
    ) -> Tuple[List[np.ndarray], Optional[dict]]:
        """
        Extract 3 candidate frames from a Live Photo video.
        
        Returns:
            - first_frame: Frame at index 0
            - middle_frame: Frame at total_frames / 2
            - sharpest_frame: Frame with highest sharpness score
            
        Args:
            video_path: Path to MP4 file
            return_metadata: If True, return frame metadata (indices, sharpness scores)
            
        Returns:
            Tuple of (frames_list, metadata_dict or None)
            
        Raises:
            FileNotFoundError: If video file doesn't exist
            RuntimeError: If video cannot be opened or no frames extracted
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        with _open_video_capture(video_path) as cap:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                raise RuntimeError(f"Video has no frames: {video_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # Extract first frame (index 0)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to extract first frame")
            first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
            
            # Extract middle frame
            middle_idx = total_frames // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_idx)
            ret, middle_frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to extract middle frame")
            middle_frame_rgb = cv2.cvtColor(middle_frame, cv2.COLOR_BGR2RGB)
            
            # Find sharpest frame using two-pass sampling:
            # Pass 1 — sample every N frames (fast coarse scan)
            # Pass 2 — search ±window around the best candidate (fine refinement)
            sample_step = max(1, total_frames // 30)  # at most 30 sample points
            coarse_best_idx = 0
            coarse_best_score = -1.0

            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            i = 0
            while i < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if not ret:
                    break
                score = self.focus_detector.compute_sharpness(frame, use_ensemble=self.use_ensemble)
                if score > coarse_best_score:
                    coarse_best_score = score
                    coarse_best_idx = i
                i += sample_step

            # Pass 2 — refine within ±sample_step of the coarse winner
            refine_start = max(0, coarse_best_idx - sample_step)
            refine_end = min(total_frames, coarse_best_idx + sample_step + 1)

            sharpest_frame_bgr = None
            sharpest_idx = coarse_best_idx
            sharpest_score = -1.0

            cap.set(cv2.CAP_PROP_POS_FRAMES, refine_start)
            for i in range(refine_start, refine_end):
                ret, frame = cap.read()
                if not ret:
                    break
                score = self.focus_detector.compute_sharpness(frame, use_ensemble=self.use_ensemble)
                if score > sharpest_score:
                    sharpest_score = score
                    sharpest_frame_bgr = frame.copy()
                    sharpest_idx = i

            if sharpest_frame_bgr is None:
                raise RuntimeError("Failed to find sharpest frame")
            
            sharpest_frame_rgb = cv2.cvtColor(sharpest_frame_bgr, cv2.COLOR_BGR2RGB)
            
            frames = [first_frame_rgb, middle_frame_rgb, sharpest_frame_rgb]
            
            metadata = None
            if return_metadata:
                # Compute scores for returned frames
                first_score = self.focus_detector.compute_sharpness(first_frame, use_ensemble=self.use_ensemble)
                middle_score = self.focus_detector.compute_sharpness(middle_frame, use_ensemble=self.use_ensemble)
                
                metadata = {
                    "total_frames": total_frames,
                    "fps": fps,
                    "frame_indices": [0, middle_idx, sharpest_idx],
                    "frame_labels": ["First Frame", "Middle Frame", "Sharpest Frame"],
                    "sharpness_scores": [first_score, middle_score, sharpest_score],
                    "video_path": str(video_path)
                }
            
            return frames, metadata
    
    def extract_frame_at_index(self, video_path: str | Path, frame_index: int) -> np.ndarray:
        """
        Extract a single frame at specified index.
        
        Args:
            video_path: Path to MP4 file
            frame_index: 0-based frame index
            
        Returns:
            Frame as RGB numpy array (H, W, 3)
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        with _open_video_capture(video_path) as cap:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_index < 0 or frame_index >= total_frames:
                raise ValueError(f"Frame index {frame_index} out of range [0, {total_frames-1}]")
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            
            if not ret:
                raise RuntimeError(f"Failed to extract frame at index {frame_index}")
            
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    def get_video_info(self, video_path: str | Path) -> dict:
        """
        Get video metadata (duration, fps, resolution, etc).
        
        Args:
            video_path: Path to MP4 file
            
        Returns:
            Dictionary with video properties
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        with _open_video_capture(video_path) as cap:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            duration_seconds = total_frames / fps if fps > 0 else 0
            
            return {
                "path": str(video_path),
                "total_frames": total_frames,
                "fps": fps,
                "width": width,
                "height": height,
                "duration_seconds": duration_seconds
            }


def _needs_ascii_temp_path(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        str(path).encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


@contextmanager
def _open_video_capture(video_path: Path) -> Iterator[cv2.VideoCapture]:
    capture_path = video_path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    if _needs_ascii_temp_path(video_path):
        temp_dir = tempfile.TemporaryDirectory(prefix="livephoto_")
        capture_path = Path(temp_dir.name) / f"input{video_path.suffix.lower()}"
        shutil.copy2(video_path, capture_path)

    cap = cv2.VideoCapture(str(capture_path))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video file: {video_path}")
        yield cap
    finally:
        cap.release()
        if temp_dir is not None:
            temp_dir.cleanup()
