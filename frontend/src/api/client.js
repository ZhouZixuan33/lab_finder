export class ApiError extends Error {
  constructor(message, { status = 0, code = "NETWORK_ERROR", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, { signal, ...options } = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      signal,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the server. Check that the backend is running.");
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const apiError = payload?.error;
    throw new ApiError(apiError?.message ?? `Request failed (${response.status}).`, {
      status: response.status,
      code: apiError?.code ?? "REQUEST_FAILED",
      details: apiError?.details ?? null,
    });
  }
  return payload;
}

function buildQuery(parameters) {
  const query = new URLSearchParams();
  Object.entries(parameters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export function getProfessors(parameters, options = {}) {
  return request(`/api/professors${buildQuery(parameters)}`, options);
}

export function getTags(options = {}) {
  return request("/api/tags", options);
}

