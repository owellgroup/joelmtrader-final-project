import 'dart:io';

String? windowsNotificationIconPath() {
  final exe = Platform.resolvedExecutable;
  if (!exe.toLowerCase().endsWith('.exe')) return null;
  final ico = File('${File(exe).parent.path}${Platform.pathSeparator}app_icon.ico');
  if (ico.existsSync()) return ico.path;
  return '$exe,0';
}
