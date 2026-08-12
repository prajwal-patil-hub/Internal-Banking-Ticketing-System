import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom persists the document between tests in the same file, so without this
// a query like getByText finds the previous test's render and the failure
// looks like a bug in the component rather than in the harness.
afterEach(cleanup);
