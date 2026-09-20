import { SiteHeader } from "@/app/(site)/components/SiteHeader";
import { SiteFooter } from "@/app/(site)/components/SiteFooter";

/**
 * Public product surface. It is deliberately a different room from the
 * research workspace: dark, editorial, short. The workspace copy is French;
 * the public story addresses an international research audience, so this
 * subtree declares its own language.
 */
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return (
    <div lang="en" className="site-root flex min-h-full flex-1 flex-col">
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}
