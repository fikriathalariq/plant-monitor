import React from "react"
import { useTable, flexRender, createCoreRowModel } from "@tanstack/react-table"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table"
import { Button } from "../../components/ui/button"
import { Input } from "../../components/ui/input"
import { ChevronLeft, ChevronRight, RefreshCw, Download, Printer, Filter } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu"
import { cn } from "../../lib/utils"

import { features } from "./data-table-features"

export function DataTable({
  columns,
  data,
  meta,
  loading,
  visitedRowId,
  tableRef,
}) {
  const [sorting, setSorting] = React.useState([
    { id: "batch_start", desc: true }
  ])
  const [columnFilters, setColumnFilters] = React.useState([])
  const [columnVisibility, setColumnVisibility] = React.useState({})
  const [rowSelection, setRowSelection] = React.useState({})
  const [pagination, setPagination] = React.useState({ pageIndex: 0, pageSize: 25 })
  const [scrolled, setScrolled] = React.useState(false)

  const handleScroll = (e) => {
    setScrolled(e.currentTarget.scrollTop > 0)
  }

  const table = useTable({
    features,
    data: data || [],
    columns,
    getCoreRowModel: createCoreRowModel(),
    getRowId: (row) => String(row.id),
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      pagination
    },
    initialState: {
      columnPinning: {
        start: ['select'],
        end: [],
      },
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    meta,
  })

  // Expose table instance to parent via tableRef without triggering re-render loops
  React.useEffect(() => {
    if (tableRef) {
      tableRef.current = table;
    }
  }, [tableRef, table]);

  // Scroll to visited row
  React.useEffect(() => {
    if (!loading && visitedRowId && data.length > 0) {
      const el = document.getElementById(`anomaly-row-${visitedRowId}`);
      if (el) {
        setTimeout(() => {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 150);
      }
    }
  }, [loading, visitedRowId, data.length]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white rounded-lg shadow-sm border border-gray-200">
      
      {/* Toolbar */}
      <div className="flex-none flex items-center py-4 px-4 bg-white border-b border-gray-200 no-print">
        <div className="flex-1"></div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="ml-auto h-9">
              Kolom <Filter className="ml-2 h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {table.getAllColumns().filter(col => col.getCanHide()).map(column => (
              <DropdownMenuCheckboxItem
                key={column.id}
                className="capitalize"
                checked={column.getIsVisible()}
                onCheckedChange={(value) => column.toggleVisibility(!!value)}
              >
                {typeof column.columnDef.header === 'string' ? column.columnDef.header : column.id.replace('_', ' ')}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Table Container */}
      <div 
        className="flex-1 min-h-0 overflow-auto relative custom-scrollbar"
        onScroll={handleScroll}
      >
        {loading && (
          <div className="absolute inset-0 bg-white/60 backdrop-blur-[1px] z-30 flex items-center justify-center no-print">
            <div className="bg-white px-5 py-3 rounded-xl shadow-lg border border-gray-100 flex items-center space-x-3">
              <RefreshCw className="w-5 h-5 text-indigo-500 animate-spin" />
              <span className="text-gray-700 font-medium text-sm">Memuat data...</span>
            </div>
          </div>
        )}

        <Table className="w-full divide-y divide-gray-200 border-separate border-spacing-0">
          <TableHeader 
            className={cn(
              "bg-white sticky top-0 z-20 transition-[box-shadow] duration-150 ease-in-out",
              "after:content-[''] after:absolute after:left-0 after:right-0 after:bottom-0 after:border-b after:border-gray-200",
              scrolled ? "shadow-sm" : "shadow-none"
            )}
          >
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const isPinned = header.column.getIsPinned();
                  return (
                    <TableHead 
                      key={header.id}
                      className={cn(
                        "px-3 py-3 text-left text-sm font-medium text-gray-900 align-middle",
                        isPinned ? "sticky z-10 bg-white shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]" : ""
                      )}
                      style={{
                        left: isPinned === 'start' ? `${header.column.getStart('start')}px` : undefined,
                        width: isPinned ? header.column.getSize() : undefined,
                        minWidth: isPinned ? header.column.getSize() : undefined,
                        maxWidth: isPinned ? header.column.getSize() : undefined,
                      }}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody className="bg-white">
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  id={`anomaly-row-${row.original.id}`}
                  data-state={row.getIsSelected() && "selected"}
                  tabIndex={0}
                  className={cn(
                    "transition-colors cursor-pointer group outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-inset",
                    row.getIsSelected()
                      ? "!bg-indigo-50 hover:!bg-indigo-100"
                      : "hover:bg-gray-50",
                    String(visitedRowId) === String(row.original.id) && !row.getIsSelected()
                      ? "bg-indigo-50/30"
                      : ""
                  )}
                  onClick={() => meta?.handleRowClick?.(row.original)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      meta?.handleRowClick?.(row.original);
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => {
                    const isPinned = cell.column.getIsPinned();
                    return (
                      <TableCell 
                        key={cell.id} 
                        className={cn(
                          "px-3 py-2 whitespace-nowrap align-middle border-b border-gray-100 text-sm text-gray-800",
                          isPinned ? "sticky z-10 bg-inherit shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]" : ""
                        )}
                        style={{
                          left: isPinned === 'start' ? `${cell.column.getStart('start')}px` : undefined,
                          width: isPinned ? cell.column.getSize() : undefined,
                          minWidth: isPinned ? cell.column.getSize() : undefined,
                          maxWidth: isPinned ? cell.column.getSize() : undefined,
                        }}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))
            ) : (
              !loading && (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="h-24 text-center text-gray-500"
                  >
                    Tidak ada data anomali yang sesuai filter.
                  </TableCell>
                </TableRow>
              )
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination Footer */}
      {!loading && table.getPrePaginatedRowModel().rows.length > 0 && (
        <div className="bg-white border-t border-gray-200 px-4 py-3 flex items-center justify-between flex-shrink-0 no-print">
          <div className="flex-1 text-sm text-gray-500">
            {table.getFilteredSelectedRowModel().rows.length} dari{" "}
            {table.getFilteredRowModel().rows.length} baris terpilih.
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
