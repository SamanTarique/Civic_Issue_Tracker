(function () {
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function sizeMap(root, map) {
    root.style.height = "280px";
    window.setTimeout(function () {
      map.invalidateSize();
    }, 200);
  }

  function addTiles(map) {
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);
  }

  function initPicker(root) {
    var latInput = document.getElementById(root.dataset.latInput);
    var lngInput = document.getElementById(root.dataset.lngInput);
    var defaultLat = parseFloat(root.dataset.defaultLat);
    var defaultLng = parseFloat(root.dataset.defaultLng);
    var map = L.map(root).setView([defaultLat, defaultLng], 13);
    addTiles(map);

    var marker = null;
    function setPoint(latlng) {
      latInput.value = latlng.lat.toFixed(6);
      lngInput.value = latlng.lng.toFixed(6);
      if (marker) {
        marker.setLatLng(latlng);
      } else {
        marker = L.marker(latlng).addTo(map);
      }
      map.panTo(latlng);
    }

    map.on("click", function (event) {
      setPoint(event.latlng);
    });

    var geoButton = root.dataset.geoButton
      ? document.getElementById(root.dataset.geoButton)
      : null;
    if (geoButton) {
      geoButton.addEventListener("click", function () {
        if (!navigator.geolocation) {
          geoButton.textContent = "Location is not available";
          return;
        }
        geoButton.disabled = true;
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            setPoint(L.latLng(pos.coords.latitude, pos.coords.longitude));
            map.setZoom(16);
            geoButton.disabled = false;
            geoButton.textContent = "Use my location";
          },
          function () {
            geoButton.disabled = false;
            geoButton.textContent = "Location denied — click the map";
          },
          { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
        );
      });
    }

    sizeMap(root, map);
  }

  function initPublic(root) {
    var defaultLat = parseFloat(root.dataset.defaultLat);
    var defaultLng = parseFloat(root.dataset.defaultLng);
    var map = L.map(root).setView([defaultLat, defaultLng], 12);
    addTiles(map);

    fetch(root.dataset.pinsUrl, { credentials: "same-origin" })
      .then(function (res) { return res.json(); })
      .then(function (pins) {
        pins.forEach(function (pin) {
          L.marker([pin.lat, pin.lng])
            .addTo(map)
            .bindPopup(escapeHtml(pin.category) + " · " + escapeHtml(pin.status_label));
        });
      })
      .catch(function () {});
    sizeMap(root, map);
  }

  function initPin(root) {
    var lat = parseFloat(root.dataset.lat);
    var lng = parseFloat(root.dataset.lng);
    var map = L.map(root).setView([lat, lng], 16);
    addTiles(map);
    L.marker([lat, lng]).addTo(map);
    sizeMap(root, map);
  }

  document.querySelectorAll(".js-map-picker").forEach(initPicker);
  document.querySelectorAll(".js-map-public").forEach(initPublic);
  document.querySelectorAll(".js-map-pin").forEach(initPin);
})();
