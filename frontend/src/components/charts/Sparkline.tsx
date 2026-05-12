import { cn } from '@/lib/cn';

interface Props {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  stroke?: string;
  fill?: string;
}

/**
 * Sparkline — small inline trend chart. Pure SVG, no library.
 * `values` is the data series; the chart auto-scales to fit.
 */
export function Sparkline({
  values,
  width = 120,
  height = 36,
  className,
  stroke = '#1F3A5F',
  fill = 'rgba(31,58,95,0.10)',
}: Props) {
  if (!values || values.length === 0) {
    return <svg width={width} height={height} className={className} />;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const dx = values.length > 1 ? width / (values.length - 1) : width;
  const pts = values.map((v, i) => {
    const x = i * dx;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y] as const;
  });
  const linePath = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');
  const areaPath = `${linePath} L ${(pts[pts.length - 1][0]).toFixed(2)} ${height} L 0 ${height} Z`;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      className={cn(className)}
      aria-hidden
    >
      <path d={areaPath} fill={fill} />
      <path d={linePath} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {pts.length > 0 && (
        <circle
          cx={pts[pts.length - 1][0]}
          cy={pts[pts.length - 1][1]}
          r={2.2}
          fill={stroke}
        />
      )}
    </svg>
  );
}
