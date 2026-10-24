/// How a step definition is written: a regular expression for the whole text of the step, and what to do with the words
/// it matched and the table or doc string under it.
library;

import '../drivers/compare.dart';
import '../drivers/errors.dart';
import '../drivers/world.dart';

typedef Handler = Future<void> Function(World world, List<String> words, Argument? argument);

class StepDefinition {
  StepDefinition(String pattern, this.handler) : expression = RegExp(pattern);

  final RegExp expression;
  final Handler handler;
}

// The three keywords only make the lists read like the features; a step matches by its text, whatever its keyword.
StepDefinition given(String pattern, Handler handler) => StepDefinition(pattern, handler);

StepDefinition when(String pattern, Handler handler) => StepDefinition(pattern, handler);

StepDefinition then(String pattern, Handler handler) => StepDefinition(pattern, handler);

/// Runs the step [text] with the one definition in [definitions] that matches it. No definition, or more than one, is a
/// defect of the test and is reported as such.
Future<void> runStep(List<StepDefinition> definitions, World world, String text, Argument? argument) async {
  final matches = [
    for (final definition in definitions)
      if (definition.expression.firstMatch(text) case final match? when match.start == 0 && match.end == text.length) (definition, match),
  ];
  if (matches.isEmpty) {
    throw StepError('Undefined step: $text');
  }
  if (matches.length > 1) {
    throw StepError('Ambiguous step: $text matches ${matches.map((m) => m.$1.expression.pattern).join(' and ')}');
  }
  final (definition, match) = matches.single;
  await definition.handler(world, [for (var group = 1; group <= match.groupCount; group++) match.group(group) ?? ''], argument);
}
