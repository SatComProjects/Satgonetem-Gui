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
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    throw new ApiError(`Network error: ${error.message || error}`, 0);
  }

  const contentType = response.headers.get("content-type") || "";
  let body = null;
  if (contentType.includes("application/json")) {
    body = await response.json().catch(() => null);
  } else {
    body = await response.text().catch(() => "");
  }

  if (!response.ok || (body && body.ok === false)) {
    throw new ApiError(
      messageFromBody(body, response.statusText || `HTTP ${response.status}`),
      response.status,
      body && body.details,
    );
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
