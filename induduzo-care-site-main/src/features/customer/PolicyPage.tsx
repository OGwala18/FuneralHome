import { Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import InfoRow from '@/components/portal/InfoRow';
import { mockPolicy } from '@/data/mockPolicy';
import { useToast } from '@/hooks/use-toast';

export default function PolicyPage() {
  const { toast } = useToast();

  const handleDownload = (doc: string) => {
    toast({ title: doc, description: 'Download will be available soon.' });
  };

  return (
    <PageContainer>
      <SectionHeader title="My Policy" description="Your active cover details and plan information." />

      {/* Cover Summary */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <CardTitle className="text-xl">{mockPolicy.planName}</CardTitle>
            <StatusBadge status={mockPolicy.status} />
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Cover Amount</p>
              <p className="text-2xl font-bold">R{mockPolicy.coverAmount.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Monthly Premium</p>
              <p className="text-2xl font-bold">R{mockPolicy.monthlyPremium}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Members Covered</p>
              <p className="text-2xl font-bold">{mockPolicy.membersCount}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Next Debit</p>
              <p className="text-2xl font-bold">
                {new Date(mockPolicy.nextDebitDate).toLocaleDateString('en-ZA', { day: 'numeric', month: 'short' })}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Policy Details */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg">Policy Details</CardTitle>
        </CardHeader>
        <CardContent>
          <InfoRow label="Policy Number" value={mockPolicy.policyNumber} />
          <InfoRow label="Plan" value={mockPolicy.planName} />
          <InfoRow label="Status" value={<StatusBadge status={mockPolicy.status} />} />
          <InfoRow label="Start Date" value={new Date(mockPolicy.startDate).toLocaleDateString('en-ZA')} />
          <InfoRow
            label="Waiting Period Ended"
            value={new Date(mockPolicy.waitingPeriodEndDate).toLocaleDateString('en-ZA')}
          />
          <InfoRow label="Monthly Premium" value={`R${mockPolicy.monthlyPremium}`} />
          <InfoRow label="Cover Amount" value={`R${mockPolicy.coverAmount.toLocaleString()}`} />
          <InfoRow label="Members Covered" value={String(mockPolicy.membersCount)} />
        </CardContent>
      </Card>

      {/* Downloads */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Documents</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col sm:flex-row gap-3">
          <Button variant="outline" className="h-11" onClick={() => handleDownload('Policy Schedule')}>
            <Download className="mr-2 h-4 w-4" />
            Policy Schedule
          </Button>
          <Button variant="outline" className="h-11" onClick={() => handleDownload('Cover Certificate')}>
            <Download className="mr-2 h-4 w-4" />
            Cover Certificate
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
