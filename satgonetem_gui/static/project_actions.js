/** Load/save project actions shared by every page. */
import { api } from "./api.js?v=4";
import { downloadBlob } from "./dom.js";

function initLoad() {
  const link = document.getElementById("loadProjectLink");
  const input = document.getElementById("loadProjectInput");
  if (!link || !input) return;

  link.addEventListener("click", (event) => {
    event.preventDefault();
    input.click();
  });

  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    const originalText = link.textContent;
    link.textContent = "Loading…";
    try {
      const text = await file.text();
      JSON.parse(text);
      await api.post("/api/project/load", { content: text }, { timeout: 600000 });
      window.location.href = "/";
    } catch (error) {
      alert(`Failed to load project: ${error.message || error}`);
    } finally {
      link.textContent = originalText;
      input.value = "";
    }
  });
}

function initSave() {
  const link = document.getElementById("saveProjectLink");
  if (!link) return;

  link.addEventListener("click", async (event) => {
    event.preventDefault();
    const originalText = link.textContent;
    link.textContent = "Saving…";
    try {
      const data = await api.get("/api/project/save", { timeout: 600000 });
      downloadBlob(
        data.filename || "project.json",
        data.content,
        "application/json",
      );
    } catch (error) {
      alert(`Failed to save project: ${error.message || error}`);
    } finally {
      link.textContent = originalText;
    }
  });
}

initLoad();
initSave();
