(function () {
  "use strict";

  var shells = [];
  var grounds = [];
  var pendingStations = [];

  var shellList = document.getElementById("shell_list");
  var groundList = document.getElementById("ground_list");
  var hiddenShells = document.getElementById("walker_shells_json");
  var hiddenGrounds = document.getElementById("ground_objects_properties_json");
  var hiddenPhy = document.getElementById("phy_configuration_json");
  var form = document.getElementById("newProjectForm");
  var createBtn = document.getElementById("createBtn");
  var createBox = document.getElementById("create-status");
  var progFill = document.getElementById("create-progress-fill");
  var progText = document.getElementById("create-progress-text");
  var progLabel = document.getElementById("create-progress-label");
  var msgEl = document.getElementById("create-msg");
  var gsCountLabel = document.getElementById("gs_count_label");

  function updateGsLabel() {
    if (pendingStations.length === 0) {
      gsCountLabel.textContent = "No stations selected";
    } else {
      gsCountLabel.textContent = pendingStations.length + " station(s) selected";
    }
  }

  function renderShells() {
    shellList.innerHTML = "";
    shells.forEach(function (s, idx) {
      var li = document.createElement("li");
      var label = document.createElement("span");
      label.textContent =
        s.constellation_property.identifier +
        " - " +
        s.type +
        " - " +
        s.constellation_property.amount_of_orbit_plane +
        "x" +
        s.constellation_property.amount_of_satellite_per_orbit_plane;
      var del = document.createElement("button");
      del.textContent = "Delete";
      del.type = "button";
      del.className = "button";
      del.style.flexShrink = "0";
      del.onclick = function () {
        shells.splice(idx, 1);
        renderShells();
      };
      li.appendChild(label);
      li.appendChild(del);
      shellList.appendChild(li);
    });
    hiddenShells.value = JSON.stringify(shells);
  }

  function renderGrounds() {
    groundList.innerHTML = "";
    grounds.forEach(function (g, idx) {
      var li = document.createElement("li");
      var label = document.createElement("span");
      var stationInfo = g.stations
        ? g.stations.length + " station(s)"
        : "no stations";
      label.textContent =
        g.identifier +
        " - " +
        g.type +
        " - " +
        stationInfo +
        " - " +
        g.connectivity_properties.maximum_connected_satellites +
        " max";
      var del = document.createElement("button");
      del.textContent = "Delete";
      del.type = "button";
      del.className = "button";
      del.style.flexShrink = "0";
      del.onclick = function () {
        grounds.splice(idx, 1);
        renderGrounds();
      };
      li.appendChild(label);
      li.appendChild(del);
      groundList.appendChild(li);
    });
    hiddenGrounds.value = JSON.stringify(grounds);
  }

  document.getElementById("add_shell_btn").addEventListener("click", function () {
    var id = document.getElementById("sh_id").value.trim() || "Shell";
    if (shells.some(function (s) { return s.constellation_property.identifier === id; })) {
      alert('A shell named "' + id + '" already exists. Use a different name.');
      return;
    }
    var type = document.getElementById("sh_type").value;
    var planes = parseInt(document.getElementById("sh_planes").value || "1", 10);
    var sats = parseInt(document.getElementById("sh_sats_plane").value || "1", 10);
    var incl = parseFloat(document.getElementById("sh_incl").value || "0");
    var rev = parseFloat(document.getElementById("sh_rev").value || "0");

    shells.push({
      type: type,
      constellation_property: {
        identifier: id,
        amount_of_orbit_plane: planes,
        amount_of_satellite_per_orbit_plane: sats,
        inclination: incl,
        phase_difference_between_satellites: true,
        mean_revolution_per_day: rev,
      },
      orbital_connectivity_property: {
        adjacent_inter_satellite_shifting: 0,
        maximum_inter_satellite_count: 4,
        maximum_inter_satellite_range_distance: 1500.0,
        maximum_ground_station_range: 1200.0,
        maximum_user_terminal_range: 1000.0,
        maximum_connected_ground_object: 10000,
        maximum_connected_user_terminal: 500,
        maximum_connected_ground_station: 10,
      },
      ground_object_white_list: ["Ground Stations"],
    });
    renderShells();
  });

  document.getElementById("add_ground_btn").addEventListener("click", function () {
    var id = document.getElementById("g_id").value.trim() || "Ground Stations";
    if (grounds.some(function (g) { return g.identifier === id; })) {
      alert('A ground object named "' + id + '" already exists. Use a different name.');
      return;
    }
    if (pendingStations.length === 0) {
      alert("Browse and select at least one ground station first.");
      return;
    }
    var type = document.getElementById("g_type").value;
    var elev = parseInt(document.getElementById("g_elev").value || "10", 10);
    var maxconn = parseInt(document.getElementById("g_maxconn").value || "3", 10);
    var strat = document.getElementById("g_strategy").value;

    grounds.push({
      identifier: id,
      stations: pendingStations.slice(),
      type: type,
      connectivity_properties: {
        ground_to_space_connections_strategy: strat,
        elevation_above_horizon: elev,
        maximum_satellite_range_distance: 1500.0,
        shell_white_lists: ["LEO"],
        maximum_connected_satellites: maxconn,
      },
    });
    pendingStations = [];
    updateGsLabel();
    renderGrounds();
  });

  document.getElementById("browse_gs_btn").addEventListener("click", function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    var backup = {
      fields: Object.fromEntries(fd.entries()),
      shells: shells,
      grounds: grounds,
      gObj: {
        id: document.getElementById("g_id").value,
        type: document.getElementById("g_type").value,
        elev: document.getElementById("g_elev").value,
        maxconn: document.getElementById("g_maxconn").value,
        strategy: document.getElementById("g_strategy").value,
      },
    };
    sessionStorage.setItem("satgonetem_form_backup", JSON.stringify(backup));
    window.location.href = "/ground_stations";
  });

  function restoreFormBackup(backup) {
    var f = backup.fields || {};
    if (f.name) document.querySelector('[name="name"]').value = f.name;
    if (f.update_time) document.querySelector('[name="update_time"]').value = f.update_time;
    if (f.start_date) document.querySelector('[name="start_date"]').value = f.start_date;
    if (f.end_date) document.querySelector('[name="end_date"]').value = f.end_date;
    if (f.isl_capacity) document.querySelector('[name="isl_capacity"]').value = f.isl_capacity;
    if (f.gs_capacity) document.querySelector('[name="gs_capacity"]').value = f.gs_capacity;
    if (f.save_path) document.querySelector('[name="save_path"]').value = f.save_path;

    shells = backup.shells || [];
    grounds = backup.grounds || [];
    renderShells();
    renderGrounds();

    var g = backup.gObj || {};
    if (g.id) document.getElementById("g_id").value = g.id;
    if (g.type) document.getElementById("g_type").value = g.type;
    if (g.elev) document.getElementById("g_elev").value = g.elev;
    if (g.maxconn) document.getElementById("g_maxconn").value = g.maxconn;
    if (g.strategy) document.getElementById("g_strategy").value = g.strategy;
  }

  function seedDefaults() {
    document.getElementById("sh_id").value = "LEO";
    document.getElementById("sh_type").value = "delta";
    document.getElementById("sh_planes").value = "12";
    document.getElementById("sh_sats_plane").value = "22";
    document.getElementById("sh_incl").value = "70";
    document.getElementById("sh_rev").value = "14.4";
    document.getElementById("add_shell_btn").click();

    document.getElementById("sh_id").value = "MEO";
    document.getElementById("sh_type").value = "star";
    document.getElementById("sh_planes").value = "3";
    document.getElementById("sh_sats_plane").value = "6";
    document.getElementById("sh_incl").value = "86.4";
    document.getElementById("sh_rev").value = "5";
    document.getElementById("add_shell_btn").click();
  }

  async function loadProjectConfig(projectName) {
    try {
      var r = await fetch("/api/project/config?name=" + encodeURIComponent(projectName));
      if (!r.ok) throw new Error("Failed to load project config");
      var cfg = await r.json();

      document.querySelector('[name="name"]').value = cfg.name || projectName;
      document.querySelector('[name="update_time"]').value = cfg.update_time != null ? cfg.update_time : 5;
      document.querySelector('[name="start_date"]').value = cfg.start_date || "01/01/2024 00:00:00";
      document.querySelector('[name="end_date"]').value = cfg.end_date || "01/01/2024 00:01:00";
      document.querySelector('[name="isl_capacity"]').value = cfg.isl_capacity != null ? cfg.isl_capacity : 100000;
      document.querySelector('[name="gs_capacity"]').value = cfg.gs_capacity != null ? cfg.gs_capacity : 100000;

      (cfg.walker_shells || []).forEach(function (s) {
        var cp = s.constellation_property || {};
        var ocp = s.orbital_connectivity_property || {};
        shells.push({
          type: s.type || "delta",
          constellation_property: {
            identifier: cp.identifier || "Shell",
            amount_of_orbit_plane: cp.amount_of_orbit_plane != null ? cp.amount_of_orbit_plane : 1,
            amount_of_satellite_per_orbit_plane: cp.amount_of_satellite_per_orbit_plane != null ? cp.amount_of_satellite_per_orbit_plane : 1,
            inclination: cp.inclination != null ? cp.inclination : 0,
            phase_difference_between_satellites: cp.phase_difference_between_satellites != null ? cp.phase_difference_between_satellites : true,
            mean_revolution_per_day: cp.mean_revolution_per_day != null ? cp.mean_revolution_per_day : 14.4,
          },
          orbital_connectivity_property: {
            adjacent_inter_satellite_shifting: ocp.adjacent_inter_satellite_shifting != null ? ocp.adjacent_inter_satellite_shifting : 0,
            maximum_inter_satellite_count: ocp.maximum_inter_satellite_count != null ? ocp.maximum_inter_satellite_count : 4,
            maximum_inter_satellite_range_distance: ocp.maximum_inter_satellite_range_distance != null ? ocp.maximum_inter_satellite_range_distance : 1500.0,
            maximum_ground_station_range: ocp.maximum_ground_station_range != null ? ocp.maximum_ground_station_range : 1200.0,
            maximum_user_terminal_range: ocp.maximum_user_terminal_range != null ? ocp.maximum_user_terminal_range : 1000.0,
            maximum_connected_ground_object: ocp.maximum_connected_ground_object != null ? ocp.maximum_connected_ground_object : 10000,
            maximum_connected_user_terminal: ocp.maximum_connected_user_terminal != null ? ocp.maximum_connected_user_terminal : 500,
            maximum_connected_ground_station: ocp.maximum_connected_ground_station != null ? ocp.maximum_connected_ground_station : 10,
          },
          ground_object_white_list: s.ground_object_white_list || [],
        });
      });
      renderShells();

      (cfg.ground_objects_properties || []).forEach(function (g) {
        var cp = g.connectivity_properties || {};
        grounds.push({
          identifier: g.identifier || "Ground Stations",
          stations: [],
          type: g.type || "ground_station",
          connectivity_properties: {
            ground_to_space_connections_strategy: cp.ground_to_space_connections_strategy || "everything-visible",
            elevation_above_horizon: cp.elevation_above_horizon != null ? cp.elevation_above_horizon : 10,
            maximum_satellite_range_distance: cp.maximum_satellite_range_distance != null ? cp.maximum_satellite_range_distance : 1500.0,
            shell_white_lists: cp.shell_white_lists || [],
            maximum_connected_satellites: cp.maximum_connected_satellites != null ? cp.maximum_connected_satellites : 3,
          },
        });
      });
      renderGrounds();
    } catch (err) {
      console.error("Could not load project config:", err);
      seedDefaults();
    }
  }

  async function waitForProjectCreation(projectName, maxAttempts, delayMs) {
    maxAttempts = maxAttempts || 1200;
    delayMs = delayMs || 500;
    var attempts = 0;
    while (attempts < maxAttempts) {
      try {
        var r = await fetch("/api/project/exists?name=" + encodeURIComponent(projectName));
        if (r.ok) {
          var j = await r.json();
          if (j.exists) return;
        }
      } catch (e) {
        // ignore network errors during polling
      }
      attempts++;
      await new Promise(function (resolve) { setTimeout(resolve, delayMs); });
    }
    throw new Error("Project creation timed out after 10 minutes");
  }

  createBtn.addEventListener("click", async function (e) {
    e.preventDefault();

    if (shells.length === 0) {
      alert("Add at least one orbit shell before creating.");
      return;
    }
    if (grounds.length === 0) {
      alert("Add at least one ground station object before creating.");
      return;
    }

    hiddenShells.value = JSON.stringify(shells);
    hiddenGrounds.value = JSON.stringify(grounds);
    hiddenPhy.value = JSON.stringify(null);

    var fd = new FormData(form);
    var payload = Object.fromEntries(fd.entries());
    var projectName = payload.name;

    try {
      createBtn.disabled = true;
      createBox.style.display = "block";
      if (msgEl) msgEl.textContent = "Starting project creation...";
      if (progLabel) progLabel.textContent = "Constellation";
      if (progFill) progFill.style.width = "10%";

      var r = await fetch("/api/project/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) throw new Error(j.error || "Failed to start project creation");

      if (msgEl) msgEl.textContent = "Building constellation topology...";
      if (progFill) progFill.style.width = "30%";

      await waitForProjectCreation(projectName);

      if (progFill) progFill.style.width = "100%";
      if (msgEl) msgEl.textContent = "Done. Redirecting to dashboard...";
      setTimeout(function () { window.location.href = "/"; }, 1000);
    } catch (err) {
      if (msgEl) msgEl.textContent = "Error: " + String(err.message || err);
      createBtn.disabled = false;
    }
  });

  var gsPending = sessionStorage.getItem("satgonetem_gs_pending");
  if (gsPending) {
    try {
      pendingStations = JSON.parse(gsPending);
    } catch (e) {
      pendingStations = [];
    }
    sessionStorage.removeItem("satgonetem_gs_pending");
    updateGsLabel();
  }

  var formBackupRaw = sessionStorage.getItem("satgonetem_form_backup");
  if (formBackupRaw) {
    try {
      var formBackup = JSON.parse(formBackupRaw);
      sessionStorage.removeItem("satgonetem_form_backup");
      restoreFormBackup(formBackup);
    } catch (e) {
      console.error("Could not restore form backup:", e);
      seedDefaults();
    }
  } else {
    var editProject = new URLSearchParams(window.location.search).get("edit");
    if (editProject) {
      loadProjectConfig(editProject);
    } else {
      seedDefaults();
    }
  }
})();
