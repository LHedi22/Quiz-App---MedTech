import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../providers/auth_providers.dart';
import '../screens/auth/login_screen.dart';
import '../screens/scan/batch_summary_screen.dart';
import '../screens/scan/camera_capture_screen.dart';

/// Bridges a Supabase auth [Stream] to go_router's `refreshListenable` (see
/// web/lib/router/app_router.dart's identical class).
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

const _publicRoutes = {'/login'};

final routerProvider = Provider<GoRouter>((ref) {
  final refreshStream = GoRouterRefreshStream(
    ref.watch(supabaseClientProvider).auth.onAuthStateChange,
  );
  ref.onDispose(refreshStream.dispose);

  return GoRouter(
    initialLocation: '/scan',
    refreshListenable: refreshStream,
    redirect: (context, state) {
      final isAuthenticated = Supabase.instance.client.auth.currentSession != null;
      final isPublicRoute = _publicRoutes.contains(state.matchedLocation);

      if (!isAuthenticated && !isPublicRoute) return '/login';
      if (isAuthenticated && isPublicRoute) return '/scan';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/scan', builder: (context, state) => const CameraCaptureScreen()),
      GoRoute(path: '/summary', builder: (context, state) => const BatchSummaryScreen()),
    ],
  );
});
