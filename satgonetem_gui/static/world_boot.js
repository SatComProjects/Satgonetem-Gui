/** Start the Cesium view only when WebGL is available. */
const world = document.getElementById("world");
const fallback = document.getElementById("world-fallback");

function showFallback(message) {
  if (world) world.style.display = "none";
  if (fallback) {
    fallback.style.display = "block";
    const text = fallback.querySelector("p");
    if (text && message) text.textContent = message;
  }
}

let supported = false;
try {
  const canvas = document.createElement("canvas");
  supported = Boolean(
    canvas.getContext("webgl2") || canvas.getContext("webgl"),
  );
} catch {
  supported = false;
}

if (!supported) {
  showFallback("This browser does not provide WebGL.");
} else {
  import("./world.js").catch((error) => {
    console.error("World view failed to start:", error);
    showFallback("The 3D view could not start. Check that the Cesium assets are reachable.");
  });
}
