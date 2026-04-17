# Photo Classifier — 미디어 관리 허브

PySide6 기반 Windows 데스크탑 앱. 세 가지 미디어 관리 도구를 하나의 허브에서 제공합니다.

---

## 도구 목록

| 도구 | 설명 |
|------|------|
| 사진/영상 분류기 | GPS 기반 국가/도시/날짜 폴더 자동 정리 |
| 동영상 해상도 변환기 | FFmpeg + GPU 가속 일괄 해상도 변환 |
| 라이브 포토 변환기 | Live Photo(MP4/MOV) → JPEG 추출 + EXIF 보존 |

---

## 프로젝트 구조

```
project/
├── app.py                         # 앱 진입점
├── _build_helper.py               # Nuitka 빌드 스크립트
├── 사용방법.txt                    # 최종 사용자 매뉴얼
├── assets/
│   ├── exiftool.exe               # 필수: EXIF 처리
│   ├── exiftool_files/            # 필수: exiftool 동반 데이터
│   ├── my_cities.csv              # 필수: 도시 데이터베이스
│   ├── Natural Earth_10m_.../     # 필수: 국가 경계 shapefile
│   ├── ffmpeg.exe                 # 선택: 동영상 변환기용
│   └── ffprobe.exe                # 선택: 동영상 변환기용
├── core/                          # 분류기·변환기 핵심 로직
│   ├── mvp.py                     # GPS 분류 파이프라인
│   ├── video_converter.py         # FFmpeg 래퍼 + GPU 감지
│   ├── classifier.py
│   ├── extractor.py
│   └── ...
├── gui/                           # PySide6 UI
│   ├── screen_setup.py            # 분류기 설정 화면
│   ├── screen_livephoto_setup.py  # 라이브 포토 설정 화면
│   └── ...
├── workers/
│   └── live_photo_worker.py       # 라이브 포토 QThread 워커
└── LivePhotoConverter/            # 독립 라이브 포토 처리 패키지
    └── core/
        ├── frame_extractor.py     # OpenCV 프레임 추출
        ├── focus_detector.py      # Laplacian+Brenner 선명도 감지
        ├── image_converter.py     # JPEG/PNG 저장
        └── metadata_handler.py   # exiftool EXIF 복사
```

---

## 빌드

### 사전 준비

```
assets/exiftool.exe
assets/exiftool_files/
assets/my_cities.csv
assets/Natural Earth_10m_admin_0_countries/ne_10m_admin_0_countries.shp
assets/ffmpeg.exe        (동영상 변환기 사용 시 필수)
assets/ffprobe.exe       (동영상 변환기 사용 시 필수)
```

### 실행

```cmd
pip install -r requirements-build.txt
python _build_helper.py
```

빌드 결과: `PhotoClassifier_Release/` 폴더

```
PhotoClassifier_Release/
├── bin/                    # Nuitka 스탠드얼론 배포 파일
│   ├── PhotoClassifier.exe
│   └── assets/
├── 사용방법.txt
└── PhotoClassifier_실행하기.bat
```

배포 시 `PhotoClassifier_Release/` 폴더를 ZIP으로 압축하여 배포하면 됩니다.

---

## 도구 1 — 사진/영상 분류기

GPS 메타데이터를 읽어 `국가/도시/날짜` 폴더 구조로 파일을 이동/복사합니다.

- shapefile(Natural Earth) + CSV 도시 데이터베이스로 역지오코딩
- GPS 없는 파일은 `No_GPS/날짜/카메라모델` 구조로 분류
- 작업 로그: `DB/DB_report.csv`, `DB/error_report.csv`

---

## 도구 2 — 동영상 해상도 변환기

FFmpeg 기반 일괄 해상도 변환. GPU 하드웨어 인코더를 자동 감지합니다.

**지원 인코더 (우선순위 순)**

| GPU | H.264 | H.265/HEVC |
|-----|-------|------------|
| NVIDIA | h264_nvenc | hevc_nvenc |
| Intel | h264_qsv | hevc_qsv |
| AMD | h264_amf | hevc_amf |
| CPU 폴백 | libx264 | libx265 |

- 지정 해상도 이하 파일은 자동 건너뜀
- 변환 실패 파일: `출력폴더/_Failed_Conversions/파일명_FAILED.txt`에 FFmpeg 로그 저장
- 동시 인코딩: NVIDIA 3개, Intel/AMD 2개, CPU 1개 (자동 결정)

---

## 도구 3 — 라이브 포토 변환기

Live Photo(MP4/MOV) → JPEG/PNG 변환. exiftool로 EXIF 메타데이터를 완전 복사합니다.

### 프레임 선택 알고리즘

| 모드 | 설명 |
|------|------|
| 최선명 | Laplacian + Brenner 앙상블 — 포커스 점수 최고 프레임 (권장) |
| 첫 번째 | 영상 시작 직후 프레임 |
| 중간 | 영상 중앙 프레임 |

### EXIF 보존 전략 (exiftool)

exiftool 단일 커맨드로 처리합니다. 우선순위가 낮은 것부터 높은 것 순으로 나열:

1. `-all:all>all:all` — 포괄적 복사 (Samsung/Sony/Canon/Nikon EXIF-IFD, DJI XMP, GoPro)
2. QuickTime/Keys 날짜 크로스 네임스페이스 — 구형 Android, DJI, GoPro 대응
3. QuickTime/Keys Make/Model — EXIF-IFD가 없는 카메라 대응
4. `Composite:GPS*` — iPhone `Keys:GPSCoordinates` 합성 문자열 분해 (최우선)

**포맷 선택:** JPEG 권장. Live Photo 원본 프레임은 이미 H.264 손실 압축이므로
PNG 저장은 품질 향상 없이 파일만 커집니다. PNG의 EXIF(eXIf 청크)는 뷰어 호환성이 낮습니다.

---

## 오류 대처

### exiftool 미탐지

```
FileNotFoundError: exiftool not found
```

`assets/exiftool.exe`와 `assets/exiftool_files/`가 있는지 확인하세요.
없으면 [exiftool.org](https://exiftool.org)에서 Windows 버전을 다운로드하여 assets에 복사합니다.

### FFmpeg 미탐지

```
FileNotFoundError: FFmpeg executable not found
```

`assets/ffmpeg.exe`와 `assets/ffprobe.exe`가 있는지 확인하세요.
없으면 [ffmpeg.org](https://ffmpeg.org/download.html)에서 다운로드하여 assets에 복사합니다.

### GPS 미보존 (JPEG 변환 후)

원본 영상에 GPS 정보가 없는 경우입니다. 확인:

```cmd
exiftool 파일명.mp4
```

`GPSLatitude`, `Keys:GPSCoordinates`, `QuickTime:GPSCoordinates` 중 하나라도 있어야 복사됩니다.

### Nuitka 빌드 실패

- Python 3.11 사용 권장 (`venv311/`)
- `requirements-build.txt` 설치 확인
- `--noinclude-setuptools-mode=nofollow` 플래그가 `_build_helper.py`에 있는지 확인

---

## 개발자 문의

오류 리포트, 기능 제안:

**andrew4may@gmail.com**

문의 시 포함해 주세요:
- 사용 도구 및 오류 메시지 전체
- 입력 파일 종류 및 촬영 기기
- 스크린샷 (가능하면)
