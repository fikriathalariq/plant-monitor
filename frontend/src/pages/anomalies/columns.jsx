import React from "react"
import { createColumnHelper } from "@tanstack/react-table"
import { ChevronsUpDown, MoreVertical, CheckCircle, Info, AlertTriangle, ArrowUp, ArrowDown, Filter, Search } from "lucide-react"
import { Button } from "../../components/ui/button"
import { Checkbox } from "../../components/ui/checkbox"
import { Input } from "../../components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu"

const columnHelper = createColumnHelper()

const DataTableColumnHeader = ({ column, title, table }) => {
  const canSort = column.getCanSort()
  const canFilter = column.getCanFilter()

  const [isOpen, setIsOpen] = React.useState(false)
  const [searchValue, setSearchValue] = React.useState("")
  
  const filterValue = column.getFilterValue()
  const isSorted = column.getIsSorted()

  const formatValue = React.useMemo(() => column.columnDef.meta?.filterValueFormatter || (val => String(val)), [column.columnDef.meta?.filterValueFormatter]);

  const uniqueValues = React.useMemo(() => {
    if (!canFilter) return [];
    const values = new Set()
    table.getCoreRowModel().rows.forEach(row => {
      let val = row.getValue(column.id)
      if (Array.isArray(val)) {
        val.forEach(v => { if (v != null) values.add(v) })
      } else if (val !== undefined && val !== null && val !== '') {
        values.add(val)
      }
    })
    return Array.from(values).sort((a, b) => {
      const aFormatted = formatValue(a);
      const bFormatted = formatValue(b);
      return aFormatted.localeCompare(bFormatted, undefined, { numeric: true });
    })
  }, [table.getCoreRowModel().rows, column.id, formatValue, canFilter])

  if (!canSort && !canFilter) {
    return <div className="text-sm font-medium text-gray-900 px-2 py-1.5">{title}</div>
  }

  const filteredUniqueValues = uniqueValues.filter(v => 
    formatValue(v).toLowerCase().includes(searchValue.toLowerCase())
  )

  const isAllSelected = filterValue === undefined || (Array.isArray(filterValue) && filterValue.length === uniqueValues.length)
  const isSomeSelected = Array.isArray(filterValue) && filterValue.length > 0 && filterValue.length < uniqueValues.length

  const toggleAll = () => {
    if (isAllSelected) {
      column.setFilterValue([])
    } else {
      column.setFilterValue(undefined)
    }
  }

  const toggleValue = (val) => {
    const current = filterValue === undefined ? uniqueValues : filterValue
    if (current.includes(val)) {
      const next = current.filter(v => v !== val)
      column.setFilterValue(next)
    } else {
      const next = [...current, val]
      if (next.length === uniqueValues.length) {
        column.setFilterValue(undefined)
      } else {
        column.setFilterValue(next)
      }
    }
  }

  return (
    <div className="flex items-center space-x-2">
      <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex items-center justify-between w-full hover:bg-gray-50 px-2 py-1.5 h-full -ml-2 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors data-[state=open]:bg-gray-100"
          >
            <span className="text-sm font-medium text-gray-900">{title}</span>
            <div className="flex items-center justify-center w-6 h-6 rounded-md">
              {isSorted === "asc" ? (
                <ArrowUp className="h-4 w-4 text-indigo-600" />
              ) : isSorted === "desc" ? (
                <ArrowDown className="h-4 w-4 text-indigo-600" />
              ) : (filterValue && filterValue.length > 0) ? (
                <Filter className="h-4 w-4 text-indigo-600 fill-indigo-100" />
              ) : (
                <ChevronsUpDown className="h-4 w-4 text-gray-400 stroke-[1.5]" />
              )}
            </div>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-60 p-2 shadow-xl border-gray-200" onClick={(e) => e.stopPropagation()}>
          {column.getCanSort() && (
            <>
              <DropdownMenuItem onClick={() => column.toggleSorting(false)} className="text-xs cursor-pointer">
                <ArrowUp className="mr-2 h-3.5 w-3.5 text-gray-500" />
                Sort A to Z
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => column.toggleSorting(true)} className="text-xs cursor-pointer">
                <ArrowDown className="mr-2 h-3.5 w-3.5 text-gray-500" />
                Sort Z to A
              </DropdownMenuItem>
              {isSorted && (
                <DropdownMenuItem onClick={() => column.clearSorting()} className="text-xs cursor-pointer">
                  <ChevronsUpDown className="mr-2 h-3.5 w-3.5 text-gray-500" />
                  Clear Sort
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
            </>
          )}

          {column.getCanFilter() && (
            <div className="flex flex-col">
              <div className="relative mb-2">
                <Search className="absolute left-2 top-2 h-3.5 w-3.5 text-gray-400" />
                <Input 
                  placeholder="Search filter..." 
                  value={searchValue}
                  onChange={(e) => setSearchValue(e.target.value)}
                  className="h-8 pl-8 text-xs rounded-sm border-gray-300"
                />
              </div>
              <div className="max-h-48 overflow-y-auto custom-scrollbar px-1">
                <div className="flex items-center space-x-2 py-1">
                  <Checkbox 
                    id={`all-${column.id}`} 
                    checked={isAllSelected ? true : isSomeSelected ? "indeterminate" : false} 
                    onCheckedChange={toggleAll}
                    className="h-3.5 w-3.5"
                  />
                  <label htmlFor={`all-${column.id}`} className="text-xs font-medium leading-none cursor-pointer text-gray-700">
                    (Select All)
                  </label>
                </div>
                {filteredUniqueValues.map((val, idx) => {
                  const isChecked = isAllSelected || (filterValue && filterValue.includes(val))
                  return (
                    <div key={`${val}-${idx}`} className="flex items-center space-x-2 py-1">
                      <Checkbox 
                        id={`filter-${column.id}-${idx}`} 
                        checked={isChecked} 
                        onCheckedChange={() => toggleValue(val)}
                        className="h-3.5 w-3.5"
                      />
                      <label htmlFor={`filter-${column.id}-${idx}`} className="text-xs leading-none cursor-pointer text-gray-600 truncate flex-1">
                        {formatValue(val)}
                      </label>
                    </div>
                  )
                })}
                {filteredUniqueValues.length === 0 && (
                  <div className="text-xs text-gray-400 text-center py-2">No matches</div>
                )}
              </div>
              {filterValue && filterValue.length > 0 && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => column.setFilterValue(undefined)} className="text-xs cursor-pointer justify-center text-indigo-600 font-medium">
                    Clear Filter
                  </DropdownMenuItem>
                </>
              )}
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

const multiSelectFilterFn = (row, columnId, filterValue) => {
  if (filterValue === undefined) return true; // (Select All) state
  if (Array.isArray(filterValue) && filterValue.length === 0) return false; // None selected

  const rowValue = row.getValue(columnId);
  if (Array.isArray(rowValue)) {
    return rowValue.some(v => filterValue.includes(v));
  }
  return filterValue.includes(rowValue);
}

multiSelectFilterFn.autoRemove = (val) => val === undefined;

const formatNumber = (val) => {
  if (val === undefined || val === null || val === '-' || val === '') return '-'
  const num = Number(val)
  return Number.isNaN(num) ? '-' : num.toFixed(1)
}

const checkAnomalyHighlight = (types, metricKey) => {
  if (!types || types.length === 0) return false
  const rules = {
    suhu: ['Suhu', 'Suhu Ekstrem (>25°C)', 'Suhu Awal Tinggi (>60°C)', 'Suhu Awal Tinggi'],
    heat: ['Heat', 'Re-Heating (≥2x Naik)', 'Reheating', 'Jeda Heating'],
    keep: ['Hold', 'Keep', 'Over-Holding (>8m)', 'Over-Holding'],
    cool: ['Cool', 'Re-Heating (≥2x Naik)', 'Reheating', 'Stagnasi Cooling', 'Cooling Lambat', 'Pasca-Cooling (>45m)', 'Pasca-Cooling >45m']
  }
  return rules[metricKey]?.some(r => types.includes(r))
}

const renderMetricCell = (actual, types, metricKey) => {
  const isAnomalous = checkAnomalyHighlight(types, metricKey)
  return (
    <div className={`text-[12px] px-1 py-0.5 rounded text-center w-full ${isAnomalous ? 'text-red-600 font-bold bg-red-50' : 'text-gray-900 font-medium'}`}>
      {formatNumber(actual)}
    </div>
  )
}

// Custom hook-like behavior needs to be injected or we pass callbacks via meta.
// In tanstack table, we can pass custom functions via `table.options.meta`.
export const columns = [
  columnHelper.display({
    id: "select",
    header: ({ table }) => (
      <div onClick={(e) => e.stopPropagation()} className="px-1 flex items-center justify-center">
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected() ||
            (table.getIsSomePageRowsSelected() && "indeterminate")
          }
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      </div>
    ),
    cell: ({ row }) => (
      <div onClick={(e) => e.stopPropagation()} className="px-1 flex items-center justify-center">
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      </div>
    ),
    enableSorting: false,
    enableColumnFilter: false,
    enableHiding: false,
    size: 40,
  }),
  columnHelper.accessor("batch_start", {
    filterFn: multiSelectFilterFn,
    meta: {
      filterValueFormatter: (val) => val ? new Date(val).toLocaleString('id-ID', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }) : '-'
    },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Waktu Start" table={table} />,
    cell: ({ row }) => {
      const date = row.getValue("batch_start")
      return (
        <div className="text-xs font-medium text-gray-600">
          {date ? new Date(date).toLocaleString('id-ID', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }) : '-'}
        </div>
      )
    },
    sortingFn: "datetime",
  }),
  columnHelper.accessor(row => `${row.machine_code} B#${row.batch_number}`, {
    id: "machine_batch",
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Batch #ID" table={table} />,
    cell: ({ row }) => (
      <div className="flex items-center space-x-1.5">
        <span className="text-[11px] font-bold text-gray-800 bg-gray-100 px-1.5 py-0.5 rounded">{row.original.machine_code}</span>
        <span className="text-[11px] font-bold text-indigo-600">B#{row.original.batch_number}</span>
      </div>
    ),
  }),
  columnHelper.accessor("program_name", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Program" table={table} />,
    cell: ({ row }) => <div className="text-xs text-gray-700 truncate max-w-[120px]" title={row.getValue("program_name")}>{row.getValue("program_name")}</div>
  }),
  columnHelper.accessor("artikel_kain", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Artikel" table={table} />,
    cell: ({ row }) => <div className="truncate max-w-[120px]" title={row.getValue("artikel_kain")}>{row.getValue("artikel_kain")}</div>
  }),
  columnHelper.accessor("nomor_order", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="PO" table={table} />,
    cell: ({ row }) => <div className="truncate">{row.getValue("nomor_order")}</div>
  }),
  columnHelper.accessor("batch_kain", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Batch Kain" table={table} />,
    cell: ({ row }) => <div className="truncate">{row.getValue("batch_kain")}</div>
  }),
  columnHelper.accessor("jenis_proses", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Proses" table={table} />,
    cell: ({ row }) => <div className="truncate">{row.getValue("jenis_proses")}</div>
  }),
  columnHelper.accessor("anomaly_types", {
    filterFn: multiSelectFilterFn,
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Tipe Analisis" table={table} />,
    cell: ({ row }) => {
      const types = row.getValue("anomaly_types") || [];
      if (types.length === 0) return <span className="text-gray-400">-</span>;
      return (
        <div className="flex flex-wrap gap-1">
          {types.map((t, i) => (
            <span key={i} className="text-xs font-medium bg-red-50 text-red-600 px-1.5 py-0.5 rounded border border-red-100">{t}</span>
          ))}
        </div>
      )
    }
  }),
  // Metrics Columns
  columnHelper.accessor(row => row.details?.actuals?.suhu, {
    id: "suhu_actual",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Max Temp" table={table} />,
    cell: ({ row }) => renderMetricCell(row.getValue("suhu_actual"), row.original.anomaly_types, 'suhu')
  }),
  columnHelper.accessor(row => row.details?.ideals?.suhu, {
    id: "suhu_ideal",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Max (Idl)" table={table} />,
    cell: ({ row }) => <div className="text-sm text-gray-500 w-full">{formatNumber(row.getValue("suhu_ideal"))}</div>
  }),

  columnHelper.accessor(row => row.details?.actuals?.heat, {
    id: "heat_actual",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Heat" table={table} />,
    cell: ({ row }) => renderMetricCell(row.getValue("heat_actual"), row.original.anomaly_types, 'heat')
  }),
  columnHelper.accessor(row => row.details?.ideals?.heat, {
    id: "heat_ideal",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Heat (Idl)" table={table} />,
    cell: ({ row }) => <div className="text-sm text-gray-500 w-full">{formatNumber(row.getValue("heat_ideal"))}</div>
  }),

  columnHelper.accessor(row => row.details?.actuals?.keep, {
    id: "keep_actual",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Hold" table={table} />,
    cell: ({ row }) => renderMetricCell(row.getValue("keep_actual"), row.original.anomaly_types, 'keep')
  }),
  columnHelper.accessor(row => row.details?.ideals?.keep, {
    id: "keep_ideal",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Hold (Idl)" table={table} />,
    cell: ({ row }) => <div className="text-sm text-gray-500 w-full">{formatNumber(row.getValue("keep_ideal"))}</div>
  }),

  columnHelper.accessor(row => row.details?.actuals?.cool, {
    id: "cool_actual",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Cool" table={table} />,
    cell: ({ row }) => renderMetricCell(row.getValue("cool_actual"), row.original.anomaly_types, 'cool')
  }),
  columnHelper.accessor(row => row.details?.ideals?.cool, {
    id: "cool_ideal",
    filterFn: multiSelectFilterFn,
    meta: { filterValueFormatter: formatNumber },
    header: ({ column, table }) => <DataTableColumnHeader column={column} title="Cool (Idl)" table={table} />,
    cell: ({ row }) => <div className="text-sm text-gray-500 w-full">{formatNumber(row.getValue("cool_ideal"))}</div>
  }),

  // Actions Column
  columnHelper.display({
    id: "actions",
    header: "Aksi",
    enableColumnFilter: false,
    cell: ({ row, table }) => {
      const a = row.original
      const meta = table.options.meta

      return (
        <div onClick={(e) => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreVertical className="h-4 w-4 text-gray-400" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {a.is_resolved ? (
                <div className="px-3 py-2 text-[11px] text-gray-500 w-40">
                  Diselesaikan dengan aksi: <strong className="text-gray-700 block mt-1">{a.resolved_action}</strong>
                </div>
              ) : (
                <>
                  <DropdownMenuItem onClick={() => meta?.openActionModal(a, 'SOLVE')} className="text-emerald-700 focus:bg-emerald-50 font-medium cursor-pointer">
                    <CheckCircle className="mr-2 h-4 w-4" /> Selesai (Fixed)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => meta?.openActionModal(a, 'INVALIDATE')} className="text-amber-700 focus:bg-amber-50 font-medium cursor-pointer">
                    <Info className="mr-2 h-4 w-4" /> Bukan Masalah
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => meta?.openActionModal(a, 'UNLINK')} className="text-rose-700 focus:bg-rose-50 font-medium cursor-pointer">
                    <AlertTriangle className="mr-2 h-4 w-4" /> Unlink Batch
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )
    },
  }),
]
