# -*- coding: utf-8 -*-
"""Image transform pipeline: Resize and Crop operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Union

from PIL import Image


class ResizeMode(Enum):
    FIT_WITHIN  = "fit_within"   # 최대 WxH 이내 (비율 유지, 이미 작으면 skip)
    BY_WIDTH    = "by_width"     # 너비 지정, 비율 유지
    BY_HEIGHT   = "by_height"    # 높이 지정, 비율 유지
    BY_PERCENT  = "by_percent"   # 비율(%)로 축소/확대
    EXACT       = "exact"        # 정확한 크기 (비율 무시 가능)


class CropMode(Enum):
    ASPECT_RATIO = "aspect_ratio"  # 중앙 기준, 가로세로 비율로 자르기
    FIXED_PIXELS = "fixed_pixels"  # 중앙 기준, 픽셀 크기로 자르기


@dataclass
class ResizeTransform:
    mode: ResizeMode
    width: int   = 1920
    height: int  = 1080
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
                return img  # already fits — skip
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
    width: int  = 1920    # FIXED_PIXELS 모드
    height: int = 1080
    ar_num: int = 16      # ASPECT_RATIO 모드 분자
    ar_den: int = 9       # ASPECT_RATIO 모드 분모

    def apply(self, img: Image.Image) -> Image.Image:
        w, h = img.size

        if self.mode == CropMode.ASPECT_RATIO:
            target = self.ar_num / self.ar_den
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
            cw = min(self.width, w)
            ch = min(self.height, h)
            left = (w - cw) // 2
            top  = (h - ch) // 2
            return img.crop((left, top, left + cw, top + ch))

        return img

    def description(self) -> str:
        if self.mode == CropMode.ASPECT_RATIO:
            return f"자르기: {self.ar_num}:{self.ar_den} 비율"
        if self.mode == CropMode.FIXED_PIXELS:
            return f"자르기: {self.width}×{self.height}px"
        return "자르기"


Transform = Union[ResizeTransform, CropTransform]


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
