import api from './api';

const base = '/engineer';

export const engineerApi = {
  commandCenter: (mineOnly = false) =>
    api.get(`${base}/command-center/`, { params: { mine_only: mineOnly } }),

  listIssues: (params = {}) => api.get(`${base}/issues/`, { params }),
  createIssue: (data) => api.post(`${base}/issues/`, data),
  createIssueFromAnomaly: (anomalyId) => api.post(`${base}/issues/from-anomaly/${anomalyId}/`),
  updateIssue: (id, data) => api.patch(`${base}/issues/${id}/`, data),

  listMachines: () => api.get(`${base}/machines/`),
  getDossier: (machineId) => api.get(`${base}/machines/${machineId}/dossier/`),

  listNotes: (machineId) => api.get(`${base}/notes/`, { params: { machine_id: machineId } }),
  createNote: (data) => api.post(`${base}/notes/`, data),

  listTemplates: () => api.get(`${base}/inspection-templates/`),
  createTemplate: (data) => api.post(`${base}/inspection-templates/`, data),
  listInspections: (params = {}) => api.get(`${base}/inspections/`, { params }),
  createInspection: (data) => api.post(`${base}/inspections/`, data),
  uploadInspectionPhoto: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`${base}/inspections/${id}/photo/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  listSpareParts: (lowStockOnly = false) =>
    api.get(`${base}/spare-parts/`, { params: { low_stock_only: lowStockOnly } }),
  createSparePart: (data) => api.post(`${base}/spare-parts/`, data),
  updateSparePart: (id, data) => api.patch(`${base}/spare-parts/${id}/`, data),
  logSpareUsage: (id, data) => api.post(`${base}/spare-parts/${id}/usage/`, data),
  listSpareUsage: (id) => api.get(`${base}/spare-parts/${id}/usage/`),

  listCalculations: () => api.get(`${base}/calculations/`),
  createCalculation: (data) => api.post(`${base}/calculations/`, data),
  getCalculation: (id) => api.get(`${base}/calculations/${id}/`),
  runCalculation: (id, params = {}) => api.post(`${base}/calculations/${id}/run/`, { parameters: params }),
  updateCalculation: (id, data) => api.patch(`${base}/calculations/${id}/`, data),

  listMeetings: () => api.get(`${base}/meetings/`),
  createMeeting: (data) => api.post(`${base}/meetings/`, data),
  getMeeting: (id) => api.get(`${base}/meetings/${id}/`),

  listActionItems: (params = {}) => api.get(`${base}/action-items/`, { params }),
  createActionItem: (data) => api.post(`${base}/action-items/`, data),
  updateActionItem: (id, data) => api.patch(`${base}/action-items/${id}/`, data),

  listUsers: () => api.get(`${base}/users/`),
};

const DRAFT_KEY = 'engineer_inspection_drafts';

export function saveInspectionDraft(draft) {
  const drafts = JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]');
  const idx = drafts.findIndex((d) => d.localId === draft.localId);
  if (idx >= 0) drafts[idx] = draft;
  else drafts.push(draft);
  localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts));
}

export function getInspectionDrafts() {
  return JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]');
}

export function removeInspectionDraft(localId) {
  const drafts = getInspectionDrafts().filter((d) => d.localId !== localId);
  localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts));
}
