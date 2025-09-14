# **Aeris AI — README Content**

## **Aeris AI**

*"An agentic AI that helps you stay safe and healthy in India’s harsh weather, from pollution to heatwaves, through actionable alerts."*

---

## **(A) Solution Approach**

### **What is Aeris AI?**

Imagine an AI that cares about your health like a personal guide—

* Alerts you about poor air quality
* Suggests wearing a mask, hydrating, or staying indoors
* Guides you safely through heat waves, monsoons, and other extreme weather

**Aeris AI** is a smart, action-oriented assistant built for India’s toughest weather conditions.

### **Problem & Inspiration**

* India experiences extreme weather and pollution affecting millions
* People often don’t have **real-time guidance** for staying safe during heatwaves, poor AQI days, or monsoon floods
* **Goal:** Create an AI agent that delivers actionable, personalized recommendations

### **Key Features**

* **Personalized recommendations** – masks, hydration, avoiding outdoor activity
* **Action-oriented guidance** – tells users exactly what to do
* **Location-based notifications** – alerts for nearby hazards
* **Predictive insights** – weather and AQI forecasts to prepare in advance
* **User-friendly interface** – simple web/mobile design
* **Health-centric** – prioritizes children, elderly, and at-risk groups
* **Telegram bot integration** – optional real-time alerts via Telegram

### **How Aeris AI Works**

1. User asks a question or requests live AQI/weather
2. Backend checks **Knowledge Base** → Wikipedia → Web fallback (DuckDuckGo)
3. FLAN-T5 AI generates **actionable responses**
4. Live data fetched from public APIs (Open-Meteo, Air Quality API)
5. Telegram bot optionally sends **real-time alerts** to subscribed users

---

## **(B) Tools, Libraries, and Datasets**

* **Python** (backend AI, API handling)
* **JavaScript / HTML / CSS** (frontend web interface)
* **Transformers / FLAN-T5** (for AI responses)
* **Requests / Wikipedia / Difflib** (data fetching & processing)
* **Telegram Bot API** (real-time alerts)
* **Public weather & AQI APIs** (Open-Meteo, OpenStreetMap, Air Quality API)
* **Knowledge Base** (custom JSON with predefined terms and definitions)

---

## **(C) Expected Outcome**

### **Impact**

* Helps users in Indian cities with extreme weather or pollution
* Encourages **safer daily choices**, reducing risks from heatwaves, floods, or poor air quality
* Prioritizes vulnerable populations: children, elderly, and people with respiratory issues

### **Future of Aeris AI**

* Expand beyond real-time weather advice → include flood warnings
* Wearable & smart-home integration for **automatic safety measures**
* Voice assistant support
* Community-level alerts for schools, offices, and public spaces
* Become a **comprehensive digital guardian** for health and safety

---

## **(D) How to Run Aeris AI**

### **Clone & Setup**

```bash
git clone https://github.com/Kartikgajjar95/Aeris-AI.git
cd Aeris-AI
python3 -m venv aeris
source aeris/bin/activate  # Linux / Mac
pip install -r backend/requirements.txt
```

### **Run Backend**

```bash
cd backend
python app.py
```

### **Run Frontend**

* Open `frontend/index.html` in a browser
* Use profile settings to set your location for live AQI/weather alerts

### **Telegram Alerts (Optional)**

* Set `telegram_chat_id` in user profile
* Use `/test_telegram_alert` API to verify alerts