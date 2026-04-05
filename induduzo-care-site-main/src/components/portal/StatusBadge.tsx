import { cn } from '@/lib/utils';

type BadgeVariant = 'active' | 'pending' | 'lapsed' | 'missed' | 'paid' | 'completed' | 'upcoming' | 'current' | 'confirmed' | 'in-progress' | 'planning' | 'rejected' | 'verified';

const variantStyles: Record<BadgeVariant, string> = {
  active: 'bg-green-100 text-green-800',
  paid: 'bg-green-100 text-green-800',
  completed: 'bg-green-100 text-green-800',
  verified: 'bg-green-100 text-green-800',
  confirmed: 'bg-green-100 text-green-800',
  pending: 'bg-yellow-100 text-yellow-800',
  planning: 'bg-yellow-100 text-yellow-800',
  'in-progress': 'bg-blue-100 text-blue-800',
  current: 'bg-blue-100 text-blue-800',
  lapsed: 'bg-red-100 text-red-800',
  missed: 'bg-red-100 text-red-800',
  rejected: 'bg-red-100 text-red-800',
  upcoming: 'bg-gray-100 text-gray-600',
};

interface StatusBadgeProps {
  status: BadgeVariant;
  label?: string;
  className?: string;
}

export default function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const displayLabel = label || status.charAt(0).toUpperCase() + status.slice(1).replace('-', ' ');
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
        variantStyles[status] || 'bg-gray-100 text-gray-600',
        className
      )}
    >
      {displayLabel}
    </span>
  );
}
