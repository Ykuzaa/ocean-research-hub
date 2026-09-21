import { SiteHeader } from "@/app/(site)/components/SiteHeader";
import { SiteFooter } from "@/app/(site)/components/SiteFooter";

/**
 * Public product surface. It is deliberately a different room from the
 * research workspace: editorial, expressive, and short. The workspace copy is French;
 * the public story addresses an international research audience, so this
 * subtree declares its own language.
 */
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return (
    <div lang="en" className="site-root flex min-h-full flex-1 flex-col">
      <a href="#main-content" className="sr-only z-50 rounded bg-sheet-0 px-4 py-3 text-ink-900 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        Skip to main content
      </a>
      <SiteHeader />
      <main id="main-content" className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}
