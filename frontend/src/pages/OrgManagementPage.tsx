import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import {
  getLevels, listOrgUnits, listOrgRoles,
  createLevel, updateLevel, deleteLevel,
  createOrgUnit, updateOrgUnit, deleteOrgUnit,
  createOrgRole, updateOrgRole, deleteOrgRole,
  type HierarchyLevel, type OrgUnit, type OrgRole,
} from '@/features/org/api';

type Tab = 'levels' | 'units' | 'roles';

// ── Shared form modal ────────────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[var(--tx)]">{title}</h2>
          <button onClick={onClose} className="btn-ghost !p-1.5 rounded-lg">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Hierarchy Levels tab ──────────────────────────────────────────────────────

function LevelsTab() {
  const qc = useQueryClient();
  const { data: levels = [] } = useQuery({ queryKey: ['org-levels'], queryFn: getLevels });
  const [editing, setEditing] = useState<HierarchyLevel | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', level_order: 1 });

  const createMut = useMutation({
    mutationFn: () => createLevel({ name: form.name, level_order: form.level_order }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-levels'] }); setCreating(false); setForm({ name: '', level_order: 1 }); },
  });
  const updateMut = useMutation({
    mutationFn: () => updateLevel(editing!.id, { name: form.name, level_order: form.level_order }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-levels'] }); setEditing(null); },
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteLevel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['org-levels'] }),
  });

  const openCreate = () => { setForm({ name: '', level_order: (levels.length || 0) + 1 }); setCreating(true); };
  const openEdit = (lvl: HierarchyLevel) => { setEditing(lvl); setForm({ name: lvl.name, level_order: lvl.level_order }); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--tx-2)]">Configure the org hierarchy levels (e.g. Branch → Regional Office → Circle Office → Head Office).</p>
        <Button onClick={openCreate} className="h-8 text-xs">+ Add Level</Button>
      </div>
      <div className="card-sm !p-0 overflow-hidden">
        <table className="data-table w-full">
          <thead><tr><th>Order</th><th>Name</th><th>Active</th><th></th></tr></thead>
          <tbody>
            {levels.sort((a, b) => a.level_order - b.level_order).map(lvl => (
              <tr key={lvl.id}>
                <td className="w-16 text-center font-mono text-xs">{lvl.level_order}</td>
                <td className="font-medium text-[var(--tx)]">{lvl.name}</td>
                <td><span className={cn('pill', lvl.is_active ? 'pill-ok' : 'pill-neu')}>{lvl.is_active ? 'Active' : 'Inactive'}</span></td>
                <td className="text-right">
                  <button onClick={() => openEdit(lvl)} className="btn-ghost !py-1 !px-2 text-xs mr-1">Edit</button>
                  <button onClick={() => { if (confirm('Delete this level?')) deleteMut.mutate(lvl.id); }} className="btn-ghost !py-1 !px-2 text-xs text-[var(--err)]">Delete</button>
                </td>
              </tr>
            ))}
            {levels.length === 0 && <tr><td colSpan={4} className="text-center text-sm text-[var(--tx-3)] py-6">No levels yet</td></tr>}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <Modal title={creating ? 'Add Hierarchy Level' : 'Edit Hierarchy Level'} onClose={() => { setCreating(false); setEditing(null); }}>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Name
              <input className="input" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Regional Office" />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Level Order (1 = lowest)
              <input type="number" min={1} className="input" value={form.level_order} onChange={e => setForm(p => ({ ...p, level_order: +e.target.value }))} />
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="ghost" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</Button>
              <Button onClick={() => creating ? createMut.mutate() : updateMut.mutate()} disabled={!form.name.trim()}>
                {creating ? 'Create' : 'Save'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Org Units tab ─────────────────────────────────────────────────────────────

function UnitsTab() {
  const qc = useQueryClient();
  const { data: levels = [] } = useQuery({ queryKey: ['org-levels'], queryFn: getLevels });
  const [search, setSearch] = useState('');
  const [filterLevelId, setFilterLevelId] = useState('');
  const [editing, setEditing] = useState<OrgUnit | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<OrgUnit & { hierarchy_level_id: string }>>({});

  const { data: unitsRes } = useQuery({
    queryKey: ['org-units', search, filterLevelId],
    queryFn: () => listOrgUnits({ search: search || undefined, hierarchy_level_id: filterLevelId || undefined, per_page: 100 }),
  });
  const units = unitsRes?.data ?? [];

  const createMut = useMutation({
    mutationFn: () => createOrgUnit(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-units'] }); setCreating(false); setForm({}); },
  });
  const updateMut = useMutation({
    mutationFn: () => updateOrgUnit(editing!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-units'] }); setEditing(null); },
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteOrgUnit(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['org-units'] }),
  });

  const openCreate = () => { setForm({}); setCreating(true); };
  const openEdit = (u: OrgUnit) => { setEditing(u); setForm({ name: u.name, code: u.code, address: u.address ?? '', contact_email: u.contact_email ?? '', contact_phone: u.contact_phone ?? '', parent_id: u.parent_id ?? undefined, hierarchy_level_id: u.hierarchy_level_id }); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <input className="input h-8 text-xs w-52" placeholder="Search name or code…" value={search} onChange={e => setSearch(e.target.value)} />
        <select className="input h-8 text-xs w-44" value={filterLevelId} onChange={e => setFilterLevelId(e.target.value)}>
          <option value="">All levels</option>
          {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <Button onClick={openCreate} className="h-8 text-xs ml-auto">+ Add Unit</Button>
      </div>

      <div className="card-sm !p-0 overflow-hidden">
        <table className="data-table w-full">
          <thead><tr><th>Code</th><th>Name</th><th>Level</th><th>Parent</th><th>Active</th><th></th></tr></thead>
          <tbody>
            {units.map(u => (
              <tr key={u.id}>
                <td className="font-mono text-xs">{u.code}</td>
                <td className="font-medium text-[var(--tx)]">{u.name}</td>
                <td><span className="pill pill-info text-[10px]">{u.hierarchy_level}</span></td>
                <td className="text-xs text-[var(--tx-3)]">{u.parent_name ?? '—'}</td>
                <td><span className={cn('pill', u.is_active ? 'pill-ok' : 'pill-neu')}>{u.is_active ? 'Active' : 'Off'}</span></td>
                <td className="text-right">
                  <button onClick={() => openEdit(u)} className="btn-ghost !py-1 !px-2 text-xs mr-1">Edit</button>
                  <button onClick={() => { if (confirm('Deactivate this unit?')) deleteMut.mutate(u.id); }} className="btn-ghost !py-1 !px-2 text-xs text-[var(--err)]">Deactivate</button>
                </td>
              </tr>
            ))}
            {units.length === 0 && <tr><td colSpan={6} className="text-center text-sm text-[var(--tx-3)] py-6">No org units found</td></tr>}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <Modal title={creating ? 'Add Org Unit' : 'Edit Org Unit'} onClose={() => { setCreating(false); setEditing(null); }}>
          <div className="flex flex-col gap-3">
            {creating && (
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Hierarchy Level *
                <select className="input" value={form.hierarchy_level_id ?? ''} onChange={e => setForm(p => ({ ...p, hierarchy_level_id: e.target.value }))}>
                  <option value="">Select level…</option>
                  {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
            )}
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Unit Name *
                <input className="input" value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Mumbai Main Branch" />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Code * (unique)
                <input className="input uppercase" value={form.code ?? ''} onChange={e => setForm(p => ({ ...p, code: e.target.value.toUpperCase() }))} placeholder="e.g. 12345" />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Parent Unit
              <select className="input" value={form.parent_id ?? ''} onChange={e => setForm(p => ({ ...p, parent_id: e.target.value || undefined }))}>
                <option value="">None (top-level)</option>
                {units.filter(u => !editing || u.id !== editing.id).map(u => <option key={u.id} value={u.id}>{u.name} ({u.code})</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Address
              <input className="input" value={form.address ?? ''} onChange={e => setForm(p => ({ ...p, address: e.target.value }))} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Contact Email
                <input className="input" type="email" value={form.contact_email ?? ''} onChange={e => setForm(p => ({ ...p, contact_email: e.target.value }))} />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Contact Phone
                <input className="input" value={form.contact_phone ?? ''} onChange={e => setForm(p => ({ ...p, contact_phone: e.target.value }))} />
              </label>
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="ghost" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</Button>
              <Button onClick={() => creating ? createMut.mutate() : updateMut.mutate()} disabled={!form.name?.trim() || !form.code?.trim() || (creating && !form.hierarchy_level_id)}>
                {creating ? 'Create' : 'Save'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Org Roles tab ─────────────────────────────────────────────────────────────

function RolesTab() {
  const qc = useQueryClient();
  const { data: levels = [] } = useQuery({ queryKey: ['org-levels'], queryFn: getLevels });
  const [filterLevelId, setFilterLevelId] = useState('');
  const { data: roles = [] } = useQuery({
    queryKey: ['org-roles', filterLevelId],
    queryFn: () => listOrgRoles(filterLevelId || undefined),
  });
  const [editing, setEditing] = useState<OrgRole | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<OrgRole & { hierarchy_level_id: string }>>({});

  const createMut = useMutation({
    mutationFn: () => createOrgRole(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); setCreating(false); setForm({}); },
  });
  const updateMut = useMutation({
    mutationFn: () => updateOrgRole(editing!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); setEditing(null); },
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteOrgRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['org-roles'] }),
  });

  const openEdit = (r: OrgRole) => { setEditing(r); setForm({ name: r.name, role_order: r.role_order, can_manage_unit: r.can_manage_unit, can_manage_subtree: r.can_manage_subtree }); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <select className="input h-8 text-xs w-44" value={filterLevelId} onChange={e => setFilterLevelId(e.target.value)}>
          <option value="">All levels</option>
          {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <Button onClick={() => { setForm({ hierarchy_level_id: filterLevelId || undefined, role_order: 0 }); setCreating(true); }} className="h-8 text-xs ml-auto">+ Add Role</Button>
      </div>

      <div className="card-sm !p-0 overflow-hidden">
        <table className="data-table w-full">
          <thead><tr><th>Level</th><th>Role Name</th><th>Order</th><th>Manage Unit</th><th>Manage Subtree</th><th></th></tr></thead>
          <tbody>
            {roles.map(r => (
              <tr key={r.id}>
                <td><span className="pill pill-info text-[10px]">{r.hierarchy_level}</span></td>
                <td className="font-medium text-[var(--tx)]">{r.name}</td>
                <td className="text-center text-xs text-[var(--tx-2)]">{r.role_order}</td>
                <td className="text-center"><span className={cn('pill', r.can_manage_unit ? 'pill-ok' : 'pill-neu')}>{r.can_manage_unit ? 'Yes' : 'No'}</span></td>
                <td className="text-center"><span className={cn('pill', r.can_manage_subtree ? 'pill-warn' : 'pill-neu')}>{r.can_manage_subtree ? 'Yes' : 'No'}</span></td>
                <td className="text-right">
                  <button onClick={() => openEdit(r)} className="btn-ghost !py-1 !px-2 text-xs mr-1">Edit</button>
                  <button onClick={() => { if (confirm('Delete this role?')) deleteMut.mutate(r.id); }} className="btn-ghost !py-1 !px-2 text-xs text-[var(--err)]">Delete</button>
                </td>
              </tr>
            ))}
            {roles.length === 0 && <tr><td colSpan={6} className="text-center text-sm text-[var(--tx-3)] py-6">No roles found</td></tr>}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <Modal title={creating ? 'Add Org Role' : 'Edit Org Role'} onClose={() => { setCreating(false); setEditing(null); }}>
          <div className="flex flex-col gap-3">
            {creating && (
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Hierarchy Level *
                <select className="input" value={form.hierarchy_level_id ?? ''} onChange={e => setForm(p => ({ ...p, hierarchy_level_id: e.target.value }))}>
                  <option value="">Select level…</option>
                  {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
            )}
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Role Name *
                <input className="input" value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Branch Head" />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Role Order
                <input type="number" min={0} className="input" value={form.role_order ?? 0} onChange={e => setForm(p => ({ ...p, role_order: +e.target.value }))} />
              </label>
            </div>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm text-[var(--tx-2)]">
                <input type="checkbox" checked={!!form.can_manage_unit} onChange={e => setForm(p => ({ ...p, can_manage_unit: e.target.checked }))} className="h-4 w-4" />
                Can manage own unit
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--tx-2)]">
                <input type="checkbox" checked={!!form.can_manage_subtree} onChange={e => setForm(p => ({ ...p, can_manage_subtree: e.target.checked }))} className="h-4 w-4" />
                Can manage subtree
              </label>
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="ghost" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</Button>
              <Button onClick={() => creating ? createMut.mutate() : updateMut.mutate()} disabled={!form.name?.trim() || (creating && !form.hierarchy_level_id)}>
                {creating ? 'Create' : 'Save'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function OrgManagementPage() {
  const [tab, setTab] = useState<Tab>('units');

  const tabs: { key: Tab; label: string }[] = [
    { key: 'units',  label: 'Org Units' },
    { key: 'levels', label: 'Hierarchy Levels' },
    { key: 'roles',  label: 'Org Roles' },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">Org Management</h1>
        <p className="text-xs text-[var(--tx-3)] mt-0.5">Configure the banking hierarchy, org units, and per-level roles.</p>
      </div>

      <div className="flex gap-1 p-1 card-sm !p-1 w-fit">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'px-4 py-1.5 text-sm font-medium rounded-lg transition-all',
              tab === t.key
                ? 'bg-[var(--brand)] text-white shadow-sm'
                : 'text-[var(--tx-2)] hover:text-[var(--tx)] hover:bg-[var(--inset)]',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'levels' && <LevelsTab />}
      {tab === 'units'  && <UnitsTab />}
      {tab === 'roles'  && <RolesTab />}
    </div>
  );
}
