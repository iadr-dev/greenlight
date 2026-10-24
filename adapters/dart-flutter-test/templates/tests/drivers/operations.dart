/// The map from the logical names used in features to this system. Features never contain widget keys, class names or
/// import paths. The step-engineer fills this in from the system map (system.md); the sample entries below belong to the
/// sample feature and can be deleted with it.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../sample/counter_page.dart';
import '../sample/domain.dart';

/// A screen: the widget to put on the stage. [state] is what the scenario said the application state is.
typedef PageBuilder = Widget Function(Map<String, Object?> state);

/// A component on the screen, found by a key, a type or a text.
typedef TargetFinder = Finder Function();

/// What a logical error looks like. Any field that is set must match.
class ErrorRule {
  const ErrorRule({this.exception, this.text});

  final String? exception; // the name of the error class
  final String? text; // text in the error message
}

final pages = <String, PageBuilder>{
  // 'orders': (state) => const OrdersApp(),
  'counter': (state) => CounterApp(start: (state['start'] as num?)?.toInt() ?? 0), // sample
};

final targets = <String, TargetFinder>{
  // 'checkout button': () => find.widgetWithText(ElevatedButton, 'Check out'),
  'add button': () => find.byKey(const Key('add')), // sample
  'count': () => find.byKey(const Key('count')), // sample
};

/// A library operation is a function the tests import: it receives the data of the step (a map for named arguments, a
/// list, or a single value) and returns the result. Import the application's libraries above and map the names here.
final lib = <String, FutureOr<Object?> Function(Object? input)>{
  'add': (input) {
    final arguments = input! as Map<String, Object?>;
    return add(arguments['a']! as int, arguments['b']! as int);
  }, // sample
};

final errors = <String, ErrorRule>{
  'negative input': const ErrorRule(exception: 'ArgumentError'), // sample
  // 'validation error': ErrorRule(text: 'invalid'),
};
