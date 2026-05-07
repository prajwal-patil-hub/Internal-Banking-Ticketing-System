import { Sparkles } from 'lucide-react';
import { Card } from '@/components/Card';

interface Props {
  title: string;
  phase: string;
  description?: string;
}

export function PlaceholderPage({ title, phase, description }: Props) {
  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto py-8">
      <div>
        <span className="label">Coming soon</span>
        <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">{title}</h1>
      </div>
      <Card>
        <div className="flex items-start gap-4">
          <span className="h-11 w-11 rounded-2xl grid place-items-center bg-brand-50 text-brand-700">
            <Sparkles className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm text-ink leading-relaxed">
              {description ?? 'This screen is part of an upcoming phase.'}
            </p>
            <p className="mt-2 text-2xs uppercase tracking-wider text-brand-700">Arrives in {phase}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
