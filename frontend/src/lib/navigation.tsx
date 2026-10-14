import React, { useEffect, useState } from "react";

type ActiveState = {
  isActive: boolean;
};

type NavLinkProps = Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  "className" | "href"
> & {
  className?: string | ((state: ActiveState) => string);
  to: string;
};

const currentPath = () => window.location.pathname.replace(/\/+$/, "") || "/";

export const usePathname = () => {
  const [pathname, setPathname] = useState(currentPath);

  useEffect(() => {
    const handleLocationChange = () => setPathname(currentPath());
    window.addEventListener("popstate", handleLocationChange);
    return () => window.removeEventListener("popstate", handleLocationChange);
  }, []);

  return pathname;
};

export const NavLink = ({
  children,
  className,
  onClick,
  target,
  to,
  ...props
}: NavLinkProps) => {
  const pathname = usePathname();
  const isActive = pathname === (to.replace(/\/+$/, "") || "/");
  const resolvedClassName =
    typeof className === "function" ? className({ isActive }) : className;

  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);

    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      target === "_blank"
    ) {
      return;
    }

    const destination = new URL(to, window.location.href);
    if (destination.origin !== window.location.origin) {
      return;
    }

    event.preventDefault();
    window.history.pushState({}, "", `${destination.pathname}${destination.search}${destination.hash}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  return (
    <a
      {...props}
      className={resolvedClassName}
      href={to}
      onClick={handleClick}
      target={target}
    >
      {children}
    </a>
  );
};
