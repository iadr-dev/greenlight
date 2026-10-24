// The scenario's clock. Application code reads `world.clock.now()` (or is handed it through System.setTime); the process
// clock is not frozen, so give the application a clock seam and note it in system.md.
import 'compare.dart';

final _hasZone = RegExp(r'(Z|[+-]\d\d:?\d\d)$');

/// An ISO date or date-time ("2026-03-01", "2026-03-01 09:30", "2026-03-01T09:30:00Z"); no zone means UTC.
DateTime parseMoment(String text) {
  final iso = text.trim();
  final moment = DateTime.tryParse(iso);
  if (moment == null) {
    throw ArgumentError("cannot read the date '$text'");
  }
  final zoned = moment.isUtc || _hasZone.hasMatch(iso);
  return zoned ? moment.toUtc() : DateTime.utc(moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second);
}

class Clock {
  DateTime? _moment;

  /// The scenario's time: the one it set, or the real time when it set none.
  DateTime now() => _moment ?? DateTime.now().toUtc();

  DateTime set(String text) => _moment = parseMoment(text);

  DateTime advance(String text) {
    final current = _moment;
    if (current == null) {
      throw StateError('set the current time first (Given the current time is ...)');
    }
    return _moment = current.add(duration(text));
  }
}
