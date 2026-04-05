export interface Address {
  street: string;
  suburb: string;
  city: string;
  province: string;
  postalCode: string;
}

export interface UserDocument {
  id: string;
  name: string;
  type: 'id' | 'proof-of-address' | 'bank-statement' | 'death-certificate' | 'other';
  uploadedAt: string;
  status: 'verified' | 'pending' | 'rejected';
}

export interface CommunicationPreferences {
  sms: boolean;
  email: boolean;
  whatsapp: boolean;
  pushNotifications: boolean;
}

export interface UserProfile {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  idNumber: string;
  dateOfBirth: string;
  address: Address;
  documents: UserDocument[];
  communicationPreferences: CommunicationPreferences;
  profileCompleteness: number;
}

export interface Policy {
  id: string;
  planName: string;
  status: 'active' | 'lapsed' | 'pending';
  monthlyPremium: number;
  nextDebitDate: string;
  coverAmount: number;
  startDate: string;
  membersCount: number;
  policyNumber: string;
  waitingPeriodEndDate: string;
}

export interface Dependant {
  id: string;
  fullName: string;
  relationship: string;
  dateOfBirth: string;
  idNumber: string;
}

export interface Beneficiary {
  id: string;
  fullName: string;
  relationship: string;
  allocationPercentage: number;
  contactNumber: string;
  idNumber: string;
}

export interface PaymentRecord {
  id: string;
  date: string;
  amount: number;
  status: 'paid' | 'missed' | 'pending';
  method: string;
  reference: string;
}

export interface PaymentSummary {
  totalPaid: number;
  arrears: number;
  missedCount: number;
  lastPaymentDate: string;
  lastPaymentStatus: 'paid' | 'missed' | 'pending';
  paymentMethod: string;
}

export type ClaimStage =
  | 'intake'
  | 'policy-validation'
  | 'beneficiary-validation'
  | 'waiting-period'
  | 'document-verification'
  | 'fraud-review'
  | 'funeral-planning'
  | 'payout';

export interface WorkflowStage {
  key: ClaimStage;
  label: string;
  status: 'completed' | 'current' | 'upcoming';
  note?: string;
  completedAt?: string;
}

export interface ClaimCase {
  id: string;
  currentStage: ClaimStage;
  deceasedName: string;
  dateOfDeath: string;
  placeOfDeath: string;
  claimantName: string;
  contactNumber: string;
  policyReference: string;
  createdAt: string;
  workflowStages: WorkflowStage[];
}

export interface FuneralItem {
  id: string;
  category: string;
  description: string;
  status: 'confirmed' | 'pending' | 'in-progress';
}

export interface FuneralArrangement {
  id: string;
  claimCaseId: string;
  caseManager: string;
  caseManagerPhone: string;
  venue: string;
  date: string;
  time: string;
  items: FuneralItem[];
  status: 'planning' | 'confirmed' | 'in-progress' | 'completed';
  nextStep: string;
}
