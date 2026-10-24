/// What a user does and sees on the screen. Finders live in operations.dart; the steps and the features only use logical
/// names. Every check pumps the frame it needs (`pumpAndSettle`): there are no fixed waits.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'compare.dart';
import 'errors.dart';
import 'operations.dart';
import 'world.dart';

enum Action { clicks, fills, selects, uploads, types, toggles }

Finder locate(String name) {
  final finder = targets[name];
  if (finder == null) {
    throw NotMapped('target', name, targets.keys);
  }
  return finder();
}

/// The component named [name], which must be on the screen: one that is not there is the feature not built yet.
Finder _present(String name) {
  final finder = locate(name);
  if (finder.evaluate().isEmpty) {
    throw ExpectedMissing('the $name component on the screen');
  }
  return finder.first;
}

Future<void> open(World world, String name) async {
  final build = pages[name];
  if (build == null) {
    throw NotMapped('page', name, pages.keys);
  }
  await world.tester.pumpWidget(build(world.appState));
  await world.tester.pumpAndSettle();
}

/// The value a step carries for an action: a `value` cell, a doc string, or the only cell.
String _valueOf(Argument? argument, String column) {
  final given = payload(argument);
  final found = given is Map ? (given[column] ?? given.values.firstOrNull) : given;
  if (found == null) {
    throw TestFailure('give the $column in a table (| $column |) or a doc string');
  }
  return '$found';
}

Future<void> act(World world, Action action, String target, Argument? argument) async {
  final finder = _present(target);
  final tester = world.tester;
  switch (action) {
    case Action.clicks || Action.toggles:
      await tester.tap(finder);
    case Action.fills || Action.types:
      await tester.enterText(finder, _valueOf(argument, 'value'));
    case Action.selects:
      await tester.tap(finder);
      await tester.pumpAndSettle();
      await tester.tap(find.text(_valueOf(argument, 'value')).last);
    case Action.uploads:
      throw ExpectedMissing('a way to hand a file to the screen (a widget test has no file picker; give the app a seam)');
  }
  await tester.pumpAndSettle();
}

/// The text a component shows: its own, the text in its field, or the texts inside it.
String _textOf(Finder finder) {
  final widget = finder.evaluate().first.widget;
  return switch (widget) {
    Text(:final data, :final textSpan) => data ?? textSpan?.toPlainText() ?? '',
    EditableText(:final controller) => controller.text,
    _ => _textsInside(finder).join(' '),
  };
}

List<String> _textsInside(Finder finder) => [
      for (final element in find.descendant(of: finder, matching: find.byType(Text)).evaluate()) (element.widget as Text).data ?? '',
    ];

String _valueIn(Finder finder) {
  final field = find.descendant(of: finder, matching: find.byType(EditableText));
  return field.evaluate().isEmpty ? _textOf(finder) : _textOf(field.first);
}

bool _enabled(Widget widget) => switch (widget) {
      ButtonStyleButton(:final enabled) => enabled,
      FloatingActionButton(:final onPressed) => onPressed != null,
      IconButton(:final onPressed) => onPressed != null,
      TextField(:final enabled) => enabled ?? true,
      Checkbox(:final onChanged) => onChanged != null,
      Switch(:final onChanged) => onChanged != null,
      _ => true,
    };

bool? _checked(Widget widget) => switch (widget) {
      Checkbox(:final value) => value,
      Switch(:final value) => value,
      _ => null,
    };

/// The visible state of a component: `text`, `value`, `enabled`, `checked`, `visible` columns, or an `item` column with
/// one row per entry of a list.
void assertShows(String target, Argument? argument) {
  final text = argument?.docString;
  if (text != null) {
    expect(_textOf(_present(target)), equals(text.trim()), reason: 'the text of $target');
    return;
  }
  final table = rows(argument?.table);
  if (table.isNotEmpty && table.every((row) => row.containsKey('item'))) {
    expect(_textsInside(_present(target)), equals([for (final row in table) '${row['item']}']), reason: 'the items of $target');
    return;
  }
  final expected = table.isEmpty ? <String, Object?>{} : table.first;
  if (expected['visible'] == false) {
    expect(locate(target).evaluate(), isEmpty, reason: '$target should be hidden');
    return;
  }
  final finder = _present(target);
  for (final MapEntry(:key, :value) in expected.entries) {
    _expectColumn(finder, key, value);
  }
}

void _expectColumn(Finder finder, String column, Object? value) {
  final widget = finder.evaluate().first.widget;
  switch (column) {
    case 'text':
      expect(_textOf(finder), equals('$value'), reason: 'the text');
    case 'value':
      expect(_valueIn(finder), equals('$value'), reason: 'the value');
    case 'enabled':
      expect(_enabled(widget), equals(value != false), reason: 'whether it is enabled');
    case 'checked':
      expect(_checked(widget), equals(value != false), reason: 'whether it is checked');
    case 'visible':
      break; // it is on the screen: that is what visible asks
    default:
      throw NotMapped('column', column, const ['text', 'value', 'enabled', 'checked', 'visible', 'item']);
  }
}

void assertHidden(String target) => expect(locate(target).evaluate(), isEmpty, reason: '$target should not be on the screen');

/// `| key | value |` rows as the application state the scenario starts from.
void setState(World world, Argument? argument) {
  for (final row in rows(argument?.table)) {
    final key = row['key'];
    if (key is! String || !row.containsKey('value')) {
      throw TestFailure('each row of the application state needs a key and a value');
    }
    world.appState[key] = row['value'];
  }
}

/// Checks the state the application reports against the `key`/`value` rows.
Future<void> assertState(World world, Argument? argument) async {
  final actual = await world.system.applicationState();
  for (final row in rows(argument?.table)) {
    final key = '${row['key']}';
    if (!actual.containsKey(key)) {
      throw TestFailure("the application state has no entry '$key'");
    }
    assertSubset(actual[key], row['value'], "the application state entry '$key'");
  }
}
