import { apiSlice } from './apiSlice';

export const planningApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getPlanningMeta: builder.query({
      query: () => '/planning/meta',
    }),
    listPlans: builder.query({
      query: (shiftDate) => ({
        url: '/planning/plans',
        params: shiftDate ? { shift_date: shiftDate } : {},
      }),
      providesTags: ['ProductionPlanning'],
    }),
    getPlan: builder.query({
      query: (id) => `/planning/plans/${id}`,
      providesTags: (result, error, id) => [{ type: 'ProductionPlanning', id }],
    }),
    createPlan: builder.mutation({
      query: (body) => ({
        url: '/planning/plans',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
    updatePlan: builder.mutation({
      query: ({ id, ...body }) => ({
        url: `/planning/plans/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (result, error, { id }) => [
        'ProductionPlanning',
        { type: 'ProductionPlanning', id },
      ],
    }),
    publishPlan: builder.mutation({
      query: (id) => ({
        url: `/planning/plans/${id}/publish`,
        method: 'POST',
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
    deletePlan: builder.mutation({
      query: (id) => ({
        url: `/planning/plans/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
    duplicatePlan: builder.mutation({
      query: ({ id, ...body }) => ({
        url: `/planning/plans/${id}/duplicate`,
        method: 'POST',
        body,
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
    // Edit/hapus SATU batch lintas-plan by id — dipakai utk batch "lanjutan" (continuation)
    // yang secara asal milik plan HARI SEBELUMNYA. Invalidasi broad karena plan sumber & plan
    // yang sedang dibuka keduanya perlu refetch. Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
    patchBatch: builder.mutation({
      query: ({ id, ...body }) => ({
        url: `/planning/batches/${id}`,
        method: 'PATCH',
        body,
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
    deleteBatch: builder.mutation({
      query: ({ id, version }) => ({
        url: `/planning/batches/${id}`,
        method: 'DELETE',
        params: { version },
      }),
      invalidatesTags: ['ProductionPlanning'],
    }),
  }),
});

export const {
  useGetPlanningMetaQuery,
  useListPlansQuery,
  useGetPlanQuery,
  useLazyGetPlanQuery,
  useCreatePlanMutation,
  useUpdatePlanMutation,
  usePublishPlanMutation,
  useDeletePlanMutation,
  useDuplicatePlanMutation,
  usePatchBatchMutation,
  useDeleteBatchMutation,
} = planningApi;
