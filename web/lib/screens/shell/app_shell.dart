import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Top-level nav shell: Quizzes / Results / Account, per Phase 7.1's spec.
class AppShell extends StatelessWidget {
  final Widget child;
  const AppShell({super.key, required this.child});

  static const _destinations = [
    (label: 'Quizzes', path: '/quizzes', icon: Icons.quiz_outlined),
    (label: 'Results', path: '/results', icon: Icons.bar_chart_outlined),
    (label: 'Account', path: '/account', icon: Icons.person_outline),
  ];

  int _currentIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    final index = _destinations.indexWhere((d) => location.startsWith(d.path));
    return index == -1 ? 0 : index;
  }

  @override
  Widget build(BuildContext context) {
    final currentIndex = _currentIndex(context);
    return Scaffold(
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: currentIndex,
            onDestinationSelected: (index) => context.go(_destinations[index].path),
            labelType: NavigationRailLabelType.all,
            destinations: [
              for (final d in _destinations)
                NavigationRailDestination(icon: Icon(d.icon), label: Text(d.label)),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: child),
        ],
      ),
    );
  }
}
