(function () {
  var button = document.getElementById("google-reauth");
  var form = document.getElementById("google-delete-form");
  var tokenField = document.getElementById("google-id-token");
  if (!button || !form || !tokenField || typeof firebase === "undefined") {
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

  button.addEventListener("click", function () {
    var provider = new firebase.auth.GoogleAuthProvider();
    firebase
      .auth()
      .signInWithPopup(provider)
      .then(function (result) {
        return result.user.getIdToken();
      })
      .then(function (idToken) {
        tokenField.value = idToken;
        if (window.confirm(form.getAttribute("data-confirm"))) {
          form.submit();
        }
      })
      .catch(function () {
        window.location.reload();
      });
  });
})();
