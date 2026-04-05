import type { Dependant, Beneficiary } from '@/types';

export const mockDependants: Dependant[] = [
  { id: 'DEP-001', fullName: 'Nomsa Dlamini', relationship: 'Spouse', dateOfBirth: '1987-04-12', idNumber: '8704120500081' },
  { id: 'DEP-002', fullName: 'Thabo Dlamini', relationship: 'Son', dateOfBirth: '2010-08-23', idNumber: '1008235800083' },
  { id: 'DEP-003', fullName: 'Zanele Dlamini', relationship: 'Daughter', dateOfBirth: '2013-11-05', idNumber: '1311055800085' },
  { id: 'DEP-004', fullName: 'Gogo MaDlamini', relationship: 'Mother', dateOfBirth: '1955-02-18', idNumber: '5502180500087' },
];

export const mockBeneficiaries: Beneficiary[] = [
  { id: 'BEN-001', fullName: 'Nomsa Dlamini', relationship: 'Spouse', allocationPercentage: 60, contactNumber: '082 456 7890', idNumber: '8704120500081' },
  { id: 'BEN-002', fullName: 'Thabo Dlamini', relationship: 'Son', allocationPercentage: 20, contactNumber: '082 345 6789', idNumber: '1008235800083' },
  { id: 'BEN-003', fullName: 'Zanele Dlamini', relationship: 'Daughter', allocationPercentage: 20, contactNumber: '082 345 6789', idNumber: '1311055800085' },
];
