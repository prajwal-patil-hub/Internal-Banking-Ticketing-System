import { Logo } from '@/components/Logo';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';

/**
 * Phase P0: visual shell only. Real submit + token storage + MFA prompt
 * are wired in Phase P1.
 */
export function LoginPage() {
  return (
    <div className="min-h-full grid lg:grid-cols-2">
      {/* Brand panel */}
      <div className="hidden lg:flex bg-brand-600 text-white p-12 flex-col justify-between dark:bg-brand-700">
        <Logo />
        <div>
          <h1 className="text-4xl font-semibold leading-tight">
            Internal Ticketing<br />
            <span className="text-accent-200">for SUCCESS Bank.</span>
          </h1>
          <p className="mt-4 text-white/80 max-w-md">
            Branches raise issues. Admins triage. Agents resolve. Supervisors watch SLAs.
            Auditors review immutable logs. One platform.
          </p>
        </div>
        <span className="text-white/60 text-xs">© SUCCESS Bank — internal use only.</span>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-8">
        <Card className="w-full max-w-md">
          <h2 className="text-xl font-semibold">Sign in</h2>
          <p className="text-sm text-slate-500 mt-1">
            Use your corporate credentials.
          </p>

          <form className="mt-6 flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
            <label className="text-sm">
              <span className="block mb-1 font-medium">Work email</span>
              <input className="input" type="email" placeholder="you@successbank.com" />
            </label>
            <label className="text-sm">
              <span className="block mb-1 font-medium">Password</span>
              <input className="input" type="password" placeholder="••••••••" />
            </label>
            <Button type="submit" disabled>
              Sign in (wired in P1)
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
