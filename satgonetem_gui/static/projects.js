/** Project workspace page controller. */
import { api, apiRequest } from "./api.js?v=4";
import { escapeHtml } from "./escape.js";
import {
  formatProjectCount,
  formatProjectDate,
  formatProjectSize,
  projectNameValid,
} from "./projects_model.js?v=1";

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("projects-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setSaveMessage(text, isError = false) {
  const element = byId("save-current-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function projectRow(project) {
  const id = escapeHtml(project.id);
  const name = escapeHtml(project.name || project.filename);
  const filename = escapeHtml(project.filename);
  return `
    <div class="project-row" data-project-id="${id}">
      <div class="project-main">
        <strong class="project-name">${name}</strong>
        <span class="project-file">${filename}</span>
      </div>
      <dl class="project-stats">
        <div><dt>Modified</dt><dd>${escapeHtml(formatProjectDate(project.modified_at))}</dd></div>
        <div><dt>Shells</dt><dd>${escapeHtml(formatProjectCount(project.shells))}</dd></div>
        <div><dt>Satellites</dt><dd>${escapeHtml(formatProjectCount(project.satellites))}</dd></div>
        <div><dt>Stations</dt><dd>${escapeHtml(formatProjectCount(project.ground_stations))}</dd></div>
        <div><dt>Size</dt><dd>${escapeHtml(formatProjectSize(project.size_bytes))}</dd></div>
      </dl>
      <div class="project-actions">
        <button type="button" class="button small" data-project-action="open" data-project-id="${id}">Open</button>
        <button type="button" class="button small secondary" data-project-action="duplicate" data-project-id="${id}">Duplicate</button>
        <button type="button" class="button small secondary" data-project-action="delete" data-project-id="${id}">Delete</button>
      </div>
    </div>`;
}

function renderProjects(data) {
  const list = byId("projects-list");
  const empty = byId("projects-empty");
  if (!list) return;
  const projects = Array.isArray(data?.projects) ? data.projects : [];
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];

  list.innerHTML = projects.map(projectRow).join("");
  if (empty) empty.hidden = projects.length > 0;

  if (warnings.length) {
    setMessage(
      `${projects.length} project(s) loaded; ${warnings.length} file(s) skipped: ${warnings.join("; ")}`,
      true,
    );
  } else {
    setMessage(`${projects.length} project(s) in the workspace.`);
  }
}

async function loadProjects() {
  const button = byId("projects-refresh");
  if (button) button.disabled = true;
  try {
    const data = await api.get("/api/projects");
    renderProjects(data);
  } catch (error) {
    setMessage(`Could not list projects: ${error.message || error}`, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function prefillCurrentName() {
  const input = byId("save-current-name");
  if (!input || input.value) return;
  try {
    const status = await api.get("/api/project/status");
    if (status && status.project_name) input.value = status.project_name;
  } catch {
    /* the workspace can still be browsed without a loaded project */
  }
}

async function openProject(projectId) {
  setSaveMessage("Opening project...");
  try {
    await api.post(`/api/projects/${encodeURIComponent(projectId)}/load`, undefined, {
      timeout: 600000,
    });
    window.location.href = "/";
  } catch (error) {
    setSaveMessage(`Could not open project: ${error.message || error}`, true);
  }
}

async function duplicateProject(projectId) {
  const name = window.prompt("Name for the duplicated workspace project:");
  if (!projectNameValid(name)) return;
  setSaveMessage("Duplicating project...");
  try {
    await api.post(`/api/projects/${encodeURIComponent(projectId)}/duplicate`, {
      name: name.trim(),
    });
    setSaveMessage("Project duplicated.");
    await loadProjects();
  } catch (error) {
    setSaveMessage(`Could not duplicate project: ${error.message || error}`, true);
  }
}

async function deleteProject(projectId, name) {
  if (!window.confirm(`Delete workspace project "${name}"? This cannot be undone.`)) {
    return;
  }
  setSaveMessage("Deleting project...");
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    });
    setSaveMessage("Project deleted.");
    await loadProjects();
  } catch (error) {
    setSaveMessage(`Could not delete project: ${error.message || error}`, true);
  }
}

async function saveCurrentToWorkspace() {
  const nameInput = byId("save-current-name");
  const overwrite = byId("save-current-overwrite");
  const name = nameInput ? nameInput.value : "";
  if (!projectNameValid(name)) {
    setSaveMessage("Enter a workspace name first.", true);
    return;
  }
  const button = byId("save-current-btn");
  if (button) button.disabled = true;
  setSaveMessage("Saving to workspace...");
  try {
    const data = await api.post(
      "/api/project/save-to",
      { name: name.trim(), overwrite: Boolean(overwrite?.checked) },
      { timeout: 600000 },
    );
    setSaveMessage(
      data.overwritten ? "Workspace project overwritten." : "Saved to workspace.",
    );
    await loadProjects();
  } catch (error) {
    setSaveMessage(`Could not save project: ${error.message || error}`, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function saveInPlace() {
  const button = byId("save-in-place-btn");
  if (button) button.disabled = true;
  setSaveMessage("Saving in place...");
  try {
    await api.post("/api/project/save-in-place", undefined, { timeout: 600000 });
    setSaveMessage("Current workspace file updated.");
    await loadProjects();
  } catch (error) {
    setSaveMessage(`Could not save in place: ${error.message || error}`, true);
  } finally {
    if (button) button.disabled = false;
  }
}

const list = byId("projects-list");
if (list) {
  list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-project-action]");
    if (!button) return;
    const id = button.dataset.projectId;
    const row = button.closest(".project-row");
    const name = row?.querySelector(".project-name")?.textContent || id;
    if (!id) return;
    if (button.dataset.projectAction === "open") openProject(id);
    else if (button.dataset.projectAction === "duplicate") duplicateProject(id);
    else if (button.dataset.projectAction === "delete") deleteProject(id, name);
  });
}

byId("projects-refresh")?.addEventListener("click", loadProjects);
byId("save-current-btn")?.addEventListener("click", saveCurrentToWorkspace);
byId("save-in-place-btn")?.addEventListener("click", saveInPlace);

loadProjects();
prefillCurrentName();
