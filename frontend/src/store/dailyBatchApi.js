import { apiSlice } from './apiSlice';

export const dailyBatchApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getDailyBatchOverview: builder.query({
      query: (params) => ({ url: '/report/daily-batch-overview', params }),
      providesTags: ['DailyBatchOverview'],
    }),
    addBatchFavorite: builder.mutation({
      query: (processId) => ({
        url: '/report/batch-favorites',
        method: 'POST',
        body: { process_id: processId },
      }),
      invalidatesTags: ['DailyBatchOverview'],
    }),
    removeBatchFavorite: builder.mutation({
      query: (processId) => ({
        url: `/report/batch-favorites/${processId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['DailyBatchOverview'],
    }),
  }),
});

export const {
  useGetDailyBatchOverviewQuery,
  useAddBatchFavoriteMutation,
  useRemoveBatchFavoriteMutation,
} = dailyBatchApi;
