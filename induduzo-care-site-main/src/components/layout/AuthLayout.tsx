import { Outlet, NavLink } from 'react-router-dom';

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-secondary/30 flex flex-col">
      <header className="w-full border-b bg-background/95 backdrop-blur py-4">
        <div className="container flex items-center justify-between">
          <NavLink to="/" className="text-2xl font-bold text-primary">
            Induduzo
          </NavLink>
          <NavLink
            to="/"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Back to website
          </NavLink>
        </div>
      </header>
      <main className="flex-1 flex items-center justify-center p-4">
        <Outlet />
      </main>
      <footer className="py-4 text-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} Induduzo Funeral Home. All rights reserved.</p>
      </footer>
    </div>
  );
}
