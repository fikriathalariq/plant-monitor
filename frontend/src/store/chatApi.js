import { apiSlice } from './apiSlice';

export const chatApi = apiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getChatContacts: builder.query({
      query: () => '/chat/contacts',
      providesTags: ['ChatContacts'],
    }),
    getChatUnreadSummary: builder.query({
      query: () => '/chat/unread-summary',
      providesTags: ['ChatUnread'],
    }),
    getChatMessages: builder.query({
      query: ({ otherUserId, afterId = 0 }) => `/chat/messages/${otherUserId}?after_id=${afterId}`,
      providesTags: (result, error, { otherUserId }) => [{ type: 'ChatMessages', id: otherUserId }],
    }),
    sendChatMessage: builder.mutation({
      query: ({ otherUserId, ...body }) => ({
        url: `/chat/messages/${otherUserId}`,
        method: 'POST',
        body,
      }),
      invalidatesTags: (result, error, { otherUserId }) => [
        { type: 'ChatMessages', id: otherUserId },
        'ChatContacts',
        'ChatUnread',
      ],
    }),
    acknowledgeMessage: builder.mutation({
      query: (messageId) => ({
        url: `/chat/messages/${messageId}/acknowledge`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, messageId) => ['ChatMessages'],
    }),
    getMachineSnapshot: builder.query({
      query: (machineCode) => `/chat/machine-snapshot/${machineCode}`,
    }),
    getActiveMachinesList: builder.query({
      query: () => '/chat/machine-list',
    }),
  }),
});

export const {
  useGetChatContactsQuery,
  useGetChatUnreadSummaryQuery,
  useGetChatMessagesQuery,
  useSendChatMessageMutation,
  useAcknowledgeMessageMutation,
  useLazyGetMachineSnapshotQuery,
  useGetActiveMachinesListQuery,
} = chatApi;
