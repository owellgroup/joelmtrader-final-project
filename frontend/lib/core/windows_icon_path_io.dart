import 'dart:io';

String? windowsNotificationIconPath() {
  final exe = Platform.resolvedExecutable;
  if (!exe.toLowerCase().endsWith('.exe')) return null;
  return '$exe,0';
}
