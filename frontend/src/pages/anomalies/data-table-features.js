import {
  tableFeatures,
  columnFilteringFeature,
  columnVisibilityFeature,
  rowSelectionFeature,
  rowPaginationFeature,
  rowSortingFeature,
  columnPinningFeature,
  columnSizingFeature,
  createFilteredRowModel,
  createSortedRowModel,
  createPaginatedRowModel,
  filterFn_includesString,
  sortFn_alphanumeric,
  sortFn_text
} from '@tanstack/react-table'

export const features = tableFeatures({
  columnFilteringFeature,
  columnVisibilityFeature,
  rowSelectionFeature,
  rowPaginationFeature,
  rowSortingFeature,
  columnPinningFeature,
  columnSizingFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString },
  sortFns: { alphanumeric: sortFn_alphanumeric, text: sortFn_text },
})
