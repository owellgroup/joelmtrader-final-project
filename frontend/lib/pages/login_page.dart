import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  late final TextEditingController _url;
  bool _busy = false, _showServer = true, _hide = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: context.read<AppState>().apiUrl);
  }

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    _url.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (_user.text.trim().isEmpty || _pass.text.isEmpty) {
      setState(() => _error = 'Enter your username and password');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      TextInput.finishAutofillContext(shouldSave: true);
      await context.read<AppState>().login(_url.text, _user.text, _pass.text);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final dark = context.isDark;
    return Scaffold(
      body: Stack(children: [
        const Positioned.fill(child: _LoginBackdrop()),
        Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: 1),
                duration: const Duration(milliseconds: 720),
                curve: Curves.easeOutCubic,
                builder: (_, v, child) => Opacity(
                  opacity: v,
                  child: Transform.translate(offset: Offset(0, 18 * (1 - v)), child: child),
                ),
                child: Container(
                  padding: const EdgeInsets.fromLTRB(28, 22, 28, 26),
                  decoration: BoxDecoration(
                    color: dark ? const Color(0xFF12182B).withValues(alpha: 0.92) : Colors.white.withValues(alpha: 0.94),
                    borderRadius: BorderRadius.circular(28),
                    border: Border.all(color: dark ? const Color(0xFF2A3558) : Colors.white),
                    boxShadow: [
                      BoxShadow(color: const Color(0xFF0000FF).withValues(alpha: dark ? 0.22 : 0.12), blurRadius: 48, offset: const Offset(0, 22)),
                    ],
                  ),
                  child: AutofillGroup(child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const BrandLogo(height: 96),
                    const SizedBox(height: 18),
                    Text('Sign in to the trading desk', style: TextStyle(color: context.muted, fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 26),
                    TextField(
                      controller: _user,
                      enableInteractiveSelection: true,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.username, AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      contextMenuBuilder: (context, state) => AdaptiveTextSelectionToolbar.editableText(editableTextState: state),
                      decoration: const InputDecoration(labelText: 'Username', prefixIcon: Icon(Icons.person_outline_rounded)),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _pass,
                      enableInteractiveSelection: true,
                      obscureText: _hide,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.done,
                      onEditingComplete: () => TextInput.finishAutofillContext(shouldSave: true),
                      onSubmitted: (_) => _login(),
                      contextMenuBuilder: (context, state) => AdaptiveTextSelectionToolbar.editableText(editableTextState: state),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          icon: Icon(_hide ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                          onPressed: () => setState(() => _hide = !_hide),
                        ),
                      ),
                    ),
                    AnimatedSize(
                      duration: const Duration(milliseconds: 280),
                      curve: Curves.easeOutCubic,
                      child: _showServer
                          ? Padding(
                              padding: const EdgeInsets.only(top: 14),
                              child: TextField(
                                controller: _url,
                                enableInteractiveSelection: true,
                                keyboardType: TextInputType.url,
                                autofillHints: const [AutofillHints.url],
                                contextMenuBuilder: (context, state) => AdaptiveTextSelectionToolbar.editableText(editableTextState: state),
                                decoration: const InputDecoration(labelText: 'Live backend URL', prefixIcon: Icon(Icons.dns_outlined), hintText: 'http://145.241.187.174:8088'),
                              ),
                            )
                          : const SizedBox(width: double.infinity),
                    ),
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 220),
                      child: _error == null
                          ? const SizedBox(width: double.infinity)
                          : Padding(
                              key: ValueKey(_error),
                              padding: const EdgeInsets.only(top: 14),
                              child: Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Palette.red, fontSize: 13, height: 1.35)),
                            ),
                    ),
                    const SizedBox(height: 22),
                    SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: FilledButton(
                        onPressed: _busy ? null : _login,
                        child: AnimatedSwitcher(
                          duration: const Duration(milliseconds: 200),
                          child: _busy
                              ? const SizedBox(key: ValueKey('busy'), height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2.2, color: Colors.white))
                              : const Text('Sign in', key: ValueKey('go'), style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, letterSpacing: 0.2)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                    TextButton.icon(
                      onPressed: () => setState(() => _showServer = !_showServer),
                      icon: const Icon(Icons.settings_ethernet, size: 16),
                      label: Text(_showServer ? 'Hide server settings' : 'Server settings'),
                    ),
                    Text(
                      'After you sign in, link your MT5 account on the dashboard. You stay signed in until you log out.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: context.muted, fontSize: 11.5, height: 1.4),
                    ),
                  ])),
                ),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

class _LoginBackdrop extends StatelessWidget {
  const _LoginBackdrop();

  @override
  Widget build(BuildContext context) {
    final dark = context.isDark;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: dark ? const [Color(0xFF070B16), Color(0xFF10163A)] : const [Color(0xFFF7F8FF), Color(0xFFE7EBFF)],
        ),
      ),
      child: Stack(children: [
        Positioned(top: -90, right: -70, child: _glow(240, dark ? 0.28 : 0.22)),
        Positioned(bottom: -110, left: -80, child: _glow(280, dark ? 0.18 : 0.16)),
      ]),
    );
  }

  Widget _glow(double size, double alpha) {
    return ImageFiltered(
      imageFilter: ImageFilter.blur(sigmaX: 70, sigmaY: 70),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(shape: BoxShape.circle, color: const Color(0xFF0000FF).withValues(alpha: alpha)),
      ),
    );
  }
}
