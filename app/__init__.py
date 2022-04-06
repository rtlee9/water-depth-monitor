import pandas as pd
from os import environ
import json
from random import shuffle
import boto3
from flask import Flask, render_template, request, session, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    SubmitField,
    DecimalField,
)
from wtforms.validators import (
    Optional,
)
from flask_session import Session
from dotenv import load_dotenv
import redis
import urllib.parse as urlparse
from urllib.parse import urlencode, urljoin
from math import inf, ceil
from datetime import datetime
from decimal import Decimal
from typing import List, Set
from collections import namedtuple
from dateutil import tz

time_zone = tz.gettz('America/Los_Angeles')
SensorReading = namedtuple('SensorReading', ['time', 'depth'])

load_dotenv()

# dynamodb for redirect logging
dynamodb = boto3.resource("dynamodb", region_name="us-west-1")
table = dynamodb.Table("water_tank_sensor")

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z'
app.config["FLASK_ENV"] = environ.get("FLASK_ENV", default="production")
Session(app)

data = []
done = False
start_key = None
while not done:
    if start_key:
        scan_kwargs['ExclusiveStartKey'] = start_key
    response = table.scan()
    data_raw = response.get('Items', [])
    app.logger.debug(f"Fetched {len(data_raw)} items from AWS DynamoDB")
    for item in data_raw:
        unix_time = int(item['sample_time'] / 1000)
        print(unix_time)
        reading = SensorReading(
            datetime.fromtimestamp(unix_time, tz=time_zone),
            float(item['device_data']['sensor_depth_in']),
        )
        data.append(reading)
    start_key = response.get('LastEvaluatedKey', None)
    done = start_key is None
app.logger.info(f"Fetched {len(data)} items from AWS DynamoDB")

# sort by time
df = pd.DataFrame(data).sort_values("time")
df.time = pd.to_datetime(df.time)
df.set_index('time', inplace=True)
df_hourly = df.resample('H').mean()
print(df_hourly)

@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    # parse args
    return render_template(
        "index.html",
        data=data,
        values=df_hourly.depth,
        labels=df_hourly.index,
        legend="Water depth",
    )
