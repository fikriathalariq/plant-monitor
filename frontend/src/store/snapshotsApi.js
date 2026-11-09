import { apiSlice } from './apiSlice';

export const snapshotsApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getSnapshotMeta: builder.query({
      query: () => '/snapshots/meta',
    }),
    getSnapshotHistory: builder.query({
      query: (params) => ({ url: '/snapshots/history', params }),
      providesTags: ['SnapshotHistory'],
    }),
    getSnapshotTimeline: builder.query({
      query: ({ date, groups, machines }) => ({
        url: '/snapshots/timeline',
        params: {
          date,
          ...(groups ? { groups } : {}),
          ...(machines ? { machines } : {}),
        },
      }),
      serializeQueryArgs: ({ queryArgs }) => (
        `timeline-${queryArgs.date || 'current'}-${queryArgs.groups || ''}-${queryArgs.machines || ''}`
      ),
      providesTags: ['SnapshotHistory'],
    }),
  }),
});

export const { useGetSnapshotMetaQuery, useGetSnapshotHistoryQuery, useGetSnapshotTimelineQuery } = snapshotsApi;
