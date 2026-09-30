import os
from datetime import datetime
from flask import request, jsonify
from pymongo import MongoClient
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go

# 1. Initialize Dash and expose the underlying Flask server
app = dash.Dash(__name__)
server = app.server

# 2. MongoDB Connection Setup
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["smart_home"]
readings = db["readings"]

FIELDS = ["temperature", "humidity", "gas", "light"]

# --- API ROUTES (Attached to Flask `server`) ---

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


# --- DASHBOARD LAYOUT ---

app.layout = html.Div(
    style={'backgroundColor': '#1e1e1e', 'color': '#ffffff', 'padding': '20px', 'fontFamily': 'Arial'},
    children=[
        html.H1("IoT Environmental Dashboard", style={'textAlign': 'center'}),
        
        # Auto-refresh component (fetches latest readings every 5 seconds)
        dcc.Interval(
            id='interval-component',
            interval=5*1000, # 5000 milliseconds
            n_intervals=0
        ),

        html.Div(style={'display': 'flex', 'justifyContent': 'space-around'}, children=[
            html.Div(style={'width': '48%'}, children=[
                dcc.Graph(id='temp-humidity-graph')
            ]),
            html.Div(style={'width': '48%'}, children=[
                dcc.Graph(id='gas-graph')
            ])
        ])
    ]
)

# --- DASH REFRESH CALLBACK ---

@app.callback(
    [Output('temp-humidity-graph', 'figure'),
     Output('gas-graph', 'figure')],
    [Input('interval-component', 'n_intervals')]
)
def update_graphs(n):
    # Retrieve the last 50 data points from MongoDB
    docs = list(readings.find({}, {"_id": 0}).sort("timestamp", -1).limit(50))
    docs.reverse() # Sort chronologically for plotting

    timestamps = [d["timestamp"].strftime("%H:%M:%S") if isinstance(d.get("timestamp"), datetime) else str(d.get("timestamp")) for d in docs]
    temps = [d.get("temperature", 0) for d in docs]
    humids = [d.get("humidity", 0) for d in docs]
    gases = [d.get("gas", 0) for d in docs]

    # Temperature & Humidity Figure
    fig_temp = go.Figure()
    fig_temp.add_trace(go.Scatter(x=timestamps, y=temps, mode='lines+markers', name='Temperature (°C)', line=dict(color='#FFA500')))
    fig_temp.add_trace(go.Scatter(x=timestamps, y=humids, mode='lines+markers', name='Humidity (%)', line=dict(color='#1E90FF')))
    fig_temp.update_layout(
        title='Temperature & Humidity Trend',
        paper_bgcolor='#1e1e1e',
        plot_bgcolor='#2d2d2d',
        font=dict(color='#ffffff')
    )

    # Air Quality (Gas) Figure
    fig_gas = go.Figure()
    fig_gas.add_trace(go.Scatter(x=timestamps, y=gases, mode='lines+markers', name='Gas Level', line=dict(color='#00FF7F')))
    fig_gas.update_layout(
        title='Air Quality Trend',
        paper_bgcolor='#1e1e1e',
        plot_bgcolor='#2d2d2d',
        font=dict(color='#ffffff')
    )

    return fig_temp, fig_gas


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run_server(host='0.0.0.0', port=port, debug=True)