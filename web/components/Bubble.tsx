/** The signature motif: this product's whole job is reading filled-in
 * answer bubbles off a scanned sheet, so the bubble itself - filled or
 * outline - is reused everywhere a state needs marking: submission
 * status, the active nav item, a version card. Not a generic dot. */
export function Bubble({
  tone = "olive",
  size = 8,
}: {
  tone?: "olive" | "flag" | "outline";
  size?: number;
}) {
  if (tone === "outline") {
    return (
      <span
        aria-hidden
        className="inline-block shrink-0 rounded-full border-[1.5px] border-ink-soft"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`inline-block shrink-0 rounded-full ${tone === "flag" ? "bg-flag" : "bg-olive"}`}
      style={{ width: size, height: size }}
    />
  );
}
