const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export type LoginResponse = {
  access: string;
  refresh: string;
};

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("accessToken");
  let response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (response.status === 401 && path !== "/auth/token/" && path !== "/auth/token/refresh/") {
    const refresh = localStorage.getItem("refreshToken");
    if (refresh) {
      const refreshResponse = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });

      if (refreshResponse.ok) {
        const tokens = (await refreshResponse.json()) as { access: string };
        localStorage.setItem("accessToken", tokens.access);
        response = await fetch(`${API_BASE_URL}${path}`, {
          ...options,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokens.access}`,
            ...options.headers,
          },
        });
      }
    }
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function login(username: string, password: string) {
  return apiRequest<LoginResponse>("/auth/token/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export const listEntities = <T>(resource: string) => apiRequest<T[]>(`/${resource}/`);

export const createEntity = <T>(resource: string, data: unknown) =>
  apiRequest<T>(`/${resource}/`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateEntity = <T>(resource: string, id: number, data: unknown) =>
  apiRequest<T>(`/${resource}/${id}/`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const patchEntity = <T>(resource: string, id: number, data: unknown) =>
  apiRequest<T>(`/${resource}/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteEntity = (resource: string, id: number) =>
  apiRequest<void>(`/${resource}/${id}/`, { method: "DELETE" });
