const API_URL = "http://127.0.0.1:5000"; // Flask backend

// Register new user
async function registerUser(username, email, password) {
    try {
        const res = await fetch(`${API_URL}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, email, password })
        });

        const data = await res.json();
        alert(data.msg);

        if (res.ok) {
            window.location.href = "login.html";
        }
    } catch (err) {
        console.error(err);
        alert("Error connecting to server.");
    }
}

// Login existing user
async function loginUser(username, password) {
    try {
        const res = await fetch(`${API_URL}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();
        alert(data.msg);

        if (res.ok) {
            localStorage.setItem("loggedInUser", JSON.stringify(data.user));
            window.location.href = "../index.html"; // go to dashboard
        }
    } catch (err) {
        console.error(err);
        alert("Error connecting to server.");
    }
}

// Logout
function logoutUser() {
    localStorage.removeItem("loggedInUser");
    window.location.href = "login.html";
}
