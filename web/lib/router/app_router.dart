import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../providers/auth_providers.dart';
import '../screens/account_screen.dart';
import '../screens/auth/login_screen.dart';
import '../screens/auth/signup_screen.dart';
import '../screens/quizzes/quiz_create_screen.dart';
import '../screens/quizzes/quiz_versions_screen.dart';
import '../screens/quizzes/quizzes_list_screen.dart';
import '../screens/results/results_screen.dart';
import '../screens/results/submission_review_screen.dart';
import '../screens/shell/app_shell.dart';

/// Bridges a Supabase auth [Stream] to go_router's `refreshListenable`, so
/// the redirect guard below re-evaluates immediately on sign-in/sign-out
/// instead of only on the next navigation attempt.
class GoRouterRefreshStream extends ChangeNotifier {
  late final StreamSubscription<AuthState> _subscription;

  GoRouterRefreshStream(Stream<AuthState> stream) {
    notifyListeners();
    _subscription = stream.asBroadcastStream().listen((_) => notifyListeners());
  }

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }
}

const _publicRoutes = {'/login', '/signup'};

final routerProvider = Provider<GoRouter>((ref) {
  final refreshStream = GoRouterRefreshStream(
    ref.watch(supabaseClientProvider).auth.onAuthStateChange,
  );
  ref.onDispose(refreshStream.dispose);

  return GoRouter(
    initialLocation: '/quizzes',
    refreshListenable: refreshStream,
    redirect: (context, state) {
      final isAuthenticated = Supabase.instance.client.auth.currentSession != null;
      final isPublicRoute = _publicRoutes.contains(state.matchedLocation);

      if (!isAuthenticated && !isPublicRoute) return '/login';
      if (isAuthenticated && isPublicRoute) return '/quizzes';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/signup', builder: (context, state) => const SignupScreen()),
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(path: '/quizzes', builder: (context, state) => const QuizzesListScreen()),
          GoRoute(path: '/quizzes/create', builder: (context, state) => const QuizCreateScreen()),
          GoRoute(
            path: '/quizzes/:id/versions',
            builder: (context, state) => QuizVersionsScreen(
              quizId: state.pathParameters['id']!,
              quizTitle: state.uri.queryParameters['title'] ?? '',
            ),
          ),
          GoRoute(path: '/results', builder: (context, state) => const ResultsScreen()),
          GoRoute(
            path: '/submissions/:id/review',
            builder: (context, state) => SubmissionReviewScreen(
              submissionId: state.pathParameters['id']!,
              quizId: state.uri.queryParameters['quiz'],
            ),
          ),
          GoRoute(path: '/account', builder: (context, state) => const AccountScreen()),
        ],
      ),
    ],
  );
});
