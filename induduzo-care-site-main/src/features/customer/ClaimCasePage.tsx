import { useParams, NavLink } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Upload } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import InfoRow from '@/components/portal/InfoRow';
import WorkflowTimeline from '@/components/portal/WorkflowTimeline';
import { mockClaims } from '@/data/mockClaims';
import { useToast } from '@/hooks/use-toast';

export default function ClaimCasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { toast } = useToast();

  const claim = mockClaims.find((c) => c.id === caseId);

  if (!claim) {
    return (
      <PageContainer>
        <SectionHeader title="Claim Not Found" />
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground mb-4">
              No claim found with ID "{caseId}".
            </p>
            <Button asChild variant="outline">
              <NavLink to="/portal/customer/claims">Back to Claims</NavLink>
            </Button>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  const currentStage = claim.workflowStages.find((s) => s.status === 'current');

  return (
    <PageContainer>
      <NavLink
        to="/portal/customer/claims"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Claims
      </NavLink>

      <SectionHeader
        title={`Claim ${claim.id}`}
        description={`Deceased: ${claim.deceasedName}`}
      />

      {/* Current Status Banner */}
      <Card className="mb-6 border-primary/30 bg-primary/5">
        <CardContent className="p-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <p className="text-sm text-muted-foreground">Current Stage</p>
              <p className="text-lg font-semibold">{currentStage?.label || 'Processing'}</p>
            </div>
            <StatusBadge status="current" label={currentStage?.label || 'In progress'} />
          </div>
          {currentStage?.note && (
            <p className="text-sm text-muted-foreground mt-2">{currentStage.note}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Claim Details */}
        <div className="lg:col-span-1 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Claim Details</CardTitle>
            </CardHeader>
            <CardContent>
              <InfoRow label="Case ID" value={<span className="font-mono">{claim.id}</span>} />
              <InfoRow label="Deceased" value={claim.deceasedName} />
              <InfoRow label="Date of Death" value={new Date(claim.dateOfDeath).toLocaleDateString('en-ZA')} />
              <InfoRow label="Place of Death" value={claim.placeOfDeath} />
              <InfoRow label="Claimant" value={claim.claimantName} />
              <InfoRow label="Contact" value={claim.contactNumber} />
              <InfoRow label="Policy Ref" value={<span className="font-mono text-xs">{claim.policyReference}</span>} />
              <InfoRow label="Submitted" value={new Date(claim.createdAt).toLocaleDateString('en-ZA')} />
            </CardContent>
          </Card>

          {/* Upload action */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Documents</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-3">
                Upload required documents to move your claim forward.
              </p>
              <Button
                variant="outline"
                className="w-full h-11"
                onClick={() => toast({ title: 'Upload', description: 'Document upload will be available soon.' })}
              >
                <Upload className="mr-2 h-4 w-4" />
                Upload Documents
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Workflow Timeline */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Claim Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <WorkflowTimeline stages={claim.workflowStages} />
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
