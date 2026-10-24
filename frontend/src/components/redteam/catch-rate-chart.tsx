import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RedTeamFamily } from "@/lib/types";

// Catch rate per attack family, baseline agent against Countersign. Baseline in muted ink, Countersign in accent (the
// emphasis pair DESIGN.md asks for; the dataviz validator passes it on CVD and normal-vision separation). Identity never
// rests on color alone: an inline legend above the plot and the rate printed on every bar. Axes are labeled in place.

export interface CatchRateDatum {
  family: RedTeamFamily;
  label: string;
  baseline: number; // 0 to 100
  countersign: number;
  attacks: number;
  caughtBaseline: number;
  caughtCountersign: number;
}

/** Recharts writes colors into SVG attributes, so resolve the theme tokens to values once mounted. */
function useTokens() {
  const read = () => {
    const css = getComputedStyle(document.documentElement);
    const v = (name: string) => css.getPropertyValue(name).trim();
    return { base: v("--ink-muted"), accent: v("--accent"), ink: v("--ink"), muted: v("--ink-muted"), rule: v("--rule"), surface: v("--surface") };
  };
  const [t, setT] = useState(read);
  useEffect(() => setT(read()), []);
  return t;
}

export function CatchRateChart({ data }: { data: CatchRateDatum[] }) {
  const t = useTokens();
  const pct = (v: number) => `${Math.round(v)}%`;
  return (
    <figure>
      <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        <span className="font-medium">Catch rate by attack family</span>
        <Key color="bg-ink-muted" label="Baseline agent" />
        <Key color="bg-accent" label="Countersign" />
      </figcaption>
      <div className="mt-3 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 22, right: 8, bottom: 4, left: 4 }} barCategoryGap="28%" barGap={2}>
            <CartesianGrid vertical={false} stroke={t.rule} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: t.rule }} tick={{ fill: t.ink, fontSize: 13 }} interval={0} />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={pct}
              tickLine={false}
              axisLine={false}
              width={44}
              tick={{ fill: t.muted, fontSize: 12, fontFamily: "IBM Plex Mono" }}
              label={{ value: "Caught", angle: -90, position: "insideLeft", offset: 4, fill: t.muted, fontSize: 12, dy: 24 }}
            />
            <Tooltip cursor={{ fill: t.rule, opacity: 0.5 }} content={(p) => <Tip {...p} />} isAnimationActive={false} />
            <Bar dataKey="baseline" name="Baseline agent" fill={t.base} radius={[0, 0, 0, 0]} isAnimationActive={false}>
              <LabelList dataKey="baseline" position="top" formatter={(v) => pct(Number(v))} fill={t.muted} fontSize={12} fontFamily="IBM Plex Mono" />
            </Bar>
            <Bar dataKey="countersign" name="Countersign" fill={t.accent} radius={[0, 0, 0, 0]} isAnimationActive={false}>
              <LabelList dataKey="countersign" position="top" formatter={(v) => pct(Number(v))} fill={t.ink} fontSize={12} fontFamily="IBM Plex Mono" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-muted">
      <span aria-hidden className={`size-2.5 ${color}`} />
      {label}
    </span>
  );
}

// Only the hovered family's datum is read, so the tooltip props are typed by what is used.
function Tip({ active, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) {
  const d = active ? (payload?.[0]?.payload as CatchRateDatum | undefined) : undefined;
  if (!d) return null;
  return (
    <div className="rounded-md border border-rule bg-surface px-3 py-2 text-sm shadow-overlay">
      <p className="font-medium">{d.label}</p>
      <p className="mt-1 text-ink-muted">
        Baseline agent <span className="figure text-ink">{d.caughtBaseline}</span> of <span className="figure">{d.attacks}</span>
      </p>
      <p className="text-ink-muted">
        Countersign <span className="figure text-ink">{d.caughtCountersign}</span> of <span className="figure">{d.attacks}</span>
      </p>
    </div>
  );
}
