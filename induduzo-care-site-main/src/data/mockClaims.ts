import type { ClaimCase, WorkflowStage } from '@/types';

const activeClaimStages: WorkflowStage[] = [
  { key: 'intake', label: 'Claim Submitted', status: 'completed', completedAt: '2026-03-15', note: 'Claim received and registered.' },
  { key: 'policy-validation', label: 'Policy Validation', status: 'completed', completedAt: '2026-03-16', note: 'Policy confirmed active and in good standing.' },
  { key: 'beneficiary-validation', label: 'Beneficiary Validation', status: 'completed', completedAt: '2026-03-17', note: 'Beneficiaries confirmed per policy record.' },
  { key: 'waiting-period', label: 'Waiting Period Check', status: 'completed', completedAt: '2026-03-17', note: 'Waiting period has been fulfilled.' },
  { key: 'document-verification', label: 'Document Verification', status: 'current', note: 'Awaiting certified death certificate copy.' },
  { key: 'fraud-review', label: 'Fraud & Risk Review', status: 'upcoming' },
  { key: 'funeral-planning', label: 'Funeral Operations Planning', status: 'upcoming' },
  { key: 'payout', label: 'Payout Preparation', status: 'upcoming' },
];

export const mockClaims: ClaimCase[] = [
  {
    id: 'CLM-2026-0001',
    currentStage: 'document-verification',
    deceasedName: 'Gogo MaDlamini',
    dateOfDeath: '2026-03-14',
    placeOfDeath: 'Edendale Hospital, Pietermaritzburg',
    claimantName: 'Sipho Dlamini',
    contactNumber: '082 345 6789',
    policyReference: 'IND-UA-2024-00142',
    createdAt: '2026-03-15',
    workflowStages: activeClaimStages,
  },
];

export function generateClaimId(): string {
  const count = mockClaims.length + 1;
  return `CLM-2026-${String(count).padStart(4, '0')}`;
}

export function createNewClaimStages(): WorkflowStage[] {
  return [
    { key: 'intake', label: 'Claim Submitted', status: 'completed', note: 'Claim received and registered.' },
    { key: 'policy-validation', label: 'Policy Validation', status: 'current', note: 'Policy details being verified.' },
    { key: 'beneficiary-validation', label: 'Beneficiary Validation', status: 'upcoming' },
    { key: 'waiting-period', label: 'Waiting Period Check', status: 'upcoming' },
    { key: 'document-verification', label: 'Document Verification', status: 'upcoming' },
    { key: 'fraud-review', label: 'Fraud & Risk Review', status: 'upcoming' },
    { key: 'funeral-planning', label: 'Funeral Operations Planning', status: 'upcoming' },
    { key: 'payout', label: 'Payout Preparation', status: 'upcoming' },
  ];
}
