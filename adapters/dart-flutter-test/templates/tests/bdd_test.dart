/// Runs every scenario of tests/features as a widget test. `bdd run` starts it through run_flutter.py, which passes the
/// feature tag, the shuffle seed and the one scenario to run in the environment (BDD_TAG, BDD_SEED, BDD_SCENARIO).
///
/// The feature files are read at run time with the official Gherkin parser, so there is nothing to generate or keep in
/// step: a changed feature is a changed run.
library;

import 'dart:io';
import 'dart:math';

import 'package:cucumber_gherkin/cucumber_gherkin.dart';
import 'package:cucumber_messages/cucumber_messages.dart' as messages;
import 'package:flutter_test/flutter_test.dart';

import 'drivers/compare.dart';
import 'drivers/world.dart';
import 'steps/core_steps.dart';
import 'steps/definition.dart';
import 'steps/project_steps.dart';

const _featuresFolder = 'features';

/// The scenarios of every feature file, compiled by the Gherkin parser; a file that does not parse stops the run.
List<messages.Pickle> _loadPickles() {
  final files = Directory(_featuresFolder).listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.feature')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  final pickles = <messages.Pickle>[];
  for (final file in files) {
    final uri = file.path.replaceAll(r'\', '/');
    for (final envelope in generateMessages(file.readAsStringSync(), uri)) {
      final error = envelope.parseError;
      if (error != null) {
        throw FormatException('$uri cannot be read: ${error.message}');
      }
      final pickle = envelope.pickle;
      if (pickle != null) {
        pickles.add(pickle);
      }
    }
  }
  return pickles;
}

/// What the step carries under its text: a doc string, a table, or nothing.
Argument? _argumentOf(messages.PickleStep step) {
  final argument = step.argument;
  final table = argument?.dataTable;
  return Argument(
    docString: argument?.docString?.content,
    table: table == null
        ? null
        : [
            for (final row in table.rows) [for (final cell in row.cells) cell.value],
          ],
  );
}

void main() {
  final environment = Platform.environment;
  final tag = environment['BDD_TAG'] ?? '';
  final only = environment['BDD_SCENARIO'] ?? '';
  final seed = int.tryParse(environment['BDD_SEED'] ?? '');

  final selected = [
    for (final pickle in _loadPickles())
      if ((tag.isEmpty || pickle.tags.any((t) => t.name == '@$tag')) && (only.isEmpty || pickle.name == only)) pickle,
  ];
  if (seed != null) {
    selected.shuffle(Random(seed));
  }

  final definitions = [...coreSteps, ...projectSteps];
  for (final pickle in selected) {
    // The test is named by its scenario alone: `bdd` finds the scenario in the name of the case.
    testWidgets(pickle.name, (tester) async {
      final world = World(tester);
      try {
        for (final step in pickle.steps) {
          await runStep(definitions, world, step.text, _argumentOf(step));
        }
      } finally {
        await world.finish();
      }
    });
  }
}
