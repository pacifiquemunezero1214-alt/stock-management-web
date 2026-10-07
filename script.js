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
const loginPassword = document.getElementById("loginPassword");
const toggleLoginPassword = document.getElementById("toggleLoginPassword");

if (loginPassword && toggleLoginPassword) {
    toggleLoginPassword.addEventListener("click", function () {

        if (loginPassword.type === "password") {
            loginPassword.type = "text";
            toggleLoginPassword.textContent = "🙈";
            toggleLoginPassword.setAttribute("aria-label", "Hide password");
        } else {
            loginPassword.type = "password";
            toggleLoginPassword.textContent = "👁️";
            toggleLoginPassword.setAttribute("aria-label", "Show password");
        }

    });
}
/* ============================================================
   STOCK MANAGEMENT PWA INSTALL
   ============================================================ */

(function () {

    let deferredInstallPrompt = null;

    const installCard =
        document.getElementById("pwaInstallCard");

    const installButton =
        document.getElementById("installStockAppBtn");


    function isStandalone() {

        return (
            window.matchMedia(
                "(display-mode: standalone)"
            ).matches
            ||
            window.navigator.standalone === true
        );

    }


    function hideInstallCard() {

        if (installCard) {
            installCard.style.display = "none";
        }

    }


    function showInstallCard() {

        if (
            installCard &&
            !isStandalone()
        ) {

            installCard.style.display = "flex";

        }

    }


    /* Already installed */

    if (isStandalone()) {

        hideInstallCard();

    }


    /* Browser says the app can be installed */

    window.addEventListener(
        "beforeinstallprompt",
        function (event) {

            event.preventDefault();

            deferredInstallPrompt = event;

            showInstallCard();

        }
    );


    /* Install button */

    if (installButton) {

        installButton.addEventListener(
            "click",
            async function () {

                if (!deferredInstallPrompt) {

                    return;

                }


                const promptEvent =
                    deferredInstallPrompt;

                deferredInstallPrompt = null;


                try {

                    await promptEvent.prompt();

                    const result =
                        await promptEvent.userChoice;


                    if (
                        result.outcome === "accepted"
                    ) {

                        hideInstallCard();

                    } else {

                        showInstallCard();

                    }

                } catch (error) {

                    console.error(
                        "PWA installation error:",
                        error
                    );

                    showInstallCard();

                }

            }
        );

    }


    /* App successfully installed */

    window.addEventListener(
        "appinstalled",
        function () {

            deferredInstallPrompt = null;

            hideInstallCard();

            console.log(
                "Stock Management installed successfully."
            );

        }
    );


    /* Check again when page becomes visible */

    window.addEventListener(
        "pageshow",
        function () {

            if (isStandalone()) {

                hideInstallCard();

            } else if (deferredInstallPrompt) {

                showInstallCard();

            }

        }
    );


})();