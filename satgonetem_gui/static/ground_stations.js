(function () {
  "use strict";

  var presets = [];
  var currentStations = [];
  var selectedKeys = new Set();
  var customStations = [];
  var customNextIdx = 100000;

  var presetSelect = document.getElementById("preset_select");
  var tbody = document.getElementById("station_tbody");
  var tableEmpty = document.getElementById("table_empty");
  var selectedCount = document.getElementById("selected_count");
  var checkAllBox = document.getElementById("check_all");
  var customList = document.getElementById("custom_list");

  function updateCount() {
    var n = selectedKeys.size + customStations.length;
    selectedCount.textContent = n + " selected";
  }

  function stationKey(s) {
    return "p_" + s.index;
  }

  function renderTable() {
    tbody.innerHTML = "";
    if (currentStations.length === 0) {
      tableEmpty.style.display = "";
      return;
    }
    tableEmpty.style.display = "none";
    currentStations.forEach(function (s) {
      var key = stationKey(s);
      var checked = selectedKeys.has(key);
      var tr = document.createElement("tr");
      if (checked) tr.classList.add("row-selected");

      var tdCheck = document.createElement("td");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.key = key;
      cb.checked = checked;
      cb.addEventListener("change", function () {
        if (cb.checked) {
          selectedKeys.add(key);
          tr.classList.add("row-selected");
        } else {
          selectedKeys.delete(key);
          tr.classList.remove("row-selected");
        }
        updateCount();
      });
      tdCheck.appendChild(cb);

      tr.appendChild(tdCheck);
      [s.index, s.name, s.latitude, s.longitude, s.elevation_km].forEach(function (val) {
        var td = document.createElement("td");
        td.textContent = val;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    updateCount();
  }

  function loadPreset(idx) {
    currentStations = (presets[idx] && presets[idx].stations) ? presets[idx].stations : [];
    renderTable();
  }

  presetSelect.addEventListener("change", function () {
    loadPreset(parseInt(this.value, 10));
  });

  checkAllBox.addEventListener("change", function () {
    currentStations.forEach(function (s) {
      if (checkAllBox.checked) {
        selectedKeys.add(stationKey(s));
      } else {
        selectedKeys.delete(stationKey(s));
      }
    });
    renderTable();
  });

  document.getElementById("select_all_btn").addEventListener("click", function () {
    currentStations.forEach(function (s) { selectedKeys.add(stationKey(s)); });
    renderTable();
  });

  document.getElementById("deselect_all_btn").addEventListener("click", function () {
    currentStations.forEach(function (s) { selectedKeys.delete(stationKey(s)); });
    renderTable();
  });

  function renderCustomList() {
    customList.innerHTML = "";
    customStations.forEach(function (s, i) {
      var li = document.createElement("li");
      var label = document.createElement("span");
      label.textContent = s.name + " (" + s.latitude + ", " + s.longitude + ", " + s.elevation_km + " km)";
      var del = document.createElement("button");
      del.textContent = "Remove";
      del.type = "button";
      del.className = "button";
      del.onclick = function () {
        customStations.splice(i, 1);
        renderCustomList();
        updateCount();
      };
      li.appendChild(label);
      li.appendChild(del);
      customList.appendChild(li);
    });
    updateCount();
  }

  document.getElementById("add_custom_btn").addEventListener("click", function () {
    var name = document.getElementById("c_name").value.trim();
    var lat = parseFloat(document.getElementById("c_lat").value);
    var lon = parseFloat(document.getElementById("c_lon").value);
    var elev = parseFloat(document.getElementById("c_elev").value || "0");
    if (!name || isNaN(lat) || isNaN(lon)) {
      alert("Name, latitude, and longitude are required.");
      return;
    }
    customStations.push({
      index: customNextIdx++,
      name: name,
      latitude: lat,
      longitude: lon,
      elevation_km: isNaN(elev) ? 0 : elev,
    });
    document.getElementById("c_name").value = "";
    document.getElementById("c_lat").value = "";
    document.getElementById("c_lon").value = "";
    document.getElementById("c_elev").value = "0.0";
    renderCustomList();
  });

  document.getElementById("apply_btn").addEventListener("click", function () {
    var stationMap = {};
    presets.forEach(function (preset) {
      preset.stations.forEach(function (s) {
        stationMap[stationKey(s)] = s;
      });
    });

    var result = [];
    selectedKeys.forEach(function (key) {
      if (stationMap[key]) result.push(stationMap[key]);
    });
    customStations.forEach(function (s) { result.push(s); });

    sessionStorage.setItem("satgonetem_gs_pending", JSON.stringify(result));
    window.location.href = "/new_project";
  });

  fetch("/api/ground_stations/presets")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      presets = data;
      data.forEach(function (p, i) {
        var opt = document.createElement("option");
        opt.value = i;
        opt.textContent = p.name;
        presetSelect.appendChild(opt);
      });
      if (data.length > 0) loadPreset(0);
    })
    .catch(function (err) {
      console.error("Failed to load ground station presets:", err);
    });
})();
