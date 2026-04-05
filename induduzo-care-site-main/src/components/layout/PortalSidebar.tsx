import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Shield,
  Users,
  CreditCard,
  FileText,
  Flower2,
  User,
  LogOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/portal/customer', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/portal/customer/policy', icon: Shield, label: 'My Policy' },
  { to: '/portal/customer/family', icon: Users, label: 'My Family' },
  { to: '/portal/customer/payments', icon: CreditCard, label: 'Payments' },
  { to: '/portal/customer/claims', icon: FileText, label: 'Claims' },
  { to: '/portal/customer/funeral-services', icon: Flower2, label: 'Funeral Services' },
  { to: '/portal/customer/profile', icon: User, label: 'Profile' },
];

export default function PortalSidebar() {
  return (
    <aside className="hidden lg:flex lg:flex-col lg:w-64 border-r bg-background h-full">
      <div className="p-6 border-b">
        <NavLink to="/" className="text-xl font-bold text-primary">
          Induduzo
        </NavLink>
        <p className="text-xs text-muted-foreground mt-1">Customer Portal</p>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              )
            }
          >
            <item.icon className="h-5 w-5 flex-shrink-0" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t">
        <NavLink
          to="/"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <LogOut className="h-5 w-5 flex-shrink-0" />
          Sign Out
        </NavLink>
      </div>
    </aside>
  );
}
