(function () {
  var input = document.getElementById("photo");
  var preview = document.getElementById("photo-preview");
  if (!input || !preview) {
    return;
  }
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) {
      preview.hidden = true;
      preview.classList.remove("is-visible");
      preview.removeAttribute("src");
      return;
    }
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    preview.classList.add("is-visible");
  });
})();
