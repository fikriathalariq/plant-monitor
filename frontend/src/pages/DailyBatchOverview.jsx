import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts';
import {
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Clock,
  Search,
  Layers,
  PlayCircle,
  CheckCircle2,
  Gauge,
  Inbox,
  X,
  Star,
} from 'lucide-react';
import {
  useGetDailyBatchOverviewQuery,
  useAddBatchFavoriteMutation,
  useRemoveBatchFavoriteMutation,
} from '../store/dailyBatchApi';

const SparklineTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="bg-white px-2 py-1.5 border border-gray-200 shadow-md rounded text-[11px] leading-tight">
      <div className="text-gray-500 font-medium">{point.time}</div>
      <div className="text-red-500 font-semibold">
        {point.temp != null ? `${Number(point.temp).toFixed(1)} °C` : '-'}
      </div>
    </div>
  );
};

const toDateInputValue = (d) => d.toISOString().slice(0, 10);

const shiftDate = (dateStr, days) => {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toDateInputValue(d);
};

const formatDateLabel = (dateStr) => {
  const d = new Date(`${dateStr}T00:00:00`);
  return d.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
};

const efficiencyTone = (eff) => {
  if (eff == null) return 'bg-gray-100 text-gray-500';
  if (eff >= 85) return 'bg-green-100 text-green-700';
  if (eff >= 60) return 'bg-amber-100 text-amber-700';
  return 'bg-red-100 text-red-700';
};

const accentBar = (b) => {
  if (b.is_running) return 'bg-blue-400';
  if (b.efficiency == null) return 'bg-gray-200';
  if (b.efficiency >= 85) return 'bg-green-400';
  if (b.efficiency >= 60) return 'bg-amber-400';
  return 'bg-red-400';
};

const StatCard = ({ icon: Icon, label, value, tone }) => (
  <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 flex items-center gap-3">
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${tone}`}>
      <Icon className="w-5 h-5" />
    </div>
    <div className="min-w-0">
      <p className="text-xs text-gray-500 truncate">{label}</p>
      <p className="text-lg font-bold text-gray-800 leading-tight">{value}</p>
    </div>
  </div>
);

const CardSkeleton = () => (
  <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 overflow-hidden">
    <div className="flex justify-between items-start mb-3">
      <div className="space-y-2 w-2/3">
        <div className="h-3.5 bg-gray-200 rounded animate-pulse w-1/2" />
        <div className="h-3 bg-gray-100 rounded animate-pulse w-3/4" />
      </div>
      <div className="h-5 w-12 bg-gray-100 rounded-full animate-pulse" />
    </div>
    <div className="h-16 bg-gray-50 rounded animate-pulse mb-3" />
    <div className="flex justify-between">
      <div className="h-3 bg-gray-100 rounded animate-pulse w-1/3" />
      <div className="h-3 bg-gray-100 rounded animate-pulse w-1/5" />
    </div>
  </div>
);

const STATUS_FILTERS = [
  { value: '', label: 'Semua' },
  { value: 'running', label: 'Berjalan' },
  { value: 'completed', label: 'Selesai' },
];

const DailyBatchOverview = () => {
  const today = toDateInputValue(new Date());
  const [date, setDate] = useState(today);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [sort, setSort] = useState('machine');
  const navigate = useNavigate();

  const queryParams = { date, page, sort };
  if (search) queryParams.search = search;
  if (status) queryParams.status = status;

  const { data, isLoading, isFetching, refetch } = useGetDailyBatchOverviewQuery(queryParams);
  const [addFavorite] = useAddBatchFavoriteMutation();
  const [removeFavorite] = useRemoveBatchFavoriteMutation();

  const toggleFavorite = async (e, batch) => {
    e.stopPropagation();
    try {
      if (batch.is_favorited) {
        await removeFavorite(batch.id).unwrap();
      } else {
        await addFavorite(batch.id).unwrap();
      }
    } catch (err) {
      console.error('Gagal mengubah favorit batch', err);
    }
  };

  const goToDate = (newDate) => {
    setDate(newDate);
    setPage(1);
  };

  const rangeLabel = useMemo(() => {
    if (!data) return '';
    const start = (page - 1) * 20 + 1;
    const end = Math.min(page * 20, data.total_matches);
    if (data.total_matches === 0) return '0 hasil';
    return `${start}-${end} dari ${data.total_matches} hasil`;
  }, [data, page]);

  return (
    <div className="p-4 sm:p-6 bg-gray-50 min-h-full pb-20 md:pb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">Ringkasan Batch Harian</h1>
          <p className="text-xs text-gray-400 capitalize">{formatDateLabel(date)}</p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={() => goToDate(shiftDate(date, -1))} className="p-2 rounded-md border border-gray-300 bg-white hover:bg-gray-50" title="Hari sebelumnya">
            <ChevronLeft className="w-4 h-4 text-gray-500" />
          </button>
          <input
            type="date"
            value={date}
            onChange={(e) => goToDate(e.target.value)}
            className="border border-gray-300 rounded-md text-sm px-2 py-1.5 bg-white"
          />
          <button onClick={() => goToDate(shiftDate(date, 1))} disabled={date >= today} className="p-2 rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed" title="Hari berikutnya">
            <ChevronRight className="w-4 h-4 text-gray-500" />
          </button>
          {date !== today && (
            <button onClick={() => goToDate(today)} className="text-xs font-medium text-blue-600 hover:text-blue-700 px-2 py-1.5 rounded-md hover:bg-blue-50">
              Hari ini
            </button>
          )}
          <button onClick={refetch} className="p-2 rounded-md border border-gray-300 bg-white hover:bg-gray-50" title="Muat ulang">
            <RefreshCw className={`w-4 h-4 text-gray-500 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <StatCard icon={Layers} label="Total Batch" value={data ? data.total_batches_today : '-'} tone="bg-indigo-50 text-indigo-600" />
        <StatCard icon={PlayCircle} label="Sedang Berjalan" value={data ? data.running_count : '-'} tone="bg-blue-50 text-blue-600" />
        <StatCard icon={CheckCircle2} label="Selesai" value={data ? data.completed_count : '-'} tone="bg-green-50 text-green-600" />
        <StatCard icon={Gauge} label="Rata-rata Efisiensi" value={data && data.avg_efficiency != null ? `${data.avg_efficiency}%` : '-'} tone="bg-amber-50 text-amber-600" />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-3 mb-4 flex flex-wrap gap-3 items-center justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Cari mesin, batch, atau program..."
              className="pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg w-64 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="flex items-center bg-gray-100 rounded-lg p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => { setStatus(f.value); setPage(1); }}
                className={`text-xs font-medium px-3 py-1.5 rounded-md transition-colors ${status === f.value ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setPage(1); }}
            className="text-sm border border-gray-200 rounded-lg px-2 py-2 text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="machine">Urutkan: Mesin</option>
            <option value="start_time">Urutkan: Waktu Mulai (Awal)</option>
            <option value="start_time_desc">Urutkan: Waktu Mulai (Terbaru)</option>
          </select>
          {data && <span className="text-xs text-gray-400 whitespace-nowrap">{rangeLabel}</span>}
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(data?.results || []).map((b) => (
            <div
              key={b.id}
              onClick={() => navigate(`/history/report/${b.id}?machine=${encodeURIComponent(b.machine_code || '')}&batch=${encodeURIComponent(b.batch_number || '')}`)}
              className={`relative bg-white rounded-xl shadow-sm border p-4 pl-5 cursor-pointer hover:shadow-md transition-all group overflow-hidden ${
                b.is_favorited ? 'border-amber-300 hover:border-amber-400' : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <span className={`absolute left-0 top-0 bottom-0 w-1.5 ${accentBar(b)}`} />

              <div className="flex justify-between items-start mb-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-bold text-gray-800 truncate">{b.machine_name}</p>
                    {b.is_running && (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-full shrink-0">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" /> Live
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 truncate">
                    Batch #{b.batch_number} &middot; {b.program_name || <span className="italic text-gray-300">Program belum diatur</span>}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                  {b.efficiency != null && (
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${efficiencyTone(b.efficiency)}`}>
                      {b.efficiency}%
                    </span>
                  )}
                  <button
                    type="button"
                    title={b.is_favorited ? 'Hapus dari favorit' : 'Tambah ke favorit'}
                    aria-label={b.is_favorited ? 'Hapus dari favorit' : 'Tambah ke favorit'}
                    onClick={(e) => toggleFavorite(e, b)}
                    className={`p-1.5 rounded-full transition-colors ${
                      b.is_favorited
                        ? 'text-amber-500 bg-amber-50 hover:bg-amber-100'
                        : 'text-gray-300 hover:text-amber-500 hover:bg-amber-50'
                    }`}
                  >
                    <Star className={`w-4 h-4 ${b.is_favorited ? 'fill-current' : ''}`} />
                  </button>
                </div>
              </div>

              <div className="h-16 -mx-1" onClick={(e) => e.stopPropagation()}>
                {b.sparkline && b.sparkline.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={b.sparkline}>
                      <Tooltip content={<SparklineTooltip />} cursor={false} />
                      <Line
                        type="monotone"
                        dataKey="temp"
                        name="Suhu"
                        stroke="#ef4444"
                        strokeWidth={1.5}
                        dot={false}
                        activeDot={{ r: 3, fill: '#ef4444', stroke: '#fff', strokeWidth: 1 }}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-[11px] text-gray-300">Tidak ada data suhu</div>
                )}
              </div>

              <div className="flex items-center justify-between text-xs text-gray-500 mt-2">
                <span className="flex items-center"><Clock className="w-3 h-3 mr-1" /> {b.start_time} &rarr; {b.end_time}</span>
                {b.loss_time != null && (
                  <span className={`font-medium ${b.loss_time > 0 ? 'text-red-500' : 'text-green-500'}`}>
                    {b.loss_time > 0 ? '+' : ''}{b.loss_time}m
                  </span>
                )}
              </div>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/history/report/${b.id}?machine=${encodeURIComponent(b.machine_code || '')}&batch=${encodeURIComponent(b.batch_number || '')}`);
                }}
                className="mt-3 w-full md:hidden flex items-center justify-center gap-1 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 active:bg-blue-100 border border-blue-100 rounded-lg py-2.5"
              >
                Lihat detail
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          ))}
          {(!data?.results || data.results.length === 0) && (
            <div className="col-span-full flex flex-col items-center justify-center text-gray-400 py-16">
              <Inbox className="w-10 h-10 mb-2 text-gray-300" />
              <p className="text-sm font-medium">Tidak ada batch ditemukan</p>
              <p className="text-xs text-gray-300 mt-1">Coba ubah tanggal, kata kunci, atau filter status.</p>
            </div>
          )}
        </div>
      )}

      {data && data.num_pages > 1 && (
        <div className="flex items-center justify-center gap-4 mt-6">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="p-2 rounded-full border border-gray-200 bg-white disabled:opacity-40">
            <ChevronLeft size={18} />
          </button>
          <span className="text-sm text-gray-600 font-medium">{data.page} / {data.num_pages}</span>
          <button onClick={() => setPage((p) => Math.min(data.num_pages, p + 1))} disabled={page === data.num_pages} className="p-2 rounded-full border border-gray-200 bg-white disabled:opacity-40">
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
};

export default DailyBatchOverview;
