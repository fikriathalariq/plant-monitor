import { apiSlice } from './apiSlice';

export const performanceApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getPerformanceSummary: builder.query({
      query: (params) => ({ url: '/performance/summary', params }),
      providesTags: ['Performance'],
    }),
  }),
});

export const { useGetPerformanceSummaryQuery } = performanceApi;
