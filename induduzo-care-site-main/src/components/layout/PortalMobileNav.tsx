import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Shield, CreditCard, FileText, User } from 'lucide-react';
import { cn } from '@/lib/utils';

const mobileNavItems = [
  { to: '/portal/customer', icon: LayoutDashboard, label: 'Home', end: true },
  { to: '/portal/customer/policy', icon: Shield, label: 'Policy' },
  { to: '/portal/customer/payments', icon: CreditCard, label: 'Pay' },
  { to: '/portal/customer/claims', icon: FileText, label: 'Claims' },
  { to: '/portal/customer/profile', icon: User, label: 'Profile' },
];

export default function PortalMobileNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t bg-background lg:hidden">
      <div className="flex items-center justify-around h-16">
        {mobileNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'flex flex-col items-center justify-center gap-0.5 px-2 py-1 min-w-[56px] text-xs transition-colors',
                isActive
                  ? 'text-primary font-semibold'
                  : 'text-muted-foreground'
              )
            }
          >
            <item.icon className="h-5 w-5" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
