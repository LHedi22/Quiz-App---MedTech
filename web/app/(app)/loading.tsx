/** Route-level loading fallback for the authenticated app (web-app audit
 * B8). Shown while a server component's data fetch is in flight. */
export default function AppLoading() {
  return (
    <div className="py-12 text-center text-sm text-ink-soft" data-testid="route-loading">
      Loading…
    </div>
  );
}
