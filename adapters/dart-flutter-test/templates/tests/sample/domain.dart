/// Code under test for the sample feature. Delete it together with tests/features/sample.feature.
int add(int a, int b) {
  if (a < 0 || b < 0) {
    throw ArgumentError('negative numbers are not allowed');
  }
  return a + b;
}
