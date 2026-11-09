import { apiSlice } from './apiSlice';

export const machinesApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getManualMachines: builder.query({
      query: () => '/machines/manual',
      providesTags: ['ManualMachines'],
    }),
    updateManualMachines: builder.mutation({
      query: (body) => ({
        url: '/machines/manual',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['ManualMachines'],
    }),
  }),
});

export const { useGetManualMachinesQuery, useUpdateManualMachinesMutation } = machinesApi;
