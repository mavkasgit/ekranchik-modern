/**
 * Test setup file for Vitest
 * Configures testing-library matchers and global test utilities
 */

import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Cleanup after each test
afterEach(() => {
  cleanup()
})
