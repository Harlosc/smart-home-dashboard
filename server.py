from flask import Flask, request, jsonify
from datetime import datetime
from pymongo import MongoClient
import os

app = Flask(__name__)

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["smart_home"]
readings = db["readings"]

FIELDS = ["temperature", "humidity", "gas", "light"]

@app.route('/data', methods=['POST'])
def receive_data():
    data = request.get_json(silent=True)

    if data is None:
        return {"status": "bad json"}, 400

    if any(data.get(k) is None for k in FIELDS):
        return {"status": "missing values"}, 400

    doc = {
        "timestamp": datetime.now(),
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "gas": data["gas"],
        "light": data["light"]
    }
    readings.insert_one(doc)
    print(f"Saved: {doc}")
    return {"status": "received"}, 200

@app.route('/data.json')
def get_data():
    docs = list(readings.find({}, {"_id": 0}).sort("timestamp", 1))
    for d in docs:
        d["timestamp"] = d["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(docs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)