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
)
from wtforms.validators import (
    Optional,
)
from wtforms_components import DateRange, DateTimeLocalField
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

time_zone = tz.gettz("America/Los_Angeles")
SensorReading = namedtuple("SensorReading", ["time", "depth"])

load_dotenv()

# dynamodb for redirect logging
dynamodb = boto3.resource("dynamodb", region_name="us-west-1")
table = dynamodb.Table("water_tank_sensor")

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z'
app.config["FLASK_ENV"] = environ.get("FLASK_ENV", default="production")
app.config["SESSION_TYPE"] = "filesystem"
# app.config["SESSION_TYPE"] = "redis"
# app.config["SESSION_REDIS"] = r
Session(app)

data = []
done = False
start_key = None
while not done:
    if start_key:
        scan_kwargs["ExclusiveStartKey"] = start_key
    response = table.scan()
    data_raw = response.get("Items", [])
    app.logger.debug(f"Fetched {len(data_raw)} items from AWS DynamoDB")
    for item in data_raw:
        unix_time = int(item["sample_time"] / 1000)
        reading = SensorReading(
            datetime.fromtimestamp(unix_time, tz=time_zone),
            float(item["device_data"]["sensor_depth_in"]),
        )
        data.append(reading)
    start_key = response.get("LastEvaluatedKey", None)
    done = start_key is None
app.logger.info(f"Fetched {len(data)} items from AWS DynamoDB")

# sort by time
df = pd.DataFrame(data).sort_values("time")
df.time = pd.to_datetime(df.time)
df.set_index("time", inplace=True)


def toDate(dateString):
    return datetime.strptime(dateString, "%Y-%m-%d %H:%M:%S")


class SlabForm(FlaskForm):
    start_time = DateTimeLocalField(validators=[Optional()], format="%Y-%m-%dT%H:%M")
    end_time = DateTimeLocalField(
        validators=[DateRange(max=datetime.today()), Optional()],
        format="%Y-%m-%dT%H:%M",
    )
    granularity = StringField("Granularity")
    submit = SubmitField("Submit")


@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():

    granularity = request.args.get("granularity", type=str)
    end_time = request.args.get("end_time", type=toDate)
    start_time = request.args.get("start_time", type=toDate)

    filters = dict(
        granularity=granularity,
        end_time=end_time,
        start_time=start_time,
    )
    # app.logger.info(f"Received filter request: {json.dumps(filters)}")
    has_filters = any([value is not None for value in filters.values()])

    # reset session if no args
    if len(request.args) == 0:
        app.logger.debug("Resetting session since no args found.")
        if "filters" in session:
            session.pop("filters")

    session["filters"] = filters

    form = SlabForm()

    # filter form
    if form.validate_on_submit():
        redirect_kwargs = {
            fieldname: form[fieldname].data
            for fieldname in filters.keys()
            if form[fieldname].data
        }
        return redirect(url_for("index", **redirect_kwargs))

    # pre-populate form
    for field in filters.keys():
        form[field].data = filters[field]

    # process data
    df_filtered = df.copy()
    if start_time:
        df_filtered = df_filtered[
            df_filtered.index.to_series() >= start_time.replace(tzinfo=time_zone)
        ]
    if end_time:
        df_filtered = df_filtered[
            df_filtered.index.to_series() <= end_time.replace(tzinfo=time_zone)
        ]
    df_hourly = df_filtered.resample(granularity if granularity else "H").mean()

    # parse args
    return render_template(
        "index.html",
        data=data,
        values=df_hourly.depth,
        labels=df_hourly.index,
        legend="Water depth",
        form=form,
    )
