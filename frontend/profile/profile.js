
document.addEventListener("DOMContentLoaded", async () => {
    let user = JSON.parse(localStorage.getItem("loggedInUser"));
    if (!user || !user.username) {
        alert("Please login first!");
        window.location.href = "../auth/login.html";
        return;
    }

    // Populate profile info
    document.getElementById("userName").textContent = user.username;
    document.getElementById("userAvatar").textContent = user.username[0].toUpperCase();
    document.getElementById("userEmail").textContent = user.email || "user@example.com";
    document.getElementById("userJoined").textContent = user.joined || "-";

    // Populate saved fields or defaults
    document.getElementById("userModeSelect").value = user.mode || "Low";
    document.getElementById("userAge").value = user.age || "";
    document.getElementById("userConditions").value = user.conditions || "";

    // Save profile
    document.getElementById("saveProfile").addEventListener("click", async () => {
        user.mode = document.getElementById("userModeSelect").value;
        user.age = document.getElementById("userAge").value || null;
        user.conditions = document.getElementById("userConditions").value.trim() || "";

        try {
            const res = await fetch(`${API_URL}/update_user`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(user)
            });

            const data = await res.json();
            console.log("Backend response:", data);

            if (res.ok && data.success) {
                localStorage.setItem("loggedInUser", JSON.stringify(data.user));
                alert("Profile saved successfully!");
            } else {
                alert("Failed to save profile: " + (data.msg || "Unknown error"));
            }
        } catch (err) {
            console.error("Error connecting to server:", err);
            alert("Error connecting to server.");
        }
    });

    // Logout
    document.getElementById("logoutBtn").addEventListener("click", () => {
        localStorage.removeItem("loggedInUser");
        window.location.href = "../auth/login.html";
    });
});
