import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/auth_providers.dart';

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(currentSessionProvider);
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Account', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 16),
          Text(session?.user.email ?? 'Unknown user'),
          const SizedBox(height: 24),
          ElevatedButton(
            key: const Key('sign_out_button'),
            onPressed: () => ref.read(supabaseClientProvider).auth.signOut(),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
  }
}
