# South America Country Classification MVP

## What this does
- Input CSV의 좌표 컬럼(`gps_lat`, `gps_lon` 또는 지정 컬럼) 기반으로 국가를 분류합니다.
- Natural Earth `admin_0` 경계(`.shp`)를 사용해 남미 국가만 `Success` 처리합니다.
- 결과를 요청 스키마 컬럼 기준으로 CSV 저장, 필요 시 SQLite DB 저장합니다.
- 도시 매핑 시 `geo_city`(원본명)와 `geo_city_ascii`(폴더용 ASCII)를 분리 저장합니다.
- 도시 매핑은 하버사인 거리 기반 최근접 + 반경 컷오프(`--max-city-distance-km`, 기본 30km)를 사용합니다.

## Lightweight stack
- Python stdlib (`csv`, `sqlite3`, `pathlib`)
- `pyshp` only (`pip install pyshp`)

## Status rules
- `Success`: 남미 국가 폴리곤 내부
- `No_GPS`: 좌표 없음
- `Invalid_GPS`: 좌표 범위 오류
- `Other_Regions`: 남미 외 지역

## Folder naming policy
- `target_folder`는 ASCII-safe 폴더명을 사용합니다.
- 예: `classified_output/SouthAmerica/Argentina`

## Run
```powershell
python country_classification_mvp.py `
  --input-csv my_cities.csv `
  --cities-csv my_cities.csv `
  --max-city-distance-km 30 `
  --fallback-city Unknown_City `
  --lat-col latitude `
  --lon-col longitude `
  --output-csv mvp_country_result.csv `
  --output-db mvp_country_result.db
```

## ExifTool batch integration (folder scan -> MVP input CSV)
1) 메타데이터 CSV 생성
```powershell
python exiftool_batch_to_mvp_csv.py `
  --scan-folder "D:\YOUR_MEDIA_FOLDER" `
  --output-csv metadata_input_from_exif.csv `
  --exiftool-path "C:\tools\exiftool.exe"
```

2) 국가 분류 실행
```powershell
python country_classification_mvp.py `
  --input-csv metadata_input_from_exif.csv `
  --cities-csv my_cities.csv `
  --max-city-distance-km 30 `
  --target-root output `
  --output-csv metadata_country_result.csv `
  --output-db metadata_country_result.db
```

## Safe file operations (Plan -> Dry-run -> Apply)
```powershell
# 1) 이동 계획 생성
python move_files_by_classification.py `
  --input-csv metadata_country_result.csv `
  --plan-csv move_plan.csv `
  --mode plan

# 2) 사전 검증
python move_files_by_classification.py `
  --input-csv metadata_country_result.csv `
  --plan-csv move_plan.csv `
  --mode dry-run

# 3) 실제 적용 (copy -> verify -> source delete)
python move_files_by_classification.py `
  --input-csv metadata_country_result.csv `
  --plan-csv move_plan.csv `
  --mode apply
```

## One-shot runner (edit only input/output)
```powershell
python run_all_pipeline.py `
  --input-folder "D:\YOUR_INPUT_ROOT" `
  --output-folder "D:\YOUR_OUTPUT_ROOT"
```

If you prefer editing values in code, update only:
- `DEFAULT_INPUT_FOLDER`
- `DEFAULT_OUTPUT_FOLDER`
in [run_all_pipeline.py](d:\2026.04.09_photo classification\run_all_pipeline.py).

## Notes
- `my_cities.csv`의 `name`은 원본 도시명으로 `geo_city`에 저장됩니다.
- `target_folder`에는 `geo_city_ascii`를 사용해 경로 안정성을 확보합니다.
- 도시가 컷오프 밖이면 `SouthAmerica/{Country}/others/{YYYY.MM.DD}`로 라우팅됩니다.
- GPS가 없으면 `No_GPS/{YYYY.MM.DD}` (날짜 미확인 시 `Unknown_Date`)로 라우팅됩니다.
- `file_path` 또는 `source_path` 컬럼이 있으면 파일 크기 자동 채움.
- `--compute-hash` 옵션 사용 시 SHA-1 해시 계산(속도 저하 가능).
