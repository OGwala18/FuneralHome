import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import { AlertTriangle, Plus } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import { mockClaims, generateClaimId, createNewClaimStages } from '@/data/mockClaims';
import { mockPolicy } from '@/data/mockPolicy';
import { useToast } from '@/hooks/use-toast';
import type { ClaimCase } from '@/types';

export default function ClaimsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [claims, setClaims] = useState<ClaimCase[]>(mockClaims);
  const [open, setOpen] = useState(false);

  const handleSubmitClaim = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const newId = generateClaimId();

    const newClaim: ClaimCase = {
      id: newId,
      currentStage: 'policy-validation',
      deceasedName: formData.get('deceased') as string,
      dateOfDeath: formData.get('dateOfDeath') as string,
      placeOfDeath: formData.get('placeOfDeath') as string,
      claimantName: formData.get('claimant') as string,
      contactNumber: formData.get('contactNumber') as string,
      policyReference: mockPolicy.policyNumber,
      createdAt: new Date().toISOString().split('T')[0],
      workflowStages: createNewClaimStages(),
    };

    setClaims((prev) => [newClaim, ...prev]);
    setOpen(false);
    toast({ title: 'Claim submitted', description: `Case ${newId} has been created.` });
    navigate(`/portal/customer/claims/${newId}`);
  };

  const handleUpload = () => {
    toast({ title: 'Upload', description: 'Document upload will be available soon.' });
  };

  return (
    <PageContainer>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <SectionHeader title="Claims" description="Track and manage your claims." />

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="h-11 sm:self-start">
              <AlertTriangle className="mr-2 h-4 w-4" />
              Notify a Death
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>Notify a Death</DialogTitle>
              <DialogDescription>
                Submit details to start a claim. We'll guide you through the process.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmitClaim} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="deceased">Name of deceased</Label>
                <Input id="deceased" name="deceased" required placeholder="Full name" className="h-11" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="policyRef">Policy / Member reference</Label>
                <Input id="policyRef" name="policyRef" defaultValue={mockPolicy.policyNumber} readOnly className="h-11 bg-secondary/50" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="claimant">Your name (claimant)</Label>
                <Input id="claimant" name="claimant" required placeholder="Your full name" className="h-11" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="dateOfDeath">Date of death</Label>
                  <Input id="dateOfDeath" name="dateOfDeath" type="date" required className="h-11" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="contactNumber">Contact number</Label>
                  <Input id="contactNumber" name="contactNumber" type="tel" required placeholder="082 000 0000" className="h-11" />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="placeOfDeath">Place of death</Label>
                <Input id="placeOfDeath" name="placeOfDeath" required placeholder="Hospital, home, etc." className="h-11" />
              </div>
              <div className="space-y-2">
                <Label>Death certificate</Label>
                <Button type="button" variant="outline" className="w-full h-11" onClick={handleUpload}>
                  <Plus className="mr-2 h-4 w-4" />
                  Upload document (coming soon)
                </Button>
              </div>
              <DialogFooter>
                <Button type="submit" className="w-full sm:w-auto h-11">Submit Claim</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Claims list */}
      {claims.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground">No claims on record.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {claims.map((claim) => {
            const currentStage = claim.workflowStages.find((s) => s.status === 'current');
            return (
              <Card
                key={claim.id}
                className="cursor-pointer hover:shadow-elevated transition-shadow"
                onClick={() => navigate(`/portal/customer/claims/${claim.id}`)}
              >
                <CardContent className="p-5">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
                    <div>
                      <p className="font-semibold">{claim.id}</p>
                      <p className="text-sm text-muted-foreground">Deceased: {claim.deceasedName}</p>
                    </div>
                    <StatusBadge
                      status="current"
                      label={currentStage?.label || 'In progress'}
                    />
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                    <div>
                      <span className="text-muted-foreground">Date of death</span>
                      <p className="font-medium">{new Date(claim.dateOfDeath).toLocaleDateString('en-ZA')}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Submitted</span>
                      <p className="font-medium">{new Date(claim.createdAt).toLocaleDateString('en-ZA')}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Claimant</span>
                      <p className="font-medium">{claim.claimantName}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Policy</span>
                      <p className="font-medium text-xs font-mono">{claim.policyReference}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </PageContainer>
  );
}
