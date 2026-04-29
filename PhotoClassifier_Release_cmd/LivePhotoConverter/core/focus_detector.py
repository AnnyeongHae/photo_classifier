"""
Focus quality detection using multiple metrics for robust frame selection.
Combines Laplacian and Brenner metrics for accurate sharpness detection.
"""

import cv2
import numpy as np
from typing import Tuple, List


class FocusDetector:
    """Detects focus quality of frames using multiple metrics."""
    
    def __init__(self, resize_scale: float = 0.5):
        """
        Initialize focus detector.
        
        Args:
            resize_scale: Scale factor for resizing frames during computation (0-1).
                         Smaller = faster computation, default 0.5 reduces to 50% size.
        """
        self.resize_scale = resize_scale
    
    def _compute_laplacian_variance(self, frame: np.ndarray) -> float:
        """
        Compute Laplacian variance as sharpness metric.
        Higher variance = sharper image.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        return float(variance)
    
    def _compute_brenner_metric(self, frame: np.ndarray) -> float:
        """
        Compute Brenner metric for focus detection.
        Brenner = sum of squared gradients, often more robust than Laplacian.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        
        # Compute gradients using Sobel
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        
        # Brenner = sum of squared gradients
        brenner = np.sum(gx ** 2 + gy ** 2)
        return float(brenner)
    
    def compute_sharpness(self, frame: np.ndarray, use_ensemble: bool = True) -> float:
        """
        Compute sharpness score for a frame.
        
        Args:
            frame: Input frame (BGR or grayscale)
            use_ensemble: If True, combine Laplacian + Brenner; else use Laplacian only
            
        Returns:
            Sharpness score (normalized 0-100 when use_ensemble=True)
        """
        # Resize for faster computation
        h, w = frame.shape[:2]
        small_frame = cv2.resize(frame, (int(w * self.resize_scale), int(h * self.resize_scale)))
        
        if use_ensemble:
            # Normalize both metrics and combine
            laplacian = self._compute_laplacian_variance(small_frame)
            brenner = self._compute_brenner_metric(small_frame)
            
            # Normalize Brenner to 0-100 scale (empirical normalization)
            brenner_normalized = min(brenner / 1e6, 100.0)
            
            # Normalize Laplacian to 0-100 scale
            laplacian_normalized = min(laplacian / 1000.0, 100.0)
            
            # Ensemble: average both metrics
            sharpness = (laplacian_normalized + brenner_normalized) / 2.0
        else:
            # Use Laplacian only
            sharpness = self._compute_laplacian_variance(small_frame)
            # Normalize to 0-100
            sharpness = min(sharpness / 1000.0, 100.0)
        
        return float(sharpness)
    
    def find_sharpest_frame(
        self, 
        frames: List[np.ndarray], 
        use_ensemble: bool = True
    ) -> Tuple[int, float]:
        """
        Find the sharpest frame from a list.
        
        Args:
            frames: List of frames (BGR or grayscale)
            use_ensemble: Use ensemble method for scoring
            
        Returns:
            Tuple of (index, sharpness_score)
        """
        if not frames:
            raise ValueError("frames list is empty")
        
        scores = [self.compute_sharpness(f, use_ensemble) for f in frames]
        best_idx = np.argmax(scores)
        best_score = scores[best_idx]
        
        return int(best_idx), float(best_score)
