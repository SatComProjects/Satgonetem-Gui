/**
 * Shared JSON API client.
 *
 * Throws ApiError for network failures, non-2xx responses, or the common
 * {ok: false, error} envelope so page controllers can present one message.
 */
export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function messageFromBody(body, fallback) {
  if (body && typeof body === "object" && typeof body.error === "string") {
    return body.error;
  }
  return fallback;
}

export async function apiRequest(path, options = {}) {
  const { timeout = 15000, signal, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let response;
  try {
    response = await fetch(path, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError("Request timed out.", 0);
    }
    throw new ApiError(`Network error: ${error.message || error}`, 0);
  } finally {
    clearTimeout(timer);
  }

  const contentType = response.headers.get("content-type") || "";
  let body = null;
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      throw new ApiError("Invalid JSON response.", response.status);
    }
  } else {
    const text = await response.text().catch(() => "");
    if (response.ok) {
      if (text.trim() !== "") {
        throw new ApiError("Unexpected non-JSON response.", response.status);
      }
      return null;
    }
    body = text;
  }

  if (!response.ok || (body && body.ok === false)) {
    const details = body && typeof body === "object" ? body.details : null;
    let message = messageFromBody(
      body,
      response.statusText || `HTTP ${response.status}`,
    );
    if (Array.isArray(details) && details[0] && details[0].msg) {
      message += ` (${details[0].msg})`;
    }
    throw new ApiError(message, response.status, details);
  }
  return body;
}

export const api = {
  get(path) {
    return apiRequest(path);
  },
  post(path, body) {
    return apiRequest(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};
