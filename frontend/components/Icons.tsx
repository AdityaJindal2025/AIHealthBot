import type { ReactNode } from "react";

// Inline SVG icons, drawn on a 24px Material-style grid. Decorative: always aria-hidden.
type IconProps = { className?: string };

function Svg({ className = "h-5 w-5", children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`flex-none ${className}`}
    >
      {children}
    </svg>
  );
}

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const SendIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4l16 8-16 8 3-8-3-8zM7 12h13" />
  </Svg>
);

export const ArrowRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const LeafIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15" />
    <path d="M5 19c3-4 6-7 10-9" />
  </Svg>
);

export const BookIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 5.5C5.5 4.5 9 4.5 12 6.5c3-2 6.5-2 9-1V19c-2.5-1-6-1-9 1-3-2-6.5-2-9-1V5.5z" />
    <path d="M12 6.5V20" />
  </Svg>
);

export const SearchIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M20 20l-4.8-4.8M8.5 12.5v-2M10.5 12.5v-4M12.5 12.5v-3" />
  </Svg>
);

export const VerifiedIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l2.4 1.6 2.9-.2 1 2.7 2.4 1.7-.9 2.7.9 2.8-2.4 1.6-1 2.8-2.9-.2L12 21l-2.4-1.5-2.9.2-1-2.8-2.4-1.6.9-2.8-.9-2.7 2.4-1.7 1-2.7 2.9.2L12 3z" />
    <path d="M8.5 12l2.5 2.5 4.5-5" />
  </Svg>
);

export const ChevronIcon = ({ up = false, className }: IconProps & { up?: boolean }) => (
  <Svg className={`${className ?? "h-4 w-4"} transition-transform ${up ? "" : "rotate-180"}`}>
    <path d="M6 15l6-6 6 6" />
  </Svg>
);

export const CopyIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="8" y="8" width="12" height="12" rx="2" />
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
  </Svg>
);

export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);

export const InfoIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </Svg>
);

export const FactCheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M7 9h4M7 13h4M14 12l1.5 1.5L18 11" />
  </Svg>
);

export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

/** Brand mark: leaf sprout on a soft tile, as in the Stitch header. */
export function LogoMark() {
  return (
    <span className="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-surface-container-low text-primary-container">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
        <path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15z" fill="currentColor" />
        <path d="M5 19c3-4 6-7 10-9" stroke="#fff" strokeWidth={1.5} strokeLinecap="round" fill="none" />
        <circle cx="19" cy="5" r="2" fill="#fd761a" />
      </svg>
    </span>
  );
}

/** Empty-state illustration from the Stitch mock (produce and a jar). */
export function ProduceIllustration() {
  return (
    <svg aria-hidden="true" className="h-16 w-16" fill="none" viewBox="0 0 72 72">
      <path d="M22 46c0-11.046 8.954-20 20-20v20H22z" fill="#15803d" opacity="0.85" />
      <path d="M42 26c11.046 0 20 8.954 20 20H42V26z" fill="#415d4d" opacity="0.7" />
      <path d="M42 26V18c0-2.21-1.79-4-4-4s-4 1.79-4 4v8" stroke="#00652c" strokeLinecap="round" strokeWidth="2.5" />
      <circle cx="27" cy="47" fill="#fd761a" r="11" />
      <circle cx="24" cy="44" fill="#ffb690" r="3.5" />
      <rect fill="#79db8d" height="22" rx="5" width="12" x="45" y="37" />
      <rect fill="#00652c" height="4" rx="1.5" width="8" x="47" y="34" />
      <path d="M23 37c-3-4-2-9 2-12 5 3 6 8 2 12" fill="#79db8d" opacity="0.9" />
    </svg>
  );
}
