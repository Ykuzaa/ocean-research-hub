export function BackendDown() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-6 py-5 text-sm text-amber-900">
        <p className="font-medium">Le serveur de données ne répond pas.</p>
        <p className="mt-1 text-amber-800">
          Lance-le depuis la racine du projet avec{" "}
          <code className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs">uv run ocean-research-hub</code>, puis
          recharge la page.
        </p>
      </div>
    </div>
  );
}
