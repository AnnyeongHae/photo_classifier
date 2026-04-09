import pandas as pd

# 1. 컬럼 이름을 지정해서 탭(\t) 기준으로 깔끔하게 읽어오기
columns = ['geonameid', 'name', 'asciiname', 'alternatenames', 'latitude', 'longitude', 
           'feature_class', 'feature_code', 'country_code', 'cc2', 'admin1_code', 
           'admin2_code', 'admin3_code', 'admin4_code', 'population', 'elevation', 
           'dem', 'timezone', 'modification_date']

df = pd.read_csv('cities1000.txt', sep='\t', names=columns, low_memory=False, encoding='utf-8')

# 2. 필요한 컬럼만 쏙 빼고, 남미 국가(예: 페루, 아르헨티나)만 필터링하기
south_america_codes = ['PE', 'AR', 'BR', 'CL', 'CO', 'EC', 'BO', 'UY', 'PY', 'VE']
my_cities = df[df['country_code'].isin(south_america_codes)][['name', 'latitude', 'longitude', 'country_code']]
my_cities.to_csv('my_cities.csv', index=False, encoding='utf-8-sig')  # 필요한 컬럼만 CSV로 저장하기
# 이제 my_cities 테이블을 이용해 사진의 좌표와 가장 가까운 도시를 찾으면 됩니다!