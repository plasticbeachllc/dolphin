/**
 * Mocha setup file that ensures BDD globals are available to all test files.
 * This file is loaded before any tests run.
 */

// Import Mocha
const Mocha = require('mocha');

// Create a minimal Mocha instance to access the BDD interface
const mocha = new Mocha({
  ui: 'bdd',
  timeout: 20000,
});

// The BDD interface is exposed via mocha.suite.emit('pre-require', ...)
// This is the standard way to set up Mocha globals
mocha.suite.emit('pre-require', global, 'setup.ts', mocha);

// The globals should now be available: describe, it, before, after, etc.

export {};