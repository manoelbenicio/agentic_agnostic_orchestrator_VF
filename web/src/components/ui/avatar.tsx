import * as React from "react";
import { UserCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";

type AvatarProps = React.HTMLAttributes<HTMLDivElement> & {
  name?: string;
  src?: string;
};

function initials(name?: string) {
  return (name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function Avatar({ className, name, src, ...props }: AvatarProps) {
  const label = initials(name);
  return (
    <div
      className={cn(
        "flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted text-xs font-semibold text-muted-foreground",
        className,
      )}
      aria-label={name}
      {...props}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={name ?? ""} className="size-full object-cover" />
      ) : label ? (
        label
      ) : (
        <UserCircle2 className="size-5" />
      )}
    </div>
  );
}

export { Avatar };
