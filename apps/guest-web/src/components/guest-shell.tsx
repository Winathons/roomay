import type { ReactNode } from "react";
import Link from "next/link";

type GuestShellProps = Readonly<{ children: ReactNode }>;

export function GuestShell({ children }: GuestShellProps) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Roomay guest services home">
          <span className="brand-mark" aria-hidden="true">
            R
          </span>
          <span className="brand-name">ROOMAY</span>
        </Link>
        <span className="header-label">Guest services</span>
      </header>
      <main id="main-content" className="page-shell" tabIndex={-1}>
        {children}
      </main>
      <footer className="site-footer">
        <span>Roomay</span>
        <span>Guest services preview</span>
      </footer>
    </>
  );
}
