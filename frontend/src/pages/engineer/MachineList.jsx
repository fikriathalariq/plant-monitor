import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { engineerApi } from '../../lib/engineerApi';

export default function MachineList() {
  const [machines, setMachines] = useState([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    engineerApi.listMachines().then((res) => setMachines(res.data.data || []));
  }, []);

  const filtered = machines.filter(
    (m) => m.code.toLowerCase().includes(search.toLowerCase())
      || m.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Machine Dossier</h2>
      <input
        className="w-full border rounded-lg px-3 py-2"
        placeholder="Cari mesin..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="grid gap-2">
        {filtered.map((m) => (
          <Link
            key={m.id}
            to={`/engineer/machines/${m.id}`}
            className="bg-white border rounded-xl p-4 hover:border-blue-300 hover:shadow-sm transition-all flex justify-between items-center"
          >
            <div>
              <p className="font-bold text-lg">{m.code}</p>
              <p className="text-sm text-slate-500">{m.name}</p>
            </div>
            <span className="text-blue-600 text-sm">Buka →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
