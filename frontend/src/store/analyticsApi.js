import { apiSlice } from './apiSlice';

export const analyticsApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getAnalyticsMachines: builder.query({
      query: () => '/analytics/machines',
      providesTags: ['Analytics'],
    }),
    getAnalyticsMulti: builder.query({
      query: (params) => ({ url: '/analytics/graph-multi', params }),
    }),
    getSteamHtoAnalytics: builder.query({
      query: (params) => ({ url: '/analytics/steam-hto', params }),
    }),
    getSnapshotDetail: builder.query({
      query: (params) => ({ url: '/analytics/snapshot-detail', params }),
    }),
  }),
});

export const {
  useGetAnalyticsMachinesQuery,
  useGetAnalyticsMultiQuery,
  useGetSteamHtoAnalyticsQuery,
  useGetSnapshotDetailQuery,
} = analyticsApi;
