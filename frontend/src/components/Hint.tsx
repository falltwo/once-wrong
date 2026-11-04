import type { ReactElement, ReactNode } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";

/**
 * Hover/focus hint on any focusable element. Radix handles keyboard focus, Escape,
 * screen-reader description and edge collision; we only style it.
 */
export function Hint({ content, children }: { content: ReactNode; children: ReactElement }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="hint" side="bottom" sideOffset={6} collisionPadding={8}>
          {content}
          <Tooltip.Arrow className="hint-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const HintProvider = Tooltip.Provider;
