import * as path from 'path';
import Mocha from 'mocha';
import { glob } from 'glob';

export async function run(): Promise<void> {
  // Create the mocha test runner
  const mocha = new Mocha({
    ui: 'bdd',
    color: true,
    timeout: 10000, // 10 seconds default timeout
    reporter: 'spec', // Use spec reporter for detailed output
  });

  const testsRoot = path.resolve(__dirname, '.');

  console.log('Tests root:', testsRoot);
  console.log('Looking for test files...');

  // Find all test files
  const files = await glob('**/**.test.js', { cwd: testsRoot });

  console.log('Found test files:', files);

  if (files.length === 0) {
    console.error('No test files found!');
    throw new Error('No test files found');
  }

  // Add files to the test suite
  files.forEach((f) => {
    const fullPath = path.resolve(testsRoot, f);
    console.log('Adding test file:', fullPath);
    mocha.addFile(fullPath);
  });

  return new Promise<void>((resolve, reject) => {
    try {
      // Run the mocha test
      console.log('Running tests...');
      mocha.run((failures: number) => {
        if (failures > 0) {
          console.error(`${failures} tests failed.`);
          reject(new Error(`${failures} tests failed.`));
        } else {
          console.log('All tests passed!');
          resolve();
        }
      });
    } catch (err) {
      console.error('Error running tests:', err);
      reject(err);
    }
  });
}
