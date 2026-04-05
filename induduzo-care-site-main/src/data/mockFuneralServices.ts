import type { FuneralArrangement } from '@/types';

export const mockFuneralArrangement: FuneralArrangement | null = {
  id: 'FUN-2026-0001',
  claimCaseId: 'CLM-2026-0001',
  caseManager: 'Thandi Mkhize',
  caseManagerPhone: '082 111 2233',
  venue: 'Edendale Community Hall',
  date: '2026-04-12',
  time: '09:00',
  status: 'planning',
  nextStep: 'Confirm venue booking and catering arrangements',
  items: [
    { id: 'FI-001', category: 'Transport', description: 'Hearse and family vehicle from Edendale mortuary to venue', status: 'confirmed' },
    { id: 'FI-002', category: 'Coffin', description: 'Premium wooden casket — oak finish', status: 'confirmed' },
    { id: 'FI-003', category: 'Venue', description: 'Edendale Community Hall — 200 capacity', status: 'pending' },
    { id: 'FI-004', category: 'Catering', description: 'Full catering for 150 guests', status: 'pending' },
    { id: 'FI-005', category: 'Flowers', description: 'Wreath and altar arrangements', status: 'in-progress' },
    { id: 'FI-006', category: 'Program', description: 'Printed memorial programs (200 copies)', status: 'pending' },
  ],
};
