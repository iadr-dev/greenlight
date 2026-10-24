// Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

/// What a step carries after the words it matched: a doc string, a table, or nothing.
class Argument {
  const Argument({this.docString, this.table});

  final String? docString;
  final List<List<String>>? table;
}

typedef Row = Map<String, Object?>;

/// A cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text.
Object? parseValue(String text) {
  try {
    return jsonDecode(text.trim());
  } on FormatException {
    return text.trim();
  }
}

/// A table with a header row as a list of maps.
List<Row> rows(List<List<String>>? table) {
  if (table == null || table.isEmpty) {
    return [];
  }
  final header = table.first;
  return [
    for (final cells in table.skip(1))
      {for (var at = 0; at < header.length; at++) header[at]: parseValue(at < cells.length ? cells[at] : '')},
  ];
}

/// The data a step carries: a doc string as JSON or text, or a table (one row becomes a map).
Object? payload(Argument? argument) {
  final text = argument?.docString;
  if (text != null) {
    return parseValue(text);
  }
  final found = rows(argument?.table);
  return found.length == 1 ? found.first : found;
}

/// A stable order for comparing record sets, where the order does not matter.
String sortKey(Object? row) => jsonEncode(row, toEncodable: (value) => value.toString());

void assertEqual(Object? actual, Object? expected, String what) {
  expect(actual, equals(expected), reason: '$what: expected ${jsonEncode(expected)} but got ${jsonEncode(actual)}');
}

/// Every field of [expected] is in [actual] (recursively); a list must contain an item matching each expected item.
void assertSubset(Object? actual, Object? expected, String what) {
  final problem = mismatch(actual, expected, '');
  if (problem != null) {
    throw TestFailure('$what: $problem (actual: ${jsonEncode(actual)})');
  }
}

/// Why [actual] does not contain [expected], or null when it does. [at] names the place, such as `order.lines`.
String? mismatch(Object? actual, Object? expected, String at) {
  if (expected is List) {
    return _listMismatch(actual, expected, at);
  }
  if (expected is Map) {
    return _mapMismatch(actual, expected, at);
  }
  return actual == expected ? null : '${at.isEmpty ? 'value' : at} is ${jsonEncode(actual)}, expected ${jsonEncode(expected)}';
}

String? _listMismatch(Object? actual, List<Object?> expected, String at) {
  final place = at.isEmpty ? 'value' : at;
  if (actual is! List) {
    return '$place should be a list';
  }
  for (final item in expected) {
    if (!actual.any((candidate) => mismatch(candidate, item, at) == null)) {
      return '$place has no item matching ${jsonEncode(item)}';
    }
  }
  return null;
}

String? _mapMismatch(Object? actual, Map<Object?, Object?> expected, String at) {
  if (actual is! Map) {
    return '${at.isEmpty ? 'value' : at} should be an object';
  }
  for (final MapEntry(:key, :value) in expected.entries) {
    final where = at.isEmpty ? '$key' : '$at.$key';
    final problem = actual.containsKey(key) ? mismatch(actual[key], value, where) : '$where is missing';
    if (problem != null) {
      return problem;
    }
  }
  return null;
}

const _secondsPerUnit = <String, int>{
  's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
  'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
  'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
  'd': 86400, 'day': 86400, 'days': 86400,
  'w': 604800, 'week': 604800, 'weeks': 604800,
};
final _token = RegExp(r'[a-z]+|[0-9.]+'); // a word or a number: no overlap, so the match time is linear

/// '2 days', '30 minutes', '1h 30m' as a Duration: pairs of a number and a unit; "and" and commas are ignored.
Duration duration(String text) {
  final lower = text.toLowerCase();
  final words = [for (final match in _token.allMatches(lower)) match.group(0)!].where((word) => word != 'and').toList();
  final separators = lower.replaceAll(_token, '').replaceAll(RegExp(r'[\s,]'), '');
  if (words.isEmpty || words.length.isOdd || separators.isNotEmpty) {
    throw ArgumentError("cannot read the duration '$text'");
  }
  var milliseconds = 0.0;
  for (var at = 0; at < words.length; at += 2) {
    final amount = double.tryParse(words[at]);
    final unit = _secondsPerUnit[words[at + 1]];
    if (amount == null || unit == null) {
      throw ArgumentError("cannot read the duration '$text'");
    }
    milliseconds += amount * unit * 1000;
  }
  return Duration(milliseconds: milliseconds.round());
}
