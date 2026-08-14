// =========================
// SHOW REGISTER
// =========================

document
    .getElementById("showRegister")
    .addEventListener("click", function () {

        document
            .getElementById("loginCard")
            .classList.add("hidden");

        document
            .getElementById("registerCard")
            .classList.remove("hidden");

    });


// =========================
// SHOW LOGIN
// =========================

document
    .getElementById("showLogin")
    .addEventListener("click", function () {

        document
            .getElementById("registerCard")
            .classList.add("hidden");

        document
            .getElementById("loginCard")
            .classList.remove("hidden");

    });


// =========================
// REGISTER
// =========================

document
    .getElementById("registerForm")
    .addEventListener("submit", async function (event) {

        event.preventDefault();

        const username =
            document.getElementById("registerUsername").value.trim();

        const password =
            document.getElementById("registerPassword").value;

        const confirm =
            document.getElementById("registerConfirm").value;


        if (password !== confirm) {

            alert("Passwords do not match!");

            return;
        }


        try {

            const response = await fetch("/register", {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    username: username,
                    password: password
                })

            });


            const result = await response.json();


            alert(result.message);


            if (result.success) {

                document
                    .getElementById("registerForm")
                    .reset();

                document
                    .getElementById("registerCard")
                    .classList.add("hidden");

                document
                    .getElementById("loginCard")
                    .classList.remove("hidden");

            }

        } catch (error) {

            alert(
                "Cannot connect to the server. " +
                "Make sure Flask is running."
            );

            console.error(error);
        }

    });


// =========================
// LOGIN
// =========================

document
    .getElementById("loginForm")
    .addEventListener("submit", async function (event) {

        event.preventDefault();


        const username =
            document.getElementById("loginUsername").value.trim();

        const password =
            document.getElementById("loginPassword").value;


        try {

            const response = await fetch("/login", {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    username: username,
                    password: password
                })

            });


            const result = await response.json();


            alert(result.message);


            if (result.success) {

                window.location.href = "/dashboard";

            }

        } catch (error) {

            alert(
                "Cannot connect to the server. " +
                "Make sure Flask is running."
            );

            console.error(error);
        }

    });