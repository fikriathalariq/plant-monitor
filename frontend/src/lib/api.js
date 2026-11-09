import axios from 'axios';

// Base URL resolution: mendukung localhost, LAN IP, dan DevTunnel.
// Jika dibuka via Nginx (port 80 atau 8000), gunakan origin yang sama persis (Same-Origin)
// sehingga tidak ada kendala CORS, session cookie tetap aman, dan tidak terbentur firewall antar port.
export function resolveBackendBaseUrl() {
  if (window.location.hostname.includes('devtunnels.ms')) {
    const backendHostname = window.location.hostname.replace(/-\d+\./, '-8000.');
    return `https://${backendHostname}`;
  }
  // Jika dev server Vite dijalankan langsung tanpa proxy Nginx (port 5173 / 8002 / 8003)
  // Port 8002, 8003, 8000 sekarang dilayani Nginx dengan reverse proxy /api/ (Same-Origin).
  // Hanya dev server Vite lokal 5173 yang mengarah ke port 8000.
  if (window.location.port === '5173') {
    return `http://${window.location.hostname}:8000`;
  }
  // Akses normal melalui Nginx (port 80, port 8000, domain LAN, dsb.)
  return window.location.origin;
}

export const BACKEND_BASE_URL = resolveBackendBaseUrl();
export const API_BASE_URL = `${BACKEND_BASE_URL}/api/v1`;

// Timeout default 15 detik (mencegah request menggantung tak terhingga saat socket stale)
export const DEFAULT_REQUEST_TIMEOUT = 15000;

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // penting untuk mengirim session cookie Django
  timeout: DEFAULT_REQUEST_TIMEOUT,
});

// Beberapa endpoint lama (Django view biasa, bukan Ninja) masih dipakai di bawah /api/,
// mis. /steam-usage-history/ -> http://host:8000/api/steam-usage-history/
export const legacyApi = axios.create({
  baseURL: `${BACKEND_BASE_URL}/api`,
  withCredentials: true,
  timeout: DEFAULT_REQUEST_TIMEOUT,
});

let onUnauthorized = null;
export function registerUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function triggerUnauthorized() {
  if (onUnauthorized) {
    onUnauthorized();
  }
}

// Cek apakah response sebenarnya adalah halaman HTML Login (biasanya karena redirect 302 dari Django saat session habis)
function isHtmlLoginResponse(response) {
  const contentType = response?.headers?.['content-type'] || '';
  if (contentType.includes('text/html')) return true;
  if (
    typeof response?.data === 'string' &&
    (response.data.includes('<!DOCTYPE') || response.data.includes('<html') || response.data.includes('id="login-form"'))
  ) {
    return true;
  }
  return false;
}

const handleResponseSuccess = (response) => {
  if (isHtmlLoginResponse(response)) {
    triggerUnauthorized();
    const error = new Error('Sesi telah berakhir atau tidak sah (HTML redirect terdeteksi).');
    error.response = { status: 401, data: response.data, headers: response.headers };
    return Promise.reject(error);
  }
  return response;
};

const handleResponseError = (error) => {
  if (error.response?.status === 401) {
    triggerUnauthorized();
  }
  return Promise.reject(error);
};

api.interceptors.response.use(handleResponseSuccess, handleResponseError);
legacyApi.interceptors.response.use(handleResponseSuccess, handleResponseError);

// =========================================================================
// Client-Side GET In-Memory Cache & In-Flight Request Deduplication with TTL
// =========================================================================
// inFlightRequests Map: key -> { promise: Promise, timestamp: number }
const inFlightRequests = new Map();
const memoryCache = new Map();

function getCacheTtl(url) {
  if (url.includes('/branding')) return 10 * 60 * 1000; // 10 menit
  if (url.includes('/history/filters')) return 5 * 60 * 1000; // 5 menit
  if (url.includes('/auth/me')) return 5 * 1000; // 5 detik
  if (url.includes('/home-korlap') || url.includes('/dashboard')) return 15 * 1000; // 15 detik
  if (url.includes('/report/') || url.includes('/analytics/') || url.includes('/snapshots/')) return 45 * 1000; // 45 detik
  if (url.includes('/history/')) return 15 * 1000; // 15 detik
  return 10 * 1000; // default 10 detik
}

export function clearApiCache(urlPattern = null) {
  if (!urlPattern) {
    memoryCache.clear();
    return;
  }
  for (const key of memoryCache.keys()) {
    if (key.includes(urlPattern)) {
      memoryCache.delete(key);
    }
  }
}

// Bersihkan in-flight requests yang macet (misal saat tab bangun dari idle atau window online)
export function clearStaleInFlightRequests() {
  inFlightRequests.clear();
}

function attachCacheAndDedup(client) {
  const originalGet = client.get.bind(client);

  client.get = function (url, config = {}) {
    const shouldBypass =
      config.cache === false ||
      config.headers?.['Cache-Control'] === 'no-cache' ||
      config.headers?.['cache-control'] === 'no-cache';

    const cacheKey = `${client.defaults.baseURL || ''}:${url}:${JSON.stringify(config.params || {})}`;

    if (!shouldBypass) {
      const cached = memoryCache.get(cacheKey);
      if (cached && Date.now() < cached.expiresAt) {
        return Promise.resolve({
          ...cached.response,
          data: JSON.parse(JSON.stringify(cached.response.data)),
          __fromCache: true,
        });
      }

      if (inFlightRequests.has(cacheKey)) {
        const item = inFlightRequests.get(cacheKey);
        // TTL Guard 15 detik: jika in-flight request sudah lebih dari 15 detik, anggap basi dan jangan pakai!
        if (Date.now() - item.timestamp < DEFAULT_REQUEST_TIMEOUT) {
          return item.promise.then((res) => ({
            ...res,
            data: JSON.parse(JSON.stringify(res.data)),
            __deduped: true,
          }));
        } else {
          inFlightRequests.delete(cacheKey);
        }
      }
    }

    // Fungsi fetch dengan 1x auto-retry pada koneksi stale / socket drop
    const executeFetch = (isRetry = false) => {
      const requestConfig = isRetry
        ? {
            ...config,
            headers: {
              ...(config.headers || {}),
              'Cache-Control': 'no-cache',
            },
          }
        : config;

      return originalGet(url, requestConfig).catch((err) => {
        const isNetworkOrTimeout =
          err.code === 'ECONNABORTED' ||
          err.message?.includes('timeout') ||
          err.message?.includes('Network Error') ||
          err.response?.status === 502 ||
          err.response?.status === 503 ||
          err.response?.status === 504;

        if (!isRetry && isNetworkOrTimeout) {
          // Retry 1x otomatis dengan jeda 350ms
          return new Promise((resolve) => setTimeout(resolve, 350)).then(() =>
            executeFetch(true)
          );
        }
        throw err;
      });
    };

    const requestPromise = executeFetch(false)
      .then((response) => {
        if (!shouldBypass && response.status >= 200 && response.status < 300) {
          const ttl = config.ttl || getCacheTtl(url);
          memoryCache.set(cacheKey, {
            response: {
              data: response.data,
              status: response.status,
              statusText: response.statusText,
              headers: response.headers,
              config: response.config,
            },
            expiresAt: Date.now() + ttl,
          });
        }
        return response;
      })
      .finally(() => {
        inFlightRequests.delete(cacheKey);
      });

    if (!shouldBypass) {
      inFlightRequests.set(cacheKey, {
        promise: requestPromise,
        timestamp: Date.now(),
      });
    }

    return requestPromise;
  };

  ['post', 'put', 'patch', 'delete'].forEach((method) => {
    const originalMethod = client[method].bind(client);
    client[method] = async function (...args) {
      const res = await originalMethod(...args);
      // Setiap kali ada mutasi data, kosongkan cache GET agar UI selalu up-to-date
      memoryCache.clear();
      return res;
    };
  });
}

attachCacheAndDedup(api);
attachCacheAndDedup(legacyApi);

// =========================================================================
// Singleton Cached Branding
// =========================================================================
let brandingPromise = null;
let cachedBranding = null;

export async function fetchBrandingCached() {
  if (cachedBranding) {
    return { data: cachedBranding };
  }
  if (!brandingPromise) {
    brandingPromise = api
      .get('/branding')
      .then((res) => {
        cachedBranding = res.data;
        return res;
      })
      .catch((err) => {
        brandingPromise = null;
        throw err;
      });
  }
  return brandingPromise;
}

export default api;
