import pandas as pd
from os import environ
import json
from random import shuffle
import boto3
from flask import Flask, render_template, request, session, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, IntegerField, BooleanField
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


def fetch_data():
    data = []
    done = False
    start_key = None
    while not done:
        if start_key:
            scan_kwargs["ExclusiveStartKey"] = start_key
        response = table.scan()
        data_raw = response.get("Items", [])
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
    return df


df = fetch_data()


def toDate(dateString):
    return datetime.strptime(dateString, "%Y-%m-%d %H:%M:%S")


# map human readable units to resample units
# https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.resample.html
granularity_unit_map = {"minutes": "min", "hours": "h", "days": "d"}


class SlabForm(FlaskForm):
    start_time = DateTimeLocalField(validators=[Optional()], format="%Y-%m-%dT%H:%M")
    end_time = DateTimeLocalField(
        validators=[DateRange(max=datetime.today()), Optional()],
        format="%Y-%m-%dT%H:%M",
    )
    granularity_quantity = IntegerField("Granularity quantity")
    granularity_unit = SelectField(
        "Granularity units", choices=granularity_unit_map.keys()
    )
    refresh = BooleanField("Refresh data")
    submit = SubmitField("Submit")


@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    global df

    granularity_quantity = request.args.get("granularity_quantity", type=int)
    granularity_unit = request.args.get("granularity_unit", type=str)
    end_time = request.args.get("end_time", type=toDate)
    start_time = request.args.get("start_time", type=toDate)
    refresh = request.args.get("refresh", type=bool)

    filters = dict(
        granularity_quantity=granularity_quantity,
        granularity_unit=granularity_unit,
        end_time=end_time,
        start_time=start_time,
        refresh=refresh,
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
        if field == "refresh":  # don't wan't refresh bool to persist every time
            break
        form[field].data = filters[field]

    # handle refresh
    if refresh:
        df = fetch_data()

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

    # set default granularity
    granularity_quantity = granularity_quantity if granularity_quantity else 1
    granularity_unit_key = granularity_unit if granularity_unit else "hours"
    granularity_unit = granularity_unit_map[granularity_unit_key]
    form["granularity_quantity"].data = granularity_quantity
    form["granularity_unit"].data = granularity_unit_key

    # resample data to desired granularity
    granularity = str(granularity_quantity) + granularity_unit
    df_agg = df_filtered.resample(granularity).mean()
    df_agg = df_agg.dropna()

    # set x-axis time units
    time_delta = df_filtered.index.max() - df_filtered.index.min()
    if time_delta.days > 3:
        time_unit = "day"
    elif time_delta.seconds > 60 * 60 * 2:
        time_unit = "hour"
    elif time_delta.seconds > 60 * 5:
        time_unit = "minute"
    else:
        time_unit = "hour"

    # parse args
    return render_template(
        "index.html",
        values=df_agg.depth,
        labels=df_agg.index,
        legend="Water depth (inches)",
        form=form,
        unit=time_unit,
    )
