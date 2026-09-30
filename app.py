import os
from datetime import datetime
from flask import request, jsonify
from pymongo import MongoClient
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["smart_home"]
readings = db["readings"]

FIELDS = ["temperature", "humidity", "gas", "light"]
STALE_SECONDS = 20


@server.route('/data', methods=['POST'])
def receive_data():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"status": "bad json"}), 400

    if any(data.get(k) is None for k in FIELDS):
        return jsonify({"status": "missing values"}), 400

    doc = {
        "timestamp": datetime.now(),
        "temperature": float(data["temperature"]),
        "humidity": float(data["humidity"]),
        "gas": int(data["gas"]),
        "light": int(data["light"])
    }
    if "led_status" in data:
        doc["led_status"] = data["led_status"]

    readings.insert_one(doc)
    print(f"Saved: {doc}")
    return jsonify({"status": "received"}), 200


@server.route('/data.json', methods=['GET'])
def get_data():
    docs = list(readings.find({}, {"_id": 0}).sort("timestamp", 1))
    for d in docs:
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(docs)


def apply_dark_chart_style(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8", family="Inter, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis=dict(gridcolor="#334155", showgrid=True),
        yaxis=dict(gridcolor="#334155", showgrid=True),
    )
    return fig


def load_data():
    docs = list(readings.find({}, {"_id": 0}).sort("timestamp", 1))
    if not docs:
        return pd.DataFrame(columns=['timestamp', 'temperature', 'humidity', 'gas', 'light'])
    df = pd.DataFrame(docs)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def filter_by_range(df, range_value):
    if df.empty:
        return df
    now = df["timestamp"].max()
    if range_value == "10m":
        return df[df["timestamp"] >= now - pd.Timedelta(minutes=10)]
    elif range_value == "1h":
        return df[df["timestamp"] >= now - pd.Timedelta(hours=1)]
    elif range_value == "24h":
        return df[df["timestamp"] >= now - pd.Timedelta(hours=24)]
    return df


app.layout = dbc.Container([

    dbc.Row([
        dbc.Col([
            html.Div([
                html.H3("Smart Home Environment Dashboard", className="d-inline-block me-3 text-white fw-bold"),
                dbc.Badge(id="status-badge", children="OFFLINE", color="secondary", className="px-2 py-1 align-middle", pill=True)
            ]),
            html.Small(id="last-updated", className="text-muted")
        ])
    ], className="my-4"),

    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardBody([
            html.P("Temperature", className="card-subtitle text-muted mb-1 fs-6"),
            html.H2(id="temp-value", className="card-title text-white fw-bold mb-0")
        ])], className="bg-dark border-secondary shadow-sm rounded-3"), width=3),

        dbc.Col(dbc.Card([dbc.CardBody([
            html.P("Humidity", className="card-subtitle text-muted mb-1 fs-6"),
            html.H2(id="humidity-value", className="card-title text-white fw-bold mb-0")
        ])], className="bg-dark border-secondary shadow-sm rounded-3"), width=3),

        dbc.Col(dbc.Card([dbc.CardBody([
            html.P("Air Quality (Gas)", className="card-subtitle text-muted mb-1 fs-6"),
            html.H2(id="gas-value", className="card-title text-white fw-bold mb-0")
        ])], className="bg-dark border-secondary shadow-sm rounded-3"), width=3),

        dbc.Col(dbc.Card([dbc.CardBody([
            html.P("Light Level", className="card-subtitle text-muted mb-1 fs-6"),
            html.H2(id="light-value", className="card-title text-white fw-bold mb-0")
        ])], className="bg-dark border-secondary shadow-sm rounded-3"), width=3),
    ], className="g-3 mb-4"),

    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Time range", className="text-light small fw-bold mb-1"),
                    dcc.Dropdown(
                        id="time-range",
                        options=[
                            {"label": "Last 10 minutes", "value": "10m"},
                            {"label": "Last 1 hour", "value": "1h"},
                            {"label": "Last 24 hours", "value": "24h"}
                        ],
                        value="10m", clearable=False, style={"color": "#000"}
                    )
                ], width=3),

                dbc.Col([
                    html.Label("Show charts", className="text-light small fw-bold mb-1"),
                    dbc.Checklist(
                        id="show-charts",
                        options=[
                            {"label": "Temp/Humidity", "value": "temp"},
                            {"label": "Gas", "value": "gas"},
                            {"label": "Light", "value": "light"}
                        ],
                        value=["temp", "gas", "light"], inline=True, className="text-light pt-2"
                    )
                ], width=3),

                dbc.Col([
                    html.Label(id="temp-slider-label", className="text-light small fw-bold mb-1"),
                    dcc.Slider(id="temp-alert-slider", min=20, max=40, step=1, value=35,
                               marks={20: '20', 30: '30', 40: '40'},
                               tooltip={"placement": "bottom", "always_visible": False})
                ], width=3),

                dbc.Col([
                    html.Label(id="gas-slider-label", className="text-light small fw-bold mb-1"),
                    dcc.Slider(id="gas-alert-slider", min=0, max=4000, step=100, value=2000,
                               marks={0: '0', 2000: '2000', 4000: '4000'},
                               tooltip={"placement": "bottom", "always_visible": False})
                ], width=3),
            ], className="align-items-center")
        ])
    ], className="bg-dark border-secondary shadow-sm rounded-3 mb-3"),

    html.Div(id="alert-section", className="mb-4"),

    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardBody([
            html.H5("Temperature & Humidity Trend", className="text-white card-title fs-6 fw-bold"),
            dcc.Graph(id="temp-chart", config={'displayModeBar': False})
        ])], className="bg-dark border-secondary shadow-sm rounded-3 mb-4"), id="temp-col", width=6),

        dbc.Col(dbc.Card([dbc.CardBody([
            html.H5("Air Quality Trend", className="text-white card-title fs-6 fw-bold"),
            dcc.Graph(id="gas-chart", config={'displayModeBar': False})
        ])], className="bg-dark border-secondary shadow-sm rounded-3 mb-4"), id="gas-col", width=6),
    ]),

    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardBody([
            html.H5("Light Level Trend", className="text-white card-title fs-6 fw-bold"),
            dcc.Graph(id="light-chart", config={'displayModeBar': False})
        ])], className="bg-dark border-secondary shadow-sm rounded-3 mb-4"), id="light-col", width=12)
    ]),

    dcc.Interval(id="interval-component", interval=5000, n_intervals=0)

], fluid=True, className="px-4 py-2 bg-black min-vh-100")


@app.callback(
    [Output("temp-value", "children"), Output("humidity-value", "children"),
     Output("gas-value", "children"), Output("light-value", "children"),
     Output("status-badge", "children"), Output("status-badge", "color"),
     Output("last-updated", "children"), Output("temp-slider-label", "children"),
     Output("gas-slider-label", "children"), Output("alert-section", "children"),
     Output("temp-chart", "figure"), Output("gas-chart", "figure"), Output("light-chart", "figure"),
     Output("temp-col", "style"), Output("gas-col", "style"), Output("light-col", "style")],
    [Input("interval-component", "n_intervals"), Input("time-range", "value"),
     Input("show-charts", "value"), Input("temp-alert-slider", "value"), Input("gas-alert-slider", "value")]
)
def update_dashboard(n, range_value, visible_charts, temp_thresh, gas_thresh):
    df = load_data()

    temp_col_style = {} if "temp" in visible_charts else {"display": "none"}
    gas_col_style = {} if "gas" in visible_charts else {"display": "none"}
    light_col_style = {} if "light" in visible_charts else {"display": "none"}

    temp_label = f"Temperature alert above: {temp_thresh} °C"
    gas_label = f"Gas alert above: {gas_thresh}"

    if df.empty:
        empty_fig = go.Figure()
        apply_dark_chart_style(empty_fig)
        no_data_alert = dbc.Alert([
            html.H5("⚠ No sensor data", className="fw-bold"),
            html.P("The sensor system has not sent any readings yet.", className="mb-0")
        ], color="secondary", className="mb-0")
        return ("--", "--", "--", "--", "OFFLINE", "secondary", "No data yet",
                temp_label, gas_label, no_data_alert, empty_fig, empty_fig, empty_fig,
                temp_col_style, gas_col_style, light_col_style)

    latest = df.iloc[-1]
    filtered = filter_by_range(df, range_value)

    seconds_since = (datetime.now() - latest["timestamp"]).total_seconds()
    badge_text, badge_color = ("ONLINE", "success") if seconds_since <= STALE_SECONDS else ("OFFLINE", "danger")

    alerts = []
    if latest["temperature"] > temp_thresh:
        alerts.append(dbc.Alert([
            html.H5("🌡️ High Temperature", className="fw-bold"),
            html.P("The temperature is above your selected alert level.", className="mb-1"),
            html.Small(f"Current temperature: {latest['temperature']:.1f} °C")
        ], color="danger", className="mb-2"))

    if latest["gas"] > gas_thresh:
        alerts.append(dbc.Alert([
            html.H5("⚠️ Poor Air Quality", className="fw-bold"),
            html.P("The gas level is above your selected alert level.", className="mb-1"),
            html.Small(f"Current gas level: {latest['gas']:.0f}")
        ], color="danger", className="mb-2"))

    if seconds_since > STALE_SECONDS:
        alerts.append(dbc.Alert([
            html.H5("📡 Device Offline", className="fw-bold"),
            html.P("No recent sensor data has been received. Please check the sensor system and Wi-Fi connection.", className="mb-0")
        ], color="warning", className="mb-2"))

    if len(alerts) == 0:
        alert_section = dbc.Alert([
            html.H5("✓ Everything looks good", className="fw-bold mb-1"),
            html.P("Your environment is currently within the selected alert levels.", className="mb-0")
        ], color="success", className="mb-0")
    else:
        alert_section = html.Div([html.H5("🔔 Attention Required", className="text-white fw-bold mb-2"), *alerts])

    fig_temp = go.Figure()
    fig_temp.add_trace(go.Scatter(x=filtered["timestamp"], y=filtered["temperature"], name="Temperature (°C)", line=dict(color="#F59E0B")))
    fig_temp.add_trace(go.Scatter(x=filtered["timestamp"], y=filtered["humidity"], name="Humidity (%)", line=dict(color="#3B82F6"), yaxis="y2"))
    fig_temp.add_hline(y=temp_thresh, line_dash="dash", line_color="#EF4444", annotation_text="Temp Alert")
    fig_temp.update_layout(yaxis2=dict(overlaying="y", side="right"))
    apply_dark_chart_style(fig_temp)

    fig_gas = go.Figure()
    fig_gas.add_trace(go.Scatter(x=filtered["timestamp"], y=filtered["gas"], name="Gas Level", line=dict(color="#10B981")))
    fig_gas.add_hline(y=gas_thresh, line_dash="dash", line_color="#EF4444", annotation_text="Alert Threshold")
    apply_dark_chart_style(fig_gas)

    fig_light = go.Figure()
    fig_light.add_trace(go.Scatter(x=filtered["timestamp"], y=filtered["light"], fill="tozeroy", name="Light Level", line=dict(color="#FBBF24"), fillcolor="rgba(251, 191, 36, 0.2)"))
    apply_dark_chart_style(fig_light)

    return (
        f"{latest['temperature']:.1f} °C", f"{latest['humidity']:.1f} %",
        f"{latest['gas']:.0f}", f"{latest['light']:.0f}",
        badge_text, badge_color, f"Last updated: {latest['timestamp']}",
        temp_label, gas_label, alert_section,
        fig_temp, fig_gas, fig_light,
        temp_col_style, gas_col_style, light_col_style
    )


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)