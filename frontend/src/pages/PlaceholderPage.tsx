import { Card } from '@/components/Card';

interface Props {
  title: string;
  phase: string;
  description?: string;
}

/** Generic stub used for routes whose feature lands in a later phase. */
export function PlaceholderPage({ title, phase, description }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <Card>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {description ?? 'This screen is part of an upcoming phase.'}
        </p>
        <p className="mt-2 text-xs uppercase tracking-wider text-brand-600">Arrives in {phase}</p>
      </Card>
    </div>
  );
}
