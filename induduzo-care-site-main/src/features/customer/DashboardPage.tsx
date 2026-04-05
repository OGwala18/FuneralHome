import { Shield, Users, CreditCard, FileText, User } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import DashboardCard from '@/components/portal/DashboardCard';
import StatusBadge from '@/components/portal/StatusBadge';
import { mockPolicy } from '@/data/mockPolicy';
import { mockDependants, mockBeneficiaries } from '@/data/mockFamily';
import { mockPaymentSummary } from '@/data/mockPayments';
import { mockClaims } from '@/data/mockClaims';
import { mockCustomer } from '@/data/mockCustomer';

export default function DashboardPage() {
  const activeClaim = mockClaims.length > 0 ? mockClaims[0] : null;

  return (
    <PageContainer>
      <SectionHeader
        title={`Welcome back, ${mockCustomer.fullName.split(' ')[0]}`}
        description="Here's an overview of your account."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* My Policy */}
        <DashboardCard to="/portal/customer/policy" icon={Shield} title="My Policy">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">{mockPolicy.planName}</span>
            <StatusBadge status={mockPolicy.status} />
          </div>
          <p>
            <span className="text-muted-foreground">Premium:</span>{' '}
            <span className="font-semibold">R{mockPolicy.monthlyPremium}/month</span>
          </p>
          <p className="text-muted-foreground">
            Next debit: {new Date(mockPolicy.nextDebitDate).toLocaleDateString('en-ZA')}
          </p>
        </DashboardCard>

        {/* My Family */}
        <DashboardCard to="/portal/customer/family" icon={Users} title="My Family">
          <p>
            <span className="text-2xl font-bold text-foreground">{mockDependants.length}</span>{' '}
            <span className="text-muted-foreground">dependants</span>
          </p>
          <p>
            <span className="text-2xl font-bold text-foreground">{mockBeneficiaries.length}</span>{' '}
            <span className="text-muted-foreground">beneficiaries</span>
          </p>
        </DashboardCard>

        {/* Payments */}
        <DashboardCard to="/portal/customer/payments" icon={CreditCard} title="Payments">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Last payment:</span>
            <StatusBadge status={mockPaymentSummary.lastPaymentStatus} />
          </div>
          <p className="text-muted-foreground">
            {new Date(mockPaymentSummary.lastPaymentDate).toLocaleDateString('en-ZA')}
          </p>
          {mockPaymentSummary.arrears > 0 && (
            <p className="text-red-600 font-medium">
              Arrears: R{mockPaymentSummary.arrears.toLocaleString()}
            </p>
          )}
        </DashboardCard>

        {/* Claims & Funeral Services */}
        <DashboardCard to="/portal/customer/claims" icon={FileText} title="Claims & Funeral Services">
          {activeClaim ? (
            <>
              <p className="text-muted-foreground">Case: {activeClaim.id}</p>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Status:</span>
                <StatusBadge status="current" label={activeClaim.workflowStages.find(s => s.status === 'current')?.label || 'In progress'} />
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">No active claims</p>
          )}
        </DashboardCard>

        {/* Profile */}
        <DashboardCard to="/portal/customer/profile" icon={User} title="Profile">
          <p className="text-muted-foreground">{mockCustomer.email}</p>
          <p className="text-muted-foreground">{mockCustomer.phone}</p>
          <div className="flex items-center gap-2 mt-1">
            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full"
                style={{ width: `${mockCustomer.profileCompleteness}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground">{mockCustomer.profileCompleteness}%</span>
          </div>
        </DashboardCard>
      </div>
    </PageContainer>
  );
}
