# Water Depth Monitor

Flask dashboard for visualizing water depth sensor readings stored in AWS DynamoDB.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=app
export FLASK_ENV=development
flask run
```

Open http://127.0.0.1:5000.

## How It Works

- Sensor readings are stored in a DynamoDB table named `water_tank_sensor` (region `us-west-1`).
- The app scans the table, converts each item to a timestamp + depth reading, and builds a pandas DataFrame.
- The UI lets you filter by time range and resample granularity, then charts the results with Chart.js.

## Configuration

The app loads environment variables from `.env` (optional).

| Variable | Default | Notes |
| --- | --- | --- |
| `FLASK_ENV` | `production` | Set to `development` for local dev.
| `PORT` | n/a | Used by `gunicorn` in `Procfile`.
| `AWS_ACCESS_KEY_ID` | n/a | Required for DynamoDB access.
| `AWS_SECRET_ACCESS_KEY` | n/a | Required for DynamoDB access.
| `AWS_SESSION_TOKEN` | n/a | Optional if using temporary credentials.
| `AWS_REGION` | `us-west-1` | Region for DynamoDB table lookup. |

If you use a shared AWS profile instead of environment variables, make sure your AWS CLI config is set up and the profile is active in your shell.

## Development Notes

- `app/__init__.py` fetches data once at startup. Use the UI "Refresh data" toggle to pull the latest readings without restarting the app.
- Session storage is configured for the filesystem by default (`SESSION_TYPE=filesystem`).

## Running in Production

The included `Procfile` runs Gunicorn:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

## Repository Layout

- `app/__init__.py` - Flask app, data fetch, filtering, and chart prep.
- `app/templates/` - Jinja templates for the dashboard.
- `app/static/` - CSS, fonts, and background assets.

## License

No license specified.
