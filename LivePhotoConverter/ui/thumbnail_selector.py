"""
PySide6-based UI for manual frame selection (hybrid mode).
Allows users to review and select best frame from 3 candidates.
"""

from typing import Optional, List, Dict, Any
import numpy as np

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSizePolicy
    )
    from PySide6.QtGui import QPixmap, QImage, QFont
    from PySide6.QtCore import Qt, QSize
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


class FrameLabel(QLabel):
    """Clickable label for displaying frame with selection feedback."""
    
    def __init__(self, frame_rgb: np.ndarray, label_text: str, parent=None):
        """
        Initialize frame label.
        
        Args:
            frame_rgb: RGB numpy array (H, W, 3)
            label_text: Description text (e.g., "Sharpest Frame")
            parent: Parent widget
        """
        super().__init__(parent)
        self.frame_rgb = frame_rgb
        self.label_text = label_text
        self.is_selected = False
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI elements."""
        # Convert frame to QPixmap
        pixmap = self._numpy_to_qpixmap(self.frame_rgb, max_width=300, max_height=300)
        self.setPixmap(pixmap)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(QSize(320, 320))
        self.setStyleSheet("border: 2px solid gray; border-radius: 4px; padding: 5px;")
    
    def _numpy_to_qpixmap(self, frame_rgb: np.ndarray, max_width: int = 300, max_height: int = 300) -> QPixmap:
        """Convert RGB numpy array to QPixmap with size limit."""
        h, w = frame_rgb.shape[:2]
        
        # Resize if needed
        if w > max_width or h > max_height:
            scale = min(max_width / w, max_height / h)
            new_w, new_h = int(w * scale), int(h * scale)
            import cv2
            frame_rgb = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            h, w = frame_rgb.shape[:2]
        
        # Ensure frame is in uint8 format
        if frame_rgb.dtype != np.uint8:
            frame_rgb = (frame_rgb * 255).astype(np.uint8)
        
        # Convert to QImage
        bytes_per_line = 3 * w
        q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        return QPixmap.fromImage(q_image)
    
    def mousePressEvent(self, event):
        """Handle mouse click for selection."""
        if event.button() == Qt.LeftButton:
            self.select()
    
    def select(self):
        """Mark this frame as selected."""
        self.is_selected = True
        self.setStyleSheet("border: 3px solid green; border-radius: 4px; padding: 5px; background-color: #e0f0e0;")
    
    def deselect(self):
        """Mark this frame as not selected."""
        self.is_selected = False
        self.setStyleSheet("border: 2px solid gray; border-radius: 4px; padding: 5px;")


class ThumbnailSelector:
    """UI for selecting best frame from candidates."""
    
    def __init__(self):
        """Initialize selector."""
        if not PYSIDE_AVAILABLE:
            raise ImportError("PySide6 is required for UI functionality")
    
    def show_selection_dialog(
        self,
        frames: List[np.ndarray],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Show frame selection dialog.
        
        Args:
            frames: List of RGB frames (typically 3 candidates)
            metadata: Optional metadata dict with frame information
            
        Returns:
            Index of selected frame or None if cancelled
        """
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        window = QMainWindow()
        window.setWindowTitle("Live Photo Frame Selection")
        window.setMinimumSize(QSize(1050, 450))
        
        # Central widget
        central = QWidget()
        window.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        
        # Title
        title = QLabel("Select the best frame:")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)
        
        # Frame layout (horizontal)
        frames_layout = QHBoxLayout()
        frame_labels = []
        
        # Get labels from metadata if available
        if metadata and "frame_labels" in metadata:
            labels = metadata["frame_labels"]
            scores = metadata.get("sharpness_scores", [None] * len(frames))
        else:
            labels = ["Frame 1", "Frame 2", "Frame 3"]
            scores = [None] * len(frames)
        
        for i, (frame_rgb, label, score) in enumerate(zip(frames, labels, scores)):
            # Frame container
            frame_container = QWidget()
            frame_layout = QVBoxLayout(frame_container)
            
            # Frame label text
            if score is not None:
                label_text = f"{label}\n(Sharpness: {score:.1f})"
            else:
                label_text = label
            
            info_label = QLabel(label_text)
            info_label.setAlignment(Qt.AlignCenter)
            info_font = QFont()
            info_font.setPointSize(10)
            info_label.setFont(info_font)
            frame_layout.addWidget(info_label)
            
            # Frame image
            frame_label = FrameLabel(frame_rgb, label_text)
            frame_labels.append(frame_label)
            frame_layout.addWidget(frame_label)
            
            frames_layout.addWidget(frame_container)
        
        main_layout.addLayout(frames_layout)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Selection tracking
        selected_idx = [None]  # Use list to allow modification in nested function
        
        def on_frame_selected(frame_label_obj, idx):
            # Deselect all
            for fl in frame_labels:
                fl.deselect()
            # Select clicked
            frame_label_obj.select()
            selected_idx[0] = idx
        
        # Connect click events
        for i, fl in enumerate(frame_labels):
            fl.mousePressEvent = lambda event, idx=i: (
                on_frame_selected(frame_labels[idx], idx),
                fl.mousePressEvent(event) if hasattr(fl, 'original_mousePressEvent') else None
            )
        
        # Buttons
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        
        def on_ok():
            window.close()
        
        def on_cancel():
            selected_idx[0] = None
            window.close()
        
        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(on_cancel)
        
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Show dialog
        window.show()
        app.exec()
        
        return selected_idx[0]
