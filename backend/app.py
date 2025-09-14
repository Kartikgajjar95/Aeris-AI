# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os
from datetime import datetime, timedelta
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# Import bot logic if you use it for chat
import bot

# telegram helper
from telegram_bot import send_message

app = Flask(__name__)
CORS(app)

# -------------------- FIXED USERS FILE PATH --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "../database")
os.makedirs(DATABASE_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATABASE_DIR, "users.json")

# ensure file exists
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump([], f, indent=2)

def load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)
    print(f"[DEBUG] Users saved to: {USERS_FILE}")

# -------------------- REGISTER --------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return jsonify({"success": False, "msg": "Missing fields"}), 400

    users = load_users()
    if any(u["username"] == username for u in users):
        return jsonify({"success": False, "msg": "Username already exists"}), 400

    new_user = {
        "username": username,
        "email": email,
        "password": password,
        "mode": "Low",
        "age": None,
        "conditions": "",
        "joined": datetime.now().strftime("%Y-%m-%d"),
        "notifications": {},
        "telegram_chat_id": None,
        "latitude": None,
        "longitude": None,
        # fields for alerts status
        "last_alert_time": None,
        "last_alert_reason": None,
        "active_conditions": []
    }

    users.append(new_user)
    save_users(users)

    return jsonify({"success": True, "msg": "Registered successfully", "user": new_user})

# -------------------- LOGIN --------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "msg": "Missing fields"}), 400

    users = load_users()
    user = next((u for u in users if u["username"] == username and u["password"] == password), None)

    if not user:
        return jsonify({"success": False, "msg": "Invalid credentials"}), 401

    return jsonify({"success": True, "msg": "Login successful", "user": user})

# -------------------- GET USER --------------------
@app.route("/user/<username>", methods=["GET"])
def get_user(username):
    users = load_users()
    user = next((u for u in users if u["username"] == username), None)
    if user:
        return jsonify({"success": True, "user": user})
    return jsonify({"success": False, "msg": "User not found"}), 404

# -------------------- UPDATE USER --------------------
@app.route("/update_user", methods=["POST"])
def update_user():
    data = request.json
    print("[DEBUG] update_user payload:", data)   # debug line
    username = data.get("username")

    if not username:
        return jsonify({"success": False, "msg": "Username is required"}), 400

    users = load_users()
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        return jsonify({"success": False, "msg": "User not found"}), 404

    # update allowed fields (everything except username/password)
    updated_fields = []
    for key, value in data.items():
        if key not in ["username", "password"]:
            user[key] = value
            updated_fields.append(key)

    save_users(users)
    return jsonify({"success": True, "msg": "User updated", "user": user, "updated_fields": updated_fields})

# -------------------- CHAT --------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "response": "Empty query"}), 400

    try:
        response = bot.generate_response(query)
        return jsonify({"success": True, "response": response})
    except Exception as e:
        print(f"[ERROR] Chat failed: {e}")
        return jsonify({"success": False, "response": "Something went wrong"}), 500

# -------------------- TELEGRAM TEST --------------------
@app.route("/test_telegram_alert", methods=["POST"])
def test_telegram_alert():
    data = request.json
    username = data.get("username")
    users = load_users()
    user = next((u for u in users if u["username"] == username), None)

    if not user or not user.get("telegram_chat_id"):
        return jsonify({"success": False, "msg": "User not linked"}), 400

    try:
        send_message(user["telegram_chat_id"], "✅ This is a test alert from Aeris AI!")
        # update last alert info for UI feedback
        user["last_alert_time"] = datetime.now().isoformat()
        user["last_alert_reason"] = "Test Alert"
        user["active_conditions"] = ["Test"]
        save_users(users)
        return jsonify({"success": True})
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return jsonify({"success": False, "msg": "Telegram failed"}), 500

# -------------------- ALERTS STATUS --------------------
@app.route("/alerts_status/<username>", methods=["GET"])
def alerts_status(username):
    users = load_users()
    user = next((u for u in users if u["username"] == username), None)

    if not user:
        return jsonify({"success": False, "msg": "User not found"}), 404

    # Check if linked
    linked = bool(user.get("telegram_chat_id"))

    # Last alert info (fallbacks if none exist)
    last_alert_time = user.get("last_alert_time")
    last_reason = user.get("last_alert_reason", "None")

    # Calculate next check time (scheduler runs every 4h = 240m)
    next_check = "Unknown"
    if last_alert_time:
        try:
            dt = datetime.fromisoformat(last_alert_time)
            next_dt = dt + timedelta(minutes=240)
            delta = next_dt - datetime.now()
            if delta.total_seconds() > 0:
                hrs = delta.seconds // 3600
                mins = (delta.seconds % 3600) // 60
                next_check = f"in {hrs}h {mins}m"
            else:
                next_check = "Soon"
        except Exception:
            next_check = "Soon"

    active_conditions = user.get("active_conditions", [])

    return jsonify({
        "success": True,
        "linked": linked,
        "last_alert": last_alert_time,
        "last_reason": last_reason,
        "active_conditions": active_conditions,
        "next_check": next_check
    })

# -------------------- BACKGROUND JOB (alerts aggregator) --------------------
def check_alerts():
    """
    Runs on schedule. For each user with a telegram_chat_id and location:
    - fetch current weather + hourly if available
    - evaluate multiple alert conditions
    - send one aggregated message (if any condition triggers)
    - update user's last_alert_time/reason/active_conditions in users.json
    """
    print("[Scheduler] Checking for alerts...")
    users = load_users()
    now = datetime.now()

    for user in users:
        try:
            chat_id = user.get("telegram_chat_id")
            lat = user.get("latitude")
            lon = user.get("longitude")

            if not chat_id or lat is None or lon is None:
                continue  # need both

            # fetch data: current weather + some hourly parameters
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}"
                   f"&longitude={lon}&current_weather=true&hourly=uv_index,pm2_5,pm10&forecast_days=1")
            res = requests.get(url, timeout=15).json()

            # safe extraction
            current = res.get("current_weather", {})
            temp = current.get("temperature")
            wind = current.get("windspeed")
            code = current.get("weathercode")

            hourly = res.get("hourly", {})
            uv_list = hourly.get("uv_index", [])
            pm25_list = hourly.get("pm2_5", [])
            pm10_list = hourly.get("pm10", [])

            uv = uv_list[0] if uv_list else None
            pm25 = pm25_list[0] if pm25_list else None
            pm10 = pm10_list[0] if pm10_list else None

            # evaluate conditions and collect reasons
            reasons = []

            # Temperature
            if temp is not None:
                if temp >= 40:
                    reasons.append(f"Extreme Heat ({temp}°C)")
                elif temp <= 5:
                    reasons.append(f"Severe Cold ({temp}°C)")

            # Wind
            if wind is not None and wind >= 60:
                reasons.append(f"High Wind ({wind} km/h)")

            # UV
            if uv is not None and uv >= 7:
                reasons.append(f"High UV (index {uv})")

            # Air quality - use pm2_5 or pm10 if available
            # thresholds are approximate and can be adjusted
            if pm25 is not None and pm25 >= 150:
                reasons.append(f"Poor Air (PM2.5 {pm25})")
            elif pm10 is not None and pm10 >= 200:
                reasons.append(f"Poor Air (PM10 {pm10})")

            # Weather codes (simple mapping)
            if code in [95, 96, 99]:
                reasons.append("Thunderstorm")
            elif code in [61, 63, 65]:
                reasons.append("Heavy Rain")
            elif code in [71, 73, 75]:
                reasons.append("Snow / Heavy Snow")

            # If any reasons, send aggregated message
            if reasons:
                # Throttle: avoid repeating identical alerts within last 4 hours
                last_alert_iso = user.get("last_alert_time")
                skip_send = False
                if last_alert_iso:
                    try:
                        last_dt = datetime.fromisoformat(last_alert_iso)
                        if now - last_dt < timedelta(minutes=240):
                            # if last_alert_reason exists and new reasons are subset of last, skip
                            last_reasons = set(user.get("active_conditions", []))
                            new_reasons = set(reasons)
                            # if identical or subset, skip to avoid spam
                            if new_reasons.issubset(last_reasons):
                                skip_send = True
                    except Exception:
                        # parsing issue -> don't skip
                        skip_send = False

                if skip_send:
                    print(f"[Scheduler] Skipping alert for {user.get('username')} (recently alerted).")
                else:
                    # build message
                    header = "🚨 Weather Alert from Aeris AI"
                    body = "\n".join(f"- {r}" for r in reasons)
                    footer = "\nStay safe. Check the dashboard for details."
                    message = f"{header}\n\n{body}{footer}"

                    try:
                        send_message(chat_id, message)
                        # update user record
                        user["last_alert_time"] = now.isoformat()
                        user["last_alert_reason"] = ", ".join(reasons)
                        user["active_conditions"] = reasons
                        save_users(users)
                        print(f"[ALERT] Sent to {user.get('username')}: {reasons}")
                    except Exception as e:
                        print(f"[Scheduler Error] Failed sending to {user.get('username')}: {e}")

        except Exception as e:
            print(f"[Scheduler Error] unexpected: {e}")

# -------------------- MAIN --------------------
if __name__ == "__main__":
    print(f"[INFO] Users file: {USERS_FILE}")

    scheduler = BackgroundScheduler()
    # every 4 hours (240 minutes). change minutes=180 for 3 hours or smaller for testing
    scheduler.add_job(check_alerts, "interval", minutes=240)
    scheduler.start()

    app.run(debug=True, host="0.0.0.0", port=5000)
