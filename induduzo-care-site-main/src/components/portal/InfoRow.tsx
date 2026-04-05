import { cn } from '@/lib/utils';

interface InfoRowProps {
  label: string;
  value: React.ReactNode;
  className?: string;
}

export default function InfoRow({ label, value, className }: InfoRowProps) {
  return (
    <div className={cn('flex flex-col sm:flex-row sm:items-center py-3 border-b last:border-b-0', className)}>
      <span className="text-sm text-muted-foreground sm:w-44 sm:flex-shrink-0">{label}</span>
      <span className="text-sm font-medium mt-0.5 sm:mt-0">{value}</span>
    </div>
  );
}
