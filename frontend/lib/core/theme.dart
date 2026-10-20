import 'package:flutter/material.dart';

ThemeData buildTheme(Brightness b) {
  final dark = b == Brightness.dark;
  const primary = Color(0xFF0000FF);
  final scheme = ColorScheme.fromSeed(seedColor: primary, brightness: b).copyWith(
    primary: primary,
    onPrimary: Colors.white,
    secondary: const Color(0xFF3D4BFF),
    surface: dark ? const Color(0xFF070B16) : const Color(0xFFF4F6FF),
  );
  final radius = BorderRadius.circular(14);
  final line = dark ? const Color(0xFF243049) : const Color(0xFFE6E9F5);
  OutlineInputBorder border(Color color, [double width = 1]) => OutlineInputBorder(borderRadius: radius, borderSide: BorderSide(color: color, width: width));

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    brightness: b,
    scaffoldBackgroundColor: scheme.surface,
    splashFactory: InkRipple.splashFactory,
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: primary,
      selectionColor: primary.withValues(alpha: 0.28),
      selectionHandleColor: primary,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
      TargetPlatform.iOS: FadeUpwardsPageTransitionsBuilder(),
      TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
      TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
      TargetPlatform.macOS: FadeUpwardsPageTransitionsBuilder(),
    }),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      elevation: 0,
      scrolledUnderElevation: 0,
      foregroundColor: dark ? const Color(0xFFE8ECF8) : const Color(0xFF0E1225),
    ),
    drawerTheme: DrawerThemeData(backgroundColor: dark ? const Color(0xFF0C1020) : Colors.white),
    cardTheme: CardThemeData(
      elevation: 0,
      color: dark ? const Color(0xFF12182B) : Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: BorderSide(color: line)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: dark ? const Color(0xFF0E1426) : const Color(0xFFF7F8FF),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: border(line),
      enabledBorder: border(line),
      focusedBorder: border(primary, 1.6),
      labelStyle: TextStyle(color: dark ? const Color(0xFF9AA6C3) : const Color(0xFF66708A)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: Colors.white,
        disabledBackgroundColor: primary.withValues(alpha: 0.35),
        disabledForegroundColor: Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: radius),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        elevation: 0,
        backgroundColor: primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: radius),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: primary,
        shape: RoundedRectangleBorder(borderRadius: radius),
        side: const BorderSide(color: primary),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: primary)),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: primary),
    dividerColor: line,
  );
}
