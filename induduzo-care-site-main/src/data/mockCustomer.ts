import type { UserProfile } from '@/types';

export const mockCustomer: UserProfile = {
  id: 'USR-001',
  fullName: 'Sipho Dlamini',
  email: 'sipho.dlamini@email.co.za',
  phone: '082 345 6789',
  idNumber: '8501015800089',
  dateOfBirth: '1985-01-01',
  address: {
    street: '45 Langalibalele Street',
    suburb: 'Edendale',
    city: 'Pietermaritzburg',
    province: 'KwaZulu-Natal',
    postalCode: '3201',
  },
  documents: [
    { id: 'DOC-001', name: 'ID Document', type: 'id', uploadedAt: '2025-06-15', status: 'verified' },
    { id: 'DOC-002', name: 'Proof of Address', type: 'proof-of-address', uploadedAt: '2025-06-15', status: 'verified' },
    { id: 'DOC-003', name: 'Bank Statement', type: 'bank-statement', uploadedAt: '2025-07-02', status: 'pending' },
  ],
  communicationPreferences: {
    sms: true,
    email: true,
    whatsapp: true,
    pushNotifications: false,
  },
  profileCompleteness: 85,
};
