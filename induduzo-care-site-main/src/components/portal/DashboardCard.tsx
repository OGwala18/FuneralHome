import { NavLink } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { ArrowRight, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DashboardCardProps {
  to: string;
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
  className?: string;
}

export default function DashboardCard({ to, icon: Icon, title, children, className }: DashboardCardProps) {
  return (
    <NavLink to={to} className="group">
      <Card className={cn('h-full hover:shadow-elevated transition-shadow', className)}>
        <CardContent className="p-6">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="flex-shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10">
                <Icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-lg font-semibold">{title}</h3>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all mt-1" />
          </div>
          <div className="space-y-1.5 text-sm">{children}</div>
        </CardContent>
      </Card>
    </NavLink>
  );
}
