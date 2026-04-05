import { Outlet } from 'react-router-dom';
import PortalSidebar from './PortalSidebar';
import PortalTopbar from './PortalTopbar';
import PortalMobileNav from './PortalMobileNav';

export default function PortalLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-secondary/20">
      <PortalSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <PortalTopbar />
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-6">
          <Outlet />
        </main>
        <PortalMobileNav />
      </div>
    </div>
  );
}
