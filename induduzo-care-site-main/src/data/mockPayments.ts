import type { PaymentRecord, PaymentSummary } from '@/types';

export const mockPayments: PaymentRecord[] = [
  { id: 'PAY-012', date: '2026-04-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2026-04-001' },
  { id: 'PAY-011', date: '2026-03-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2026-03-001' },
  { id: 'PAY-010', date: '2026-02-01', amount: 350, status: 'missed', method: 'Debit Order', reference: 'DO-2026-02-001' },
  { id: 'PAY-009', date: '2026-01-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2026-01-001' },
  { id: 'PAY-008', date: '2025-12-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-12-001' },
  { id: 'PAY-007', date: '2025-11-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-11-001' },
  { id: 'PAY-006', date: '2025-10-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-10-001' },
  { id: 'PAY-005', date: '2025-09-01', amount: 350, status: 'missed', method: 'Debit Order', reference: 'DO-2025-09-001' },
  { id: 'PAY-004', date: '2025-08-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-08-001' },
  { id: 'PAY-003', date: '2025-07-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-07-001' },
  { id: 'PAY-002', date: '2025-06-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-06-001' },
  { id: 'PAY-001', date: '2025-05-01', amount: 350, status: 'paid', method: 'Debit Order', reference: 'DO-2025-05-001' },
];

export const mockPaymentSummary: PaymentSummary = {
  totalPaid: 3500,
  arrears: 700,
  missedCount: 2,
  lastPaymentDate: '2026-04-01',
  lastPaymentStatus: 'paid',
  paymentMethod: 'Debit Order (FNB ****4521)',
};
