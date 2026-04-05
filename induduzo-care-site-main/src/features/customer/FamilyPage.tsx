import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { UserPlus } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import { mockDependants, mockBeneficiaries } from '@/data/mockFamily';
import { useToast } from '@/hooks/use-toast';

export default function FamilyPage() {
  const { toast } = useToast();

  const handleAction = (action: string) => {
    toast({ title: action, description: 'This feature will be available soon.' });
  };

  return (
    <PageContainer>
      <SectionHeader title="My Family" description="Manage your dependants and beneficiaries." />

      {/* Dependants */}
      <Card className="mb-6">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <CardTitle className="text-lg">Dependants ({mockDependants.length})</CardTitle>
          <Button variant="outline" size="sm" className="h-10" onClick={() => handleAction('Add Dependant')}>
            <UserPlus className="mr-2 h-4 w-4" />
            Add Dependant
          </Button>
        </CardHeader>
        <CardContent>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Full Name</TableHead>
                  <TableHead>Relationship</TableHead>
                  <TableHead>Date of Birth</TableHead>
                  <TableHead>ID Number</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockDependants.map((dep) => (
                  <TableRow key={dep.id}>
                    <TableCell className="font-medium">{dep.fullName}</TableCell>
                    <TableCell>{dep.relationship}</TableCell>
                    <TableCell>{new Date(dep.dateOfBirth).toLocaleDateString('en-ZA')}</TableCell>
                    <TableCell className="font-mono text-xs">{dep.idNumber}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {mockDependants.map((dep) => (
              <div key={dep.id} className="border rounded-lg p-4">
                <p className="font-medium">{dep.fullName}</p>
                <p className="text-sm text-muted-foreground">{dep.relationship}</p>
                <p className="text-sm text-muted-foreground">
                  Born: {new Date(dep.dateOfBirth).toLocaleDateString('en-ZA')}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Beneficiaries */}
      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <CardTitle className="text-lg">Beneficiaries ({mockBeneficiaries.length})</CardTitle>
          <Button variant="outline" size="sm" className="h-10" onClick={() => handleAction('Edit Beneficiaries')}>
            Request Change
          </Button>
        </CardHeader>
        <CardContent>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Full Name</TableHead>
                  <TableHead>Relationship</TableHead>
                  <TableHead>Allocation</TableHead>
                  <TableHead>Contact</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockBeneficiaries.map((ben) => (
                  <TableRow key={ben.id}>
                    <TableCell className="font-medium">{ben.fullName}</TableCell>
                    <TableCell>{ben.relationship}</TableCell>
                    <TableCell>
                      <span className="font-semibold">{ben.allocationPercentage}%</span>
                    </TableCell>
                    <TableCell>{ben.contactNumber}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {mockBeneficiaries.map((ben) => (
              <div key={ben.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{ben.fullName}</p>
                  <span className="text-sm font-semibold text-primary">{ben.allocationPercentage}%</span>
                </div>
                <p className="text-sm text-muted-foreground">{ben.relationship}</p>
                <p className="text-sm text-muted-foreground">{ben.contactNumber}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 p-3 bg-secondary/50 rounded-lg">
            <p className="text-xs text-muted-foreground">
              Total allocation:{' '}
              <span className="font-semibold">
                {mockBeneficiaries.reduce((sum, b) => sum + b.allocationPercentage, 0)}%
              </span>
            </p>
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
