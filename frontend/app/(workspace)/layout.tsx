import { NavBar } from "@/app/components/NavBar";

/** Research workspace chrome: persistent navigation, light surface, dense. */
export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <NavBar />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-slate-500 sm:px-6">
          Ocean Research Hub — chaque information affichée est retrouvée mot pour mot dans le PDF du
          papier.
        </div>
      </footer>
    </div>
  );
}
