/* Vendored Firebase 10.14.1. Runtime hosts: identitytoolkit.googleapis.com,
   securetoken.googleapis.com, www.googleapis.com, accounts.google.com, *.firebaseapp.com */
(function () {
  var button = document.getElementById("google-login");
  if (!button || typeof firebase === "undefined") {
    return;
  }

  var emulator = (button.getAttribute("data-emulator") || "").trim();
  firebase.initializeApp({
    apiKey: button.getAttribute("data-api-key"),
    authDomain: button.getAttribute("data-auth-domain"),
    projectId: button.getAttribute("data-project-id"),
  });
  if (emulator) {
    firebase.auth().useEmulator("http://" + emulator);
  }
  firebase.auth().signOut().catch(function () {});

  function postToken(idToken) {
    var body = new URLSearchParams();
    body.set("csrf_token", button.getAttribute("data-csrf"));
    body.set("id_token", idToken);
    var next = document.querySelector("input[name='next']");
    if (next && next.value) {
      body.set("next", next.value);
    }
    return fetch("/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      credentials: "same-origin",
      redirect: "follow",
    });
  }

  button.addEventListener("click", function () {
    var provider = new firebase.auth.GoogleAuthProvider();
    firebase
      .auth()
      .signInWithPopup(provider)
      .then(function (result) {
        return result.user.getIdToken();
      })
      .then(function (idToken) {
        return postToken(idToken);
      })
      .then(function (response) {
        if (response.redirected) {
          window.location.href = response.url;
          return;
        }
        window.location.reload();
      })
      .catch(function () {
        window.location.reload();
      });
  });
})();
