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
  let timer;
  let timedOut = false;
  const timeoutPromise = new Promise((_resolve, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
      reject(new ApiError("Request timed out.", 0));
    }, timeout);
  });
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const response = await Promise.race([
      fetch(path, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      }),
      timeoutPromise,
    ]);

    const contentType = response.headers.get("content-type") || "";
    let body = null;
    if (contentType.includes("application/json")) {
      try {
        body = await Promise.race([response.json(), timeoutPromise]);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (timedOut) throw new ApiError("Request timed out.", 0);
        throw new ApiError("Invalid JSON response.", response.status);
      }
    } else {
      let text = "";
      try {
        text = await Promise.race([response.text(), timeoutPromise]);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (timedOut) throw new ApiError("Request timed out.", 0);
      }
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
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) throw new ApiError("Request timed out.", 0);
    throw new ApiError(`Network error: ${error.message || error}`, 0);
  } finally {
    clearTimeout(timer);
  }
}

export async function apiGetAll(path, options = {}) {
  const { pageSize = 1000, ...requestOptions } = options;
  const items = [];
  let offset = 0;
  for (let pageNumber = 0; pageNumber < 1000; pageNumber += 1) {
    const separator = path.includes("?") ? "&" : "?";
    const page = await apiRequest(
      `${path}${separator}limit=${pageSize}&offset=${offset}`,
      requestOptions,
    );
    if (!Array.isArray(page)) {
      throw new ApiError("Expected a list response.", 0);
    }
    items.push(...page);
    if (page.length < pageSize) return items;
    offset += pageSize;
  }
  throw new ApiError("Pagination limit reached.", 0);
}

export const api = {
  get(path, options) {
    return apiRequest(path, options);
  },
  getAll(path, options) {
    return apiGetAll(path, options);
  },
  post(path, body, options = {}) {
    return apiRequest(path, {
      ...options,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};
