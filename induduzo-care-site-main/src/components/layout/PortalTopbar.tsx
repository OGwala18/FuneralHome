import { NavLink } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import {
  LayoutDashboard,
  Shield,
  Users,
  CreditCard,
  FileText,
  Flower2,
  User,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { mockCustomer } from '@/data/mockCustomer';

const navItems = [
  { to: '/portal/customer', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/portal/customer/policy', icon: Shield, label: 'My Policy' },
  { to: '/portal/customer/family', icon: Users, label: 'My Family' },
  { to: '/portal/customer/payments', icon: CreditCard, label: 'Payments' },
  { to: '/portal/customer/claims', icon: FileText, label: 'Claims' },
  { to: '/portal/customer/funeral-services', icon: Flower2, label: 'Funeral Services' },
  { to: '/portal/customer/profile', icon: User, label: 'Profile' },
];

export default function PortalTopbar() {
  const firstName = mockCustomer.fullName.split(' ')[0];

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-3">
          {/* Mobile hamburger */}
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Open menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SheetHeader className="p-6 border-b">
                <SheetTitle className="text-left">
                  <span className="text-xl font-bold text-primary">Induduzo</span>
                  <p className="text-xs text-muted-foreground mt-1 font-normal">Customer Portal</p>
                </SheetTitle>
              </SheetHeader>
              <nav className="p-4 space-y-1">
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
              <div className="p-4 border-t mt-auto">
                <NavLink
                  to="/"
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  <LogOut className="h-5 w-5 flex-shrink-0" />
                  Sign Out
                </NavLink>
              </div>
            </SheetContent>
          </Sheet>

          <span className="text-lg font-bold text-primary lg:hidden">Induduzo</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground hidden sm:inline">
            Welcome, <span className="font-medium text-foreground">{firstName}</span>
          </span>
          <NavLink to="/portal/customer/profile">
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary">
              {firstName.charAt(0)}
            </div>
          </NavLink>
        </div>
      </div>
    </header>
  );
}
