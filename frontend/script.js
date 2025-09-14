// script.js (replace your current file)
// ---------- CONFIG ----------
const API_URL = "http://127.0.0.1:5000"; // update if your backend uses a different port

// ---------- STATE ----------
let user = JSON.parse(localStorage.getItem("loggedInUser")) || {};

// ---------- UTIL ----------
function qs(id) { return document.getElementById(id); }
function showAlert(msg) { alert(msg); } // simple, replace with nicer UI if you want

// ---------- USER LOAD ----------
async function loadUserData() {
    if (!user.username) {
        // Not logged in, redirect to login page
        window.location.href = "./auth/login.html";
        return;
    }

    try {
        const res = await fetch(`${API_URL}/user/${user.username}`);
        const data = await res.json();

        if (data.success) {
            user = data.user; // update local user object
            localStorage.setItem("loggedInUser", JSON.stringify(user)); // sync localStorage

            qs("userName").textContent = user.username;
            qs("userAvatar").textContent = user.username[0].toUpperCase();
            qs("userMode").textContent = user.mode || "Balanced";
        } else {
            showAlert("User not found. Please login again.");
            logoutUser();
        }
    } catch (err) {
        console.error("Failed to fetch user data:", err);
        showAlert("Error connecting to server.");
    }
}

// ---------- LOCATION ----------
async function promptLocation() {
    if (!user.latitude || !user.longitude) {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(async pos => {
                const lat = pos.coords.latitude, lon = pos.coords.longitude;
                user.latitude = lat; user.longitude = lon;
                try {
                    const res = await fetch(`https://geocoding-api.open-meteo.com/v1/reverse?latitude=${lat}&longitude=${lon}`);
                    const geoData = await res.json();
                    user.city = geoData.name || "Unknown";
                } catch {
                    user.city = "Ahmedabad"; user.latitude = 23.0225; user.longitude = 72.5714;
                }
                qs("locationName").textContent = user.city;
                qs("locChip").textContent = user.city;
                localStorage.setItem("loggedInUser", JSON.stringify(user));
                // save location back to backend so scheduler can use it
                await updateUserOnServer({ username: user.username, latitude: user.latitude, longitude: user.longitude });
                fetchWeather();
            }, () => setFallbackCity());
        } else { setFallbackCity(); }
    } else {
        qs("locationName").textContent = user.city;
        qs("locChip").textContent = user.city;
        fetchWeather();
    }
}

function setFallbackCity() {
    user.city = "Ahmedabad"; user.latitude = 23.0225; user.longitude = 72.5714;
    qs("locationName").textContent = user.city;
    qs("locChip").textContent = user.city;
    localStorage.setItem("loggedInUser", JSON.stringify(user));
    updateUserOnServer({ username: user.username, latitude: user.latitude, longitude: user.longitude });
    fetchWeather();
}

// ---------- SIMPLE USER UPDATE HELPER ----------
async function updateUserOnServer(payload) {
    // payload should include { username: user.username, ...other fields... }
    try {
        const res = await fetch(`${API_URL}/update_user`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) {
            console.warn("update_user failed:", data);
        }
        return data;
    } catch (err) {
        console.error("updateUserOnServer error:", err);
        return { success: false, msg: err.message || "Network error" };
    }
}

// ---------- CLOCK ----------
function updateClock() {
    qs("timeVal").textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
updateClock(); setInterval(updateClock, 1000);

// ---------- CHART & WEATHER LOGIC ----------
const ctx = qs("tempChart");
let chart = null;

function createOrUpdateChart(labels, data) {
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ label: "Temperature (°C)", data, tension: 0.35, pointRadius: 3 }] },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: false, ticks: { callback: v => v + "°" } },
                x: { ticks: { maxRotation: 0 } }
            }
        }
    });
}

async function fetchWeather() {
    if (!user.latitude || !user.longitude) return;
    const lat = user.latitude, lon = user.longitude;

    try {
        // current weather
        const weatherRes = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true`);
        const weatherData = await weatherRes.json();
        const cw = weatherData.current_weather;
        qs("bigTemp").textContent = `${cw.temperature}°C`;
        qs("subLine").textContent = `Wind ${cw.windspeed} km/h`;
        qs("windVal").textContent = `${cw.windspeed} km/h`;

        // AQI & UV
        try {
            const aqiRes = await fetch(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${lat}&longitude=${lon}&hourly=pm2_5,pm10,european_aqi&current=uv_index`);
            const aqiData = await aqiRes.json();
            const now = new Date();
            let idx = aqiData.hourly.time.findIndex(t => new Date(t) >= now);
            if (idx === -1) idx = 0;
            const aqi = Math.round(aqiData.hourly.european_aqi[idx]);
            qs("aqiVal").textContent = aqi;
            const uvIndex = aqiData.current.uv_index;
            let uvDesc = uvIndex <= 2 ? "Low" : uvIndex <= 5 ? "Moderate" : uvIndex <= 7 ? "High" : uvIndex <= 10 ? "Very High" : "Extreme";
            qs("uvVal").textContent = `${uvIndex} (${uvDesc})`;
            updateMessages(aqi, cw.temperature, cw.windspeed, uvIndex);
        } catch {
            qs("aqiVal").textContent = "--";
            qs("uvVal").textContent = "--";
        }

        await fetchHourlyWeather(lat, lon);

        // weekly
        const dailyRes = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&daily=temperature_2m_max,temperature_2m_min&forecast_days=16`);
        const dailyData = await dailyRes.json();
        const weekLabels = generateWeekLabels(dailyData.daily.temperature_2m_max);
        const weekTemps = dailyData.daily.temperature_2m_max;
        updateWeekDays(weekLabels.slice(0, 7), dailyData.daily.temperature_2m_max.slice(0, 7), dailyData.daily.temperature_2m_min.slice(0, 7));
        createOrUpdateChart(window.hourLabels || [], window.hourTemps || []);
    } catch (err) {
        console.error("fetchWeather error:", err);
    }
}

async function fetchHourlyWeather(lat, lon) {
    try {
        const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&hourly=temperature_2m,windspeed_10m`);
        const data = await res.json();
        const now = new Date();
        let startIndex = data.hourly.time.findIndex(t => new Date(t) >= now);
        if (startIndex === -1) startIndex = 0;
        const nextHours = Math.min(12, data.hourly.time.length - startIndex);

        window.hourLabels = data.hourly.time.slice(startIndex, startIndex + nextHours)
            .map(t => { const dt = new Date(t); return dt.getHours().toString().padStart(2, '0') + ':' + dt.getMinutes().toString().padStart(2, '0'); });
        window.hourTemps = data.hourly.temperature_2m.slice(startIndex, startIndex + nextHours);
        window.hourWinds = data.hourly.windspeed_10m.slice(startIndex, startIndex + nextHours);

        updateHourlyCards(window.hourLabels, window.hourTemps, window.hourWinds);

        const activeTab = document.querySelector(".tab.active");
        if (activeTab && activeTab.dataset.mode === "hour") createOrUpdateChart(window.hourLabels, window.hourTemps);
    } catch (err) {
        console.error("fetchHourlyWeather error:", err);
    }
}

// ---------- UI Helpers ----------
function generateWeekLabels(dailyData) {
    const labels = [];
    const today = new Date();
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    for (let i = 0; i < dailyData.length; i++) {
        labels.push(i === 0 ? "Today" : i === 1 ? "Tomorrow" : dayNames[(today.getDay() + i) % 7]);
    }
    return labels;
}

function updateWeekDays(labels, tempsMax, tempsMin) {
    const container = qs("weekDays");
    container.innerHTML = "";
    for (let i = 0; i < labels.length; i++) {
        const dayCard = document.createElement("div");
        dayCard.className = "day";
        dayCard.innerHTML = `<span class="day-name">${labels[i]}</span><span class="day-temp">${tempsMax[i]}° / ${tempsMin[i]}°</span>`;
        container.appendChild(dayCard);
    }
}

function updateHourlyCards(labels, temps, winds) {
    const container = qs("hourlyCards"); container.innerHTML = "";
    for (let i = 0; i < labels.length; i++) {
        const div = document.createElement("div");
        div.className = "hour-card";
        div.innerHTML = `<div class="hour-time">${labels[i]}</div><div class="hour-icon">🌤</div><div class="hour-info">Temp ${temps[i]}°C<br>Wind ${winds[i]} km/h</div>`;
        container.appendChild(div);
    }
}

function updateMessages(aqi, temp, wind, uv) {
    const container = qs("messagesContainer");
    container.innerHTML = '<div style="font-weight:700;margin-bottom:4px;">Messages</div>';
    const mode = user.mode || "Balanced";

    if (mode === "Health-first") {
        if (aqi > 50) container.innerHTML += '<div class="msg bad">AQI alert! Sensitive individuals take care.</div>';
        if (uv > 5) container.innerHTML += '<div class="msg bad">High UV — use sunscreen or stay indoors.</div>';
    } else if (mode === "Weather Watch") {
        if (temp >= 35) container.innerHTML += '<div class="msg bad">Extreme heat warning!</div>';
        if (wind >= 50) container.innerHTML += '<div class="msg bad">Strong wind alert!</div>';
    } else {
        if (aqi <= 50) container.innerHTML += '<div class="msg good">AQI is good — safe to go outside.</div>';
        else if (aqi <= 100) container.innerHTML += '<div class="msg normal">AQI is moderate — sensitive groups take care.</div>';
        else container.innerHTML += '<div class="msg bad">AQI is high — limit outdoor activities.</div>';

        if (uv <= 2) container.innerHTML += '<div class="msg good">UV is low — minimal sun protection needed.</div>';
        else if (uv <= 5) container.innerHTML += '<div class="msg normal">UV is moderate — apply sunscreen.</div>';
        else container.innerHTML += '<div class="msg bad">UV is high — cover up and use SPF.</div>';
    }

    if (temp >= 35) container.innerHTML += '<div class="msg bad">High heat — stay hydrated!</div>';
    else if (temp >= 30) container.innerHTML += '<div class="msg normal">Warm day — light clothing recommended.</div>';
    else container.innerHTML += '<div class="msg good">Comfortable temperature — enjoy your day!</div>';

    if (wind >= 50) container.innerHTML += '<div class="msg bad">Strong winds — caution outdoors.</div>';
    else if (wind >= 25) container.innerHTML += '<div class="msg normal">Moderate winds — secure loose items.</div>';
    else container.innerHTML += '<div class="msg good">Calm winds — nice weather.</div>';
}

// ---------- TABS ----------
document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        if (btn.dataset.mode === "hour") createOrUpdateChart(window.hourLabels || [], window.hourTemps || []);
        else createOrUpdateChart(window.weekLabels ? window.weekLabels.slice(0, 7) : [], window.weekTemps ? window.weekTemps.slice(0, 7) : []);
    });
});

// ---------- NAV ----------
qs("GotoProfile").addEventListener("click", () => {
    localStorage.setItem("loggedInUser", JSON.stringify(user));
    window.location.href = "./profile/profile.html";
});

// ---------- LOGOUT ----------
function logoutUser() {
    localStorage.removeItem("loggedInUser");
    window.location.href = "./auth/login.html";
}

// ---------- CHAT UI ----------
const openChatBtn = qs("openChat");
const chatPage = qs("chatPage");
const closeChatBtn = qs("closeChat");
const chatBody = qs("chatBody");
const chatInput = qs("chatInput");
const sendBtn = qs("sendBtn");

openChatBtn.addEventListener("click", () => { chatPage.classList.remove("hidden"); chatInput.focus(); });
closeChatBtn.addEventListener("click", () => { chatPage.classList.add("hidden"); });

function appendMessage(text, sender) {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("chat-msg", sender);
    msgDiv.textContent = text;
    chatBody.appendChild(msgDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
}

sendBtn.addEventListener("click", async () => {
    const text = chatInput.value.trim();
    if (!text) return;
    appendMessage(text, "user");
    chatInput.value = "";
    try {
        const res = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: text })
        });
        const data = await res.json();
        if (data.success) appendMessage(data.response, "ai");
        else appendMessage("Server error: " + data.response, "ai");
    } catch (err) {
        appendMessage("Could not reach server.", "ai");
        console.error(err);
    }
});

chatInput.addEventListener("keypress", (e) => { if (e.key === "Enter") sendBtn.click(); });

// ---------- TELEGRAM SECTION (fixed + improved) ----------
const alertsContent = qs("alertsContent");

async function renderTelegramSection() {
    alertsContent.innerHTML = "<p>Loading...</p>";

    try {
        const res = await fetch(`${API_URL}/alerts_status/${user.username}`);
        const data = await res.json();

        if (!data.success) {
            alertsContent.innerHTML = `<p style="color:red;">${data.msg}</p>`;
            return;
        }

        if (data.linked) {
            // Linked view (no test button)
            alertsContent.innerHTML = `
                <div style="padding:10px; border-radius:8px; background:#f9f9f9;">
                    <p style="font-weight:600;">✅ Telegram linked</p>
                    <p>🔔 Auto alerts active</p>
                    <p>🕒 Last Alert: ${data.last_alert ? new Date(data.last_alert).toLocaleString() : "None"}</p>
                    <p>📋 Last Reason: ${data.last_reason || "None"}</p>
                    <p>⚠️ Active Conditions: ${data.active_conditions.length ? data.active_conditions.join(", ") : "None"}</p>
                    <p>⏳ Next Check: ${data.next_check}</p>
                    <button id="unlinkTelegramBtn" style="margin-top:8px;">Unlink Telegram</button>
                </div>
            `;
            // unlink handler
            qs("unlinkTelegramBtn").addEventListener("click", async () => {
                if (!confirm("Unlink Telegram? You will stop receiving alerts.")) return;
                const res = await updateUserOnServer({ username: user.username, telegram_chat_id: null });
                if (res.success) {
                    user.telegram_chat_id = null;
                    localStorage.setItem("loggedInUser", JSON.stringify(user));
                    renderTelegramSection();
                    showAlert("Telegram unlinked.");
                } else {
                    showAlert("Failed to unlink.");
                }
            });

        } else {
            // Not linked - show input + save
            alertsContent.innerHTML = `
                <input type="text" id="telegramChatId" placeholder="Enter Telegram Chat ID" style="width:70%; padding:6px;"/>
                <button id="saveTelegramIdBtn" style="margin-left:6px;">Save</button>
                <p id="alertsMsg" style="color:red; margin-top:8px;"></p>
                <div style="font-size:12px; margin-top:6px; color:#666;">
                    Tip: message your bot on Telegram first (press Start). Use @userinfobot to get your numeric chat id.
                </div>
            `;

            const telegramInput = qs("telegramChatId");
            const saveBtn = qs("saveTelegramIdBtn");
            const alertsMsg = qs("alertsMsg");

            saveBtn.addEventListener("click", async () => {
                const chatId = telegramInput.value.trim();
                if (!chatId) { alertsMsg.textContent = "Enter your numeric chat id."; return; }
                alertsMsg.textContent = "Saving...";
                try {
                    const res = await updateUserOnServer({ username: user.username, telegram_chat_id: chatId });
                    if (res.success) {
                        user.telegram_chat_id = chatId;
                        localStorage.setItem("loggedInUser", JSON.stringify(user));
                        alertsMsg.style.color = "green";
                        alertsMsg.textContent = "Telegram ID saved ✅";
                        // also trigger a test send to confirm server/bot works
                        await fetch(`${API_URL}/test_telegram_alert`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ username: user.username })
                        });
                        // refresh UI
                        setTimeout(renderTelegramSection, 800);
                    } else {
                        alertsMsg.style.color = "red";
                        alertsMsg.textContent = "Save failed: " + (res.msg || "unknown");
                    }
                } catch (err) {
                    alertsMsg.style.color = "red";
                    alertsMsg.textContent = "Server error";
                    console.error(err);
                }
            });
        }
    } catch (err) {
        alertsContent.innerHTML = `<p style="color:red;">Server error</p>`;
        console.error(err);
    }
}

// ---------- INIT ----------
loadUserData().then(async () => {
    // ensure UI updates after user data comes back
    await promptLocation();
    await fetchWeather();
    renderTelegramSection(); // important: render the Telegram section after load
});
