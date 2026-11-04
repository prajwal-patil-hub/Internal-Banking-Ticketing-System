import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AIBadge } from './AIBadge';

/**
 * The regression these guard is a threshold that existed in two places.
 *
 * This component used to band risk itself at 0.7/0.3 while the backend banded
 * at 0.7/0.4, so a ticket scored 0.35 displayed "Med Risk" here and was
 * returned by `?ai_risk=low` from the API. The component now renders the band
 * the server sends and computes nothing.
 */

describe('AIBadge', () => {
  it('renders the band the server sent', () => {
    render(<AIBadge category={null} confidence={null} riskScore={0.35} riskBand="low" />);
    expect(screen.getByText(/Low Risk \(35%\)/)).toBeInTheDocument();
  });

  it('does not re-derive the band from the score', () => {
    // 0.35 is the score that used to disagree between screens. Whatever the
    // server says wins — even when it contradicts the old local rule.
    render(<AIBadge category={null} confidence={null} riskScore={0.35} riskBand="low" />);
    expect(screen.queryByText(/Med Risk/)).not.toBeInTheDocument();
  });

  it('trusts the server even for a band the old rule would have called low', () => {
    render(<AIBadge category={null} confidence={null} riskScore={0.2} riskBand="high" />);
    expect(screen.getByText(/High Risk \(20%\)/)).toBeInTheDocument();
  });

  it('shows the score without a verdict when no band is supplied', () => {
    // An API older than the banding change. Showing the number is honest;
    // guessing the verdict is what caused the drift in the first place.
    render(<AIBadge category={null} confidence={null} riskScore={0.35} riskBand={null} />);
    expect(screen.getByText(/Risk 35%/)).toBeInTheDocument();
    expect(screen.queryByText(/Med Risk|Low Risk|High Risk/)).not.toBeInTheDocument();
  });

  it('renders the category pill with its confidence', () => {
    render(
      <AIBadge category="fraud" confidence={0.91} riskScore={null} riskBand={null} />,
    );
    expect(screen.getByText(/AI: fraud \(91%\)/)).toBeInTheDocument();
  });

  it('renders nothing when there is neither a category nor a score', () => {
    const { container } = render(
      <AIBadge category={null} confidence={null} riskScore={null} riskBand={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('omits the category pill when the score exists but the category does not', () => {
    // Portal-created tickets have a risk score seeded but no category.
    render(<AIBadge category={null} confidence={0.9} riskScore={0.8} riskBand="high" />);
    expect(screen.queryByText(/AI:/)).not.toBeInTheDocument();
    expect(screen.getByText(/High Risk/)).toBeInTheDocument();
  });
});
