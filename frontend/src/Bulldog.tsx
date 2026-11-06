// Handsome Dan, the same original bulldog face drawn for the HW4 Campus Customs site
// (no real photo or Yale logo). `ink` is the outline/ears color, `face` the fur color.
export default function Bulldog({ size = 32, ink = "var(--yale)", face = "#ffffff", title }: {
  size?: number;
  ink?: string;
  face?: string;
  title?: string;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true} aria-label={title}>
      <path d="M15 20 C9 13 3 15 3 23 C7 20 11 21 14 25 Z" fill={ink} />
      <path d="M49 20 C55 13 61 15 61 23 C57 20 53 21 50 25 Z" fill={ink} />
      <path d="M32 15 C49 15 58 24 58 36 C58 49 47 57 32 57 C17 57 6 49 6 36 C6 24 15 15 32 15 Z" fill={face} stroke={ink} strokeWidth="3" />
      <path d="M17 42 Q15 51 22 54" fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round" />
      <path d="M47 42 Q49 51 42 54" fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round" />
      <path d="M25 21 Q32 18 39 21" fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round" />
      <path d="M27 25 Q32 23 37 25" fill="none" stroke={ink} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="22.5" cy="31" r="3.2" fill={ink} />
      <circle cx="41.5" cy="31" r="3.2" fill={ink} />
      <circle cx="23.5" cy="30" r="1" fill={face} />
      <circle cx="42.5" cy="30" r="1" fill={face} />
      <ellipse cx="32" cy="44" rx="15" ry="9.5" fill={face} stroke={ink} strokeWidth="2.2" />
      <path d="M26.5 36.5 H37.5 Q37.5 42 32 43 Q26.5 42 26.5 36.5 Z" fill={ink} />
      <path d="M32 43 V46" stroke={ink} strokeWidth="2" strokeLinecap="round" />
      <path d="M23 46.5 Q32 53 41 46.5" fill="none" stroke={ink} strokeWidth="2.2" strokeLinecap="round" />
      <path d="M26 48 L27.5 45.5 L29 48.8 Z" fill={face} stroke={ink} strokeWidth="1" strokeLinejoin="round" />
      <path d="M38 48 L36.5 45.5 L35 48.8 Z" fill={face} stroke={ink} strokeWidth="1" strokeLinejoin="round" />
    </svg>
  );
}
