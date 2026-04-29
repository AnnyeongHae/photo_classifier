# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.video_converter import (
    VideoConverterConfig,
    detect_hardware_encoder,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
)
from gui.screen_setup import FolderRow


# ── 공통 스타일 상수 ──────────────────────────────────────────────────────────
_GROUPBOX_STYLE = """
    QGroupBox {
        font-size: 13px;
        font-weight: 700;
        color: #1f2937;
        border: 1.5px solid #e5e7eb;
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 18px;
        background: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #1f2937;
    }
"""

_COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 13px;
        color: #111827;
        background: #f9fafb;
        min-height: 36px;
    }
    QComboBox:hover  { border-color: #9ca3af; background: #f3f4f6; color: #111827; }
    QComboBox:focus  { border-color: #2563eb; background: #ffffff; color: #111827; }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox QAbstractItemView {
        border: 1.5px solid #d1d5db;
        border-radius: 6px;
        background: #ffffff;
        color: #111827;
        selection-background-color: #eff6ff;
        selection-color: #1d4ed8;
        font-size: 13px;
        padding: 4px;
    }
"""


def _flabel(text: str) -> QLabel:
    """폼 레이아웃용 굵은 레이블."""
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #111827; background: transparent;")
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return lbl


def _hint(text: str) -> QLabel:
    """옵션 아래 회색 설명 텍스트."""
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #6b7280; margin-top: -4px; background: transparent;")
    lbl.setWordWrap(True)
    return lbl


class VideoSetupScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._detected_encoder: str | None = None
        self._gpu_available = False
        self._build_ui()
        self._check_dependencies()

    def _build_ui(self) -> None:
        # ── 최상위 레이아웃: 스크롤 영역 + 고정 하단 버튼 ──────────────────
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # 스크롤 가능 콘텐츠 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: #f3f4f6; }")

        content = QWidget()
        content.setStyleSheet("background: #f3f4f6;")
        root = QVBoxLayout(content)
        root.setSpacing(16)
        root.setContentsMargins(40, 32, 40, 24)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ── 헤더 ────────────────────────────────────────────────────────────
        title = QLabel("비디오 해상도 변환기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("고해상도 원본(4K/8K)을 유지한 채, 다루기 쉬운 FHD/HD 포맷으로 압축 변환합니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;"
        )
        root.addWidget(subtitle)

        # ── GPU 상태 카드 (상단 배치 — 가장 눈에 잘 띄는 위치) ───────────
        self._gpu_card = QFrame()
        self._gpu_card.setFrameShape(QFrame.NoFrame)
        self._gpu_card.setFixedHeight(52)
        self._gpu_card.setStyleSheet(
            "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0;"
            "border-radius: 10px; }"
        )
        gpu_card_inner = QHBoxLayout(self._gpu_card)
        gpu_card_inner.setContentsMargins(20, 0, 20, 0)

        self._gpu_label = QLabel("GPU 상태: 확인 중...")
        self._gpu_label.setAlignment(Qt.AlignCenter)
        self._gpu_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
        )
        gpu_card_inner.addWidget(self._gpu_label)
        root.addWidget(self._gpu_card)

        # ── 1. 파일 경로 ─────────────────────────────────────────────────────
        folder_group = QGroupBox("  파일 경로")
        folder_group.setStyleSheet(_GROUPBOX_STYLE)
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(10)
        folder_layout.setContentsMargins(20, 16, 20, 20)

        self._input_row = FolderRow("입력 폴더", "변환할 영상이 있는 폴더 선택")
        self._output_row = FolderRow("출력 폴더", "변환된 영상이 저장될 폴더 선택")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        # ── 2. 출력 설정 ──────────────────────────────────────────────────────
        res_group = QGroupBox("  출력 설정")
        res_group.setStyleSheet(_GROUPBOX_STYLE)
        res_layout = QFormLayout(res_group)
        res_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        res_layout.setContentsMargins(20, 16, 20, 20)
        res_layout.setSpacing(10)
        res_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._res_cb = QComboBox()
        self._res_cb.addItem("FHD 1080p  (1920×1080) — 범용 권장", "fhd")
        self._res_cb.addItem("HD  720p   (1280×720)  — 용량 최소화", "hd")
        self._res_cb.addItem("4K  2160p  (3840×2160) — 고화질 유지", "4k")
        self._res_cb.setToolTip("목표 해상도보다 작은 영상은 그대로 유지됩니다.")
        self._res_cb.setStyleSheet(_COMBO_STYLE)
        res_layout.addRow(_flabel("목표 해상도"), self._res_cb)
        res_layout.addRow("", _hint("목표 해상도보다 작은 영상은 변환하지 않고 건너뜁니다."))

        self._codec_cb = QComboBox()
        self._codec_cb.addItem("H.264  — 호환성 우선 (모든 기기에서 재생)", "h264")
        self._codec_cb.addItem("H.265 / HEVC  — 압축률 우선 (최신 기기 권장)", "hevc")
        self._codec_cb.setStyleSheet(_COMBO_STYLE)
        self._codec_cb.currentIndexChanged.connect(self._on_codec_changed)
        res_layout.addRow(_flabel("코덱 포맷"), self._codec_cb)

        self._quality_cb = QComboBox()
        self._quality_cb.addItem("고화질 (CQ 18) — 시각적 무손실, 파일 큼", 18)
        self._quality_cb.addItem("균형    (CQ 23) — 화질·용량 타협점", 23)
        self._quality_cb.addItem("저용량  (CQ 28) — 눈에 띄는 압축, 파일 매우 작음", 28)
        self._quality_cb.setStyleSheet(_COMBO_STYLE)
        res_layout.addRow(_flabel("화질 수준"), self._quality_cb)

        self._audio_cb = QComboBox()
        self._audio_cb.addItem("256 kbps — 고음질 (기본값)", "256k")
        self._audio_cb.addItem("192 kbps — 균형", "192k")
        self._audio_cb.addItem("128 kbps — 용량 절약", "128k")
        self._audio_cb.setStyleSheet(_COMBO_STYLE)
        res_layout.addRow(_flabel("오디오 품질"), self._audio_cb)

        root.addWidget(res_group)

        # ── 3. 성능 및 고급 옵션 ─────────────────────────────────────────────
        adv_group = QGroupBox("  성능 및 고급 옵션")
        adv_group.setStyleSheet(_GROUPBOX_STYLE)
        adv_layout = QFormLayout(adv_group)
        adv_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        adv_layout.setContentsMargins(20, 16, 20, 20)
        adv_layout.setSpacing(10)
        adv_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._gpu_mode_cb = QComboBox()
        self._gpu_mode_cb.addItem("자동 선택 — GPU 우선, 없으면 CPU", "auto")
        self._gpu_mode_cb.addItem("GPU 강제 사용", "gpu")
        self._gpu_mode_cb.addItem("CPU만 사용  (느리지만 안정적)", "cpu")
        self._gpu_mode_cb.setStyleSheet(_COMBO_STYLE)
        self._gpu_mode_cb.currentIndexChanged.connect(self._update_gpu_status_text)
        adv_layout.addRow(_flabel("인코딩 장치"), self._gpu_mode_cb)

        self._concurrent_cb = QComboBox()
        self._concurrent_cb.addItem("자동 — 장치 성능 기준으로 결정", 0)
        self._concurrent_cb.addItem("1개  — 시스템 부하 최소화", 1)
        self._concurrent_cb.addItem("2개", 2)
        self._concurrent_cb.addItem("3개", 3)
        self._concurrent_cb.setStyleSheet(_COMBO_STYLE)
        self._concurrent_cb.setToolTip("NVENC 세션 제한이 있을 경우 '2개' 이하를 권장합니다.")
        adv_layout.addRow(_flabel("동시 처리"), self._concurrent_cb)
        adv_layout.addRow("", _hint("GPU 인코더는 동시 처리 세션 수에 제한이 있을 수 있습니다."))

        self._dup_cb = QComboBox()
        self._dup_cb.addItem("건너뛰기  — 이미 변환된 파일 재처리 안 함 (권장)", "skip")
        self._dup_cb.addItem("덮어쓰기  — 기존 출력 파일을 덮어씀", "overwrite")
        self._dup_cb.addItem("번호 추가 — video_1.mp4, video_2.mp4…", "rename")
        self._dup_cb.setStyleSheet(_COMBO_STYLE)
        adv_layout.addRow(_flabel("중복 파일 처리"), self._dup_cb)

        root.addWidget(adv_group)

        # ── 의존성 상태 (하단 작은 텍스트) ───────────────────────────────────
        self._deps_label = QLabel()
        self._deps_label.setAlignment(Qt.AlignCenter)
        self._deps_label.setStyleSheet(
            "font-size: 12px; color: #374151; background: transparent;"
        )
        root.addWidget(self._deps_label)

        root.addStretch()

        # ── 고정 하단 버튼 영역 ───────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            "QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }"
        )
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(8)

        self._run_btn = QPushButton("변환 시작")
        self._run_btn.setFixedHeight(52)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; font-size: 16px;"
            "  border-radius: 10px; font-weight: 800; border: none; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:pressed { background: #1e40af; }"
            "QPushButton:disabled { background: #9ca3af; }"
        )
        footer_layout.addWidget(self._run_btn)

        self._back_btn = QPushButton("← 허브로 돌아가기")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(
            "QPushButton { color: #374151; font-size: 13px; font-weight: 600;"
            "  border: none; padding: 4px; background: transparent; }"
            "QPushButton:hover { color: #111827; }"
        )
        footer_layout.addWidget(self._back_btn, alignment=Qt.AlignCenter)

        outer.addWidget(footer)

    # --- 이하 로직 부분은 기존 코드와 100% 동일하게 유지합니다. ---
    def _on_codec_changed(self) -> None:
        self._detected_encoder = None
        self._gpu_available = False
        try:
            ffmpeg_path = resolve_ffmpeg_path()
            self._detect_gpu(ffmpeg_path)
        except Exception:
            pass

    def _check_dependencies(self) -> None:
        missing = []
        ffmpeg_path = None
        try:
            ffmpeg_path = resolve_ffmpeg_path()
        except FileNotFoundError:
            missing.append("FFmpeg")

        try:
            resolve_ffprobe_path()
        except FileNotFoundError:
            missing.append("FFprobe")

        if missing:
            self._deps_label.setText(f"⚠️ 필수 도구 누락: {', '.join(missing)} (assets 폴더 확인)")
            self._deps_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px;")
            self._gpu_label.setText("GPU 상태: FFmpeg 미탐지로 확인 불가")
            self._set_gpu_card_style("gray")
        else:
            self._deps_label.setText("✓ 필수 도구 정상 로드됨 (FFmpeg, FFprobe)")
            self._deps_label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")

            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._detect_gpu(ffmpeg_path))

    def _detect_gpu(self, ffmpeg_path: str) -> None:
        self._gpu_label.setText(f"GPU 상태: {self.codec_choice.upper()}용 하드웨어 인코더 탐색 중...")
        self._gpu_label.repaint()
        encoder = detect_hardware_encoder(ffmpeg_path, Path.home(), self.codec_choice)
        self._detected_encoder = encoder
        self._gpu_available = encoder not in ["libx264", "libx265"]
        self._update_gpu_status_text()

    def _cpu_encoder_for_codec(self) -> str:
        return "libx265" if self.codec_choice == "hevc" else "libx264"

    def _set_gpu_card_style(self, variant: str) -> None:
        """GPU 카드 배경/테두리 색상을 상태에 맞게 변경."""
        styles = {
            "green":  ("background: #f0fdf4; border: 1.5px solid #bbf7d0;", "color: #166534;"),
            "yellow": ("background: #fffbeb; border: 1.5px solid #fde68a;", "color: #92400e;"),
            "red":    ("background: #fef2f2; border: 1.5px solid #fecaca;", "color: #991b1b;"),
            "purple": ("background: #ede9fe; border: 1.5px solid #c4b5fd;", "color: #4c1d95;"),
            "gray":   ("background: #f3f4f6; border: 1.5px solid #d1d5db;", "color: #4b5563;"),
        }
        card_css, label_css = styles.get(variant, styles["gray"])
        self._gpu_card.setStyleSheet(
            f"QFrame {{ {card_css} border-radius: 10px; }}"
        )
        base = "font-size: 14px; font-weight: 700; background: transparent; border: none;"
        self._gpu_label.setStyleSheet(f"{base} {label_css}")

    def _update_gpu_status_text(self) -> None:
        mode = self._gpu_mode_cb.currentData()

        if mode == "cpu":
            self._gpu_label.setText(f"⚡ CPU 단독 인코딩 ({self._cpu_encoder_for_codec()})")
            self._set_gpu_card_style("purple")
            return

        if self._gpu_available and self._detected_encoder:
            name = (
                "NVIDIA NVENC" if "nvenc" in self._detected_encoder
                else "Intel QSV" if "qsv" in self._detected_encoder
                else "AMD AMF" if "amf" in self._detected_encoder
                else self._detected_encoder
            )
            if mode == "gpu":
                self._gpu_label.setText(f"🚀 GPU 강제 할당 ({name})")
            else:
                self._gpu_label.setText(f"🚀 GPU 자동 할당 ({name})")
            self._set_gpu_card_style("green")
            return

        if mode == "gpu":
            self._gpu_label.setText(f"⚠️ {self.codec_choice.upper()}용 GPU 인코더를 찾지 못했습니다.")
            self._set_gpu_card_style("red")
        else:
            self._gpu_label.setText(f"⚡ GPU 미탐지, CPU로 우회 진행 ({self._cpu_encoder_for_codec()})")
            self._set_gpu_card_style("yellow")

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 폴더 누락", "입력 폴더를 선택해 주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "입력 폴더 없음", "입력 폴더가 존재하지 않습니다.")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "출력 폴더 누락", "출력 폴더를 선택해 주세요.")
            return False

        try:
            resolve_ffmpeg_path()
            resolve_ffprobe_path()
        except FileNotFoundError:
            QMessageBox.critical(self, "필수 파일 누락", "FFmpeg 또는 FFprobe가 없습니다.")
            return False

        if self._gpu_mode_cb.currentData() == "gpu" and not self._gpu_available:
            QMessageBox.warning(
                self,
                "GPU 인코더 미탐지",
                "GPU 강제 사용이 선택되었지만 사용 가능한 GPU 인코더를 찾지 못했습니다.\n"
                "GPU 드라이버/FFmpeg 설정을 확인하거나 '자동 선택' 또는 'CPU만 사용'을 선택해 주세요.",
            )
            return False

        return True

    def build_config(self) -> VideoConverterConfig:
        res_key = self._res_cb.currentData()
        w, h = 1920, 1080
        if res_key == "hd":
            w, h = 1280, 720
        elif res_key == "4k":
            w, h = 3840, 2160

        mode = self._gpu_mode_cb.currentData()
        selected_encoder = self._detected_encoder
        if mode == "cpu":
            selected_encoder = self._cpu_encoder_for_codec()
        elif mode == "gpu":
            selected_encoder = self._detected_encoder

        return VideoConverterConfig(
            input_folder=Path(self._input_row.path),
            output_folder=Path(self._output_row.path),
            max_width=w,
            max_height=h,
            codec=self.codec_choice,
            encoder=selected_encoder,
            quality=self._quality_cb.currentData(),
            audio_bitrate=self._audio_cb.currentData(),
            duplicate_handling=self._dup_cb.currentData(),
            max_concurrent_encodes=self._concurrent_cb.currentData(),
        )

    @property
    def output_folder(self) -> str:
        return self._output_row.path

    @property
    def target_resolution(self) -> str:
        return self._res_cb.currentData()

    @property
    def codec_choice(self) -> str:
        return self._codec_cb.currentData()

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn