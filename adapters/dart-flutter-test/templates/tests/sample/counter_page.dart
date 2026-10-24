/// The screen the sample feature drives. Delete it together with tests/features/sample.feature.
library;

import 'package:flutter/material.dart';

class CounterApp extends StatelessWidget {
  const CounterApp({super.key, this.start = 0});

  final int start;

  @override
  Widget build(BuildContext context) => MaterialApp(home: CounterPage(start: start));
}

class CounterPage extends StatefulWidget {
  const CounterPage({super.key, this.start = 0});

  final int start;

  @override
  State<CounterPage> createState() => _CounterPageState();
}

class _CounterPageState extends State<CounterPage> {
  late int count = widget.start;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(child: Text('$count', key: const Key('count'))),
        floatingActionButton: FloatingActionButton(
          key: const Key('add'),
          onPressed: () => setState(() => count += 1),
          child: const Icon(Icons.add),
        ),
      );
}
