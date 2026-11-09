import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { API_BASE_URL, triggerUnauthorized, DEFAULT_REQUEST_TIMEOUT } from '../lib/api';

const rawBaseQuery = fetchBaseQuery({
  baseUrl: API_BASE_URL,
  credentials: 'include',
  timeout: DEFAULT_REQUEST_TIMEOUT || 15000,
});

// Custom baseQuery dengan penanganan sesi expired (401), jebakan HTML login redirect,
// dan 1x auto-retry pada koneksi socket stale / timeout setelah tab idle
const baseQueryWithReauth = async (args, api, extraOptions) => {
  let result = await rawBaseQuery(args, api, extraOptions);

  // Jika timeout atau fetch error (misal socket drop saat laptop baru wake up), coba 1x lagi
  if (result.error && (result.error.status === 'FETCH_ERROR' || result.error.status === 'TIMEOUT_ERROR')) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    result = await rawBaseQuery(args, api, extraOptions);
  }

  // Deteksi status 401 Unauthorized
  const isUnauthorized = result.error?.status === 401;

  // Deteksi jika server mengembalikan halaman HTML Login (PARSING_ERROR karena HTML di-parse sebagai JSON)
  const isHtmlRedirect =
    result.error?.status === 'PARSING_ERROR' &&
    typeof result.error?.data === 'string' &&
    (result.error.data.includes('<!DOCTYPE') ||
      result.error.data.includes('<html') ||
      result.error.data.includes('id="login-form"'));

  if (isUnauthorized || isHtmlRedirect) {
    triggerUnauthorized();
  }

  return result;
};

// RTK Query base API. Halaman baru (Manual Machine Usage, Snapshot History,
// Performance Summary, Analytics/Grafik, Daily Batch Overview) menggunakan
// slice ini agar mendapat caching, dedup request, dan polling terkelola.
// Halaman lama tetap memakai axios langsung untuk saat ini (migrasi bertahap).
export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['ManualMachines', 'SnapshotHistory', 'Performance', 'Analytics', 'DailyBatchOverview', 'ProductionPlanning', 'ChatContacts', 'ChatMessages', 'ChatUnread'],
  keepUnusedDataFor: 300, // 5 menit client-side cache agar navigasi antar halaman terasa instan
  refetchOnFocus: false,
  refetchOnReconnect: true,
  endpoints: () => ({}),
});
