(function () {
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.querySelector("#google-id-token")) {
        return;
      }
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.getAttribute("data-password-toggle"));
      if (!input) {
        return;
      }
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", show ? "true" : "false");
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.textContent = show ? "Hide" : "Show";
    });
  });

  var toggle = document.querySelector(".nav-toggle");
  var header = document.querySelector(".header");
  if (toggle && header) {
    toggle.addEventListener("click", function () {
      var open = header.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      if (select.form) {
        select.form.submit();
      }
    });
  });

  document.querySelectorAll(".btn, .nav-toggle, .password-toggle").forEach(function (button) {
    function clearPressState() {
      button.classList.remove("is-pressed");
    }
    button.addEventListener("pointerdown", function () {
      button.classList.add("is-pressed");
    });
    button.addEventListener("pointerup", clearPressState);
    button.addEventListener("pointerleave", clearPressState);
    button.addEventListener("pointercancel", clearPressState);
    button.addEventListener("blur", clearPressState);
  });
})();
