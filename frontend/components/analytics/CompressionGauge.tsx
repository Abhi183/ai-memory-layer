"use client";

interface Props {
  ratio: number; // e.g. 8.4 means 8.4x compression
}

/**
 * Semicircle gauge built entirely with CSS/SVG — no extra deps.
 * Green  → ratio >= 5
 * Yellow → 2 <= ratio < 5
 * Gray   → ratio < 2 or no data
 */
export default function CompressionGauge({ ratio }: Props) {
  const hasData = ratio > 0;

  // Clamp ratio for display (cap at 15x)
  const capped = Math.min(ratio, 15);
  // Map 0–15 to 0–180 degrees sweep
  const sweepDeg = hasData ? (capped / 15) * 180 : 0;

  // Colour thresholds
  const color =
    !hasData || ratio < 2
      ? { track: "#1e293b", fill: "#334155", text: "#64748b", label: "No data" }
      : ratio < 5
      ? { track: "#422006", fill: "#eab308", text: "#fbbf24", label: "Moderate" }
      : { track: "#052e16", fill: "#22c55e", text: "#4ade80", label: "Excellent" };

  // SVG arc parameters
  const cx = 100;
  const cy = 100;
  const r = 70;
  const strokeWidth = 14;

  // Helper: polar to cartesian
  function polarToCartesian(angleDeg: number) {
    const rad = ((angleDeg - 180) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  }

  // Track arc: full 180° from left to right
  const trackStart = polarToCartesian(0);
  const trackEnd = polarToCartesian(180);
  const trackPath = `M ${trackStart.x} ${trackStart.y} A ${r} ${r} 0 0 1 ${trackEnd.x} ${trackEnd.y}`;

  // Fill arc: 0° to sweepDeg
  const fillEnd = polarToCartesian(sweepDeg);
  const largeArcFlag = sweepDeg > 90 ? 1 : 0;
  const fillPath =
    sweepDeg > 0
      ? `M ${trackStart.x} ${trackStart.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${fillEnd.x} ${fillEnd.y}`
      : "";

  // Needle angle: 0 = left, 180 = right, in SVG space: left is 0°, right is 180°
  const needleAngleDeg = sweepDeg; // 0–180
  const needleRad = ((needleAngleDeg - 180) * Math.PI) / 180;
  const needleTip = {
    x: cx + (r - strokeWidth / 2) * Math.cos(needleRad),
    y: cy + (r - strokeWidth / 2) * Math.sin(needleRad),
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-white">Compression Ratio</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          How much smaller memory context is vs full history
        </p>
      </div>

      <div className="flex flex-col items-center">
        {/* SVG Gauge */}
        <div className="relative w-full max-w-[220px]">
          <svg viewBox="0 0 200 115" className="w-full overflow-visible">
            {/* Track */}
            <path
              d={trackPath}
              fill="none"
              stroke={color.track}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />

            {/* Filled portion */}
            {fillPath && (
              <path
                d={fillPath}
                fill="none"
                stroke={color.fill}
                strokeWidth={strokeWidth}
                strokeLinecap="round"
                style={{
                  filter: `drop-shadow(0 0 6px ${color.fill}88)`,
                  transition: "stroke-dashoffset 0.8s ease",
                }}
              />
            )}

            {/* Needle */}
            {hasData && (
              <>
                <line
                  x1={cx}
                  y1={cy}
                  x2={needleTip.x}
                  y2={needleTip.y}
                  stroke={color.fill}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  style={{ transition: "all 0.8s ease" }}
                />
                <circle cx={cx} cy={cy} r={5} fill={color.fill} />
              </>
            )}

            {/* Scale labels */}
            <text x="22" y="108" fill="#475569" fontSize="9" textAnchor="middle">1×</text>
            <text x="100" y="26" fill="#475569" fontSize="9" textAnchor="middle">7.5×</text>
            <text x="178" y="108" fill="#475569" fontSize="9" textAnchor="middle">15×</text>
          </svg>

          {/* Center value */}
          <div className="absolute inset-0 flex items-end justify-center pb-1">
            <div className="text-center">
              <p
                className="text-3xl font-bold leading-none"
                style={{ color: color.text }}
              >
                {hasData ? `${ratio.toFixed(1)}×` : "—"}
              </p>
              <p className="text-xs font-medium mt-1" style={{ color: color.text }}>
                {color.label}
              </p>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-slate-600 inline-block" />
            &lt;2× low
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />
            2–5× moderate
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
            5×+ excellent
          </span>
        </div>

        {/* Extra stat */}
        {hasData && (
          <div className="mt-4 w-full grid grid-cols-2 gap-2 text-center">
            <div className="bg-slate-800/60 rounded-xl py-2.5 px-3">
              <p className="text-sm font-semibold text-white">
                {Math.round(100 - (100 / ratio))}%
              </p>
              <p className="text-xs text-slate-500 mt-0.5">context reduction</p>
            </div>
            <div className="bg-slate-800/60 rounded-xl py-2.5 px-3">
              <p className="text-sm font-semibold text-white">
                {(1 / ratio * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-slate-500 mt-0.5">of original size</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
