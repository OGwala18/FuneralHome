import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Phone, MapPin, Calendar, Clock, ArrowRight } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import InfoRow from '@/components/portal/InfoRow';
import { mockFuneralArrangement } from '@/data/mockFuneralServices';

export default function FuneralServicesPage() {
  const arrangement = mockFuneralArrangement;

  if (!arrangement) {
    return (
      <PageContainer>
        <SectionHeader title="Funeral Services" description="No active funeral arrangements." />
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground">
              Funeral arrangements will appear here once a claim reaches the planning stage.
            </p>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <SectionHeader title="Funeral Services" description="Funeral arrangement details and progress." />

      {/* Overview */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <CardTitle className="text-xl">Arrangement {arrangement.id}</CardTitle>
            <StatusBadge status={arrangement.status} />
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
            <div className="flex items-start gap-3">
              <Calendar className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Service Date</p>
                <p className="font-medium">{new Date(arrangement.date).toLocaleDateString('en-ZA', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Clock className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Time</p>
                <p className="font-medium">{arrangement.time}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <MapPin className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Venue</p>
                <p className="font-medium">{arrangement.venue}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Phone className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Case Manager</p>
                <p className="font-medium">{arrangement.caseManager}</p>
                <p className="text-sm text-muted-foreground">{arrangement.caseManagerPhone}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Next Step */}
      <Card className="mb-6 border-primary/30 bg-primary/5">
        <CardContent className="p-5 flex items-start gap-3">
          <ArrowRight className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-primary">Next Step</p>
            <p className="text-sm">{arrangement.nextStep}</p>
          </div>
        </CardContent>
      </Card>

      {/* Service Items */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Service Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {arrangement.items.map((item) => (
              <div key={item.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold">{item.category}</span>
                  <StatusBadge status={item.status} />
                </div>
                <p className="text-sm text-muted-foreground">{item.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
