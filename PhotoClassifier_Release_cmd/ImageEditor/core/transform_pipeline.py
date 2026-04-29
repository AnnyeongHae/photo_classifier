# -*- coding: utf-8 -*-
"""Image transform pipeline: Resize, Crop, and Rotate operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Union

from PIL import Image


class ResizeMode(Enum):
    FIT_WITHIN  = "fit_within"
    BY_WIDTH    = "by_width"
    BY_HEIGHT   = "by_height"
    BY_PERCENT  = "by_percent"
    EXACT       = "exact"


class CropMode(Enum):
    ASPECT_RATIO = "aspect_ratio"   # 중앙 기준, 비율로 자르기
    FIXED_PIXELS = "fixed_pixels"   # 중앙 기준, 픽셀 크기로 자르기
    MANUAL       = "manual"         # 사용자가 직접 지정한 영역 (정규화 좌표 0–1)


@dataclass
class ResizeTransform:
    mode: ResizeMode
    width: int    = 1920
    height: int   = 1080
    percent: float = 50.0

    def apply(self, img: Image.Image) -> Image.Image:
        w, h = img.size

        if self.mode == ResizeMode.BY_PERCENT:
            nw = max(1, round(w * self.percent / 100))
            nh = max(1, round(h * self.percent / 100))

        elif self.mode == ResizeMode.BY_WIDTH:
            nw = self.width
            nh = max(1, round(h * nw / w))

        elif self.mode == ResizeMode.BY_HEIGHT:
            nh = self.height
            nw = max(1, round(w * nh / h))

        elif self.mode == ResizeMode.FIT_WITHIN:
            ratio = min(self.width / w, self.height / h)
            if ratio >= 1.0:
                return img
            nw = max(1, round(w * ratio))
            nh = max(1, round(h * ratio))

        elif self.mode == ResizeMode.EXACT:
            nw, nh = self.width, self.height

        else:
            return img

        if (nw, nh) == (w, h):
            return img
        return img.resize((nw, nh), Image.LANCZOS)

    def description(self) -> str:
        if self.mode == ResizeMode.BY_PERCENT:
            return f"크기 조절: {self.percent:.0f}%"
        if self.mode == ResizeMode.BY_WIDTH:
            return f"크기 조절: 너비 {self.width}px"
        if self.mode == ResizeMode.BY_HEIGHT:
            return f"크기 조절: 높이 {self.height}px"
        if self.mode == ResizeMode.FIT_WITHIN:
            return f"크기 조절: {self.width}×{self.height} 이내"
        if self.mode == ResizeMode.EXACT:
            return f"크기 조절: {self.width}×{self.height} (정확)"
        return "크기 조절"


@dataclass
class CropTransform:
    mode: CropMode
    width: int    = 1920    # FIXED_PIXELS
    height: int   = 1080
    ar_num: int   = 16      # ASPECT_RATIO 분자
    ar_den: int   = 9       # ASPECT_RATIO 분모
    # MANUAL: 정규화 좌표 (0.0–1.0)
    left:   float = 0.0
    top:    float = 0.0
    right:  float = 1.0
    bottom: float = 1.0

    def apply(self, img: Image.Image) -> Image.Image:
        w, h = img.size

        if self.mode == CropMode.ASPECT_RATIO:
            target  = self.ar_num / self.ar_den
            current = w / h
            if current > target:
                nw = round(h * target)
                nh = h
            else:
                nw = w
                nh = round(w / target)
            left = (w - nw) // 2
            top  = (h - nh) // 2
            return img.crop((left, top, left + nw, top + nh))

        if self.mode == CropMode.FIXED_PIXELS:
            cw   = min(self.width, w)
            ch   = min(self.height, h)
            left = (w - cw) // 2
            top  = (h - ch) // 2
            return img.crop((left, top, left + cw, top + ch))

        if self.mode == CropMode.MANUAL:
            l = max(0, int(self.left   * w))
            t = max(0, int(self.top    * h))
            r = min(w, int(self.right  * w))
            b = min(h, int(self.bottom * h))
            if r > l and b > t:
                return img.crop((l, t, r, b))

        return img

    def description(self) -> str:
        if self.mode == CropMode.ASPECT_RATIO:
            return f"자르기: {self.ar_num}:{self.ar_den} 비율 (중앙)"
        if self.mode == CropMode.FIXED_PIXELS:
            return f"자르기: {self.width}×{self.height}px (중앙)"
        if self.mode == CropMode.MANUAL:
            lp = round(self.left   * 100)
            tp = round(self.top    * 100)
            rp = round(self.right  * 100)
            bp = round(self.bottom * 100)
            pw = round((self.right - self.left)  * 100)
            ph = round((self.bottom - self.top)  * 100)
            return f"자르기: ({lp}%,{tp}%)→({rp}%,{bp}%)  {pw}%×{ph}%"
        return "자르기"


@dataclass
class RotateTransform:
    angle: int = 90   # 양수 = 시계방향 (CW); Pillow rotate는 CCW이므로 내부에서 음수 변환

    def apply(self, img: Image.Image) -> Image.Image:
        if self.angle % 360 == 0:
            return img
        fillcolor: object = (255, 255, 255) if img.mode == "RGB" else 0
        return img.rotate(-self.angle, expand=True,
                          resample=Image.BICUBIC, fillcolor=fillcolor)

    def description(self) -> str:
        if self.angle == 90:
            return "회전: 90° 시계방향"
        if self.angle == -90:
            return "회전: 90° 반시계방향"
        if abs(self.angle) == 180:
            return "회전: 180°"
        direction = "시계" if self.angle > 0 else "반시계"
        return f"회전: {abs(self.angle)}° {direction}방향"


Transform = Union[ResizeTransform, CropTransform, RotateTransform]


@dataclass
class TransformPipeline:
    transforms: List[Transform] = field(default_factory=list)

    def apply(self, img: Image.Image) -> Image.Image:
        for t in self.transforms:
            img = t.apply(img)
        return img

    def is_empty(self) -> bool:
        return not self.transforms

    def descriptions(self) -> List[str]:
        return [t.description() for t in self.transforms]
