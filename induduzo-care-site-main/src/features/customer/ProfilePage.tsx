import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Edit } from 'lucide-react';
import PageContainer from '@/components/portal/PageContainer';
import SectionHeader from '@/components/portal/SectionHeader';
import StatusBadge from '@/components/portal/StatusBadge';
import InfoRow from '@/components/portal/InfoRow';
import { mockCustomer } from '@/data/mockCustomer';
import { useToast } from '@/hooks/use-toast';

export default function ProfilePage() {
  const { toast } = useToast();

  const handleEdit = (section: string) => {
    toast({ title: `Edit ${section}`, description: 'This feature will be available soon.' });
  };

  return (
    <PageContainer>
      <SectionHeader title="Profile" description="Your personal information and preferences." />

      {/* Completeness */}
      <Card className="mb-6">
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium">Profile completeness</p>
            <span className="text-sm font-semibold">{mockCustomer.profileCompleteness}%</span>
          </div>
          <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${mockCustomer.profileCompleteness}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Personal Details */}
      <Card className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Personal Details</CardTitle>
          <Button variant="outline" size="sm" className="h-9" onClick={() => handleEdit('Personal Details')}>
            <Edit className="mr-2 h-3.5 w-3.5" />
            Edit
          </Button>
        </CardHeader>
        <CardContent>
          <InfoRow label="Full Name" value={mockCustomer.fullName} />
          <InfoRow label="ID Number" value={<span className="font-mono">{mockCustomer.idNumber}</span>} />
          <InfoRow label="Date of Birth" value={new Date(mockCustomer.dateOfBirth).toLocaleDateString('en-ZA')} />
        </CardContent>
      </Card>

      {/* Contact Info */}
      <Card className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Contact Information</CardTitle>
          <Button variant="outline" size="sm" className="h-9" onClick={() => handleEdit('Contact Info')}>
            <Edit className="mr-2 h-3.5 w-3.5" />
            Edit
          </Button>
        </CardHeader>
        <CardContent>
          <InfoRow label="Email" value={mockCustomer.email} />
          <InfoRow label="Phone" value={mockCustomer.phone} />
        </CardContent>
      </Card>

      {/* Address */}
      <Card className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Address</CardTitle>
          <Button variant="outline" size="sm" className="h-9" onClick={() => handleEdit('Address')}>
            <Edit className="mr-2 h-3.5 w-3.5" />
            Edit
          </Button>
        </CardHeader>
        <CardContent>
          <InfoRow label="Street" value={mockCustomer.address.street} />
          <InfoRow label="Suburb" value={mockCustomer.address.suburb} />
          <InfoRow label="City" value={mockCustomer.address.city} />
          <InfoRow label="Province" value={mockCustomer.address.province} />
          <InfoRow label="Postal Code" value={mockCustomer.address.postalCode} />
        </CardContent>
      </Card>

      {/* Documents */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg">Documents</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {mockCustomer.documents.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between border rounded-lg p-3">
                <div>
                  <p className="text-sm font-medium">{doc.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Uploaded: {new Date(doc.uploadedAt).toLocaleDateString('en-ZA')}
                  </p>
                </div>
                <StatusBadge status={doc.status} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Communication Preferences */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Communication Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(mockCustomer.communicationPreferences).map(([key, value]) => {
            const labels: Record<string, string> = {
              sms: 'SMS Notifications',
              email: 'Email Notifications',
              whatsapp: 'WhatsApp Messages',
              pushNotifications: 'Push Notifications',
            };
            return (
              <div key={key} className="flex items-center justify-between">
                <Label htmlFor={key} className="text-sm font-normal cursor-pointer">
                  {labels[key] || key}
                </Label>
                <Switch
                  id={key}
                  defaultChecked={value}
                  onCheckedChange={() =>
                    toast({ title: 'Preferences', description: 'Preference update will be available soon.' })
                  }
                />
              </div>
            );
          })}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
