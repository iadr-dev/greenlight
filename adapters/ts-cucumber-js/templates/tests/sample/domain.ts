// Code under test for the sample feature. Delete it together with tests/features/sample.feature.
export function add(a: number, b: number): number {
  if (a < 0 || b < 0) {
    throw new RangeError('negative numbers are not allowed');
  }
  return a + b;
}
