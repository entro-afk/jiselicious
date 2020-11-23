import yaml
from sqlalchemy import *

with open(r'jiselConf.yaml') as file:
    # The FullLoader parameter handles the conversion from YAML
    # scalar values to Python the dictionary format
    jiselConf = yaml.load(file, Loader=yaml.FullLoader)

    print(jiselConf)

db_string = "postgres+psycopg2://postgres:{password}@{host}:{port}/postgres".format(username='root', password=jiselConf['postgres']['pwd'], host=jiselConf['postgres']['host'], port=jiselConf['postgres']['port'])
db = create_engine(db_string)
