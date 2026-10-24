/// The project's own steps, written with the same drivers as the core ones. A phrase here must not also be matched by a core
/// step (the run reports an ambiguous step as a defect). Delete the example when you add the first real step.
library;

import 'definition.dart';

final projectSteps = <StepDefinition>[
  // then(r'^the receipt total is (\d+)$', (world, words, argument) async {
  //   assertEqual(await world.system.records('receipt'), [...], 'the receipts');
  // }),
];
