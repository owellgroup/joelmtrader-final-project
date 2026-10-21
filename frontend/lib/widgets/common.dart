import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../core/utils.dart';

class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;
  final Color? color;
  final Gradient? gradient;
  const AppCard({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap, this.color, this.gradient});

  @override
  Widget build(BuildContext context) {
    final box = Container(
      decoration: BoxDecoration(
        color: gradient == null ? (color ?? context.cardColor2) : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: context.borderColor),
        boxShadow: context.isDark
            ? null
            : [BoxShadow(color: const Color(0xFF0000FF).withValues(alpha: 0.05), blurRadius: 24, offset: const Offset(0, 10))],
      ),
      padding: padding,
      child: child,
    );
    if (onTap == null) return box;
    return Pressable(onPressed: onTap, padding: EdgeInsets.zero, background: Colors.transparent, borderRadius: BorderRadius.circular(20), child: box);
  }
}

/// A clickable control whose label can still be dragged and copied.
/// A short click runs [onPressed]. A drag selects the text instead.
class Pressable extends StatefulWidget {
  final VoidCallback? onPressed;
  final Widget child;
  final Widget? icon;
  final Color? background;
  final Color? foreground;
  final BorderSide? side;
  final EdgeInsetsGeometry padding;
  final BorderRadius borderRadius;
  final bool expand;
  final double? minHeight;
  final MainAxisAlignment alignment;

  const Pressable({
    super.key,
    required this.onPressed,
    required this.child,
    this.icon,
    this.background,
    this.foreground,
    this.side,
    this.padding = const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
    this.borderRadius = const BorderRadius.all(Radius.circular(14)),
    this.expand = false,
    this.minHeight,
    this.alignment = MainAxisAlignment.center,
  });

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> {
  Offset? _down;
  bool _hover = false;
  bool _pressed = false;

  void _release(PointerEvent event) {
    final start = _down;
    setState(() {
      _down = null;
      _pressed = false;
    });
    if (widget.onPressed == null || start == null) return;
    if ((event.position - start).distance > 8) return;
    context.findAncestorStateOfType<SelectableRegionState>()?.clearSelection();
    widget.onPressed!();
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onPressed != null;
    final fg = widget.foreground ?? Palette.brand;
    final bg = widget.background;
    final hover = _hover && enabled;
    final pressed = _pressed && enabled;
    Color? fill = bg;
    if (fill != null && fill.a > 0) {
      if (pressed) fill = Color.alphaBlend(Colors.black.withValues(alpha: 0.12), fill);
      else if (hover) fill = Color.alphaBlend(Colors.white.withValues(alpha: 0.08), fill);
    } else if (hover) {
      fill = Palette.brand.withValues(alpha: 0.08);
    }
    final row = widget.icon == null
        ? widget.child
        : Row(mainAxisSize: widget.expand ? MainAxisSize.max : MainAxisSize.min, mainAxisAlignment: widget.alignment, children: [
            IconTheme.merge(data: IconThemeData(color: fg, size: 18), child: widget.icon!),
            const SizedBox(width: 8),
            if (widget.expand) Flexible(child: widget.child) else widget.child,
          ]);
    return MouseRegion(
      cursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() {
        _hover = false;
        _pressed = false;
      }),
      child: Listener(
        behavior: HitTestBehavior.translucent,
        onPointerDown: enabled
            ? (e) => setState(() {
                  _down = e.position;
                  _pressed = true;
                })
            : null,
        onPointerUp: enabled ? _release : null,
        onPointerCancel: enabled
            ? (_) => setState(() {
                  _down = null;
                  _pressed = false;
                })
            : null,
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 120),
          opacity: enabled ? 1 : 0.45,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: widget.expand ? double.infinity : null,
            constraints: BoxConstraints(minHeight: widget.minHeight ?? 0),
            alignment: Alignment.center,
            padding: widget.padding,
            decoration: BoxDecoration(
              color: fill,
              borderRadius: widget.borderRadius,
              border: widget.side == null ? null : Border.fromBorderSide(widget.side!),
            ),
            child: DefaultTextStyle.merge(
              style: TextStyle(color: fg, fontWeight: FontWeight.w600),
              child: IconTheme.merge(data: IconThemeData(color: fg, size: 18), child: row),
            ),
          ),
        ),
      ),
    );
  }
}

class SelectChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onSelected;
  final TextStyle? style;
  const SelectChip({super.key, required this.label, required this.selected, required this.onSelected, this.style});

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onPressed: onSelected,
      background: selected ? Palette.brand.withValues(alpha: 0.14) : (context.isDark ? const Color(0xFF12182B) : Colors.white),
      foreground: selected ? Palette.brand : context.textColor,
      side: BorderSide(color: selected ? Palette.brand : context.borderColor),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      borderRadius: BorderRadius.circular(20),
      child: Text(label, style: style ?? const TextStyle(fontWeight: FontWeight.w700)),
    );
  }
}

class ToggleLine extends StatelessWidget {
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool>? onChanged;
  final bool checkbox;
  const ToggleLine({super.key, required this.title, required this.value, required this.onChanged, this.subtitle, this.checkbox = false});

  @override
  Widget build(BuildContext context) {
    final control = checkbox
        ? Checkbox(value: value, onChanged: onChanged == null ? null : (v) => onChanged!(v ?? false))
        : Switch(value: value, onChanged: onChanged);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
            if (subtitle != null) Padding(padding: const EdgeInsets.only(top: 2), child: Text(subtitle!, style: TextStyle(fontSize: 12.5, color: context.muted, height: 1.35))),
          ]),
        ),
        control,
      ]),
    );
  }
}

/// Launcher mark from assets/images/icon.svg.
class AppIcon extends StatelessWidget {
  final double size;
  const AppIcon({super.key, this.size = 72});

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      'assets/images/icon.svg',
      width: size,
      height: size,
      fit: BoxFit.contain,
      alignment: Alignment.center,
      clipBehavior: Clip.none,
      excludeFromSemantics: true,
    );
  }
}

/// Brand image from assets/images/logo.svg.
class BrandLogo extends StatelessWidget {
  final double height;
  const BrandLogo({super.key, this.height = 88});

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      'assets/images/logo.svg',
      height: height,
      width: height * (7500 / 2700),
      fit: BoxFit.contain,
      alignment: Alignment.centerLeft,
      clipBehavior: Clip.none,
      excludeFromSemantics: true,
    );
  }
}

class SectionTitle extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? trailing;
  const SectionTitle(this.title, {super.key, this.subtitle, this.trailing});

  @override
  Widget build(BuildContext context) {
    final heading = SizedBox(
      width: double.infinity,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, softWrap: true, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, height: 1.25)),
        if (subtitle != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(subtitle!, softWrap: true, style: TextStyle(fontSize: 13, color: context.muted, height: 1.4)),
          ),
      ]),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: LayoutBuilder(builder: (context, c) {
        // Keep the sentence on its own full-width line. A row lets the
        // buttons steal the width and the words stack one under another.
        final stack = trailing != null && c.maxWidth < 840;
        if (trailing == null) return heading;
        if (stack) {
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            heading,
            const SizedBox(height: 12),
            Align(alignment: Alignment.centerLeft, child: trailing!),
          ]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: heading),
          const SizedBox(width: 12),
          Flexible(child: Align(alignment: Alignment.centerRight, child: trailing!)),
        ]);
      }),
    );
  }
}

class KpiCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color? valueColor;
  final String? hint;
  const KpiCard({super.key, required this.label, required this.value, required this.icon, this.valueColor, this.hint});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(color: Palette.brand.withOpacity(0.12), borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, color: Palette.brand, size: 20),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: TextStyle(fontSize: 11.5, color: context.muted, fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 350),
              child: Text(value, key: ValueKey(value), maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: valueColor)),
            ),
            if (hint != null) Text(hint!, style: TextStyle(fontSize: 10.5, color: context.muted)),
          ]),
        ),
      ]),
    );
  }
}

class StatusPill extends StatelessWidget {
  final String text;
  final Color color;
  final bool pulse;
  const StatusPill(this.text, this.color, {super.key, this.pulse = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(color: color.withOpacity(0.13), borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        pulse ? _Dot(color) : Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 7),
        Text(text, style: TextStyle(color: color, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: .3)),
      ]),
    );
  }
}

class _Dot extends StatefulWidget {
  final Color color;
  const _Dot(this.color);
  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat(reverse: true);
  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween(begin: 0.35, end: 1.0).animate(c),
      child: Container(width: 8, height: 8, decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle)),
    );
  }
}

class Tag extends StatelessWidget {
  final String text;
  final Color color;
  const Tag(this.text, this.color, {super.key});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: color.withOpacity(0.14), borderRadius: BorderRadius.circular(8)),
        child: Text(text, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800)),
      );
}

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  const EmptyState({super.key, required this.icon, required this.title, this.message});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(32),
        child: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 48, color: context.muted.withOpacity(0.6)),
            const SizedBox(height: 12),
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            if (message != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(message!, textAlign: TextAlign.center, style: TextStyle(color: context.muted))),
          ]),
        ),
      );
}

class ErrorBanner extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;
  const ErrorBanner(this.message, {super.key, this.onRetry});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: Palette.red.withOpacity(0.08), borderRadius: BorderRadius.circular(14), border: Border.all(color: Palette.red.withOpacity(0.3))),
        child: LayoutBuilder(builder: (context, c) {
          final text = Expanded(child: Text(message, style: const TextStyle(fontSize: 13, height: 1.35)));
          final retry = onRetry == null ? null : Pressable(onPressed: onRetry, padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8), background: Colors.transparent, child: const Text('Retry'));
          if (c.maxWidth < 420) {
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.error_outline, color: Palette.red),
                const SizedBox(width: 10),
                text,
              ]),
              if (retry != null) Align(alignment: Alignment.centerRight, child: retry),
            ]);
          }
          return Row(children: [
            const Icon(Icons.error_outline, color: Palette.red),
            const SizedBox(width: 10),
            text,
            if (retry != null) retry,
          ]);
        }),
      );
}

/// Lays children in 1..n columns depending on available width.
class ResponsiveGrid extends StatelessWidget {
  final List<Widget> children;
  final double minTileWidth;
  final double spacing;
  const ResponsiveGrid({super.key, required this.children, this.minTileWidth = 240, this.spacing = 12});
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      final cols = (c.maxWidth / minTileWidth).floor().clamp(1, 6);
      final w = (c.maxWidth - spacing * (cols - 1)) / cols;
      return Wrap(spacing: spacing, runSpacing: spacing, children: [for (final ch in children) SizedBox(width: w, child: ch)]);
    });
  }
}

Future<bool> confirmDialog(BuildContext context, String title, String message, {String confirm = 'Confirm', bool danger = false}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (_) => SelectionArea(child: AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        Pressable(onPressed: () => Navigator.pop(context, false), padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12), background: Colors.transparent, child: const Text('Cancel')),
        Pressable(
          onPressed: () => Navigator.pop(context, true),
          background: danger ? Palette.red : Palette.brand,
          foreground: Colors.white,
          child: Text(confirm),
        ),
      ],
    )),
  );
  return r ?? false;
}
