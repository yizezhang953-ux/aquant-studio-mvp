// Right-click menu: a list of actions shown at the pointer, closed by any click, scroll or Esc.
import { useEffect } from "react";

export type MenuItem = { label: string; onClick: () => void; danger?: boolean; disabled?: boolean };
export type MenuState = { x: number; y: number; items: MenuItem[] } | null;

export function ContextMenu({ menu, onClose }: { menu: MenuState; onClose: () => void }) {
  useEffect(() => {
    if (!menu) return;
    const close = () => onClose();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu, onClose]);

  if (!menu) return null;
  // keep the menu on screen near the right / bottom edges
  const left = Math.min(menu.x, window.innerWidth - 240);
  const top = Math.min(menu.y, window.innerHeight - menu.items.length * 36 - 16);
  return (
    <ul className="context-menu" role="menu" style={{ left, top }} onContextMenu={(e) => e.preventDefault()}>
      {menu.items.map((item) => (
        <li key={item.label}>
          <button
            role="menuitem"
            className={item.danger ? "danger" : ""}
            disabled={item.disabled}
            onClick={() => {
              onClose();
              item.onClick();
            }}
          >
            {item.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
