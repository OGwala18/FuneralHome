import { Download, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import InfoRow from '@/components/portal/InfoRow';
import { mockPayments, mockPaymentSummary } from '@/data/mockPayments';
import { useToast } from '@/hooks/use-toast';

export default function PaymentsPage() {
  const { toast } = useToast();

  const handleAction = (action: string) => {
    toast({ title: action, description: 'This feature will be available soon.' });
  };

  return (
    <PageContainer>
      <SectionHeader title="Payments" description="Your payment history and account status." />

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Total Paid</p>
            <p className="text-2xl font-bold mt-1">R{mockPaymentSummary.totalPaid.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card className={mockPaymentSummary.arrears > 0 ? 'border-red-200' : ''}>
          <CardContent className="p-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Arrears</p>
            <p className={`text-2xl font-bold mt-1 ${mockPaymentSummary.arrears > 0 ? 'text-red-600' : ''}`}>
              R{mockPaymentSummary.arrears.toLocaleString()}
            </p>
            {mockPaymentSummary.arrears > 0 && (
              <p className="text-xs text-red-500 flex items-center gap-1 mt-1">
                <AlertTriangle className="h-3 w-3" />
                {mockPaymentSummary.missedCount} missed payment(s)
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Payment Method</p>
            <p className="text-sm font-medium mt-1">{mockPaymentSummary.paymentMethod}</p>
            <Button variant="link" className="p-0 h-auto text-xs" onClick={() => handleAction('Update Payment Method')}>
              Update method
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Payment History */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Payment History</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>Reference</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockPayments.map((payment) => (
                  <TableRow key={payment.id}>
                    <TableCell>{new Date(payment.date).toLocaleDateString('en-ZA')}</TableCell>
                    <TableCell className="font-medium">R{payment.amount}</TableCell>
                    <TableCell><StatusBadge status={payment.status} /></TableCell>
                    <TableCell>{payment.method}</TableCell>
                    <TableCell className="font-mono text-xs">{payment.reference}</TableCell>
                    <TableCell>
                      {payment.status === 'paid' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8"
                          onClick={() => handleAction(`Receipt ${payment.reference}`)}
                        >
                          <Download className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Mobile list */}
          <div className="md:hidden space-y-3">
            {mockPayments.map((payment) => (
              <div key={payment.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">R{payment.amount}</span>
                  <StatusBadge status={payment.status} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {new Date(payment.date).toLocaleDateString('en-ZA')}
                </p>
                <p className="text-xs text-muted-foreground font-mono">{payment.reference}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
