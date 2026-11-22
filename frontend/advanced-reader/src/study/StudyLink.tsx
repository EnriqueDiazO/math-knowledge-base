import type { ReactNode } from "react";
import type { Navigate } from "./navigation";

export function StudyLink({
  to,
  navigate,
  children,
}: {
  to: string;
  navigate: Navigate;
  children: ReactNode;
}) {
  return (
    <a
      href={to}
      onClick={(event) => {
        if (
          event.button ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        )
          return;
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
