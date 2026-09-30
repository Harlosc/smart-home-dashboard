import os
from datetime import datetime, timezone

from flask import request, jsonify
from pymongo import MongoClient

import dash
from dash import dcc, html, Input, Output, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd


# =========================================================
# MONGODB
# =========================================================

MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is missing.")

client = MongoClient(MONGO_URI)

db = client["smart_home"]
readings = db["readings"]


# =========================================================
# DASH APP
# =========================================================

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY]
)

server = app.server


# =========================================================
# DROPDOWN / UI CSS
# =========================================================

# Dash's DARKLY theme can make the selected value inside a
# white dropdown appear blank. Force the selected value and
# placeholder text to use a dark color.
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Smart Home IoT Dashboard</title>
        {%favicon%}
        {%css%}
        <style>
            .time-range-dropdown .Select-control {
                background-color: #ffffff !important;
                color: #111827 !important;
            }

            .time-range-dropdown .Select-value-label {
                color: #111827 !important;
            }

            .time-range-dropdown .Select-placeholder {
                color: #111827 !important;
            }

            .time-range-dropdown .Select-input > input {
                color: #111827 !important;
            }

            .time-range-dropdown .Select-menu-outer {
                background-color: #ffffff !important;
            }

            .time-range-dropdown .Select-option {
                color: #111827 !important;
                background-color: #ffffff !important;
            }

            .time-range-dropdown .Select-option:hover {
                background-color: #e5e7eb !important;
                color: #111827 !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


# =========================================================
# SETTINGS
# =========================================================

STALE_SECONDS = 20

FIELDS = [
    "temperature",
    "humidity",
    "gas",
    "light"
]


# =========================================================
# HEALTH CHECK
# =========================================================

@server.route("/")
def home():
    return """
    <h1>Smart Home IoT API</h1>
    <p>Server is running successfully.</p>
    <p>POST sensor data to /data</p>
    <p>GET sensor data from /data.json</p>
    """


@server.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "smart-home-dashboard"
    })


# =========================================================
# RECEIVE ESP32 DATA
# =========================================================

@server.route("/data", methods=["POST"])
def receive_data():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "message": "Invalid JSON"
        }), 400

    # Check required values
    for field in FIELDS:

        if field not in data:
            return jsonify({
                "status": "error",
                "message": f"Missing field: {field}"
            }), 400

    try:

        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        gas = int(data["gas"])
        light = int(data["light"])

    except (ValueError, TypeError):

        return jsonify({
            "status": "error",
            "message": "Invalid sensor value"
        }), 400


    # UTC timestamp
    timestamp = datetime.now(timezone.utc)


    document = {
        "timestamp": timestamp,
        "temperature": temperature,
        "humidity": humidity,
        "gas": gas,
        "light": light
    }


    # Optional LED state
    if "led_status" in data:

        document["led_status"] = bool(
            data["led_status"]
        )


    # Save to MongoDB
    readings.insert_one(document)


    print(
        f"DATA RECEIVED | "
        f"Temp={temperature} | "
        f"Humidity={humidity} | "
        f"Gas={gas} | "
        f"Light={light}"
    )


    return jsonify({
        "status": "received",
        "message": "Sensor data saved successfully"
    }), 200


# =========================================================
# GET DATA
# =========================================================

@server.route("/data.json", methods=["GET"])
def get_data():

    documents = list(
        readings
        .find({}, {"_id": 0})
        .sort("timestamp", 1)
    )


    output = []

    for document in documents:

        timestamp = document.get("timestamp")

        if isinstance(timestamp, datetime):

            timestamp = (
                pd.Timestamp(timestamp)
                .tz_localize("UTC")
                .tz_convert("Asia/Colombo")
                .isoformat()
    )

        output.append({
            "timestamp": timestamp,
            "temperature": document.get("temperature"),
            "humidity": document.get("humidity"),
            "gas": document.get("gas"),
            "light": document.get("light"),
            "led_status": document.get("led_status", False)
        })


    return jsonify(output)


# =========================================================
# LOAD MONGODB DATA
# =========================================================

def load_data():

    documents = list(
        readings
        .find({}, {"_id": 0})
        .sort("timestamp", 1)
    )

    if not documents:

        return pd.DataFrame(
            columns=[
                "timestamp",
                "temperature",
                "humidity",
                "gas",
                "light"
            ]
        )

    df = pd.DataFrame(documents)

    # MongoDB timestamps are stored in UTC
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True
    )

    # Convert UTC to Sri Lanka time
    df["timestamp"] = df["timestamp"].dt.tz_convert(
        "Asia/Colombo"
    )

    return df


# =========================================================
# FILTER DATA
# =========================================================

def filter_data(df, time_range):

    if df.empty:
        return df


    latest_time = df["timestamp"].max()


    if time_range == "10m":

        start_time = latest_time - pd.Timedelta(
            minutes=10
        )


    elif time_range == "1h":

        start_time = latest_time - pd.Timedelta(
            hours=1
        )


    elif time_range == "6h":

        start_time = latest_time - pd.Timedelta(
            hours=6
        )


    elif time_range == "24h":

        start_time = latest_time - pd.Timedelta(
            hours=24
        )


    else:

        start_time = df["timestamp"].min()


    return df[
        df["timestamp"] >= start_time
    ]


# =========================================================
# GRAPH STYLE
# =========================================================

def style_graph(fig):

    fig.update_layout(

        template="plotly_dark",

        paper_bgcolor="rgba(0,0,0,0)",

        plot_bgcolor="rgba(0,0,0,0)",

        margin=dict(
            l=50,
            r=30,
            t=40,
            b=50
        ),

        hovermode="x unified",

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),

        xaxis=dict(
            showgrid=True,
            gridcolor="#334155",
            tickformat="%I:%M:%S %p",
            title="Sri Lanka Time",
            type="date"
        ),

        yaxis=dict(
            showgrid=True,
            gridcolor="#334155"
        )
    )

    return fig


# =========================================================
# DASHBOARD LAYOUT
# =========================================================

app.layout = dbc.Container(

    [

        # HEADER
        dbc.Row(
            [

                dbc.Col(
                    [

                        html.H2(
                            "Smart Home IoT Dashboard",
                            className="text-white fw-bold mb-1"
                        ),

                        html.P(
                            "Real-time environmental monitoring",
                            className="text-secondary mb-1"
                        ),

                        html.Div(
                            id="last-updated",
                            children="Last updated: --",
                            style={
                                "color": "#94a3b8",
                                "fontSize": "14px",
                                "marginTop": "4px"
                            }
                        )

                    ],

                    width=9
                ),

                dbc.Col(
                    [

                        html.Div(
                            id="system-status",
                            className="text-end"
                        )

                    ],

                    width=3
                )

            ],

            className="pt-4 pb-3"
        ),


        # SENSOR CARDS
        dbc.Row(
            [

                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [

                                html.Small(
                                    "TEMPERATURE",
                                    className="text-secondary"
                                ),

                                html.Div(
                                    [
                                        html.H2(
                                            id="temperature-value",
                                            children="--",
                                            className="text-white fw-bold mb-0",
                                            style={
                                                "display": "inline-block"
                                            }
                                        ),

                                        html.Span(
                                            " °C",
                                            className="text-white fw-bold",
                                            style={
                                                "fontSize": "2rem",
                                                "marginLeft": "8px",
                                                "verticalAlign": "baseline"
                                            }
                                        )
                                    ],
                                    style={
                                        "display": "flex",
                                        "alignItems": "baseline",
                                        "marginTop": "4px"
                                    }
                                )

                            ]
                        ),
                        className="bg-dark border-secondary h-100"
                    ),

                    width=3
                ),


                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [

                                html.Small(
                                    "HUMIDITY",
                                    className="text-secondary"
                                ),

                                html.Div(
                                    [
                                        html.H2(
                                            id="humidity-value",
                                            children="--",
                                            className="text-white fw-bold mb-0",
                                            style={
                                                "display": "inline-block"
                                            }
                                        ),

                                        html.Span(
                                            " %",
                                            className="text-white fw-bold",
                                            style={
                                                "fontSize": "2rem",
                                                "marginLeft": "8px",
                                                "verticalAlign": "baseline"
                                            }
                                        )
                                    ],
                                    style={
                                        "display": "flex",
                                        "alignItems": "baseline",
                                        "marginTop": "4px"
                                    }
                                )

                            ]
                        ),
                        className="bg-dark border-secondary h-100"
                    ),

                    width=3
                ),


                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [

                                html.Small(
                                    "GAS LEVEL",
                                    className="text-secondary"
                                ),

                                html.H2(
                                    id="gas-value",
                                    children="--",
                                    className="text-white fw-bold"
                                ),

                            ]
                        ),
                        className="bg-dark border-secondary h-100"
                    ),

                    width=3
                ),


                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [

                                html.Small(
                                    "LIGHT LEVEL",
                                    className="text-secondary"
                                ),

                                html.H2(
                                    id="light-value",
                                    children="--",
                                    className="text-white fw-bold"
                                ),

                            ]
                        ),
                        className="bg-dark border-secondary h-100"
                    ),

                    width=3
                )

            ],

            className="g-3 mb-4"
        ),


        # CONTROLS
        dbc.Card(
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            # TIME RANGE
                            dbc.Col(
                                [
                                    html.Label(
                                        "Time range",
                                        className="text-white fw-bold mb-2"
                                    ),

                                    dcc.Dropdown(
                                        id="time-range",
                                        options=[
                                            {
                                                "label": "Last 10 minutes",
                                                "value": "10m"
                                            },
                                            {
                                                "label": "Last 1 hour",
                                                "value": "1h"
                                            },
                                            {
                                                "label": "Last 6 hours",
                                                "value": "6h"
                                            },
                                            {
                                                "label": "Last 24 hours",
                                                "value": "24h"
                                            }
                                        ],
                                        value="10m",
                                        clearable=False,
                                        searchable=False,
                                        className="time-range-dropdown",
                                        style={
                                            "color": "#111827",
                                            "backgroundColor": "#ffffff"
                                        }
                                    )
                                ],
                                xs=12,
                                md=3
                            ),

                            # SHOW CHARTS
                            dbc.Col(
                                [
                                    html.Label(
                                        "Show charts",
                                        className="text-white fw-bold mb-2"
                                    ),

                                    dcc.Checklist(
                                        id="show-charts",
                                        options=[
                                            {
                                                "label": " Temp/Humidity",
                                                "value": "temp"
                                            },
                                            {
                                                "label": " Gas",
                                                "value": "gas"
                                            },
                                            {
                                                "label": " Light",
                                                "value": "light"
                                            }
                                        ],
                                        value=["temp", "gas", "light"],
                                        inline=True,
                                        inputStyle={
                                            "marginRight": "6px"
                                        },
                                        labelStyle={
                                            "color": "#cbd5e1",
                                            "marginRight": "12px",
                                            "fontSize": "15px"
                                        }
                                    )
                                ],
                                xs=12,
                                md=3,
                                className="mt-3 mt-md-0"
                            ),

                            # TEMPERATURE ALERT
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Temperature alert above: ",
                                                className="text-white fw-bold mb-0"
                                            ),

                                            html.Span(
                                                id="temp-threshold-label",
                                                children="35 °C",
                                                className="text-white fw-bold"
                                            )
                                        ]
                                    ),

                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Slider(
                                                    id="temp-alert-threshold",
                                                    min=20,
                                                    max=40,
                                                    step=1,
                                                    value=35,
                                                    marks={
                                                        20: "20",
                                                        30: "30",
                                                        40: "40"
                                                    },
                                                    tooltip={
                                                        "placement": "bottom",
                                                        "always_visible": False
                                                    }
                                                ),
                                                width=9
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="temp-alert-input",
                                                    type="number",
                                                    min=20,
                                                    max=40,
                                                    step=1,
                                                    value=35,
                                                    debounce=True,
                                                    style={
                                                        "width": "100%",
                                                        "height": "38px",
                                                        "backgroundColor": "#ffffff",
                                                        "color": "#111827",
                                                        "border": "1px solid #e5e7eb",
                                                        "borderRadius": "4px",
                                                        "textAlign": "center"
                                                    }
                                                ),
                                                width=3
                                            )
                                        ],
                                        className="align-items-center"
                                    )
                                ],
                                xs=12,
                                md=3,
                                className="mt-3 mt-md-0"
                            ),

                            # GAS ALERT
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Gas alert above: ",
                                                className="text-white fw-bold mb-0"
                                            ),

                                            html.Span(
                                                id="gas-threshold-label",
                                                children="2000",
                                                className="text-white fw-bold"
                                            )
                                        ]
                                    ),

                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Slider(
                                                    id="gas-alert-threshold",
                                                    min=0,
                                                    max=4000,
                                                    step=100,
                                                    value=2000,
                                                    marks={
                                                        0: "0",
                                                        2000: "2000",
                                                        4000: "4000"
                                                    },
                                                    tooltip={
                                                        "placement": "bottom",
                                                        "always_visible": False
                                                    }
                                                ),
                                                width=9
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="gas-alert-input",
                                                    type="number",
                                                    min=0,
                                                    max=4000,
                                                    step=100,
                                                    value=2000,
                                                    debounce=True,
                                                    style={
                                                        "width": "100%",
                                                        "height": "38px",
                                                        "backgroundColor": "#ffffff",
                                                        "color": "#111827",
                                                        "border": "1px solid #e5e7eb",
                                                        "borderRadius": "4px",
                                                        "textAlign": "center"
                                                    }
                                                ),
                                                width=3
                                            )
                                        ],
                                        className="align-items-center"
                                    )
                                ],
                                xs=12,
                                md=3,
                                className="mt-3 mt-md-0"
                            )
                        ],
                        className="align-items-center"
                    )
                ]
            ),
            className="bg-dark border-secondary mb-4"
        ),

        # ALERT
        html.Div(
            id="alert-section",
            className="mb-4"
        ),


        # GRAPHS - OLD STYLE: TEMPERATURE/HUMIDITY + AIR QUALITY SIDE BY SIDE
        dbc.Row(
            [

                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5(
                                    "Temperature & Humidity Trend",
                                    className="text-white fw-bold mb-3"
                                ),

                                dcc.Graph(
                                    id="temperature-chart",
                                    config={
                                        "displayModeBar": False
                                    },
                                    style={"height": "500px"}
                                )
                            ]
                        ),
                        className="bg-dark border-secondary h-100",
                        id="temp-chart-card"
                    ),
                    width=6
                ),

                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5(
                                    "Air Quality Trend",
                                    className="text-white fw-bold mb-3"
                                ),

                                dcc.Graph(
                                    id="gas-chart",
                                    config={
                                        "displayModeBar": False
                                    },
                                    style={"height": "500px"}
                                )
                            ]
                        ),
                        className="bg-dark border-secondary h-100",
                        id="gas-chart-card"
                    ),
                    width=6
                )

            ],
            className="g-4 mb-4"
        ),


        # LIGHT - FULL WIDTH LIKE THE OLDER VERSION
        dbc.Card(
            dbc.CardBody(
                [

                    html.H5(
                        "Light Level Trend",
                        className="text-white fw-bold mb-3"
                    ),

                    dcc.Graph(
                        id="light-chart",
                        config={
                            "displayModeBar": False
                        },
                        style={"height": "470px"}
                    )

                ]
            ),

            className="bg-dark border-secondary mb-4",
            id="light-chart-card"
        ),


        # AUTO REFRESH
        dcc.Interval(
            id="refresh",
            interval=5000,
            n_intervals=0
        )

    ],

    fluid=True,

    className="bg-black min-vh-100 px-4"
)


# =========================================================
# DASH CALLBACK
# =========================================================

@app.callback(

    [

        Output(
            "temperature-value",
            "children"
        ),

        Output(
            "humidity-value",
            "children"
        ),

        Output(
            "gas-value",
            "children"
        ),

        Output(
            "light-value",
            "children"
        ),

        Output(
            "system-status",
            "children"
        ),

        Output(
            "last-updated",
            "children"
        ),

        Output(
            "alert-section",
            "children"
        ),

        Output(
            "temp-threshold-label",
            "children"
        ),

        Output(
            "gas-threshold-label",
            "children"
        ),

        Output(
            "temperature-chart",
            "figure"
        ),

        Output(
            "gas-chart",
            "figure"
        ),

        Output(
            "light-chart",
            "figure"
        )

    ],

    [

        Input(
            "refresh",
            "n_intervals"
        ),

        Input(
            "time-range",
            "value"
        ),

        Input(
            "temp-alert-threshold",
            "value"
        ),

        Input(
            "gas-alert-threshold",
            "value"
        )

    ]

)
def update_dashboard(
    n_intervals,
    time_range,
    temp_alert_threshold,
    gas_alert_threshold
):

    df = load_data()


    # ==============================================
    # NO DATA
    # ==============================================

    if df.empty:

        empty_temperature = go.Figure()

        empty_gas = go.Figure()

        empty_light = go.Figure()


        for fig in [
            empty_temperature,
            empty_gas,
            empty_light
        ]:

            style_graph(fig)

            fig.update_layout(
                annotations=[
                    dict(
                        text="Waiting for sensor data...",
                        x=0.5,
                        y=0.5,
                        xref="paper",
                        yref="paper",
                        showarrow=False,
                        font=dict(size=18)
                    )
                ]
            )


        return (

            "--",
            "--",
            "--",
            "--",

            dbc.Badge(
                "OFFLINE",
                color="danger",
                className="px-3 py-2"
            ),

            "Last updated: No sensor data",

            dbc.Alert(
                "Waiting for ESP32 sensor data...",
                color="secondary"
            ),

            f"{temp_alert_threshold:.0f} °C",
            f"{gas_alert_threshold:.0f}",

            empty_temperature,
            empty_gas,
            empty_light

        )


    # ==============================================
    # LATEST READING
    # ==============================================

    latest = df.iloc[-1]


    # ==============================================
    # FILTER
    # ==============================================

    filtered = filter_data(
        df,
        time_range
    )


    # ==============================================
    # ONLINE STATUS
    # ==============================================

    now = pd.Timestamp.now(
    tz="Asia/Colombo"
)


    seconds_old = (
        now - latest["timestamp"]
    ).total_seconds()


    if seconds_old <= STALE_SECONDS:

        status = dbc.Badge(
            "ONLINE",
            color="success",
            className="px-3 py-2"
        )

    else:

        status = dbc.Badge(
            "OFFLINE",
            color="danger",
            className="px-3 py-2"
        )


    # ==============================================
    # ALERT
    # ==============================================

    alerts = []


    if latest["temperature"] >= temp_alert_threshold:

        alerts.append(
            dbc.Alert(
                "High temperature detected!",
                color="danger"
            )
        )


    if latest["gas"] >= gas_alert_threshold:

        alerts.append(
            dbc.Alert(
                "High gas level detected!",
                color="danger"
            )
        )


    if seconds_old > STALE_SECONDS:

        alerts.append(
            dbc.Alert(
                "ESP32 is not sending recent data.",
                color="warning"
            )
        )


    if not alerts:

        alert_section = dbc.Alert(
            "✓ Everything looks good",
            color="success"
        )

    else:

        alert_section = html.Div(
            alerts
        )


    # ==============================================
    # TEMPERATURE + HUMIDITY
    # ==============================================

    temp_fig = go.Figure()


    temp_fig.add_trace(

        go.Scatter(

            x=filtered["timestamp"],

            y=filtered["temperature"],

            mode="lines+markers",

            name="Temperature",

            line=dict(
                width=3,
                color="#f59e0b"
            ),

            marker=dict(
                size=5,
                color="#f59e0b"
            )

        )

    )


    temp_fig.add_trace(

        go.Scatter(

            x=filtered["timestamp"],

            y=filtered["humidity"],

            mode="lines+markers",

            name="Humidity",

            yaxis="y2",

            line=dict(
                width=3,
                color="#3b82f6"
            ),

            marker=dict(
                size=5,
                color="#3b82f6"
            )

        )

    )


    temp_fig.update_layout(

        yaxis=dict(
            title="Temperature (°C)"
        ),

        yaxis2=dict(

            title="Humidity (%)",

            overlaying="y",

            side="right"

        )

    )


    style_graph(temp_fig)

    # Older dashboard style: red dashed temperature alert line
    temp_fig.add_hline(
        y=temp_alert_threshold,
        line_dash="dash",
        line_width=2,
        line_color="#ff5c5c",
        annotation_text=f"Temp Alert ({temp_alert_threshold:.0f} °C)",
        annotation_position="top right",
        annotation_font_color="#94a3b8"
    )

    # Keep the dual-axis presentation clean.
    temp_fig.update_layout(
        height=500,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.02,
            xanchor="left",
            x=0
        )
    )


    # ==============================================
    # GAS
    # ==============================================

    gas_fig = go.Figure()


    gas_fig.add_trace(

        go.Scatter(

            x=filtered["timestamp"],

            y=filtered["gas"],

            mode="lines+markers",

            name="Gas Level",

            line=dict(
                width=3,
                color="#10b981"
            ),

            marker=dict(
                size=5,
                color="#10b981"
            )

        )

    )


    style_graph(gas_fig)

    # Older dashboard style: red dashed gas alert threshold
    gas_fig.add_hline(
        y=gas_alert_threshold,
        line_dash="dash",
        line_width=2,
        line_color="#ff5c5c",
        annotation_text=f"Alert Threshold ({gas_alert_threshold:.0f})",
        annotation_position="top right",
        annotation_font_color="#94a3b8"
    )

    gas_fig.update_layout(
        height=430,
        yaxis_title="MQ-135 Value"
    )


    # ==============================================
    # LIGHT
    # ==============================================

    light_fig = go.Figure()


    light_fig.add_trace(

        go.Scatter(

            x=filtered["timestamp"],

            y=filtered["light"],

            mode="lines+markers",

            name="Light Level",

            fill="tozeroy",

            line=dict(
                width=3,
                color="#fbbf24"
            ),

            marker=dict(
                size=5,
                color="#fbbf24"
            ),

            fillcolor="rgba(251, 191, 36, 0.18)"

        )

    )


    style_graph(light_fig)

    light_fig.update_layout(
        height=470,
        yaxis_title="LDR Value"
    )


    # ==============================================
    # RETURN
    # ==============================================

    return (

        f"{latest['temperature']:.1f}",

        f"{latest['humidity']:.1f}",

        f"{latest['gas']:.0f}",

        f"{latest['light']:.0f}",

        status,

        f"Last updated: {latest['timestamp'].strftime('%Y-%m-%d %I:%M:%S %p')}",

        alert_section,

        f"{temp_alert_threshold:.0f} °C",

        f"{gas_alert_threshold:.0f}",

        temp_fig,

        gas_fig,

        light_fig

    )


# =========================================================
# ALERT THRESHOLD INPUT SYNC
# =========================================================

@app.callback(
    [
        Output("temp-alert-threshold", "value"),
        Output("temp-alert-input", "value")
    ],
    [
        Input("temp-alert-threshold", "value"),
        Input("temp-alert-input", "value")
    ],
    prevent_initial_call=True
)
def sync_temp_threshold(slider_value, input_value):

    if ctx.triggered_id == "temp-alert-input":
        value = input_value if input_value is not None else 35
    else:
        value = slider_value if slider_value is not None else 35

    value = max(20, min(40, float(value)))

    return value, value


@app.callback(
    [
        Output("gas-alert-threshold", "value"),
        Output("gas-alert-input", "value")
    ],
    [
        Input("gas-alert-threshold", "value"),
        Input("gas-alert-input", "value")
    ],
    prevent_initial_call=True
)
def sync_gas_threshold(slider_value, input_value):

    if ctx.triggered_id == "gas-alert-input":
        value = input_value if input_value is not None else 2000
    else:
        value = slider_value if slider_value is not None else 2000

    value = max(0, min(4000, float(value)))

    # Keep gas threshold on 100-point increments.
    value = round(value / 100) * 100

    return value, value


# =========================================================
# SHOW / HIDE CHARTS

# =========================================================

@app.callback(

    [
        Output("temp-chart-card", "style"),
        Output("gas-chart-card", "style"),
        Output("light-chart-card", "style")
    ],

    Input(
        "show-charts",
        "value"
    )

)
def toggle_charts(selected_charts):

    selected_charts = selected_charts or []

    return (
        {"display": "block"} if "temp" in selected_charts else {"display": "none"},
        {"display": "block"} if "gas" in selected_charts else {"display": "none"},
        {"display": "block"} if "light" in selected_charts else {"display": "none"}
    )


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )