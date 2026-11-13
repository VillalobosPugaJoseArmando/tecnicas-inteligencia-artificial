import { useOverlays } from "../hooks/useOverlays";
import type { TextOverlay } from "../hooks/useOverlays";
import { useVideoSizing } from "../hooks/useVideoSizing";

function DrawingOverlay() {
  const overlays = useOverlays();
  const { videoRect } = useVideoSizing();

  const style: React.CSSProperties = {
    position: "absolute",
    left: videoRect.x,
    top: videoRect.y,
    width: videoRect.width,
    height: videoRect.height,
    pointerEvents: "none",
  };

  const banners = overlays.filter((o): o is TextOverlay => o.type === "text");

  return (
    <div style={style} className="z-10">
      <svg viewBox="0 0 1 1" width="100%" height="100%" preserveAspectRatio="none">
        {overlays.map((o, i) =>
          o.type === "rect" ? (
            <rect
              key={i}
              x={o.coords[0]}
              y={o.coords[1]}
              width={o.coords[2] - o.coords[0]}
              height={o.coords[3] - o.coords[1]}
              fill="none"
              stroke={o.color || "lime"}
              strokeWidth={3}
              vectorEffect="non-scaling-stroke"
            />
          ) : null
        )}
      </svg>
      {banners.map((b, i) => (
        <div
          key={`banner-${i}`}
          style={{
            position: "fixed",
            top: 72 + i * 44,
            zIndex: 50,
            left: "50%",
            transform: "translateX(-50%)",
            padding: "6px 14px",
            borderRadius: 8,
            background: "rgba(0, 0, 0, 0.7)",
            color: b.color || "white",
            fontWeight: 700,
            fontSize: 20,
            whiteSpace: "nowrap",
          }}
        >
          {b.text}
        </div>
      ))}
    </div>
  );
}

// Making the component available as both a default and named export
// to resolve the import issue in App.tsx.
export { DrawingOverlay };
export default DrawingOverlay;
