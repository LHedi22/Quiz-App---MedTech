import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

final supabaseClientProvider = Provider<SupabaseClient>((ref) {
  return Supabase.instance.client;
});

/// Emits every auth transition (signed in/out/token refreshed). The router's
/// redirect guard listens to this via `GoRouterRefreshStream` so protected
/// routes react immediately to sign-in/sign-out, not just on next navigation
/// (mirrors web/lib/providers/auth_providers.dart).
final authStateChangesProvider = StreamProvider<AuthState>((ref) {
  return ref.watch(supabaseClientProvider).auth.onAuthStateChange;
});

final currentSessionProvider = Provider<Session?>((ref) {
  ref.watch(authStateChangesProvider);
  return ref.watch(supabaseClientProvider).auth.currentSession;
});

final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(currentSessionProvider) != null;
});
