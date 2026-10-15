import 'package:flutter/material.dart';

/// PantryPilot design tokens and Material theme.
///
/// Warm off-white surfaces, a fresh-produce green as the primary colour and a
/// terracotta accent. Colours used for text meet WCAG AA contrast on the
/// surfaces they sit on.
class AppTheme {
  AppTheme._();

  // ── Colour tokens ─────────────────────────────────────────────────────
  static const Color backgroundColor = Color(0xFFF6F5F0);
  static const Color cardSurface = Color(0xFFFFFFFF);
  static const Color surfaceMuted = Color(0xFFF0EEE7);
  static const Color borderColor = Color(0xFFE5E2D9);

  static const Color textPrimaryColor = Color(0xFF1D211B);
  static const Color textSecondaryColor = Color(0xFF5C6157);
  static const Color textTertiaryColor = Color(0xFF7D8278);

  static const Color primaryColor = Color(0xFF467536);
  static const Color primaryDark = Color(0xFF345A28);
  static const Color lightGreen = Color(0xFFE3EFD9);
  static const Color secondaryColor = Color(0xFF6F8F72);
  static const Color accentColor = Color(0xFFB9784A);
  static const Color accentLight = Color(0xFFF6E7DA);

  static const Color warningColor = Color(0xFFB26B00);
  static const Color warningLight = Color(0xFFFFF1D6);
  static const Color dangerColor = Color(0xFFC2412D);
  static const Color dangerLight = Color(0xFFFBE4DF);
  static const Color infoColor = Color(0xFF2F6599);
  static const Color infoLight = Color(0xFFE1ECF7);

  static const Color successColor = primaryColor;
  static const Color errorColor = dangerColor;

  // ── Shape & spacing ───────────────────────────────────────────────────
  static const double radiusSm = 10;
  static const double radiusMd = 14;
  static const double radiusLg = 20;

  static List<BoxShadow> get softShadow => [
        BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 12, offset: const Offset(0, 3)),
      ];

  /// Horizontal page padding for the available width.
  static double gutter(double width) => width < 600 ? 16 : (width < 1000 ? 24 : 32);

  static ThemeData get lightTheme {
    final scheme = ColorScheme.fromSeed(
      seedColor: primaryColor,
      brightness: Brightness.light,
    ).copyWith(
      primary: primaryColor,
      onPrimary: Colors.white,
      secondary: accentColor,
      surface: cardSurface,
      onSurface: textPrimaryColor,
      onSurfaceVariant: textSecondaryColor,
      surfaceContainerHighest: surfaceMuted,
      outline: borderColor,
      outlineVariant: borderColor,
      error: dangerColor,
    );

    const font = 'Inter';
    final base = ThemeData(useMaterial3: true, colorScheme: scheme, fontFamily: font);
    final text = base.textTheme.copyWith(
      headlineMedium: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: textPrimaryColor, height: 1.2),
      headlineSmall: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: textPrimaryColor, height: 1.25),
      titleLarge: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: textPrimaryColor, height: 1.3),
      titleMedium: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: textPrimaryColor, height: 1.3),
      titleSmall: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: textPrimaryColor, height: 1.3),
      bodyLarge: const TextStyle(fontSize: 16, color: textPrimaryColor, height: 1.45),
      bodyMedium: const TextStyle(fontSize: 14, color: textSecondaryColor, height: 1.45),
      bodySmall: const TextStyle(fontSize: 12.5, color: textSecondaryColor, height: 1.4),
      labelLarge: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, height: 1.2),
      labelMedium: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500, color: textSecondaryColor),
      labelSmall: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500, color: textSecondaryColor),
    );

    final inputBorder = OutlineInputBorder(
      borderRadius: BorderRadius.circular(radiusSm),
      borderSide: const BorderSide(color: borderColor),
    );

    return base.copyWith(
      scaffoldBackgroundColor: backgroundColor,
      textTheme: text,
      appBarTheme: const AppBarTheme(
        backgroundColor: backgroundColor,
        foregroundColor: textPrimaryColor,
        elevation: 0,
        scrolledUnderElevation: 0.5,
        centerTitle: false,
        titleTextStyle: TextStyle(fontFamily: font, fontSize: 18, fontWeight: FontWeight.w600, color: textPrimaryColor),
      ),
      cardTheme: CardThemeData(
        color: cardSurface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          side: const BorderSide(color: borderColor),
        ),
      ),
      dividerTheme: const DividerThemeData(color: borderColor, thickness: 1, space: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: cardSurface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: inputBorder,
        enabledBorder: inputBorder,
        focusedBorder: inputBorder.copyWith(borderSide: const BorderSide(color: primaryColor, width: 1.6)),
        errorBorder: inputBorder.copyWith(borderSide: const BorderSide(color: dangerColor)),
        focusedErrorBorder: inputBorder.copyWith(borderSide: const BorderSide(color: dangerColor, width: 1.6)),
        labelStyle: const TextStyle(color: textSecondaryColor),
        hintStyle: const TextStyle(color: textTertiaryColor),
        errorMaxLines: 3,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(64, 48),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radiusSm)),
          textStyle: const TextStyle(fontFamily: font, fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(64, 48),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          foregroundColor: textPrimaryColor,
          side: const BorderSide(color: borderColor),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radiusSm)),
          textStyle: const TextStyle(fontFamily: font, fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryColor,
          textStyle: const TextStyle(fontFamily: font, fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: cardSurface,
        selectedColor: lightGreen,
        side: const BorderSide(color: borderColor),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        labelStyle: const TextStyle(fontFamily: font, fontSize: 13, fontWeight: FontWeight.w500, color: textPrimaryColor),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: cardSurface,
        indicatorColor: lightGreen,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        height: 68,
        labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
              fontFamily: font,
              fontSize: 12,
              fontWeight: s.contains(WidgetState.selected) ? FontWeight.w600 : FontWeight.w500,
              color: s.contains(WidgetState.selected) ? textPrimaryColor : textSecondaryColor,
            )),
        iconTheme: WidgetStateProperty.resolveWith((s) =>
            IconThemeData(color: s.contains(WidgetState.selected) ? primaryDark : textSecondaryColor)),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: cardSurface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(radiusLg))),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: cardSurface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radiusLg)),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radiusSm)),
      ),
      listTileTheme: const ListTileThemeData(iconColor: textSecondaryColor),
      progressIndicatorTheme: const ProgressIndicatorThemeData(color: primaryColor),
    );
  }
}
